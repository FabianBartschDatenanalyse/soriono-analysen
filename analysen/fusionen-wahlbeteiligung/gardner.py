"""Zweistufige Differenz-in-Differenzen nach Gardner (2022), speicherschonend.

`pyfixest.did2s` bildet für die Standardfehler eine dichte Matrix aller festen
Effekte; bei 370'000 Abstimmungsbeobachtungen wären das 18 GB. Hier dieselben
Punktschätzungen in zwei Schritten:

1. Feste Effekte Gemeinde und Kanton × Termin nur aus unbehandelten Beobachtungen.
2. Bereinigte Beteiligung (beobachtet minus vorhergesagt). Die Wirkung ist ihr
   Mittel über die behandelten Beobachtungen (je Ereigniszeit, Gruppe oder gesamt);
   in den unbehandelten ist ihr Mittel durch Stufe 1 genau 0.

Standardfehler: Cluster-Bootstrap über Gemeinden oder gröbere Cluster wie Bezirke (beide Stufen neu geschätzt).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pyfixest as pf

from analyse import bereinigen


def bereinigt(p: pd.DataFrame) -> pd.Series:
    erste = pf.feols("beteiligung ~ 1 | gemeinde_hstnr + kantonjahr", data=p[p["behandelt"] == 0])
    vorhergesagt = erste.predict(newdata=p)
    rest = p["beteiligung"].to_numpy() - np.asarray(vorhergesagt)
    if np.isnan(rest).any():
        raise ValueError(f"{int(np.isnan(rest).sum())} Beobachtungen ohne geschätzte feste Effekte")
    return pd.Series(rest, index=p.index)


def kennzahlen(p: pd.DataFrame, rest: pd.Series, gruppen: dict[str, pd.Series]) -> dict[str, float]:
    """Alle Schätzungen aus einer bereinigten Beteiligung: Ereigniszeit, gesamt und je Gruppe."""
    aus = {}
    ref = rest[p["rel"] == -1].mean()
    for k, wert in rest.groupby(p["rel"]).mean().items():
        if k != -1:
            aus[f"rel:{k}"] = wert - ref
    beh = p["behandelt"] == 1
    aus["alle"] = rest[beh].mean()
    for name, gruppe in gruppen.items():
        g = p["gemeinde_hstnr"].map(gruppe)
        for wert, mittel in rest[beh].groupby(g[beh]).mean().items():
            aus[f"{name}:{wert}"] = mittel
    return aus


def schaetzen(p: pd.DataFrame, gruppen: dict[str, pd.Series] | None = None, ziehungen: int = 200,
              seed: int = 1, cluster: str = "gemeinde_hstnr") -> pd.DataFrame:
    """Punktschätzungen und Bootstrap-Standardfehler; gezogen werden ganze Cluster (Standard: Gemeinden)."""
    gruppen = gruppen or {}
    punkt = kennzahlen(p, bereinigt(p), gruppen)
    ids = p[cluster].unique()
    zeilen_je = p.groupby(cluster).indices
    rng = np.random.default_rng(seed)
    proben = []
    for _ in range(ziehungen):
        gezogen = rng.choice(ids, size=len(ids), replace=True)
        idx = np.concatenate([zeilen_je[c] for c in gezogen])
        kopie = np.concatenate([[i] * len(zeilen_je[c]) for i, c in enumerate(gezogen)])
        neu = p.iloc[idx].copy()
        alt = neu["gemeinde_hstnr"].to_numpy()
        # Eine mehrfach gezogene Gemeinde zählt als eigene Einheit (eigener fester Effekt).
        neue_ids = pd.Series(alt).astype(str).str.cat(pd.Series(kopie).astype(str), sep="_").to_numpy()
        neu["gemeinde_hstnr"] = neue_ids
        zuordnung = pd.Series(alt, index=neue_ids).groupby(level=0).first()
        g2 = {k: pd.Series(v.reindex(zuordnung.to_numpy()).to_numpy(), index=zuordnung.index) for k, v in gruppen.items()}
        # Wie die Hauptstichprobe: jede Gemeinde und Zelle mit mindestens zwei unbehandelten Beobachtungen.
        neu = bereinigen(neu).reset_index(drop=True)
        proben.append(kennzahlen(neu, bereinigt(neu), g2))
    boot = pd.DataFrame(proben)
    tab = pd.DataFrame({"schaetzung": pd.Series(punkt), "se": boot.std()})
    tab["unten"] = tab["schaetzung"] - 1.96 * tab["se"]
    tab["oben"] = tab["schaetzung"] + 1.96 * tab["se"]
    tab.attrs["ziehungen"] = len(boot)
    return tab
