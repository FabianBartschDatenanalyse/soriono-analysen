"""Auswertung: Haushaltsbeispiele, Verteilung der Entlastung und die Zahlen zu den Argumenten beider Lager.

Liest `ausgabe/simulation.parquet` und `ausgabe/eichung_gitter.csv` (aus modell.py) und schreibt
`ausgabe/ergebnisse.json` sowie Tabellen für die Grafiken. Spannen kommen aus allen Einstellungen des
Eichgitters, die zu den Prüfwerten der Bundesverwaltung passen (modell.PASSEND).
"""
from __future__ import annotations

import json
import sys
from dataclasses import replace

import numpy as np
import pandas as pd

import modell
import steuer
from modell import AUSGABE

REGELN = {"heute": "Heute", "individual": "Individualbesteuerung (ab 2032)",
          "initiative_mit": "Initiative, mit Privileg", "initiative_ohne": "Initiative, ohne Privileg"}


def haushalte() -> pd.DataFrame:
    """Steuer für typische Ehepaare nach Einkommen, Aufteilung und Kinderzahl unter allen Regeln."""
    zeilen = []
    for y in (80_000, 120_000, 180_000, 250_000):
        for anteil in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0):
            for kinder in (0, 2):
                y1, y2 = y * anteil, y * (1 - anteil)
                zeilen.append({"einkommen": y, "anteil_hoeher": anteil, "kinder": kinder,
                               "heute": steuer.ehepaar(y1, y2, kinder),
                               "konkubinat": steuer.konkubinat(y1, y2, kinder),
                               "individual": sum(steuer.ehepaar_individuell(y1, y2, kinder)),
                               "initiative_mit": steuer.ehepaar_initiative(y1, y2, kinder, "mit_privileg"),
                               "initiative_ohne": steuer.ehepaar_initiative(y1, y2, kinder, "ohne_privileg")})
    return pd.DataFrame(zeilen)


def grenzsteuer_zweiteinkommen(y1: float, kinder: int, regel: str, schritt: float = 10_000) -> list[dict]:
    """Wie viel der nächsten 10'000 Franken Zweiteinkommen geht an die Bundessteuer?"""
    aus = []
    for y2 in range(0, 100_001, 10_000):
        def t(z):
            if regel == "heute":
                return steuer.ehepaar(y1, z, kinder)
            if regel == "individual":
                return sum(steuer.ehepaar_individuell(y1, z, kinder))
            return steuer.ehepaar_initiative(y1, z, kinder, regel.replace("initiative_", "") + "_privileg")
        aus.append({"zweiteinkommen": y2, "grenzsteuer_prozent": round(100 * (t(y2 + schritt) - t(y2)) / schritt, 2)})
    return aus


