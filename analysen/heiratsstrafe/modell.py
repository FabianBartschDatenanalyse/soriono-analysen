"""Schätzmodell: Wie viele Ehepaare betrifft die Initiative, und was kostet sie?

Die Bundessteuerstatistik kennt bei Ehepaaren nur das gemeinsame Einkommen, nicht die Aufteilung
zwischen den Eheleuten. Die Bundesverwaltung stützt sich dafür auf Strukturdaten aus 10 Kantonen von 2015
(WiSiER, Botschaft BBl 2025 1092, Ziff. 4.2.1). Dieses Modell verwendet nur öffentliche Daten:

1. Steuerbares Einkommen der 1'770'250 Ehepaare 2022: Perzentile der ESTV-Statistik
   (quellen/estv/statistik-dbst-np-kennzahlen-ohne-2022.xlsx, Blatt Schweiz).
2. Erwerbsmodelle von Paaren nach Kinderzahl: BFS, SAKE 2025 (quellen/bfs/cc-d-20.04.03.03.01-erwerbsmodelle.xlsx).
3. Anteile Rentnerpaare und Kinderabzüge: Botschaft, Tabellen 1 und 2.

Daraus entstehen simulierte Ehepaare mit Einkommen beider Eheleute und Kinderzahl. Für jedes werden die
Steuern unter allen Regeln berechnet (steuer.py). Jede Annahme ist ein Parameter in ANNAHMEN; `main`
rechnet die Hauptvariante, `sensitivitaet` variiert die unsicheren Annahmen.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path

import numpy as np
import pandas as pd

import steuer

HIER = Path(__file__).resolve().parent
AUSGABE = HIER / "ausgabe"
QUELLEN = HIER / "quellen"

EHEPAARE_2022 = 1_770_250       # ESTV Kennzahlen 2022, Verheiratete oder eingetragene Partnerschaften
STEUER_EHEPAARE_2022 = 7_820_813_841  # Einnahmen direkte Bundessteuer aus diesen Steuerpflichtigen, CHF
MITTEL_STEUERBAR_2022 = 101_847.6

# Erwerbsmodelle der SAKE 2025 (Spalten der BFS-Tabelle) als Erwerbsgrade (Partner, Partnerin).
# Ein Bereich wird gleichverteilt gezogen; 0 heisst ohne Erwerbseinkommen.
MODELLE = {
    "Partner Vollzeit / Partnerin nicht erwerbstätig": ((1, 1), (0, 0)),
    "Partner Vollzeit / Partnerin Teilzeit 1–49%": ((1, 1), (0.15, 0.49)),
    "Partner Vollzeit / Partnerin Teilzeit 50–89%": ((1, 1), (0.5, 0.89)),
    "Beide Vollzeit": ((1, 1), (1, 1)),
    "Beide Teilzeit  1-89%": ((0.5, 0.89), (0.4, 0.89)),
    "Partner nicht oder Teilzeit (1-89%) erwerbstätig / Partnerin Vollzeit": ((0, 0.89), (1, 1)),
    "Partner erwerbslos / Partnerin erwerbstätig": ((0, 0), (0.5, 1)),
    "Partner erwerbstätig / Partnerin erwerbslos": ((0.8, 1), (0, 0)),
    "Beide Partner erwerbslos oder einer erwerbslos und der andere nicht erwerbstätig": ((0, 0), (0, 0)),
    "Partner oder Partnerin Teilzeit 1-89% und Partner/in nicht erwerbstätig": ((0.3, 0.89), (0, 0)),
    "Beide Partner nicht erwerbstätig": ((0, 0), (0, 0)),
}


@dataclass(frozen=True)
class Annahmen:
    n: int = 200_000                    # simulierte Ehepaare
    seed: int = 1
    rentner_anteil: float = 506_426 / 1_766_032  # Botschaft Tabelle 1 (Steuerjahr 2025)
    rentner_gefaelle: float = 0.6       # Rentnerpaare häufiger bei tiefen Einkommen: Anteil 1+g/2 .. 1-g/2 entlang der Verteilung
    kinderlos_anteil: float = 0.35      # Nicht-Rentnerpaare ohne Kinderabzug (abgeleitet, siehe kinder_verteilung)
    kinder_1_2_3: tuple = (0.43, 0.42, 0.15)  # Verteilung bei Paaren mit Kindern (1, 2, 3)
    lohnverhaeltnis_median: float = 0.85     # Stundenlohn der Partnerin relativ zum Partner (Median)
    lohnverhaeltnis_streuung: float = 0.5    # Streuung (Standardabweichung des Logarithmus)
    rentner_anteil_hoeher_mittel: float = 0.62  # Anteil der höheren Rente am Paareinkommen (AHV-Splitting, BVG)
    rentner_anteil_hoeher_streuung: float = 0.08
    einverdiener_zusatz: float = 0.0        # zusätzlicher Anteil Einverdienerpaare (geeicht auf die Steuerstatistik)
    jahr_einkommen: str = "2022"


def perzentile() -> tuple[np.ndarray, np.ndarray]:
    t = pd.read_excel(QUELLEN / "estv" / "statistik-dbst-np-kennzahlen-ohne-2022.xlsx", sheet_name="Schweiz - Suisse", header=None)
    kopf = [str(x).split("\n")[0] for x in t.iloc[0]]
    zeile = dict(zip(kopf, t.iloc[1].tolist()))
    assert str(zeile["Einheit"]).startswith("Verheiratete") and int(zeile["stpf"]) == EHEPAARE_2022
    punkte = {"p1": .01, "p5": .05, "p10": .10, "p20": .20, "p25": .25, "p30": .30, "p40": .40, "p50": .50, "p60": .60,
              "p70": .70, "p75": .75, "p80": .80, "p90": .90, "p95": .95, "p96": .96, "p97": .97, "p98": .98,
              "p99": .99, "p99_5": .995, "p99_9": .999, "p99_99": .9999}
    u = np.array(list(punkte.values()))
    y = np.array([float(zeile[k]) for k in punkte])
    return u, y


def quantil(u: np.ndarray, pu: np.ndarray, py: np.ndarray, alpha: float | None = None) -> np.ndarray:
    """Steuerbares Einkommen zum Rang u.

    Bis zum 90. Perzentil linear zwischen den Perzentilen; darüber log-linear in log(1-u) (Pareto-artig,
    die Interpolation unterschätzt so den Mittelwert nicht wie eine Gerade ihn überschätzt); über dem
    99,99. Perzentil ein Pareto-Rand, dessen Exponent den Mittelwert der ESTV trifft (`pareto_alpha`).
    """
    alpha = alpha or pareto_alpha(pu, py)
    y = np.interp(u, np.r_[0, pu], np.r_[0, py])
    hoch = (u >= 0.90) & (u <= pu[-1])
    k = pu >= 0.90
    y[hoch] = np.exp(np.interp(-np.log(1 - u[hoch]), -np.log(1 - pu[k]), np.log(py[k])))
    oben = u > pu[-1]
    y[oben] = py[-1] * ((1 - pu[-1]) / (1 - u[oben])) ** (1 / alpha)
    return y


def pareto_alpha(pu: np.ndarray, py: np.ndarray) -> float:
    """Exponent des Rands über dem 99,99. Perzentil, so dass der Mittelwert 101'848 Franken (ESTV) beträgt."""
    raster = (np.arange(2_000_000) + 0.5) / 2_000_000
    koerper = raster[raster <= pu[-1]]
    y = np.interp(koerper, np.r_[0, pu], np.r_[0, py])
    hoch = koerper >= 0.90
    k = pu >= 0.90
    y[hoch] = np.exp(np.interp(-np.log(1 - koerper[hoch]), -np.log(1 - pu[k]), np.log(py[k])))
    rest = MITTEL_STEUERBAR_2022 - y.sum() / len(raster)  # Beitrag, den der Rand liefern muss
    rand = rest / (1 - pu[-1])                          # mittleres Einkommen im Rand
    if rand <= py[-1]:
        raise ValueError("Rand kann den Mittelwert nicht treffen")
    return rand / (rand - py[-1])                       # Pareto: Mittel = a/(a-1) * x_m


