"""Einbürgerungsquote und lokales Abstimmungsklima vor und nach dem Bürgerrechtsgesetz 2018.

Hauptmodell (Differenz der Differenzen mit stetiger Behandlung):

    quote_gt = a_g + d_{Kanton × Jahr} + b · klima_g · nach_t + e_gt

klima_g = Ja-Anteil zur Masseneinwanderungsinitiative 2014 in 10 Prozentpunkten (vor dem Gesetz
gemessen), nach_t = Jahr ab 2018. Gemeinde-Effekte nehmen alles Dauerhafte jeder Gemeinde auf,
Kanton × Jahr alles, was ein Kanton in einem Jahr anders macht (Gesetz, Verfahren, Gebühren).
b misst also, um wie viel sich die Quote in Gemeinden mit höherem Ja-Anteil ab 2018 stärker
verändert hat als in Gemeinden desselben Kantons mit tieferem Ja-Anteil. Gewichte: ausländische
Wohnbevölkerung; Standardfehler nach Kanton geklumpt.

Schreibt nach `ausgabe/`: ergebnisse.json, ereignis.csv, gruppen.csv, robustheit.csv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pyfixest as pf

HIER = Path(__file__).resolve().parent
AUSGABE = HIER / "ausgabe"
MINDEST_AUSLAENDER = 50  # ausländische Wohnbevölkerung Ende 2016
GESETZ = 2018
REFERENZ = 2016  # letztes Jahr vor dem Ansturm auf das alte Recht 2017


def laden() -> pd.DataFrame:
    panel = pd.read_parquet(AUSGABE / "panel.parquet")
    gemeinden = pd.read_parquet(AUSGABE / "gemeinden.parquet")
    gemeinden = gemeinden[gemeinden["auslaender_2016"] >= MINDEST_AUSLAENDER]
    d = panel.merge(gemeinden, on="hstnr", how="inner")
    d["klima"] = d["masseneinwanderung_2014"] * 10  # in 10 Prozentpunkten
    d["nach"] = (d["jahr"] >= GESETZ).astype(int)
    d["kanton_jahr"] = d["kanton"] + "_" + d["jahr"].astype(str)
    for n in ("eu_efta", "uebriges_europa", "ausserhalb_europas"):
        d[f"quote_{n}"] = d[f"einb_{n}"] / d["auslaender_vorjahr"] * 100
    return d


def schaetzen(d: pd.DataFrame, formel: str, *, gewichtet: bool = True, cluster: str = "kanton", term: str = "klima:nach") -> dict:
    m = pf.feols(formel, data=d, weights="auslaender_vorjahr" if gewichtet else None, vcov={"CRV1": cluster})
    t = m.tidy().loc[term]
    return {"schaetzung": float(t["Estimate"]), "se": float(t["Std. Error"]),
            "unten": float(t["2.5%"]), "oben": float(t["97.5%"]), "n": int(m._N)}


def mittel(d: pd.DataFrame, spalte: str = "einbuergerungen") -> float:
    return float(d[spalte].sum() / d["auslaender_vorjahr"].sum() * 100)


def ereignisstudie(d: pd.DataFrame) -> pd.DataFrame:
    m = pf.feols(f"quote ~ i(jahr, klima, ref={REFERENZ}) | hstnr + kanton_jahr", data=d,
                 weights="auslaender_vorjahr", vcov={"CRV1": "kanton"})
    t = m.tidy()
    t = t[t.index.str.startswith("jahr::")]
    out = pd.DataFrame({"jahr": [int(i.split("::")[1].split(":")[0]) for i in t.index], "schaetzung": t["Estimate"].values,
                        "unten": t["2.5%"].values, "oben": t["97.5%"].values})
    out = pd.concat([out, pd.DataFrame([{"jahr": REFERENZ, "schaetzung": 0.0, "unten": 0.0, "oben": 0.0}])])
    return out.sort_values("jahr").reset_index(drop=True)


def gruppen(d: pd.DataFrame) -> pd.DataFrame:
    """Quote je Fünftel des Ja-Anteils 2014, gewichtet mit der ausländischen Bevölkerung; Fünftel innerhalb der Kantone."""
    g = d[d["jahr"] == REFERENZ][["hstnr", "kanton", "klima", "auslaender_vorjahr"]].copy()
    # Rang innerhalb des Kantons, damit jedes Fünftel Gemeinden aller Kantone enthält.
    g["rang"] = g.groupby("kanton")["klima"].rank(pct=True, method="average")
    g["fuenftel"] = np.minimum((g["rang"] * 5).apply(np.ceil).astype(int), 5)
    d = d.merge(g[["hstnr", "fuenftel"]], on="hstnr")
    t = d.groupby(["fuenftel", "jahr"]).apply(lambda x: pd.Series({
        "quote": mittel(x), "ja_2014": np.average(x["klima"] * 10, weights=x["auslaender_vorjahr"]),
        "gemeinden": x["hstnr"].nunique()}), include_groups=False).reset_index()
    vorher = t[t["jahr"] < 2017].groupby("fuenftel")["quote"].mean().rename("quote_vorher")
    t = t.merge(vorher, on="fuenftel")
    t["index"] = t["quote"] / t["quote_vorher"] * 100
    return t


def fehlende(d: pd.DataFrame, b: float) -> dict:
    """Einbürgerungen ab 2018, die bei der Kluft von vor 2018 zusätzlich (oder weniger) zu erwarten gewesen wären."""
    n = d[d["nach"] == 1]
    mitte = np.average(n["klima"], weights=n["auslaender_vorjahr"])
    wirkung = b * (n["klima"] - mitte) * n["auslaender_vorjahr"] / 100  # Abweichung in Personen
    ueber = n["klima"] > mitte
    return {"klima_mitte_ja_prozent": float(mitte * 10),
            "weniger_ueber_mitte": float(-wirkung[ueber].sum()), "mehr_unter_mitte": float(wirkung[~ueber].sum()),
            "einbuergerungen_ueber_mitte": float(n.loc[ueber, "einbuergerungen"].sum()),
            "jahre": f"{GESETZ}–{int(n['jahr'].max())}"}


def robustheit(d: pd.DataFrame) -> pd.DataFrame:
    basis = "quote ~ klima:nach | hstnr + kanton_jahr"
    z = []

    def zeile(name, hinweis, r):
        z.append({"name": name, "hinweis": hinweis, **r})

    zeile("Hauptschätzung", "Gemeinde und Kanton × Jahr", schaetzen(d, basis))
    zeile("Unsicherheit je Bezirk", "geklumpt nach Bezirk", schaetzen(d, basis, cluster="bezirk"))
    zeile("Ungewichtet", "jede Gemeinde gleich", schaetzen(d, basis, gewichtet=False))
    zeile("Ohne 2017 und 2018", "Ansturm auf das alte Recht", schaetzen(d[~d["jahr"].isin([2017, 2018])], basis))
    zeile("Ab 200 Ausländerinnen und Ausländern", "grössere Gemeinden", schaetzen(d[d["auslaender_2016"] >= 200], basis))
    k = d.copy()
    for spalte in ("neu_zugewandert_2016", "auslaenderanteil_2016"):
        k[spalte + "_n"] = k[spalte] * k["nach"]
    k["einkommen_n"] = np.log(k["einkommen_2016"]) * k["nach"]
    k["groesse_n"] = np.log(k["einwohner_2016"]) * k["nach"]
    wellen = [f"welle_{a}_{b}" for a, b in ((1996, 2000), (2001, 2005), (2006, 2010), (2011, 2016))]
    for w in wellen:
        k[w + "_n"] = k[w] * k["nach"]
    zeile("Einwanderungswellen", "Einwanderung 1996–2016 in vier Wellen, je × ab 2018",
          schaetzen(k, "quote ~ klima:nach + " + " + ".join(w + "_n" for w in wellen) + " | hstnr + kanton_jahr"))
    zeile("Wohlstand und Grösse", "Einkommen 2016, Einwohner, Ausländeranteil, je × ab 2018",
          schaetzen(k.dropna(subset=["einkommen_n"]), "quote ~ klima:nach + auslaenderanteil_2016_n + einkommen_n + groesse_n | hstnr + kanton_jahr"))
    zeile("Alle Kontrollen", "Wellen, Einkommen, Grösse, Ausländeranteil",
          schaetzen(k.dropna(subset=["einkommen_n"]), "quote ~ klima:nach + auslaenderanteil_2016_n + einkommen_n + groesse_n + "
                    + " + ".join(w + "_n" for w in wellen) + " | hstnr + kanton_jahr"))
    for spalte, name in (("demokratische_einbuergerungen_2008", "Klima: Einbürgerungsinitiative 2008"),
                         ("klima_index", "Klima: Mittel der vier Vorlagen 2014–2026"),
                         ("zehn_millionen_2026", "Klima: 10-Millionen-Initiative 2026")):
        k2 = d.copy()
        k2["klima"] = k2[spalte] * 10
        zeile(name, "Ja-Anteil in 10 Prozentpunkten", schaetzen(k2.dropna(subset=["klima"]), basis))
    v = d[d["jahr"] <= 2017].copy()
    v["nach"] = (v["jahr"] >= 2015).astype(int)
    zeile("Placebo: Bruch 2015", "nur 2011–2017", schaetzen(v, basis))
    # Poisson mit der ausländischen Bevölkerung als Exposition: Wirkung als relative Änderung.
    p = d.copy()
    p["log_auslaender"] = np.log(p["auslaender_vorjahr"])
    m = pf.fepois("einbuergerungen ~ klima:nach | hstnr + kanton_jahr", data=p, offset="log_auslaender", vcov={"CRV1": "kanton"})
    t = m.tidy().loc["klima:nach"]
    zeile("Poisson (relative Wirkung)", "Änderung in Prozent je 10 Punkte Ja",
          {"schaetzung": float(np.expm1(t["Estimate"]) * 100), "se": float(t["Std. Error"] * 100),
           "unten": float(np.expm1(t["2.5%"]) * 100), "oben": float(np.expm1(t["97.5%"]) * 100), "n": int(m._N)})
    ohne = [schaetzen(d[d["kanton"] != k_], basis)["schaetzung"] for k_ in sorted(d["kanton"].unique())]
    zeile("Ohne je einen Kanton", "kleinste und grösste Schätzung", {"schaetzung": float(np.median(ohne)), "unten": float(min(ohne)),
                                                                   "oben": float(max(ohne)), "se": float("nan"), "n": 0})
    return pd.DataFrame(z)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    d = laden()
    vorher, nachher = d[d["jahr"] < 2017], d[d["nach"] == 1]
    haupt = schaetzen(d, "quote ~ klima:nach | hstnr + kanton_jahr")
    herkunft = {}
    for n in ("eu_efta", "uebriges_europa", "ausserhalb_europas"):
        r = schaetzen(d, f"quote_{n} ~ klima:nach | hstnr + kanton_jahr")
        r["mittel_vorher"] = mittel(vorher, f"einb_{n}")
        r["relativ_prozent"] = r["schaetzung"] / r["mittel_vorher"] * 100
        herkunft[n] = r
    ergebnisse = {
        "gemeinden": int(d["hstnr"].nunique()), "kantone": int(d["kanton"].nunique()),
        "gemeinde_jahre": int(len(d)), "einbuergerungen": int(d["einbuergerungen"].sum()),
        "anteil_einbuergerungen_schweiz": None,
        "quote_vorher": mittel(vorher), "quote_nachher": mittel(nachher),
        "ja_2014_p10": float(np.percentile(d.loc[d["jahr"] == REFERENZ, "klima"] * 10, 10)),
        "ja_2014_p90": float(np.percentile(d.loc[d["jahr"] == REFERENZ, "klima"] * 10, 90)),
        "haupt": haupt, "relativ_prozent": haupt["schaetzung"] / mittel(nachher) * 100,
        "herkunft": herkunft, "fehlende": fehlende(d, haupt["schaetzung"]),
    }
    p = pd.read_parquet(AUSGABE / "panel.parquet")
    ergebnisse["anteil_einbuergerungen_schweiz"] = float(d["einbuergerungen"].sum() / p["einbuergerungen"].sum())
    ereignis = ereignisstudie(d)
    vor = ereignis[ereignis["jahr"] < 2017]
    ergebnisse["ereignis_vorher_mittel"] = float(vor["schaetzung"].mean())
    ergebnisse["ereignis_nachher_mittel"] = float(ereignis.loc[ereignis["jahr"] >= GESETZ, "schaetzung"].mean())
    ereignis.to_csv(AUSGABE / "ereignis.csv", index=False)
    gruppen(d).to_csv(AUSGABE / "gruppen.csv", index=False)
    rob = robustheit(d)
    rob.to_csv(AUSGABE / "robustheit.csv", index=False)
    (AUSGABE / "ergebnisse.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ergebnisse, ensure_ascii=False, indent=1))
    print(ereignis.round(3).to_string())
    print(rob.round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
