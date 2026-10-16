"""Wirkung von Gemeindefusionen auf die Beteiligung an eidgenössischen Abstimmungen.

Gleiches Design wie `analyse.py` (Wahlen), aber je Abstimmungstag und mit `gardner.py`
(speicherschonend, Bootstrap-Standardfehler): feste Effekte für
Gemeinde und Kanton × Abstimmungstag, Ereigniszeit in Jahren seit der Fusion.
Liest `ausgabe/panel_abstimmungen.csv` (aus `daten_abstimmungen.py`).
"""

from __future__ import annotations

import json
import sys

import numpy as np
import pandas as pd

import gardner
from analyse import AUSGABE, bereinigen, ereignisstudie, grafik

VOR, NACH = -8, 8  # Jahre; Ränder gebündelt
ZIEHUNGEN = 200


def laden() -> pd.DataFrame:
    p = pd.read_csv(AUSGABE / "panel_abstimmungen.csv", dtype={"bfs_nr": str, "gemeinde_hstnr": str},
                    parse_dates=["tag", "fusion_datum"])
    # Moutier wechselte am Tag seiner Fusion (1.1.2026) den Kanton: nicht trennbar.
    p = p[(p["abtausch"] == 0) & (p["kanton_tag"] != "BE*") & (p["gemeinde"] != "Moutier")]
    p = p.dropna(subset=["beteiligung"]).copy()
    p["kantonjahr"] = p["kanton_tag"] + "_" + p["tag"].dt.strftime("%Y-%m-%d")
    p["behandelt"] = (p["fusion_datum"].notna() & (p["tag"] > p["fusion_datum"])).astype(int)
    jahre = np.floor((p["tag"] - p["fusion_datum"]).dt.days / 365.25)
    p["rel"] = jahre.clip(VOR, NACH).fillna(-1).astype(int)  # nie fusioniert: Referenz
    # Grösse vor der Fusion: Stimmberechtigte am letzten Abstimmungstag davor (gleiches Gebiet).
    davor = p[p["tag"] < p["fusion_datum"]].sort_values("tag").groupby("gemeinde_hstnr")["stimmberechtigte"].last()
    p["berechtigte_vorher"] = p["gemeinde_hstnr"].map(davor)
    return bereinigen(p)


def vorwegnahme(p: pd.DataFrame) -> dict:
    """Robustheit: das Jahr vor der Fusion nicht als Vergleich verwenden (Fusionswahlkampf).

    Die erste Stufe schätzt dann ohne Jahr -1; berichtet werden die Wirkung nach der Fusion,
    die Abweichung im Jahr -1 und die Wirkung gegenüber den Jahren -7 bis -4 (Punktschätzungen).
    """
    q = p.copy()
    nach = q["behandelt"] == 1
    q.loc[q["rel"].eq(-1) & q["fusion_datum"].notna(), "behandelt"] = 1
    q = bereinigen(q)
    nach = nach.reindex(q.index)
    rest = gardner.bereinigt(q)
    fus = q["fusion_datum"].notna()
    frueh = rest[fus & q["rel"].between(-7, -4)].mean()
    return {"wirkung": round(float(rest[nach].mean()), 2),
            "jahr_vorher": round(float(rest[fus & q["rel"].eq(-1)].mean()), 2),
            "wirkung_gegen_jahre_minus7_bis_minus4": round(float(rest[nach].mean() - frueh), 2)}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    p = laden()
    behandelte = p[p["fusion_datum"].notna()].drop_duplicates("gemeinde_hstnr")
    print(f"{len(p)} Beobachtungen, {p['gemeinde_hstnr'].nunique()} Gemeinden, "
          f"{p['tag'].nunique()} Abstimmungstage, {len(behandelte)} mit Fusion", flush=True)

    b = behandelte.set_index("gemeinde_hstnr")
    gruppen = {
        "groesse": pd.cut(b["berechtigte_vorher"], [0, 1000, 5000, np.inf], right=False,
                          labels=["a_unter_1000", "b_1000_bis_4999", "c_ab_5000"]).astype(str).replace("nan", np.nan),
        "anteil_aufgegangen": pd.cut(b["anteil_aufgegangen"], [0, 0.2, 0.4, 1.01], right=False,
                                     labels=["a_unter_20_prozent", "b_20_bis_39_prozent", "c_ab_40_prozent"]
                                     ).astype(str).replace("nan", np.nan),
        "zeitraum": pd.Series(np.where(b["fusion_datum"].dt.year >= 2001, "b_ab_2001", "a_bis_2000"), index=b.index),
    }
    tab = gardner.schaetzen(p, gruppen, ziehungen=ZIEHUNGEN)
    print(f"Bootstrap: {tab.attrs['ziehungen']} Ziehungen", flush=True)

    def eintrag(schluessel: str, anzahl: int | None = None) -> dict:
        r = {k: round(float(v), 2) for k, v in tab.loc[schluessel].items()}
        return r | ({"gemeinden": anzahl} if anzahl is not None else {})

    es_did2s = pd.DataFrame([{"rel": int(k.split(":")[1]), **eintrag(k)} for k in tab.index if k.startswith("rel:")]
                            + [{"rel": -1, "schaetzung": 0.0, "se": 0.0, "unten": 0.0, "oben": 0.0}]).sort_values("rel")
    es_twfe = ereignisstudie(p, "twfe")
    es_gew = ereignisstudie(p, "twfe", gewichte="stimmberechtigte")
    grafik({"Gardner (zweistufig)": es_did2s, "TWFE": es_twfe, "TWFE, gewichtet": es_gew},
           "ereignisstudie_abstimmungen.png", "Stimmbeteiligung vor und nach der ersten Fusion",
           vor=VOR, nach=NACH, x_text="Jahre seit der Fusion (0 = erstes Jahr danach)",
           y_text="Stimmbeteiligung, Prozentpunkte")

    ergebnisse: dict = {"alle": eintrag("alle", len(behandelte)), "ziehungen": tab.attrs["ziehungen"]}
    ergebnisse["vorher_beteiligung_mittel"] = round(float(
        p.loc[p["rel"].eq(-1) & p["fusion_datum"].notna(), "beteiligung"].mean()), 1)
    for name, gruppe in gruppen.items():
        ergebnisse[name] = {w: eintrag(f"{name}:{w}", int((gruppe == w).sum()))
                            for w in sorted(set(gruppe.dropna())) if f"{name}:{w}" in tab.index}
    # Robustheit: jeden Kanton mit mindestens zehn Fusionen einmal weglassen (Punktschätzung).
    ohne = {}
    for kanton in sorted(behandelte["kanton"].unique()):
        if (behandelte["kanton"] == kanton).sum() >= 10:
            d = bereinigen(p[p["kanton"] != kanton])
            ohne[kanton] = round(float(gardner.kennzahlen(d, gardner.bereinigt(d), {})["alle"]), 2)
    ergebnisse["ohne_kanton"] = ohne
    ergebnisse["vorwegnahme"] = vorwegnahme(p)

    for name, t in (("did2s", es_did2s), ("twfe", es_twfe), ("twfe_gewichtet", es_gew)):
        t.round(3).to_csv(AUSGABE / f"ereignisstudie_abstimmungen_{name}.csv", index=False)
    (AUSGABE / "ergebnisse_abstimmungen.json").write_text(json.dumps(ergebnisse, indent=1, ensure_ascii=False), encoding="utf-8")
    print(es_did2s.round(2).to_string(index=False))
    print(json.dumps(ergebnisse, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