def reineinkommen(steuerbar: float, anteil_hoeher: float, kinder: int, zweiverdiener: bool) -> tuple[float, float]:
    """Einkommen beider Eheleute (wie in steuer.ehepaar) so, dass das steuerbare Einkommen stimmt."""
    fest = steuer.VERSICHERUNG_VERHEIRATET + steuer.ABZUG_VERHEIRATET + kinder * (steuer.ABZUG_KIND + steuer.VERSICHERUNG_KIND)
    y = steuerbar + fest
    for _ in range(30):  # Zweiverdienerabzug hängt vom tieferen Einkommen ab: Fixpunkt
        tief = (1 - anteil_hoeher) * y
        neu = steuerbar + fest + (steuer.zweiverdienerabzug(tief) if zweiverdiener else 0)
        if abs(neu - y) < 0.5:
            break
        y = neu
    return anteil_hoeher * y, (1 - anteil_hoeher) * y


def simulieren(a: Annahmen) -> pd.DataFrame:
    rng = np.random.default_rng(a.seed)
    pu, py = perzentile()
    u = (np.arange(a.n) + rng.random(a.n)) / a.n  # geschichtete Ränge
    steuerbar = quantil(u, pu, py)
    p_rentner = np.clip(a.rentner_anteil * (1 + a.rentner_gefaelle * (0.5 - u)), 0, 1)
    rentner = rng.random(a.n) < p_rentner

    sake = pd.read_excel(QUELLEN / "bfs" / "cc-d-20.04.03.03.01-erwerbsmodelle.xlsx", sheet_name="2025", header=None)
    norm = lambda s: " ".join(str(s).split())  # noqa: E731 – Leerzeichen und Umbrüche der BFS-Spaltennamen
    kopf = [norm(x) for x in sake.iloc[2]]
    zeilen = {str(sake.iloc[i, 0]).strip(): i for i in range(3, 33)}
    def verteilung(zeile: int) -> np.ndarray:
        w = np.array([pd.to_numeric(sake.iloc[zeile, kopf.index(norm(m))], errors="coerce") for m in MODELLE], float)
        w = np.nan_to_num(w)
        return w / w.sum()
    # Zeilen 5–7: Paare mit jüngstem Kind unter 25 Jahren mit 1, 2, 3+ Kindern; Zeile 32: ohne Kinder.
    vert = {0: verteilung(zeilen["Paare ohne Kinder im Haushalt"]), 1: verteilung(5), 2: verteilung(6), 3: verteilung(7)}

    kinder = np.zeros(a.n, int)
    mit = ~rentner & (rng.random(a.n) >= a.kinderlos_anteil)
    kinder[mit] = rng.choice([1, 2, 3], size=mit.sum(), p=np.array(a.kinder_1_2_3) / sum(a.kinder_1_2_3))

    namen = list(MODELLE)
    modell = np.empty(a.n, object)
    for k in (0, 1, 2, 3):
        idx = np.where(~rentner & (kinder == k))[0]
        modell[idx] = rng.choice(namen, size=len(idx), p=vert[k])
    # Die SAKE erfasst Paare von 25 bis 54 Jahren, auch unverheiratete; verheiratete Paare insgesamt sind häufiger
    # Einverdienerpaare. Der Zusatz wird so geeicht, dass die Zahl der Paare mit Zweiverdienerabzug stimmt (eichen).
    zusatz = ~rentner & (rng.random(a.n) < a.einverdiener_zusatz)
    modell[zusatz] = "Partner Vollzeit / Partnerin nicht erwerbstätig"
    modell[rentner] = "Rentnerpaar"

    def grad(bereich, m):
        lo, hi = bereich
        return lo + (hi - lo) * rng.random(m)
    grad_m = np.zeros(a.n); grad_f = np.zeros(a.n)
    for name, (bm, bf) in MODELLE.items():
        idx = modell == name
        grad_m[idx] = grad(bm, idx.sum()); grad_f[idx] = grad(bf, idx.sum())
    lohn = a.lohnverhaeltnis_median * np.exp(a.lohnverhaeltnis_streuung * rng.standard_normal(a.n))
    arbeit_m, arbeit_f = grad_m, grad_f * lohn
    summe = arbeit_m + arbeit_f
    anteil = np.where(summe > 0, np.maximum(arbeit_m, arbeit_f) / np.where(summe > 0, summe, 1), 0.5)
    zweiverdiener = (arbeit_m > 0) & (arbeit_f > 0)
    r = rentner
    anteil[r] = np.clip(a.rentner_anteil_hoeher_mittel + a.rentner_anteil_hoeher_streuung * rng.standard_normal(r.sum()), 0.5, 0.97)
    zweiverdiener[r] = False
    ohne_erwerb = ~r & (summe == 0)  # Paare ohne Erwerbseinkommen: übrige Einkünfte hälftig
    anteil[ohne_erwerb] = 0.5

    y1 = np.empty(a.n); y2 = np.empty(a.n)
    for i in range(a.n):
        y1[i], y2[i] = reineinkommen(steuerbar[i], anteil[i], int(kinder[i]), bool(zweiverdiener[i]))
    return pd.DataFrame({"rang": u, "steuerbar": steuerbar, "rentner": rentner, "kinder": kinder, "modell": modell,
                         "anteil_hoeher": anteil, "zweiverdiener": zweiverdiener, "y1": y1, "y2": y2,
                         "gewicht": EHEPAARE_2022 / a.n})


