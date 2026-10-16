"""Panel Gemeinde × Nationalratswahl mit Fusionsereignissen.

Liest nur aus dem veröffentlichten Datenmodell (zuerst `modell_laden.py`) und schreibt
`ausgabe/panel.csv` und `ausgabe/ereignisse.csv`.

Einheit: Gemeinde im Stand 1.7.2023. Das BFS hat alle Wahljahre auf diesen Stand
umgerechnet; eine heutige Gemeinde umfasst also in jedem Jahr dasselbe Gebiet.
Behandlung: die erste Fusion nach der Wahl 1971, an der die Gemeinde (oder ihre
Vorgänger) beteiligt war.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

HIER = Path(__file__).resolve().parent
MODELL = HIER.parents[1] / "state" / "analysen" / "modell.duckdb"  # modell_laden.py
AUSGABE = HIER / "ausgabe"
STAND = "bfs-wahlen-kanton-bezirk-gemeinde@2023-07-01"

# Wahltage der Nationalratswahlen (jeweils Oktober).
WAHLTAGE = {
    1971: date(1971, 10, 31), 1975: date(1975, 10, 26), 1979: date(1979, 10, 21),
    1983: date(1983, 10, 23), 1987: date(1987, 10, 18), 1991: date(1991, 10, 20),
    1995: date(1995, 10, 22), 1999: date(1999, 10, 24), 2003: date(2003, 10, 19),
    2007: date(2007, 10, 21), 2011: date(2011, 10, 23), 2015: date(2015, 10, 18),
    2019: date(2019, 10, 20), 2023: date(2023, 10, 22),
}
STICHTAG = date(2023, 7, 1)

SQL_PANEL = f"""
select z.gemeinde_hstnr, z.gebiet_quellcode as bfs_nr,
       trim(replace(z.bezeichnung_quelltext, '.', '')) as gemeinde,
       cast(split_part(f.periode_id, ':', 2) as integer) as jahr,
       f.wahlberechtigte, f.waehlende
from model.fact_nationalratswahlen f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
where f.gebiet_stand_id = '{STAND}' and z.gebietsart = 'gemeinde'
"""

SQL_ZUSTAENDE = """
select GDE_GHSTNR as hstnr, GDE_GBFSNR as bfs, GDE_GNAME as name, GDE_KTKZ as kanton,
       GDE_BHSTNR as bezirk_hstnr, GDE_GARTE as art,
       GDE_GINIMUT as ini_mut, GDE_GINIART as ini_art, GDE_GINIDAT as ini_dat,
       GDE_GFINMUT as fin_mut, GDE_GFINART as fin_art, GDE_GFINDAT as fin_dat
