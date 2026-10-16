"""Prüft `steuer.py` gegen die Haushaltsbeispiele der ESTV (Status quo 2026).

Das Modell der ESTV rechnet den Tarif stetig; das Gesetz rundet das steuerbare Einkommen auf 100 Franken
und die Steuer auf 5 Rappen ab. Die Prüfung läuft darum im stetigen Modus und verlangt höchstens 1 Franken
Abweichung (die ESTV rundet Ehepaar-Steuern auf ganze Franken). Mit `--gesetz` zeigt sie die Abweichungen
durch die gesetzliche Rundung. Ergebnis: `ausgabe/pruefung.csv`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import steuer

HIER = Path(__file__).resolve().parent
QUELLEN = HIER / "quellen" / "estv"
AUSGABE = HIER / "ausgabe"
TOLERANZ = 1.0  # die ESTV weist Ehepaar-Steuern auf ganze Franken gerundet aus


def ehepaare(datei: str, zweiverdiener: bool) -> pd.DataFrame:
    d = pd.read_excel(QUELLEN / datei, sheet_name=0)
    d.columns = ["y", "y1", "y2", "anteil", "kinder", "sq", "reform", "reform_1", "reform_2"]
    d["rechner"] = [steuer.ehepaar(a, b, int(k), zweiverdiener) for a, b, k in zip(d["y1"], d["y2"], d["kinder"])]
    d["datei"] = datei
    return d


def einzelne() -> pd.DataFrame:
    d = pd.read_excel(QUELLEN / "tax-burden-single-y2026-de.xlsx", sheet_name=0)
    d.columns = ["y", "kinder", "sq", "reform"]
    d["rechner"] = [steuer.unverheiratet(y, int(k)) for y, k in zip(d["y"], d["kinder"])]
    d["datei"] = "single"
    return d


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    steuer.STETIG = "--gesetz" not in sys.argv  # Standard: stetig wie das Modell der ESTV
    AUSGABE.mkdir(exist_ok=True)
    teile = [ehepaare("tax-burden-married-y2026-de.xlsx", True),
             ehepaare("tax-burden-married-pens-k12000-y2026-de.xlsx", False), einzelne()]
    alle = pd.concat(teile, ignore_index=True)
    alle["diff"] = (alle["rechner"] - alle["sq"]).round(2)
    alle.to_csv(AUSGABE / "pruefung.csv", index=False)
    for name, g in alle.groupby("datei"):
        falsch = g[g["diff"].abs() > TOLERANZ]
        print(f"{name}: {len(g)} Fälle, {len(falsch)} über {TOLERANZ} Fr., grösste Abweichung {g['diff'].abs().max():.2f}, "
              f"genau gleich {(g['diff'].abs() < 0.5).mean():.1%}")
        if len(falsch):
            print(falsch.head(8).to_string(index=False))
    return 0 if (alle["diff"].abs() <= TOLERANZ).all() else 1


if __name__ == "__main__":
    raise SystemExit(main())