def steuern(d: pd.DataFrame) -> pd.DataFrame:
    d = d.copy()
    rechne = lambda f: [f(a, b, int(k), bool(z)) for a, b, k, z in zip(d.y1, d.y2, d.kinder, d.zweiverdiener)]  # noqa: E731
    d["heute"] = rechne(lambda a, b, k, z: steuer.ehepaar(a, b, k, z))
    d["konkubinat"] = rechne(lambda a, b, k, z: steuer.konkubinat(a, b, k))
    d["initiative_mit"] = rechne(lambda a, b, k, z: steuer.ehepaar_initiative(a, b, k, "mit_privileg", z))
    d["initiative_ohne"] = rechne(lambda a, b, k, z: steuer.ehepaar_initiative(a, b, k, "ohne_privileg", z))
    d["individual"] = rechne(lambda a, b, k, z: sum(steuer.ehepaar_individuell(a, b, k)))
    return d


def kennzahlen(d: pd.DataFrame) -> dict:
    w = d.gewicht
    rel = (d.heute - d.konkubinat) / d.konkubinat.where(d.konkubinat > 0)
    strafe = (rel >= 0.10) | ((d.konkubinat == 0) & (d.heute > 0))
    bonus = rel <= -0.10
    return {
        "steuer_heute_mrd": round(float((w * d.heute).sum()) / 1e9, 3),
        "zweiverdiener_tsd": round(float(w[d.zweiverdiener].sum()) / 1e3),
        "rentner_tsd": round(float(w[d.rentner].sum()) / 1e3),
        "mehrbelastung_10_tsd": round(float(w[strafe].sum()) / 1e3),
        "minderbelastung_10_tsd": round(float(w[bonus].sum()) / 1e3),
        "kosten_initiative_mit_privileg_mrd": round(float((w * (d.heute - d.initiative_mit)).sum()) / 1e9, 3),
        "kosten_initiative_ohne_privileg_mrd": round(float((w * (d.heute - d.initiative_ohne)).sum()) / 1e9, 3),
        "entlastet_mit_privileg_tsd": round(float(w[d.initiative_mit < d.heute - 0.5].sum()) / 1e3),
        "entlastet_ohne_privileg_tsd": round(float(w[d.initiative_ohne < d.heute - 0.5].sum()) / 1e3),
        "belastet_ohne_privileg_tsd": round(float(w[d.initiative_ohne > d.heute + 0.5].sum()) / 1e3),
        "differenz_individual_mrd": round(float((w * (d.heute - d.individual)).sum()) / 1e9, 3),
    }