def kennwerte(d: pd.DataFrame) -> dict:
    w = d.gewicht
    def summe(maske, spalte):
        return float((w[maske] * spalte[maske]).sum())
    entl_mit = d.heute - d.initiative_mit
    entl_ohne = d.heute - d.initiative_ohne
    alle = np.ones(len(d), bool)
    unter75 = (d.y1 + d.y2) < 75_000
    ueber150 = (d.y1 + d.y2) >= 150_000
    ueber250 = (d.y1 + d.y2) >= 250_000
    nach_initiative_weniger_als_konkubinat = d.initiative_mit < d.konkubinat - 0.5
    individual_mehr = d.individual > d.heute + 0.5
    individual_weniger = d.individual < d.heute - 0.5
    einverdiener = ~d.zweiverdiener & ~d.rentner
    return {
        "entlastung_mit_mrd": summe(alle, entl_mit) / 1e9,
        "entlastung_ohne_mrd": summe(alle, entl_ohne) / 1e9,
        "anteil_entlastung_mit_unter_75k": summe(unter75, entl_mit) / summe(alle, entl_mit),
        "anteil_entlastung_mit_ab_150k": summe(ueber150, entl_mit) / summe(alle, entl_mit),
        "anteil_entlastung_mit_ab_250k": summe(ueber250, entl_mit) / summe(alle, entl_mit),
        "anteil_paare_unter_75k": float(w[unter75].sum() / w.sum()),
        "anteil_paare_ab_150k": float(w[ueber150].sum() / w.sum()),
        "anteil_paare_ab_250k": float(w[ueber250].sum() / w.sum()),
        "paare_initiative_unter_konkubinat_tsd": float(w[nach_initiative_weniger_als_konkubinat].sum() / 1e3),
        "paare_individual_mehr_tsd": float(w[individual_mehr].sum() / 1e3),
        "paare_individual_weniger_tsd": float(w[individual_weniger].sum() / 1e3),
        "einverdiener_individual_mehr_anteil": float(w[einverdiener & individual_mehr].sum() / w[einverdiener].sum()),
        "zweiverdiener_individual_weniger_anteil": float(w[d.zweiverdiener & individual_weniger].sum() / w[d.zweiverdiener].sum()),
        "rentner_individual_mehr_anteil": float(w[d.rentner & individual_mehr].sum() / w[d.rentner].sum()),
        "paare_ohne_privileg_mehr_tsd": float(w[d.initiative_ohne > d.heute + 0.5].sum() / 1e3),
        "einverdiener_ohne_privileg_mehr_anteil": float(w[einverdiener & (d.initiative_ohne > d.heute + 0.5)].sum() / w[einverdiener].sum()),
    }


def nach_einkommen(d: pd.DataFrame) -> pd.DataFrame:
    """Durchschnittliche Veränderung je Paar und Anteil an der gesamten Entlastung, nach Paareinkommen."""
    klassen = [0, 50_000, 75_000, 100_000, 150_000, 250_000, 500_000, np.inf]
    namen = ["unter 50'000", "50'000–75'000", "75'000–100'000", "100'000–150'000", "150'000–250'000",
             "250'000–500'000", "ab 500'000"]
    d = d.assign(klasse=pd.cut(d.y1 + d.y2, klassen, labels=namen, right=False))
    zeilen = []
    for name, g in d.groupby("klasse", observed=True):
        w = g.gewicht
        zeilen.append({"klasse": name, "paare_tsd": float(w.sum() / 1e3),
                       **{f"mittel_{r}": float((w * (g[r] - g.heute)).sum() / w.sum()) for r in REGELN if r != "heute"},
                       "steuer_heute_mittel": float((w * g.heute).sum() / w.sum())})
    t = pd.DataFrame(zeilen)
    for r in ("initiative_mit", "initiative_ohne", "individual"):
        gesamt = (t[f"mittel_{r}"] * t.paare_tsd).sum()
        t[f"anteil_{r}"] = t[f"mittel_{r}"] * t.paare_tsd / gesamt
    return t


