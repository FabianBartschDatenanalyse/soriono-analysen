"""Einbürgerungen der ganzen Schweiz nach Art des Erwerbs und früherer Staatsangehörigkeit (BFS).

Diese Aufteilung gibt das BFS nur für Kantone und die Schweiz heraus (Tabelle px-x-0103030100_101);
sie ist noch nicht in Prelude und wird hier direkt über die PxWeb-Schnittstelle abgefragt.
Schreibt `ausgabe/kontext.csv` mit der Abfrage-Antwort unverändert in `ausgabe/kontext.json`.
"""

from __future__ import annotations

import itertools
import json
import sys
import urllib.request
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
TABELLE = "px-x-0103030100_101"
LAENDER = {"0": "Total", "8207": "Deutschland", "8212": "Frankreich", "8218": "Italien", "8231": "Portugal",
           "8215": "Vereinigtes Königreich", "8256": "Kosovo", "8248": "Serbien", "8362": "Eritrea"}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    abfrage = {"query": [
        {"code": "Kanton", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Art des Erwerbs", "selection": {"filter": "all", "values": ["*"]}},
        {"code": "Geschlecht", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Alter", "selection": {"filter": "item", "values": ["0"]}},
        {"code": "Staatsangehörigkeit ehemalig", "selection": {"filter": "item", "values": list(LAENDER)}}],
        "response": {"format": "json-stat2"}}
    url = f"https://www.pxweb.bfs.admin.ch/api/v1/de/{TABELLE}/{TABELLE}.px"
    anfrage = urllib.request.Request(url, data=json.dumps(abfrage).encode(),
                                     headers={"User-Agent": "swiss-data-mirror", "Content-Type": "application/json"})
    antwort = json.load(urllib.request.urlopen(anfrage, timeout=120))
    (HIER / "ausgabe" / "kontext.json").write_text(json.dumps(antwort, ensure_ascii=False), encoding="utf-8")
    dims = antwort["id"]
    codes = [list(antwort["dimension"][d]["category"]["index"]) for d in dims]
    namen = [antwort["dimension"][d]["category"]["label"] for d in dims]
    zeilen = [dict(zip(dims, (n[c] for n, c in zip(namen, kombi))), code_staat=kombi[-1], wert=v)
              for kombi, v in zip(itertools.product(*codes), antwort["value"])]
    d = pd.DataFrame(zeilen)
    d["staat"] = d["code_staat"].map(LAENDER)
    d = d.rename(columns={"Jahr": "jahr", "Art des Erwerbs": "art"})[["jahr", "staat", "art", "wert"]]
    d.to_csv(HIER / "ausgabe" / "kontext.csv", index=False)
    print(d[d["art"] == "Ordentliche Einbürgerung"].pivot(index="staat", columns="jahr", values="wert").to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