# Prüfwerte der Bundesverwaltung (Steuerjahr 2025, Botschaft BBl 2025 1092), auf die 1'770'250 Ehepaare 2022 skaliert.
SKALA = EHEPAARE_2022 / 1_766_032
ZIEL_ZWEIVERDIENER = 854_282 * SKALA
ZIEL_MEHR, ZIEL_MINDER = 670_000 * SKALA, 650_000 * SKALA


GITTER = {"rentner_anteil_hoeher_mittel": (0.6, 0.7, 0.8), "lohnverhaeltnis_median": (0.5, 0.7, 0.9),
          "lohnverhaeltnis_streuung": (0.6, 1.0, 1.4, 1.8)}
PASSEND = 60_000  # Abstand zu den Prüfwerten (Mehr- und Minderbelastung zusammen), bis zu dem eine Einstellung als passend gilt


def eichen(a: Annahmen, n: int = 40_000) -> tuple[Annahmen, pd.DataFrame]:
    """Eichung in zwei Schritten.

    1) Einverdiener-Zusatz so, dass die Zahl der Paare mit Zweiverdienerabzug stimmt (Halbierungsverfahren).
    2) Gitter über die drei unsichersten Annahmen (Rentenaufteilung, Lohnverhältnis, Lohnstreuung); jede
       Einstellung wird an der Zahl der Paare mit Mehr- und Minderbelastung von mindestens 10 % gemessen.
    Zurück kommen die beste Einstellung und alle Gitterpunkte; die passenden (Abstand < PASSEND) ergeben
    die Unsicherheitsspanne der Ergebnisse.
    """
    probe = replace(a, n=n)
    lo, hi = 0.0, 0.6
    for _ in range(14):
        mitte = (lo + hi) / 2
        if modell_zweiverdiener(replace(probe, einverdiener_zusatz=mitte)) > ZIEL_ZWEIVERDIENER:
            lo = mitte
        else:
            hi = mitte
    probe = replace(probe, einverdiener_zusatz=round((lo + hi) / 2, 4))
    zeilen = []
    for rm in GITTER["rentner_anteil_hoeher_mittel"]:
        for med in GITTER["lohnverhaeltnis_median"]:
            for s in GITTER["lohnverhaeltnis_streuung"]:
                einstellung = replace(probe, rentner_anteil_hoeher_mittel=rm, lohnverhaeltnis_median=med, lohnverhaeltnis_streuung=s)
                k = kennzahlen(steuern(simulieren(einstellung)))
                abstand = ((k["mehrbelastung_10_tsd"] * 1e3 - ZIEL_MEHR) ** 2 + (k["minderbelastung_10_tsd"] * 1e3 - ZIEL_MINDER) ** 2) ** 0.5
                zeilen.append({"rentner_anteil_hoeher_mittel": rm, "lohnverhaeltnis_median": med,
                               "lohnverhaeltnis_streuung": s, "abstand_tsd": round(abstand / 1e3), **k})
                print(f"  rente {rm} lohn {med} streuung {s}: mehr {k['mehrbelastung_10_tsd']} minder {k['minderbelastung_10_tsd']}"
                      f" abstand {abstand/1e3:.0f}", flush=True)
    gitter = pd.DataFrame(zeilen).sort_values("abstand_tsd")
    beste = gitter.iloc[0]
    geeicht = replace(a, einverdiener_zusatz=probe.einverdiener_zusatz,
                      rentner_anteil_hoeher_mittel=float(beste.rentner_anteil_hoeher_mittel),
                      lohnverhaeltnis_median=float(beste.lohnverhaeltnis_median),
                      lohnverhaeltnis_streuung=float(beste.lohnverhaeltnis_streuung))
    return geeicht, gitter


