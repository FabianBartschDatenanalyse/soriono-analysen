"""Panel Gemeinde × eidgenössischer Abstimmungstag mit Fusionsereignissen.

Liest nur aus dem veröffentlichten Datenmodell (zuerst `modell_laden.py`) und schreibt
`ausgabe/panel_abstimmungen.csv`.

Einheit: Gemeinde im Stand 1.1.2026. Das BFS hat alle Abstimmungen auf diesen Stand
umgerechnet. Beteiligung je Tag: die Vorlage mit den meisten abgegebenen Stimmen
(an einem Tag unterscheiden sich die Vorlagen kaum; Median der Spanne 0 Punkte).
Behandlung: die erste Fusion nach dem 1.1.1961; der Tag der Fusion selbst fällt weg,
weil an einem Fusionstag (z. B. im Tessin) offen ist, in welchen Gemeinden abgestimmt wurde.
"""

from __future__ import annotations

import sys
from datetime import date

import pandas as pd

from daten import AUSGABE, bestandteile, bestandteile_nur_nach_vz, ereignisse, fusionen_ab, verbinden, zustaende_laden

STAND = "bfs-abstimmungen-kanton-bezirk-gemeinde@2026-01-01"
AB = date(1961, 1, 1)  # mindestens ein Abstimmungsjahr vor der Fusion

SQL_PANEL = f"""
with je_vorlage as (
  select z.gemeinde_hstnr, z.gebiet_quellcode as bfs_nr,
         trim(replace(z.bezeichnung_quelltext, '.', '')) as gemeinde,
         v.abstimmungsdatum as tag, f.stimmberechtigte, f.abgegebene_stimmen
  from model.fact_volksabstimmungen f
  join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
  join model.dim_vorlage v using (vorlage_id)
  where f.gebiet_stand_id = '{STAND}' and z.gebietsart = 'gemeinde'
    and f.stimmberechtigte > 0 and f.abgegebene_stimmen is not null
)
select gemeinde_hstnr, bfs_nr, gemeinde, tag,
       arg_max(stimmberechtigte, abgegebene_stimmen) as stimmberechtigte,
       max(abgegebene_stimmen) as abgegebene_stimmen
from je_vorlage group by all
"""


def kanton_am_tag(kanton: str, bezirk: str, name: str, tag: date) -> str:
    """Kanton am Abstimmungstag; das Panel steht im Stand 2026 (siehe Vertragshinweise)."""
    if kanton == "JU" and name == "Moutier" and tag < date(2026, 1, 1):
        return "BE"
    if kanton == "JU" and tag < date(1979, 1, 1):
        return "BE"
    if bezirk == "Bezirk Laufen" and tag < date(1994, 1, 1):
        return "BE"
    if name == "Courrendlin" and tag < date(1996, 7, 1):  # enthält seit 2019 Vellerat
        return "BE*"
    return kanton


def bauen(con) -> pd.DataFrame:
    panel = con.sql(SQL_PANEL).df()
    panel["tag"] = pd.to_datetime(panel["tag"]).dt.date
    zustaende = zustaende_laden(con)
    bezirke = con.sql("select BEZ_BHSTNR as bezirk_hstnr, BEZ_BNAME as bezirk from model.agvch_historisch_bezirke").df()
    ev = ereignisse(zustaende, sorted(panel["gemeinde_hstnr"].unique()))
    info = zustaende[["hstnr", "kanton", "bezirk_hstnr"]].rename(columns={"hstnr": "gemeinde_hstnr"})
    info = info.merge(bezirke, on="bezirk_hstnr", how="left").drop(columns="bezirk_hstnr")
    panel = panel.merge(info, on="gemeinde_hstnr", how="left")
    panel = panel.merge(fusionen_ab(ev, AB), on="gemeinde_hstnr", how="left")
    panel["abtausch"] = panel["abtausch"].fillna(0).astype(int)
    panel["fusionen"] = panel["fusionen"].fillna(0).astype(int)
    panel = panel.merge(bestandteile(con, STAND), on="gemeinde_hstnr", how="left")
    bestandteile_nur_nach_vz(panel)
    panel["kanton_tag"] = [kanton_am_tag(k, b, n, t) for k, b, n, t in
                           zip(panel["kanton"], panel["bezirk"], panel["gemeinde"], panel["tag"])]
    panel["beteiligung"] = 100 * panel["abgegebene_stimmen"] / panel["stimmberechtigte"]
    fusionstag = panel["fusion_datum"].notna() & (panel["tag"] == panel["fusion_datum"])
    return panel[~fusionstag].sort_values(["bfs_nr", "tag"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with verbinden() as con:
        panel = bauen(con)
    panel.to_csv(AUSGABE / "panel_abstimmungen.csv", index=False)
    einheiten = panel.drop_duplicates("gemeinde_hstnr")
    print(f"{len(panel)} Zeilen, {len(einheiten)} Gemeinden (Stand 2026), {panel['tag'].nunique()} Abstimmungstage")
    print(f"mit Fusion seit 1961: {einheiten['fusion_datum'].notna().sum()}, "
          f"mit Gebietsabtausch: {(einheiten['abtausch'] > 0).sum()}")
    print(pd.to_datetime(einheiten["fusion_datum"]).dt.year.floordiv(10).mul(10).value_counts().sort_index().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
