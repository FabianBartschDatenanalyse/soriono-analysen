"""Baupreisindex des BFS (Basis Oktober 2020 = 100) aus Prelude, als Jahresmittel aus April und Oktober.

Quelle in Prelude: fact_baupreisindex (BFS, cc-t-05.05.01), Objekte Neubau Mehrfamilienhaus (5)
und Renovation Mehrfamilienhaus (11), je Grossregion und für die Schweiz.
"""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

MODELL = Path(__file__).resolve().parents[2] / "state" / "analysen" / "modell.duckdb"
OBJEKTE = {5: "neubau_mfh", 11: "renovation_mfh"}

SQL = f"""
select coalesce(g.bezeichnung, 'Schweiz') as region, cast(substr(f.periode_id, 7, 4) as integer) as jahr,
       f.baupreisobjekt_id, avg(f.indexwert) as wert, count(*) as monate
from model.fact_baupreisindex f
join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
left join model.dim_grossregion g on g.grossregion_id = m.grossregion_id
where f.baupreisobjekt_id in ({", ".join(map(str, OBJEKTE))})
group by all
"""


def jahresindex(pfad: Path = MODELL) -> pd.DataFrame:
    """Je Grossregion (und Schweiz) und Jahr: Index Neubau und Renovation Mehrfamilienhaus."""
    with duckdb.connect(str(pfad), read_only=True) as con:
        d = con.sql(SQL).df()
    # Nur Jahre mit beiden Erhebungen (April und Oktober) zählen als Jahresmittel.
    d = d[d["monate"] == 2]
    d["objekt"] = d["baupreisobjekt_id"].map(OBJEKTE)
    return d.pivot_table(index=["region", "jahr"], columns="objekt", values="wert").reset_index()


if __name__ == "__main__":
    print(jahresindex().query("region == 'Schweiz' and jahr >= 2010").round(1).to_string())