def modell_zweiverdiener(a: Annahmen) -> float:
    d = simulieren(a)
    return float(d.gewicht[d.zweiverdiener].sum())


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    AUSGABE.mkdir(exist_ok=True)
    a, gitter = eichen(Annahmen())
    gitter.to_csv(AUSGABE / "eichung_gitter.csv", index=False)
    print("geeicht:", a, flush=True)
    pu, py = perzentile()
    probe = quantil((np.arange(400_000) + 0.5) / 400_000, pu, py)
    print(f"Mittel steuerbar Modell {probe.mean():,.0f} vs ESTV {MITTEL_STEUERBAR_2022:,.0f}")
    d = steuern(simulieren(a))
    k = kennzahlen(d)
    passend = gitter[gitter.abstand_tsd < PASSEND / 1e3]
    spanne = {c: [float(passend[c].min()), float(passend[c].max())] for c in k}
    print(json.dumps(k, indent=1)); print("Spanne passender Einstellungen:", json.dumps(spanne))
    d.to_parquet(AUSGABE / "simulation.parquet")
    (AUSGABE / "modell_kennzahlen.json").write_text(json.dumps(
        {"annahmen": a.__dict__, "kennzahlen": k, "passende_einstellungen": len(passend), "spanne": spanne,
         "alpha": round(pareto_alpha(pu, py), 3), "mittel_steuerbar_modell": round(float(probe.mean())),
         "pruefwerte": {"zweiverdiener": ZIEL_ZWEIVERDIENER, "mehrbelastung": ZIEL_MEHR, "minderbelastung": ZIEL_MINDER,
                        "steuer_ehepaare_2022_mrd": STEUER_EHEPAARE_2022 / 1e9,
                        "kosten_botschaft_mrd": [0.7, 1.4]}}, indent=1, default=str), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
