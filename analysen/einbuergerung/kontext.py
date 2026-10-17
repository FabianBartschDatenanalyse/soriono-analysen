"""Einbürgerungen der ganzen Schweiz nach Art des Erwerbs und früherer Staatsangehörigkeit.

Liest fact_einbuergerungen_kanton aus Prelude (BFS, px-x-0103030100_101; nur für Kantone und die
Schweiz veröffentlicht, darum nicht im Gemeindevergleich). Schreibt `ausgabe/kontext.csv`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import duckdb

HIER = Path(__file__).resolve().parent
MODELL = HIER.parents[1] / "state" / "analysen" / "modell.duckdb"
STAATEN = {8207: "Deutschland", 8212: "Frankreich", 8218: "Italien", 8231: "Portugal",
           8215: "Vereinigtes Königreich", 8256: "Kosovo", 8248: "Serbien", 8362: "Eritrea"}

SQL = f"""
with alle as (
  select cast(split_part(f.periode_id, ':', 2) as integer) as jahr, f.staat_id, a.bezeichnung as art, sum(f.einbuergerungen) as wert
  from model.fact_einbuergerungen_kanton f
  join model.gebiet_zuordnung m using (gebiet_stand_id, gebiet_quellcode)
  join model.dim_art_des_erwerbs a using (art_des_erwerbs_id)
  where m.gebietsart = 'schweiz'
  group by all
)
select jahr, 'Total' as staat, art, sum(wert) as wert from alle group by all
union all
select jahr, 'Total', 'Art des Erwerbs - Total', sum(wert) from alle group by all
union all
select jahr, s.staat, art, wert from alle join (values {", ".join(f"({k}, '{v}')" for k, v in STAATEN.items())}) s(staat_id, staat) using (staat_id)
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    with duckdb.connect(str(MODELL), read_only=True) as con:
        d = con.sql(SQL).df().sort_values(["staat", "art", "jahr"])
    d.to_csv(HIER / "ausgabe" / "kontext.csv", index=False)
    print(d[d["art"] == "Ordentliche Einbürgerung"].pivot(index="staat", columns="jahr", values="wert").to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
