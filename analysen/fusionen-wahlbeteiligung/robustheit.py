"""Robustheitsprüfungen für beide Reihen (Wahlen, Abstimmungen), wie sie ein Gutachten verlangen würde.

Jede Prüfung ändert genau eine Annahme der Hauptschätzung und schätzt die Wirkung nach der
Fusion neu (Gardner, zweistufig; Bootstrap-Standardfehler). Schreibt `ausgabe/robustheit.json`.

1. bezirk_termin: Vergleich nur mit Gemeinden desselben Bezirks am selben Termin.
2. cluster_bezirk: Standardfehler mit ganzen Bezirken als Cluster.
3. eine_fusion: nur Fusionsgemeinden mit genau einer Fusion.
4. ausgewogen: nur Fusionsgemeinden, die in jeder Ereigniszeit des Kernfensters beobachtet sind.
5. placebo: erfundene Fusion 4 Jahre (2 Wahlen) zu früh, nur Beobachtungen vor der echten Fusion.
6. vortrend_linear: Ereigniszeit-Schätzungen abzüglich eines linear fortgeschriebenen Vortrends.
7. gestapelt: Stacked DiD (Cengiz et al. 2019) als anderer Schätzer, Abstimmungen je Jahr.
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd
import pyfixest as pf

import analyse
import analyse_abstimmungen
import gardner
from analyse import AUSGABE, bereinigen

ZIEHUNGEN = 100


def wirkung(p: pd.DataFrame, cluster: str = "gemeinde_hstnr") -> dict:
    tab = gardner.schaetzen(p, ziehungen=ZIEHUNGEN, cluster=cluster)
    r = {k: round(float(v), 2) for k, v in tab.loc["alle"].items()}
    return r | {"gemeinden": int(p.loc[p["fusion_datum"].notna(), "gemeinde_hstnr"].nunique())}


def mit_bezirk(p: pd.DataFrame, termin: str) -> pd.DataFrame:
    q = p.copy()
    q["bezirk_id"] = q["kanton"] + "_" + q["bezirk"].fillna("ohne")
    q["kantonjahr"] = q["bezirk_id"] + "_" + q[termin].astype(str)
    return bereinigen(q)


def placebo_wahlen(p: pd.DataFrame) -> pd.DataFrame:
    q = p[p["behandelt"] == 0].copy()
    falsch = q["fusion_wahl"] - 8
    q["behandelt"] = (q["fusion_wahl"].notna() & (q["jahr"] >= falsch)).astype(int)
    q["rel"] = ((q["jahr"] - falsch) / 4).clip(analyse.VOR, analyse.NACH).fillna(-1).astype(int)
    return bereinigen(q)


def placebo_abstimmungen(p: pd.DataFrame) -> pd.DataFrame:
    q = p[p["behandelt"] == 0].copy()
    falsch = q["fusion_datum"] - pd.DateOffset(years=4)
    q["behandelt"] = (q["fusion_datum"].notna() & (q["tag"] > falsch)).astype(int)
    q["rel"] = np.floor((q["tag"] - falsch).dt.days / 365.25).clip(
        analyse_abstimmungen.VOR, analyse_abstimmungen.NACH).fillna(-1).astype(int)
    return bereinigen(q)


def ausgewogen(p: pd.DataFrame, fenster: range) -> pd.DataFrame:
    beh = p[p["fusion_datum"].notna() & p["rel"].isin(list(fenster))]
    voll = beh.groupby("gemeinde_hstnr")["rel"].nunique().loc[lambda s: s == len(fenster)].index
    return bereinigen(p[p["fusion_datum"].isna() | p["gemeinde_hstnr"].isin(voll)])


def vortrend_linear(datei: str, von: int, bis: int) -> dict:
    """Linearer Trend durch die Vorperioden von..-1 (Referenz -1 = 0), fortgeschrieben auf die Nachperioden."""
    es = pd.read_csv(AUSGABE / datei)
    vor = es[es["rel"].between(von, -1)]
    steigung, achse = np.polyfit(vor["rel"], vor["schaetzung"], 1)
    nach = es[es["rel"].between(0, bis)].copy()
    nach["bereinigt"] = nach["schaetzung"] - (achse + steigung * nach["rel"])
    return {"steigung_je_periode": round(float(steigung), 3), "wirkung_roh": round(float(nach["schaetzung"].mean()), 2),
            "wirkung_ohne_vortrend": round(float(nach["bereinigt"].mean()), 2), "perioden": f"{von}..{bis}"}


def gestapelt(p: pd.DataFrame, fenster: int = 5) -> dict:
    """Stacked DiD auf Gemeinde × Jahr: je Fusionsjahr ein Stapel mit sauberen Kontrollen."""
    j = p.assign(jahr=p["tag"].dt.year).groupby(["gemeinde_hstnr", "jahr"], as_index=False).agg(
        beteiligung=("beteiligung", "mean"), kanton_tag=("kanton_tag", "first"), fusion_datum=("fusion_datum", "first"))
    erstes = p[p["behandelt"] == 1].groupby("gemeinde_hstnr")["tag"].min().dt.year
    j["start"] = j["gemeinde_hstnr"].map(erstes)
    stapel = []
    for kohorte in sorted(erstes.unique()):
        jahre = range(kohorte - fenster, kohorte + fenster + 1)
        teil = j[j["jahr"].isin(jahre)]
        # Kontrollen: nie fusioniert oder erst nach dem Fenster behandelt (im Fenster unbehandelt).
        sauber = teil["start"].isna() | (teil["start"] > kohorte + fenster)
        teil = teil[(teil["start"] == kohorte) | sauber].copy()
        if (teil["start"] == kohorte).sum() == 0:
            continue
        teil["stapel"] = kohorte
        teil["beh"] = (teil["start"] == kohorte).astype(int)
        teil["rel"] = np.where(teil["beh"] == 1, teil["jahr"] - kohorte, -1)
        stapel.append(teil)
    s = pd.concat(stapel, ignore_index=True)
    s["einheit"] = s["gemeinde_hstnr"] + "_" + s["stapel"].astype(str)
    s["kantonjahr"] = s["kanton_tag"] + "_" + s["jahr"].astype(str) + "_" + s["stapel"].astype(str)
    s["nach"] = ((s["beh"] == 1) & (s["rel"] >= 0)).astype(int)
    fit = pf.feols("beteiligung ~ nach | einheit + kantonjahr", data=s, vcov={"CRV1": "gemeinde_hstnr"})
    r = fit.tidy().loc["nach"]
    es = pf.feols("beteiligung ~ i(rel, ref=-1) | einheit + kantonjahr", data=s, vcov={"CRV1": "gemeinde_hstnr"}).tidy()
    return {"schaetzung": round(float(r["Estimate"]), 2), "se": round(float(r["Std. Error"]), 2),
            "unten": round(float(r["2.5%"]), 2), "oben": round(float(r["97.5%"]), 2),
            "gemeinden": int(s.loc[s["beh"] == 1, "gemeinde_hstnr"].nunique()), "stapel": int(s["stapel"].nunique()),
            "zeilen": len(s), "fenster_jahre": fenster,
            "ereigniszeit": {str(k): round(float(v), 2) for k, v in
                             zip(es.index.astype(str).str.extract(r"(-?\d+)\]?$")[0], es["Estimate"])}}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    aus: dict = {"ziehungen": ZIEHUNGEN}
    reihen = {"wahlen": (analyse.laden(), "jahr", placebo_wahlen, range(-2, 3)),
              "abstimmungen": (analyse_abstimmungen.laden(), "tag", placebo_abstimmungen, range(-4, 5))}
    for name, (p, termin, placebo, fenster) in reihen.items():
        r = {}
        r["haupt"] = wirkung(p)
        r["bezirk_termin"] = wirkung(mit_bezirk(p, termin))
        q = p.assign(bezirk_id=p["kanton"] + "_" + p["bezirk"].fillna("ohne"))
        r["cluster_bezirk"] = wirkung(q, cluster="bezirk_id")
        r["eine_fusion"] = wirkung(bereinigen(p[p["fusion_datum"].isna() | (p["fusionen"] == 1)]))
        r["ausgewogen"] = wirkung(ausgewogen(p, fenster)) | {"fenster": f"{fenster.start}..{fenster.stop - 1}"}
        r["placebo"] = wirkung(placebo(p))
        aus[name] = r
        print(name, json.dumps(r, ensure_ascii=False), flush=True)
    aus["wahlen"]["vortrend_linear"] = vortrend_linear("ereignisstudie_did2s.csv", -4, 4)
    aus["abstimmungen"]["vortrend_linear"] = vortrend_linear("ereignisstudie_abstimmungen_did2s.csv", -7, 8)
    aus["abstimmungen"]["gestapelt"] = gestapelt(reihen["abstimmungen"][0])
    (AUSGABE / "robustheit.json").write_text(json.dumps(aus, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(aus, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