def spannen(n: int = 40_000) -> dict:
    gitter = pd.read_csv(AUSGABE / "eichung_gitter.csv")
    passend = gitter[gitter.abstand_tsd < modell.PASSEND / 1e3]
    basis = json.loads((AUSGABE / "modell_kennzahlen.json").read_text(encoding="utf-8"))["annahmen"]
    werte = []
    for _, z in passend.iterrows():
        a = replace(modell.Annahmen(n=n), einverdiener_zusatz=basis["einverdiener_zusatz"],
                    rentner_anteil_hoeher_mittel=z.rentner_anteil_hoeher_mittel,
                    lohnverhaeltnis_median=z.lohnverhaeltnis_median, lohnverhaeltnis_streuung=z.lohnverhaeltnis_streuung)
        werte.append(kennwerte(modell.steuern(modell.simulieren(a))))
    t = pd.DataFrame(werte)
    return {c: [round(float(t[c].min()), 4), round(float(t[c].max()), 4)] for c in t}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    d = pd.read_parquet(AUSGABE / "simulation.parquet")
    h = haushalte(); h.to_csv(AUSGABE / "haushalte.csv", index=False)
    g = nach_einkommen(d); g.to_csv(AUSGABE / "nach_einkommen.csv", index=False)
    grenz = {f"{regel}|{y1}|{k}": grenzsteuer_zweiteinkommen(y1, k, regel)
             for regel in ("heute", "individual", "initiative_mit", "initiative_ohne") for y1 in (100_000,) for k in (0, 2)}
    ergebnis = {"haupt": {k: round(v, 4) for k, v in kennwerte(d).items()}, "spanne": spannen(),
                "grenzsteuer_zweiteinkommen": grenz,
                "modell": json.loads((AUSGABE / "modell_kennzahlen.json").read_text(encoding="utf-8"))}
    (AUSGABE / "ergebnisse.json").write_text(json.dumps(ergebnis, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps(ergebnis["haupt"], indent=1)); print(json.dumps(ergebnis["spanne"]))
    print(g.round(3).to_string(index=False))
    print(h[(h.kinder == 0) & h.einkommen.isin([120_000, 250_000])].to_string(index=False))
    return 0


if __name__ == "__main__" and "--robust" not in sys.argv:
    raise SystemExit(main())


SZENARIEN = {
    "Hauptvariante": {},
    "weniger Paare ohne Kinder (25 %)": {"kinderlos_anteil": 0.25},
    "mehr Paare ohne Kinder (45 %)": {"kinderlos_anteil": 0.45},
    "Rentnerpaare über alle Einkommen gleich verteilt": {"rentner_gefaelle": 0.0},
    "Rentnerpaare stark bei tiefen Einkommen": {"rentner_gefaelle": 1.2},
    "mehr kinderreiche Familien (1/2/3 Kinder: 35/45/20 %)": {"kinder_1_2_3": (0.35, 0.45, 0.20)},
    "Partnerin verdient gleich viel pro Stunde": {"lohnverhaeltnis_median": 1.0},
    "geringere Lohnstreuung im Paar": {"lohnverhaeltnis_streuung": 0.8},
}


def robustheit(n: int = 60_000) -> pd.DataFrame:
    """Eine Annahme nach der anderen ändern; die übrigen bleiben auf der geeichten Hauptvariante."""
    basis = json.loads((AUSGABE / "modell_kennzahlen.json").read_text(encoding="utf-8"))["annahmen"]
    a0 = replace(modell.Annahmen(n=n), **{k: (tuple(v) if isinstance(v, list) else v) for k, v in basis.items() if k not in ("n",)})
    zeilen = []
    for name, aenderung in SZENARIEN.items():
        d = modell.steuern(modell.simulieren(replace(a0, **aenderung)))
        k, w = modell.kennzahlen(d), kennwerte(d)
        zeilen.append({"szenario": name, "mehrbelastung_tsd": k["mehrbelastung_10_tsd"], "minderbelastung_tsd": k["minderbelastung_10_tsd"],
                       "kosten_mit_mrd": round(w["entlastung_mit_mrd"], 2), "kosten_ohne_mrd": round(w["entlastung_ohne_mrd"], 2),
                       "anteil_entlastung_ab_150k": round(w["anteil_entlastung_mit_ab_150k"], 3),
                       "anteil_entlastung_unter_75k": round(w["anteil_entlastung_mit_unter_75k"], 4),
                       "ohne_privileg_mehr_tsd": round(w["paare_ohne_privileg_mehr_tsd"]),
                       "einverdiener_individual_mehr": round(w["einverdiener_individual_mehr_anteil"], 3)})
        print(zeilen[-1], flush=True)
    t = pd.DataFrame(zeilen)
    t.to_csv(AUSGABE / "robustheit.csv", index=False)
    return t


if __name__ == "__main__" and "--robust" in sys.argv:
    sys.stdout.reconfigure(encoding="utf-8")
    robustheit()
