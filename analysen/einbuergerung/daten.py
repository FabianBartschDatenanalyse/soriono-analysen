"""Panel Gemeinde × Jahr 2011–2025: Einbürgerungen, ausländische Wohnbevölkerung, Abstimmungsklima.

Liest nur aus dem veröffentlichten Datenmodell Prelude (zuerst `../gemeinsam/modell_laden.py`)
und schreibt `ausgabe/panel.parquet` und `ausgabe/gemeinden.parquet`.

Einheit ist die Gemeinde im Stand 6.4.2025: Auf diesem Stand weist das BFS Einbürgerungen,
Bevölkerung und Wanderungen für alle Jahre aus. Die Abstimmungsergebnisse (Stand 1.1.2026)
werden über das historische Gemeindeverzeichnis darauf umgerechnet; Gemeinden mit einem nicht
eindeutig zuordenbaren Stück fehlen.

Einbürgerungsquote = Einbürgerungen im Jahr je 100 ausländische Personen der ständigen
Wohnbevölkerung am Ende des Vorjahres.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

HIER = Path(__file__).resolve().parent
MODELL = HIER.parents[1] / "state" / "analysen" / "modell.duckdb"
AUSGABE = HIER / "ausgabe"
STAND = "bfs-kanton-bezirk-gemeinde@2025-04-06"
STAND_ABSTIMMUNGEN = "bfs-abstimmungen-kanton-bezirk-gemeinde@2026-01-01"

# Vorlagen zu Zuwanderung und Einbürgerung; die Masseneinwanderungsinitiative 2014 liegt vor dem
# Gesetz von 2018 und ist das Hauptmass des lokalen Klimas.
VORLAGEN = {
    5320: "demokratische_einbuergerungen_2008",
    5800: "masseneinwanderung_2014",
    5970: "durchsetzung_2016",
    6310: "begrenzung_2020",
    6860: "zehn_millionen_2026",
}
WELLEN = ((1996, 2000), (2001, 2005), (2006, 2010), (2011, 2016))
HERKUNFT = {  # frühere Staatsangehörigkeit (Codeliste staatsangehoerigkeit_ehemalig)
    "eu_efta": (1, 2),
    "uebriges_europa": (3,),
    "ausserhalb_europas": (4, 5, 6, 7, 8),
}

SQL_EINBUERGERUNGEN = f"""
select z.gemeinde_hstnr as hstnr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr,
       sum(f.einbuergerungen) as einbuergerungen,
       {", ".join(f"sum(f.einbuergerungen) filter (where f.staatsangehoerigkeit_ehemalig_id in ({', '.join(map(str, c))})) as einb_{n}" for n, c in HERKUNFT.items())}
from model.fact_einbuergerungen f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
where z.gebietsart = 'gemeinde' and z.gebiet_stand_id = 'bfs-einbuergerung-kanton-bezirk-gemeinde@2025-04-06'
group by all
"""

# Bestand am 31.12. des Vorjahres: Nenner der Quote des Jahres.
SQL_BEVOELKERUNG = f"""
select z.gemeinde_hstnr as hstnr, cast(split_part(f.periode_id, ':', 2) as integer) + 1 as jahr,
       sum(f.personen) as einwohner_vorjahr,
       sum(f.personen) filter (where f.staatsangehoerigkeitskategorie_id = 2) as auslaender_vorjahr
from model.fact_bevoelkerungsbestand f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
where z.gebietsart = 'gemeinde' and z.gebiet_stand_id = '{STAND}' and f.bevoelkerungstyp_id = 1
group by all
"""

# Einwanderungen von Ausländerinnen und Ausländern: Wer in den letzten Jahren kam, hat meist
# noch keine Niederlassungsbewilligung C, die seit 2018 Voraussetzung ist.
SQL_EINWANDERUNG = """
select z.gemeinde_hstnr as hstnr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr,
       sum(f.einwanderungen) filter (where f.staatsangehoerigkeitskategorie_id = 2) as einwanderungen_ausland
from model.fact_bevoelkerungsbewegung f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
where z.gebietsart = 'gemeinde' and f.periode_id between 'kalenderjahr:1996' and 'kalenderjahr:2025'
group by all
"""

SQL_ABSTIMMUNGEN = f"""
select u.neu_hstnr as hstnr, f.vorlage_id, sum(f.ja) as ja, sum(f.nein) as nein,
       bool_or(u.zuordnung = 'mehrdeutig') as mehrdeutig
from model.fact_volksabstimmungen f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
join model.gemeinden_umrechnen('{STAND_ABSTIMMUNGEN}', '{STAND}') u on u.alt_hstnr = z.gemeinde_hstnr
where z.gebietsart = 'gemeinde' and f.vorlage_id in ({", ".join(map(str, VORLAGEN))})
group by all
"""

SQL_GEMEINDEN = f"""
select z.gemeinde_hstnr as hstnr, any_value(g.GDE_GBFSNR) as bfs, any_value(g.GDE_GNAME) as gemeinde,
       any_value(g.GDE_KTKZ) as kanton, any_value(g.GDE_BHSTNR) as bezirk
