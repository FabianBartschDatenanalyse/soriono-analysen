"""Warum entstehen weniger Wohnungen? Zerlegung von Investitionen, Baupreisen und Kosten je Wohnung.

Zerlegung (in Logarithmen, darum additiv):

    Wohnungen = Neubauinvestitionen nominal / Baupreisindex / reale Investition je Wohnung

Die Investition je Wohnung bezieht die fertiggestellten Wohnungen eines Jahres auf das Mittel der
Neubauinvestitionen dieses und des Vorjahres, weil ein Mehrfamilienhaus meist über zwei Jahre gebaut
wird. Real heisst: mit dem Baupreisindex der Grossregion des Kantons auf Preise von Oktober 2020.

Schreibt nach `ausgabe/`: ergebnisse.json, schweiz.csv, regionen.csv, kantone.csv, robustheit.csv.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HIER = Path(__file__).resolve().parent
AUSGABE = HIER / "ausgabe"
VOR = (2016, 2019)   # Vergleichszeitraum vor dem Preisschub
NACH = (2021, 2024)  # seit dem Preisschub
ERSTES = 2013        # erstes Jahr mit neu erstellten Wohnungen in Prelude


def real(d: pd.DataFrame, deflator: str = "neubau_mfh") -> pd.DataFrame:
    d = d.copy()
    d["neubau_real"] = d["neubau_mio"] / d[deflator] * 100
    d["umbau_real"] = d["umbau_mio"] / d["renovation_mfh"] * 100
    d["vorrat_neubau_real"] = d["vorrat_neubau_mio"] / d[deflator] * 100
    return d


def reihe(d: pd.DataFrame, gruppe: str | None, verzoegerung: int = 2) -> pd.DataFrame:
    """Summen je Jahr (und Gruppe) mit der realen Investition je fertiggestellter Wohnung."""
    schluessel = ["jahr"] + ([gruppe] if gruppe else [])
    s = d.groupby(schluessel)[["neubau_mio", "umbau_mio", "vorrat_neubau_mio", "neubau_real", "umbau_real",
                               "vorrat_neubau_real", "privat_mio", "wohnungen", "einwohner"]].sum(min_count=1).reset_index()
    s = s.sort_values(schluessel[::-1])
    nach_gruppe = s.groupby(gruppe) if gruppe else s
    roll = lambda spalte: nach_gruppe[spalte].transform(lambda x: x.rolling(verzoegerung).mean()) if gruppe else s[spalte].rolling(verzoegerung).mean()  # noqa: E731
    s["neubau_real_glatt"] = roll("neubau_real")
    s["neubau_nom_glatt"] = roll("neubau_mio")
    s["real_je_wohnung"] = s["neubau_real_glatt"] * 1e6 / s["wohnungen"]
    s["preis"] = s["neubau_nom_glatt"] / s["neubau_real_glatt"] * 100
    s["zuwachs"] = nach_gruppe["einwohner"].diff() if gruppe else s["einwohner"].diff()
    s["umbau_anteil"] = s["umbau_mio"] / (s["umbau_mio"] + s["neubau_mio"])
    return s.sort_values(schluessel).reset_index(drop=True)


def mittel(s: pd.DataFrame, spalte: str, zeitraum: tuple[int, int]) -> float:
    return float(s.loc[s["jahr"].between(*zeitraum), spalte].mean())


def zerlegung(s: pd.DataFrame) -> dict:
    """Anteile von nominalen Investitionen, Preisen und Kosten je Wohnung am Rückgang der Wohnungen."""
    a = {k: mittel(s, k, VOR) for k in ("wohnungen", "neubau_nom_glatt", "preis", "real_je_wohnung")}
    b = {k: mittel(s, k, NACH) for k in a}
    w = np.log(b["wohnungen"] / a["wohnungen"])
    teile = {"nominale_investitionen": np.log(b["neubau_nom_glatt"] / a["neubau_nom_glatt"]),
             "baupreise": -np.log(b["preis"] / a["preis"]),
             "kosten_je_wohnung": -np.log(b["real_je_wohnung"] / a["real_je_wohnung"])}
    rest = w - sum(teile.values())  # Mittelwerte von Quotienten: kleiner Rest
    return {"wohnungen_vorher": a["wohnungen"], "wohnungen_nachher": b["wohnungen"],
            "veraenderung_wohnungen_prozent": float(np.expm1(w) * 100),
            **{f"beitrag_{k}_prozentpunkte": float(v * 100) for k, v in teile.items()},
            "rest_prozentpunkte": float(rest * 100),
            "real_je_wohnung_vorher": a["real_je_wohnung"], "real_je_wohnung_nachher": b["real_je_wohnung"],
            "preis_vorher": a["preis"], "preis_nachher": b["preis"]}


def kennzahlen(s: pd.DataFrame) -> dict:
    x = s.set_index("jahr")
    spitze = int(x.loc[2010:2020, "neubau_real"].idxmax())
    return {
        "neubau_real_spitze_jahr": spitze, "neubau_real_spitze": float(x.loc[spitze, "neubau_real"]),
        "neubau_real_2024": float(x.loc[2024, "neubau_real"]),
        "neubau_real_rueckgang_prozent": float((x.loc[2024, "neubau_real"] / x.loc[spitze, "neubau_real"] - 1) * 100),
        "neubau_nom_rueckgang_prozent": float((x.loc[2024, "neubau_mio"] / x.loc[spitze, "neubau_mio"] - 1) * 100),
        "neubau_nom_2024": float(x.loc[2024, "neubau_mio"]), "neubau_nom_spitze": float(x.loc[spitze, "neubau_mio"]),
        "baupreis_2020": float(x.loc[2020, "preis"]), "baupreis_2024": float(x.loc[2024, "neubau_mio"] / x.loc[2024, "neubau_real"] * 100),
        "umbau_anteil_2016": float(x.loc[2016, "umbau_anteil"]), "umbau_anteil_2024": float(x.loc[2024, "umbau_anteil"]),
        "umbau_nom_2020": float(x.loc[2020, "umbau_mio"]), "umbau_nom_2024": float(x.loc[2024, "umbau_mio"]),
        "vorrat_real_spitze_jahr": int(x.loc[2010:2020, "vorrat_neubau_real"].idxmax()),
        "vorrat_real_2024": float(x.loc[2024, "vorrat_neubau_real"]),
        "vorrat_real_rueckgang_prozent": float((x.loc[2024, "vorrat_neubau_real"] / x.loc[2010:2020, "vorrat_neubau_real"].max() - 1) * 100),
        "privat_anteil_2024": float(x.loc[2024, "privat_mio"] / (x.loc[2024, "neubau_mio"] + x.loc[2024, "umbau_mio"])),
        "wohnungen_2024": int(x.loc[2024, "wohnungen"]), "wohnungen_vor_mittel": mittel(s, "wohnungen", VOR),
        "wohnungen_je_zuwachs_vor": float(x.loc[VOR[0]:VOR[1], "wohnungen"].sum() / x.loc[VOR[0]:VOR[1], "zuwachs"].sum()),
        "wohnungen_je_zuwachs_nach": float(x.loc[NACH[0]:NACH[1], "wohnungen"].sum() / x.loc[NACH[0]:NACH[1], "zuwachs"].sum()),
        "zuwachs_vor_jahr": mittel(s, "zuwachs", VOR), "zuwachs_nach_jahr": mittel(s, "zuwachs", NACH),
    }


def gruppen(d: pd.DataFrame, gruppe: str) -> pd.DataFrame:
    s = reihe(d, gruppe)
    zeilen = []
    for g, x in s.groupby(gruppe):
        x = x.set_index("jahr")
        vor_real = x.loc[VOR[0]:VOR[1], "neubau_real"].mean()
        zeilen.append({gruppe: g,
                       "neubau_real_veraenderung_prozent": (x.loc[NACH[0]:NACH[1], "neubau_real"].mean() / vor_real - 1) * 100,
                       "vorrat_real_2024_je_vorher_prozent": (x.loc[2024, "vorrat_neubau_real"] / x.loc[VOR[0]:VOR[1], "vorrat_neubau_real"].mean() - 1) * 100,
                       "wohnungen_je_zuwachs_vor": x.loc[VOR[0]:VOR[1], "wohnungen"].sum() / x.loc[VOR[0]:VOR[1], "zuwachs"].sum(),
                       "wohnungen_je_zuwachs_nach": x.loc[NACH[0]:NACH[1], "wohnungen"].sum() / x.loc[NACH[0]:NACH[1], "zuwachs"].sum(),
                       "zuwachs_nach_prozent": (x.loc[NACH[1], "einwohner"] / x.loc[NACH[0] - 1, "einwohner"] - 1) * 100,
                       "umbau_anteil_vor": x.loc[VOR[0]:VOR[1], "umbau_mio"].sum() / (x.loc[VOR[0]:VOR[1], "umbau_mio"] + x.loc[VOR[0]:VOR[1], "neubau_mio"]).sum(),
                       "umbau_anteil_nach": x.loc[NACH[0]:NACH[1], "umbau_mio"].sum() / (x.loc[NACH[0]:NACH[1], "umbau_mio"] + x.loc[NACH[0]:NACH[1], "neubau_mio"]).sum(),
                       "einwohner_2024": x.loc[2024, "einwohner"]})
    return pd.DataFrame(zeilen)


def robustheit(d: pd.DataFrame) -> pd.DataFrame:
    zeilen = []
    for name, dd, lag in (("Hauptrechnung", real(d), 2), ("Ein Jahr Bauzeit", real(d), 1), ("Drei Jahre Bauzeit", real(d), 3),
                          ("Preise der Schweiz statt der Grossregion", real(_landesindex(d)), 2)):
        z = zerlegung(reihe(dd, None, lag))
        zeilen.append({"name": name, **z})
    return pd.DataFrame(zeilen)


def _landesindex(d: pd.DataFrame) -> pd.DataFrame:
    from bpi import jahresindex
    ch = jahresindex().query("region == 'Schweiz'")[["jahr", "neubau_mfh", "renovation_mfh"]]
    return d.drop(columns=["neubau_mfh", "renovation_mfh"]).merge(ch, on="jahr", how="left")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    d = real(pd.read_parquet(AUSGABE / "kantone.parquet"))
    s = reihe(d, None)
    s.to_csv(AUSGABE / "schweiz.csv", index=False)
    ergebnisse = {"zeitraeume": {"vor": VOR, "nach": NACH}, "kennzahlen": kennzahlen(s), "zerlegung": zerlegung(s)}
    regionen = gruppen(d, "grossregion")
    kantone = gruppen(d, "kanton")
    regionen.to_csv(AUSGABE / "regionen.csv", index=False)
    kantone.to_csv(AUSGABE / "kantone.csv", index=False)
    rob = robustheit(d)
    rob.to_csv(AUSGABE / "robustheit.csv", index=False)
    (AUSGABE / "ergebnisse.json").write_text(json.dumps(ergebnisse, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ergebnisse, ensure_ascii=False, indent=1))
    print(regionen.round(2).to_string())
    print(kantone.sort_values("wohnungen_je_zuwachs_nach").round(2).to_string())
    print(rob.round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
