"""Panel Kanton × Jahr: Wohnbauinvestitionen, Arbeitsvorrat, neue Wohnungen, Bevölkerung, Baupreise.

Liest aus dem veröffentlichten Datenmodell Prelude (zuerst `../gemeinsam/modell_laden.py wohnungsbau`)
und aus dem Baupreisindex des BFS (`bpi.py`). Schreibt `ausgabe/kantone.parquet`.

Wohnen ist die Bauwerkkategorie 900. Neubau und Umbau kommen aus fact_bauinvestitionen_arbeiten,
private und öffentliche Auftraggeber aus fact_bauinvestitionen (gleiche Erhebung, gleiche Summen).
Alle Beträge in Millionen Franken zu laufenden Preisen; real = geteilt durch den Baupreisindex
der Grossregion des Kantons (Neubau bzw. Renovation Mehrfamilienhaus, Oktober 2020 = 100).
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb
import pandas as pd

from bpi import jahresindex

HIER = Path(__file__).resolve().parent
MODELL = HIER.parents[1] / "state" / "analysen" / "modell.duckdb"
AUSGABE = HIER / "ausgabe"
WOHNEN = 900

SQL_ARBEITEN = f"""
select m.kanton_nr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr,
       sum(f.bauinvestitionen_tchf) filter (where f.art_der_arbeiten_id = 1) / 1000.0 as neubau_mio,
       sum(f.bauinvestitionen_tchf) filter (where f.art_der_arbeiten_id = 2) / 1000.0 as umbau_mio,
       sum(f.arbeitsvorrat_tchf) filter (where f.art_der_arbeiten_id = 1) / 1000.0 as vorrat_neubau_mio,
       sum(f.arbeitsvorrat_tchf) filter (where f.art_der_arbeiten_id = 2) / 1000.0 as vorrat_umbau_mio
from model.fact_bauinvestitionen_arbeiten f
join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
where m.gebietsart = 'kanton' and f.bauwerkkategorie_id = {WOHNEN}
group by all
"""

SQL_AUFTRAGGEBER = f"""
select m.kanton_nr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr,
       sum(f.bauinvestitionen_tchf) filter (where f.auftraggeber_id = 2) / 1000.0 as privat_mio
from model.fact_bauinvestitionen f
join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
where m.gebietsart = 'kanton' and f.bauwerkkategorie_id = {WOHNEN}
group by all
"""

SQL_WOHNUNGEN = """
select m.kanton_nr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr, sum(f.wohnungen) as wohnungen
from model.fact_neubauwohnungen f
join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
where m.gebietsart = 'kanton'
group by all
"""

# Ständige Wohnbevölkerung am 31.12.
SQL_BEVOELKERUNG = """
select m.kanton_nr, cast(split_part(f.periode_id, ':', 2) as integer) as jahr, sum(f.personen) as einwohner
from model.fact_bevoelkerungsbestand f
join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
where m.gebietsart = 'kanton' and f.bevoelkerungstyp_id = 1
group by all
"""

SQL_KANTONE = """
select k.KT_KTNR as kanton_nr, k.KT_KTKZ as kanton, g.bezeichnung as grossregion
from model.agvch_historisch_kantone k
join model.kanton_grossregion kg on kg.kanton_nr = k.KT_KTNR
join model.dim_grossregion g using (grossregion_id)
"""


def bauen(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    d = con.sql(SQL_ARBEITEN).df()
    for sql in (SQL_AUFTRAGGEBER, SQL_WOHNUNGEN, SQL_BEVOELKERUNG):
        d = d.merge(con.sql(sql).df(), on=["kanton_nr", "jahr"], how="outer")
    d = d.merge(con.sql(SQL_KANTONE).df(), on="kanton_nr", how="left")
    if d["grossregion"].isna().any():
        raise ValueError("Kantone ohne Grossregion")
    preise = jahresindex().rename(columns={"region": "grossregion"})
    d = d.merge(preise, on=["grossregion", "jahr"], how="left")
    return d.sort_values(["kanton", "jahr"]).reset_index(drop=True)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    AUSGABE.mkdir(exist_ok=True)
    with duckdb.connect(str(MODELL), read_only=True) as con:
        d = bauen(con)
    d.to_parquet(AUSGABE / "kantone.parquet", index=False)
    s = d.groupby("jahr")[["neubau_mio", "umbau_mio", "vorrat_neubau_mio", "wohnungen", "einwohner"]].sum(min_count=1)
    print(f"Kantone: {d['kanton'].nunique()}, Jahre {d['jahr'].min()}–{d['jahr'].max()}")
    print(s.loc[2008:].round(1).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
