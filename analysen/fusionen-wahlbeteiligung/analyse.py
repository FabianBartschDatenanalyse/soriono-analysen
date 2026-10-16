"""Wirkung von Gemeindefusionen auf die Beteiligung an Nationalratswahlen.

Liest `ausgabe/panel.csv` (aus `daten.py`) und schreibt Schätzungen und Grafiken
nach `ausgabe/`.

Design: gestaffelte Differenz-in-Differenzen. Verglichen wird jede Fusionsgemeinde
mit noch nicht oder nie fusionierten Gemeinden desselben Kantons in derselben
Wahl (feste Effekte Gemeinde und Kanton × Wahljahr). Hauptschätzer ist das
zweistufige Verfahren von Gardner (2022, `did2s`), das bei gestaffelter Einführung
keine bereits behandelten Gemeinden als Vergleich verwendet; TWFE zum Vergleich.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pyfixest as pf

HIER = Path(__file__).resolve().parent
AUSGABE = HIER / "ausgabe"
VOR, NACH = -5, 4  # Ereignisfenster in Wahlen; Ränder gebündelt


def laden() -> pd.DataFrame:
    p = pd.read_csv(AUSGABE / "panel.csv", dtype={"bfs_nr": str, "gemeinde_hstnr": str})
    p = p[(p["abtausch"] == 0) & (p["kanton_wahl"] != "BE*")].dropna(subset=["beteiligung"]).copy()
    p["kantonjahr"] = p["kanton_wahl"] + "_" + p["jahr"].astype(str)
    p["behandelt"] = (p["fusion_wahl"].notna() & (p["jahr"] >= p["fusion_wahl"])).astype(int)
    rel = (p["jahr"] - p["fusion_wahl"]) / 4
    p["rel"] = rel.clip(VOR, NACH).fillna(-1).astype(int)  # nie fusioniert: Referenz
    # Grösse vor der Fusion: Wahlberechtigte bei der letzten Wahl davor (gleiches Gebiet).
    vorher = p[p["jahr"] == p["fusion_wahl"] - 4].set_index("gemeinde_hstnr")["wahlberechtigte"]
    p["berechtigte_vorher"] = p["gemeinde_hstnr"].map(vorher)
    return bereinigen(p)


def bereinigen(p: pd.DataFrame) -> pd.DataFrame:
    # Die erste Stufe schätzt die festen Effekte nur aus unbehandelten Beobachtungen:
    # jede Gemeinde und jede Kanton-Wahl-Zelle braucht mindestens zwei davon.
    while True:
        unbeh = p[p["behandelt"] == 0]
        ok_g = unbeh.groupby("gemeinde_hstnr").size().loc[lambda s: s >= 2].index
        ok_k = unbeh.groupby("kantonjahr").size().loc[lambda s: s >= 2].index
        neu = p[p["gemeinde_hstnr"].isin(ok_g) & p["kantonjahr"].isin(ok_k)]  # kantonjahr: Kanton × Wahl oder Tag
        if len(neu) == len(p):
            return p
        p = neu.copy()


def laden_ohne(p: pd.DataFrame, kanton: str) -> pd.DataFrame:
    return p[p["kanton"] != kanton]


def ereignisstudie(p: pd.DataFrame, schaetzer: str, gewichte: str | None = None) -> pd.DataFrame:
    if schaetzer == "did2s":
        fit = pf.did2s(
            p, yname="beteiligung", first_stage="~ 0 | gemeinde_hstnr + kantonjahr",
            second_stage=f"~ i(rel, ref={-1})", treatment="behandelt",
            cluster="gemeinde_hstnr",
        )
    else:
        fit = pf.feols(
            f"beteiligung ~ i(rel, ref={-1}) | gemeinde_hstnr + kantonjahr", data=p,
            vcov={"CRV1": "gemeinde_hstnr"}, weights=gewichte,
        )
    t = fit.tidy().reset_index()
    t["rel"] = t["Coefficient"].astype(str).str.extract(r"(-?\d+)\]?$")[0].astype(int)
    t = t[["rel", "Estimate", "Std. Error", "2.5%", "97.5%"]]
    t.columns = ["rel", "schaetzung", "se", "unten", "oben"]
    ref = pd.DataFrame([{"rel": -1, "schaetzung": 0.0, "se": 0.0, "unten": 0.0, "oben": 0.0}])
    return pd.concat([t, ref]).sort_values("rel").reset_index(drop=True)


def did2s_fit(d: pd.DataFrame, zweite_stufe: str):
    return pf.did2s(
        d, yname="beteiligung", first_stage="~ 0 | gemeinde_hstnr + kantonjahr",
        second_stage=zweite_stufe, treatment="behandelt", cluster="gemeinde_hstnr",
    )


def zeile(r: pd.Series) -> dict:
    return {k: round(float(r[s]), 2) for k, s in
            (("schaetzung", "Estimate"), ("se", "Std. Error"), ("unten", "2.5%"), ("oben", "97.5%"))}


def gesamt(d: pd.DataFrame) -> dict:
    """Durchschnittliche Wirkung in allen Wahlen nach der Fusion (did2s)."""
    r = zeile(did2s_fit(d, "~ behandelt").tidy().loc["behandelt"])
    r["gemeinden"] = int(d.loc[d["fusion_datum"].notna(), "gemeinde_hstnr"].nunique())
    return r


def nach_gruppe(d: pd.DataFrame, gruppe: pd.Series) -> dict:
    """Wirkung je Gruppe der Fusionsgemeinden in einem Modell (gemeinsame erste Stufe)."""
    d = d.copy()
    d["gruppe"] = np.where(d["behandelt"] == 1, d["gemeinde_hstnr"].map(gruppe).fillna("unbekannt"), "keine")
    tab = did2s_fit(d, "~ i(gruppe, ref='keine')").tidy()
    aus = {}
    for name in sorted(set(gruppe.dropna())):
        treffer = [i for i in tab.index if str(i).endswith(f"::{name}") or str(i).endswith(f"[T.{name}]")]
        if treffer:
            aus[name] = zeile(tab.loc[treffer[0]]) | {"gemeinden": int((gruppe == name).sum())}
    return aus


def grafik(reihen: dict[str, pd.DataFrame], datei: str, titel: str, vor: int = VOR, nach: int = NACH,
           x_text: str = "Wahlen relativ zur ersten Wahl nach der Fusion (0)",
           y_text: str = "Wahlbeteiligung, Prozentpunkte") -> None:
    fig, ax = plt.subplots(figsize=(7.5, 4.2), dpi=150)
    versatz = np.linspace(-0.12, 0.12, len(reihen))
    farben = ["#2a5d9f", "#b5651d", "#5b8c5a"]
    for (name, t), dx, farbe in zip(reihen.items(), versatz, farben):
        ax.errorbar(t["rel"] + dx, t["schaetzung"], yerr=[t["schaetzung"] - t["unten"], t["oben"] - t["schaetzung"]],
                    fmt="o", ms=4, capsize=2, color=farbe, label=name)
    ax.axhline(0, color="#888", lw=0.8)
    ax.axvline(-0.5, color="#888", lw=0.8, ls="--")
    ax.set_xticks(range(vor, nach + 1))
    ax.set_xticklabels([f"≤{vor}" if r == vor else (f"≥{nach}" if r == nach else str(r)) for r in range(vor, nach + 1)])
    ax.set_xlabel(x_text)
    ax.set_ylabel(y_text)
    ax.set_title(titel, fontsize=10)
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(AUSGABE / datei)
    plt.close(fig)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = laden()
    behandelte = p[p["fusion_wahl"].notna()].drop_duplicates("gemeinde_hstnr")
    print(f"{len(p)} Beobachtungen, {p['gemeinde_hstnr'].nunique()} Gemeinden, {len(behandelte)} mit Fusion")

    es_did2s = ereignisstudie(p, "did2s")
    es_twfe = ereignisstudie(p, "twfe")
    es_gew = ereignisstudie(p, "twfe", gewichte="wahlberechtigte")
    grafik({"Gardner (did2s)": es_did2s, "TWFE": es_twfe, "TWFE, gewichtet": es_gew},
           "ereignisstudie.png", "Wahlbeteiligung vor und nach der ersten Fusion")

    b = behandelte.set_index("gemeinde_hstnr")
    ergebnisse: dict = {"alle": gesamt(p)}
    ergebnisse["vorher_beteiligung_mittel"] = round(float(
        p.loc[p["rel"].eq(-1) & p["fusion_wahl"].notna(), "beteiligung"].mean()), 1)
    ergebnisse["groesse"] = nach_gruppe(p, pd.cut(
        b["berechtigte_vorher"], [0, 1000, 5000, np.inf], right=False,
        labels=["a_unter_1000", "b_1000_bis_4999", "c_ab_5000"]).astype(str).replace("nan", np.nan))
    ergebnisse["anteil_aufgegangen"] = nach_gruppe(p, pd.cut(
        b["anteil_aufgegangen"], [0, 0.2, 0.4, 1.01], right=False,
        labels=["a_unter_20_prozent", "b_20_bis_39_prozent", "c_ab_40_prozent"]).astype(str).replace("nan", np.nan))
    ergebnisse["zeitraum"] = nach_gruppe(p, pd.Series(
        np.where(b["fusion_wahl"] >= 2003, "b_ab_2001", "a_bis_2000"), index=b.index))
    # Robustheit: jeden Kanton einmal weglassen; Gewichtung mit Wahlberechtigten (TWFE).
    ohne = {}
    for kanton in sorted(behandelte["kanton"].unique()):
        if (behandelte["kanton"] == kanton).sum() >= 10:
            ohne[kanton] = gesamt(laden_ohne(p, kanton))
    ergebnisse["ohne_kanton"] = ohne

    for name, t in (("did2s", es_did2s), ("twfe", es_twfe), ("twfe_gewichtet", es_gew)):
        t.round(3).to_csv(AUSGABE / f"ereignisstudie_{name}.csv", index=False)
    (AUSGABE / "ergebnisse.json").write_text(json.dumps(ergebnisse, indent=1, ensure_ascii=False), encoding="utf-8")
    print(es_did2s.round(2).to_string(index=False))
    print(json.dumps(ergebnisse, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