from model.gebiet_zuordnung z
join model.agvch_historisch_gemeinden g on g.GDE_GHSTNR = z.gemeinde_hstnr
where z.gebiet_stand_id = '{STAND}' and z.gebietsart = 'gemeinde'
group by 1
"""

# Mittleres steuerbares Einkommen 2016 (ESTV) als Kontrolle; Gemeindezustände 2016 auf den Stand 2025.
SQL_EINKOMMEN = f"""
select u.neu_hstnr as hstnr, sum(f.steuerbares_einkommen_mittel_chf * f.steuerpflichtige) / sum(f.steuerpflichtige) as einkommen_2016,
       bool_or(u.zuordnung = 'mehrdeutig') as mehrdeutig
from model.fact_bundessteuer_personen f
join model.gebiet_zuordnung z using (gebiet_stand_id, gebiet_quellcode)
join model.gemeinden_umrechnen('estv-dbst-kanton-gemeinde@2016-01-01', '{STAND}') u on u.alt_hstnr = z.gemeinde_hstnr
where z.gebietsart = 'gemeinde' and f.periode_id = 'kalenderjahr:2016' and f.steuerpflichtigengruppe_id = 0
group by 1
"""


def bauen(con: duckdb.DuckDBPyConnection) -> tuple[pd.DataFrame, pd.DataFrame]:
    gemeinden = con.sql(SQL_GEMEINDEN).df()
    stimmen = con.sql(SQL_ABSTIMMUNGEN).df()
    eindeutig = stimmen.groupby("hstnr")["mehrdeutig"].any()
    stimmen = stimmen[~stimmen["hstnr"].isin(eindeutig[eindeutig].index)]
    stimmen["ja_anteil"] = stimmen["ja"] / (stimmen["ja"] + stimmen["nein"])
    breit = stimmen.pivot(index="hstnr", columns="vorlage_id", values="ja_anteil").rename(columns=VORLAGEN)
    # Index des Klimas: Mittel der vier Zuwanderungsvorlagen seit 2014.
    breit["klima_index"] = breit[["masseneinwanderung_2014", "durchsetzung_2016", "begrenzung_2020", "zehn_millionen_2026"]].mean(axis=1)
    gemeinden = gemeinden.merge(breit.reset_index(), on="hstnr", how="inner")

    einkommen = con.sql(SQL_EINKOMMEN).df()
    einkommen = einkommen[~einkommen["mehrdeutig"]].drop(columns="mehrdeutig")
    gemeinden = gemeinden.merge(einkommen, on="hstnr", how="left")

    einwanderung = con.sql(SQL_EINWANDERUNG).df()
    # Einwanderungswellen: Wer 1996–2010 kam, wurde mit 10 bis 12 Jahren Wohnsitz um 2018 einbürgerungsberechtigt.
    for von, bis in WELLEN:
        welle = einwanderung[einwanderung["jahr"].between(von, bis)].groupby("hstnr")["einwanderungen_ausland"].sum()
        gemeinden = gemeinden.merge(welle.rename(f"einwanderungen_{von}_{bis}").reset_index(), on="hstnr", how="left")

    panel = con.sql(SQL_EINBUERGERUNGEN).df().merge(con.sql(SQL_BEVOELKERUNG).df(), on=["hstnr", "jahr"], how="left")
    panel = panel[panel["jahr"].between(2011, 2025)].merge(
        einwanderung.rename(columns={"einwanderungen_ausland": "einwanderungen_jahr"}), on=["hstnr", "jahr"], how="left")
    panel = panel.merge(gemeinden[["hstnr"]], on="hstnr", how="inner")
    if panel["auslaender_vorjahr"].isna().any():
        raise ValueError("Gemeinde-Jahre ohne Bevölkerungsbestand: Gebietsstände passen nicht")
    panel["quote"] = panel["einbuergerungen"] / panel["auslaender_vorjahr"] * 100

    # Merkmale vor dem Gesetz (Bestand Ende 2016) für Kontrollen.
    vorher = panel[panel["jahr"] == 2017][["hstnr", "einwohner_vorjahr", "auslaender_vorjahr"]].rename(
        columns={"einwohner_vorjahr": "einwohner_2016", "auslaender_vorjahr": "auslaender_2016"})
    gemeinden = gemeinden.merge(vorher, on="hstnr", how="left")
    gemeinden["auslaenderanteil_2016"] = gemeinden["auslaender_2016"] / gemeinden["einwohner_2016"]
    for von, bis in WELLEN:
        gemeinden[f"welle_{von}_{bis}"] = gemeinden[f"einwanderungen_{von}_{bis}"].fillna(0) / gemeinden["auslaender_2016"]
    gemeinden["neu_zugewandert_2016"] = gemeinden["welle_2011_2016"]
    return panel, gemeinden


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    AUSGABE.mkdir(exist_ok=True)
    with duckdb.connect(str(MODELL), read_only=True) as con:
        panel, gemeinden = bauen(con)
    panel.to_parquet(AUSGABE / "panel.parquet", index=False)
    gemeinden.to_parquet(AUSGABE / "gemeinden.parquet", index=False)
    summe = panel.groupby("jahr")[["einbuergerungen", "auslaender_vorjahr"]].sum()
    summe["quote"] = summe["einbuergerungen"] / summe["auslaender_vorjahr"] * 100
    print(f"Gemeinden: {len(gemeinden)}; Gemeinde-Jahre: {len(panel)}")
    print(summe.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