from model.agvch_historisch_gemeinden
"""


# Bevölkerung 2000 der damaligen Gemeinden, umgerechnet auf die Gemeinden eines späteren
# Gebietsstands. Zeigt für Fusionen nach dem 5.12.2000, aus wie vielen und wie grossen
# Gemeinden eine heutige Gemeinde entstand.
SQL_BESTANDTEILE = """
with vz as (
  select z.gemeinde_hstnr, f.personen
  from model.fact_bevoelkerung_volkszaehlung f
  join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
  where f.periode_id = 'kalenderjahr:2000' and z.gebietsart = 'gemeinde'
)
select u.neu_hstnr as gemeinde_hstnr, u.zuordnung, vz.personen
from model.gemeinden_umrechnen('bfs-volkszaehlung-kanton-bezirk-gemeinde@2000-12-05', '{stand}') u
join vz on vz.gemeinde_hstnr = u.alt_hstnr
"""
VZ_STICHTAG = date(2000, 12, 5)


def verbinden(pfad: Path = MODELL) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(pfad), read_only=True)


def erste_wahl_ab(tag: date) -> int | None:
    """Erste Nationalratswahl am oder nach `tag`."""
    for jahr, wahltag in WAHLTAGE.items():
        if wahltag >= tag:
            return jahr
    return None


def ereignisse(zustaende: pd.DataFrame, einheiten: list[str]) -> pd.DataFrame:
    """Alle Mutationen mit mindestens zwei politischen Vorgängern in der Herkunft jeder Einheit.

    Eine Mutation gilt als `fusion`, wenn sie genau einen politischen Nachfolger hat.
    Mehrere Nachfolger heissen `abtausch` (Gebietsabtausch oder Teilung); sie ändern
    das heutige Gebiet nicht als Ganzes und zählen nicht als Behandlung.
    """
    pol = zustaende[zustaende["art"] == "11"]
    vor = pol.dropna(subset=["fin_mut"]).groupby("fin_mut")["hstnr"].apply(list)
    nach = pol.dropna(subset=["ini_mut"]).groupby("ini_mut")["hstnr"].apply(list)
    nach_ini = zustaende.set_index("hstnr")
    zeilen = []
    for einheit in einheiten:
        offen, gesehen = [einheit], set()
        while offen:
            zustand = offen.pop()
            if zustand in gesehen:
                continue
            gesehen.add(zustand)
            mut = nach_ini.at[zustand, "ini_mut"]
            if pd.isna(mut):
                continue
            vorgaenger = vor.get(mut, [])
            offen.extend(vorgaenger)
            if len(vorgaenger) >= 2:
                nachfolger = nach.get(mut, [])
                zeilen.append({
                    "gemeinde_hstnr": einheit,
                    "mutation": mut,
                    "datum": nach_ini.at[zustand, "ini_dat"],
                    "vorgaenger": len(vorgaenger),
                    "nachfolger": len(nachfolger),
                    "art": "fusion" if len(nachfolger) == 1 else "abtausch",
                })
    return pd.DataFrame(zeilen).drop_duplicates(["gemeinde_hstnr", "mutation"])


def zustaende_laden(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    zustaende = con.sql(SQL_ZUSTAENDE).df()
    for spalte in ("ini_dat", "fin_dat"):
        zustaende[spalte] = pd.to_datetime(zustaende[spalte]).dt.date
    return zustaende


def fusionen_ab(ev: pd.DataFrame, ab: date) -> pd.DataFrame:
    """Je Einheit die erste Fusion nach `ab`, die Zahl ihrer Fusionen und ob ein Gebietsabtausch dabei war."""
    fus = ev[(ev["art"] == "fusion") & (ev["datum"] > ab)]
    erste = (
        fus.sort_values("datum").groupby("gemeinde_hstnr")
        .agg(fusion_datum=("datum", "first"), fusion_vorgaenger=("vorgaenger", "first"),
             fusionen=("mutation", "nunique"))
        .reset_index()
    )
    abtausch = ev[(ev["art"] == "abtausch") & (ev["datum"] > ab)]
    abtausch = abtausch.groupby("gemeinde_hstnr").size().rename("abtausch").reset_index()
    return erste.merge(abtausch, on="gemeinde_hstnr", how="outer")


def bestandteile(con: duckdb.DuckDBPyConnection, stand: str) -> pd.DataFrame:
    """Bestandteile 2000 jeder Gemeinde von `stand`; Gemeinden mit mehrdeutiger Herkunft fehlen."""
    teile = con.sql(SQL_BESTANDTEILE.format(stand=stand)).df()
    mehrdeutig = set(teile.loc[teile["zuordnung"] == "mehrdeutig", "gemeinde_hstnr"])
    teile = teile[~teile["gemeinde_hstnr"].isin(mehrdeutig)]
    bestand = teile.groupby("gemeinde_hstnr")["personen"].agg(
        teile_2000="size", personen_2000="sum", groesster_teil_2000="max", kleinster_teil_2000="min"
    ).reset_index()
    # Anteil der Bevölkerung, deren Gemeinde in der Fusion aufging (nicht der grösste Teil).
    bestand["anteil_aufgegangen"] = 1 - bestand["groesster_teil_2000"] / bestand["personen_2000"]
    return bestand


def bestandteile_nur_nach_vz(panel: pd.DataFrame) -> None:
    vor_vz = panel["fusion_datum"].notna() & (pd.to_datetime(panel["fusion_datum"]).dt.date <= VZ_STICHTAG)
    for spalte in ("teile_2000", "kleinster_teil_2000", "anteil_aufgegangen"):
        panel.loc[vor_vz, spalte] = pd.NA  # Fusion vor der Volkszählung: Bestandteile unbekannt


def kanton_zur_wahl(kanton: str, bezirk: str, name: str, jahr: int) -> str:
    """Kanton am Wahltag; das Panel steht im Stand 2023 (siehe Vertragshinweise)."""
    if kanton == "JU" and jahr <= 1975:
        return "BE"
    if bezirk == "Laufen" and jahr <= 1991:
        return "BE"
    if name == "Courrendlin" and jahr <= 1995:  # enthält seit 2019 Vellerat, bis 30.6.1996 bei BE
        return "BE*"
    return kanton


def bauen(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = con.sql(SQL_PANEL).df()
    zustaende = zustaende_laden(con)
    bezirke = con.sql(
        "select BEZ_BHSTNR as bezirk_hstnr, BEZ_BNAME as bezirk from model.agvch_historisch_bezirke"
    ).df()

    einheiten = sorted(panel["gemeinde_hstnr"].unique())
    ev = ereignisse(zustaende, einheiten)
    ev["wahl"] = ev["datum"].map(erste_wahl_ab)

    # Nur Fusionen nach der Wahl 1971 sind beobachtbar (vorher fehlt eine Vorperiode).
    erste = fusionen_ab(ev, WAHLTAGE[1971])
    erste["fusion_wahl"] = erste["fusion_datum"].map(lambda d: erste_wahl_ab(d) if pd.notna(d) else None)

    info = zustaende[["hstnr", "kanton", "bezirk_hstnr"]].rename(columns={"hstnr": "gemeinde_hstnr"})
    info = info.merge(bezirke, on="bezirk_hstnr", how="left").drop(columns="bezirk_hstnr")
    panel = panel.merge(info, on="gemeinde_hstnr", how="left")
    panel = panel.merge(erste, on="gemeinde_hstnr", how="left")
    panel["abtausch"] = panel["abtausch"].fillna(0).astype(int)
    panel["fusionen"] = panel["fusionen"].fillna(0).astype(int)
    panel = panel.merge(bestandteile(con, STAND), on="gemeinde_hstnr", how="left")
    bestandteile_nur_nach_vz(panel)
    panel["kanton_wahl"] = [
        kanton_zur_wahl(k, b, n, j)
        for k, b, n, j in zip(panel["kanton"], panel["bezirk"], panel["gemeinde"], panel["jahr"])
    ]
    panel["beteiligung"] = 100 * panel["waehlende"] / panel["wahlberechtigte"]
    return panel.sort_values(["bfs_nr", "jahr"]), ev


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    AUSGABE.mkdir(exist_ok=True)
    with verbinden() as con:
        panel, ev = bauen(con)
    panel.to_csv(AUSGABE / "panel.csv", index=False)
    ev.to_csv(AUSGABE / "ereignisse.csv", index=False)
    einheiten = panel.drop_duplicates("gemeinde_hstnr")
    print(f"{len(panel)} Zeilen, {len(einheiten)} Gemeinden (Stand 2023)")
    print(f"mit Fusion nach 1971: {einheiten['fusion_wahl'].notna().sum()}")
    print(einheiten.groupby("fusion_wahl").size().to_string())
    print(f"mit Gebietsabtausch nach 1971: {(einheiten['abtausch'] > 0).sum()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
