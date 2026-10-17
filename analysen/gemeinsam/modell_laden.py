"""Lädt das veröffentlichte Datenmodell einmal in eine lokale DuckDB.

Jede Person kann eine Analyse so mit demselben Stand nachrechnen. Der verwendete
Katalogstand wird im Ordner der Analyse in `ausgabe/modellstand.txt` festgehalten:

    python gemeinsam/modell_laden.py einbuergerung
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import duckdb

HIER = Path(__file__).resolve().parent
ZIEL = HIER.parents[1] / "state" / "analysen" / "modell.duckdb"
ANALYSEN = HIER.parent
WURZEL = "https://files.soriono.ch/"


def holen(url: str) -> bytes:
    anfrage = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(anfrage).read()


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2 or not (ANALYSEN / sys.argv[1]).is_dir():
        raise SystemExit("Aufruf: python gemeinsam/modell_laden.py <ordner der analyse>")
    aktuell = json.loads(holen(WURZEL + "lab/data-model/model-catalog/current.json"))
    ordner = WURZEL + aktuell["manifest_key"].rsplit("/", 1)[0] + "/"
    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    ZIEL.unlink(missing_ok=True)
    with duckdb.connect(str(ZIEL), config={"custom_user_agent": "Mozilla/5.0"}) as con:
        con.execute(holen(ordner + "bootstrap-lokal.sql").decode())
        con.execute(holen(ordner + "checks.sql").decode())
    ausgabe = ANALYSEN / sys.argv[1] / "ausgabe"
    ausgabe.mkdir(exist_ok=True)
    (ausgabe / "modellstand.txt").write_text(ordner + "\n", encoding="utf-8")
    print(f"Modell geladen: {ordner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
