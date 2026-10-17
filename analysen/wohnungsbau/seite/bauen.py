"""Setzt die Artikelseite aus der Vorlage und den Ergebnisdateien in `../ausgabe/` zusammen.

Jede Zahl in Text, Diagrammen und Tabellen kommt aus den Ergebnisdateien; `[[NAME]]` in der
Vorlage wird hier ersetzt, eine unbekannte oder nicht ersetzte Marke bricht ab. Schreibt
`wohnungsbau.html` (Artefakt) und mit `--soriono=<public>` die Seite für soriono.ch.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
GEMEINSAM = HIER.parents[1] / "gemeinsam"
AUSGABE = HIER.parent / "ausgabe"
SEITENPFAD = "wohnungsbau-real-geschrumpft"
DATUM = "17. Oktober 2026"
TITEL = "Der Wohnungsbau ist real um ein Viertel geschrumpft"
BESCHREIBUNG = ("Seit 2017 sind die Investitionen in neue Wohnbauten real um ein Viertel gesunken. Die Baupreise erklären "
                "mehr als die Hälfte des Rückgangs bei den neuen Wohnungen, die Kosten je Wohnung kaum.")
# Kantone, deren Bevölkerung in einem Zeitraum kaum oder gar nicht wuchs: das Verhältnis ist dort nicht aussagekräftig.
OHNE = {"TI", "NE", "JU"}
NAMEN = {"ZH": "Zürich", "BE": "Bern", "LU": "Luzern", "UR": "Uri", "SZ": "Schwyz", "OW": "Obwalden", "NW": "Nidwalden",
         "GL": "Glarus", "ZG": "Zug", "FR": "Freiburg", "SO": "Solothurn", "BS": "Basel-Stadt", "BL": "Basel-Landschaft",
         "SH": "Schaffhausen", "AR": "Appenzell Ausserrhoden", "AI": "Appenzell Innerrhoden", "SG": "St. Gallen",
         "GR": "Graubünden", "AG": "Aargau", "TG": "Thurgau", "TI": "Tessin", "VD": "Waadt", "VS": "Wallis",
         "NE": "Neuenburg", "GE": "Genf", "JU": "Jura"}


def komma(v: float, d: int = 1) -> str:
    return f"{v:,.{d}f}".replace(",", "'").replace(".", ",")


def ganz(v: float, runden: int = 0) -> str:
    return f"{round(v, runden):,.0f}".replace(",", "'")


def vz(v: float, d: int = 1) -> str:
    return ("−" if v < 0 else "+" if v > 0 else "") + komma(abs(v), d)


def aufzaehlen(teile: list[str]) -> str:
    return ", ".join(teile[:-1]) + " und " + teile[-1] if len(teile) > 1 else teile[0]


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    e = json.loads((AUSGABE / "ergebnisse.json").read_text(encoding="utf-8"))
    k, z = e["kennzahlen"], e["zerlegung"]
    s = pd.read_csv(AUSGABE / "schweiz.csv").set_index("jahr")
    regionen = pd.read_csv(AUSGABE / "regionen.csv")
    kantone = pd.read_csv(AUSGABE / "kantone.csv")
    rob = pd.read_csv(AUSGABE / "robustheit.csv")

    jahre = list(range(2008, 2025))
    investitionen = {"titel": "Investitionen in neue Wohnbauten 2008 bis 2024, real und nominal", "jahre": jahre,
                     "y": [10, 26], "ticks": [10, 14, 18, 22, 26], "dezimalen": 1,
                     "marke": {"jahr": 2020.5, "text": "Preisschub"},
                     "reihen": [{"name": "Real (Preise 2020)", "kurz": "real", "farbe": "var(--series-1)",
                                 "werte": [round(s.loc[j, "neubau_real"] / 1000, 3) for j in jahre]},
                                {"name": "Nominal", "kurz": "nominal", "farbe": "var(--series-2)",
                                 "werte": [round(s.loc[j, "neubau_mio"] / 1000, 3) for j in jahre]}]}
    zerlegung = {"titel": "Zerlegung des Rückgangs der neuen Wohnungen", "bereich": [-14, 6], "ticks": [-12, -8, -4, 0, 4],
                 "einheit": "", "zeilen": [
                     {"name": "Neue Wohnungen", "wert": z["veraenderung_wohnungen_prozent"], "summe": True},
                     {"name": "Nominale Investitionen", "wert": z["beitrag_nominale_investitionen_prozentpunkte"]},
                     {"name": "Baupreise", "wert": z["beitrag_baupreise_prozentpunkte"]},
                     {"name": "Reale Kosten je Wohnung", "wert": z["beitrag_kosten_je_wohnung_prozentpunkte"]}]}
    r = regionen.sort_values("neubau_real_veraenderung_prozent")
    regionen_daten = {"titel": "Veränderung der realen Neubauinvestitionen nach Grossregion", "bereich": [-45, 10],
                      "ticks": [-40, -30, -20, -10, 0], "einheit": " %",
                      "zeilen": [{"name": x.grossregion, "wert": x.neubau_real_veraenderung_prozent} for x in r.itertuples()]}
    vergleichbar = kantone[~kantone["kanton"].isin(OHNE)].sort_values("wohnungen_je_zuwachs_nach")
    kantone_daten = {"titel": "Neue Wohnungen je zusätzliche Person nach Kanton, 2016–2019 und 2021–2024", "bereich": [0, 2.4],
                     "ticks": [0, 0.5, 1.0, 1.5, 2.0], "achse": "Neue Wohnungen je zusätzliche Person",
                     "zeilen": [{"name": NAMEN[x.kanton], "vor": round(x.wohnungen_je_zuwachs_vor, 3), "nach": round(x.wohnungen_je_zuwachs_nach, 3)}
                                for x in vergleichbar.itertuples()]}
    p = lambda v: komma(v, 1) + " %"  # noqa: E731
    tabellen = {
        "regionen-voll": {"kopf": ["Grossregion", "Neubau real", "Auftragsbestand 2025 real", "Wohnungen je Person 2016–19", "2021–24", "Umbauanteil 2016–19", "2021–24"],
                          "reihen": [[x.grossregion, vz(x.neubau_real_veraenderung_prozent) + " %", vz(x.vorrat_real_2024_je_vorher_prozent) + " %",
                                      komma(x.wohnungen_je_zuwachs_vor, 2) if x.wohnungen_je_zuwachs_vor > 0 else "–", komma(x.wohnungen_je_zuwachs_nach, 2),
                                      p(x.umbau_anteil_vor * 100), p(x.umbau_anteil_nach * 100)] for x in r.itertuples()]},
        "kantone-voll": {"kopf": ["Kanton", "Wohnungen je Person 2016–19", "2021–24", "Wachstum 2021–24", "Neubau real", "Auftragsbestand 2025 real"],
                         "reihen": [[NAMEN[x.kanton], komma(x.wohnungen_je_zuwachs_vor, 2) if 0 < x.wohnungen_je_zuwachs_vor < 5 else "–",
                                     komma(x.wohnungen_je_zuwachs_nach, 2), p(x.zuwachs_nach_prozent), vz(x.neubau_real_veraenderung_prozent) + " %",
                                     vz(x.vorrat_real_2024_je_vorher_prozent) + " %"] for x in kantone.sort_values("wohnungen_je_zuwachs_nach").itertuples()]},
        "robust": {"kopf": ["Variante", "Wohnungen", "Nominal", "Baupreise", "Kosten je Wohnung", "Rest"],
                   "reihen": [[x.name, vz(x.veraenderung_wohnungen_prozent), vz(x.beitrag_nominale_investitionen_prozentpunkte),
                               vz(x.beitrag_baupreise_prozentpunkte), vz(x.beitrag_kosten_je_wohnung_prozentpunkte), vz(x.rest_prozentpunkte)]
                              for x in rob.itertuples()]},
    }

    luecke = int((vergleichbar["wohnungen_je_zuwachs_nach"] < vergleichbar["wohnungen_je_zuwachs_vor"]).sum())
    tief = [NAMEN[x] for x in vergleichbar["kanton"].head(4)]
    werte = {
        "DATUM": DATUM, "REAL_RUECKGANG": komma(abs(k["neubau_real_rueckgang_prozent"]), 0), "SPITZE": str(k["neubau_real_spitze_jahr"]),
        "PREIS_ANSTIEG": komma((k["baupreis_2024"] / k["baupreis_2020"] - 1) * 100, 0),
        "JE_ZUWACHS_NACH": komma(k["wohnungen_je_zuwachs_nach"], 2), "JE_ZUWACHS_VOR": komma(k["wohnungen_je_zuwachs_vor"], 2),
        "VORRAT_RUECKGANG": komma(abs(k["vorrat_real_rueckgang_prozent"]), 0), "VORRAT_SPITZE": str(k["vorrat_real_spitze_jahr"]),
        "WOHNUNGEN_2024": ganz(k["wohnungen_2024"]), "WOHNUNGEN_DIFF": ganz(k["wohnungen_vor_mittel"] - k["wohnungen_2024"], -3),
        "ZUWACHS_NACH": ganz(k["zuwachs_nach_jahr"], -3), "ZUWACHS_VOR": ganz(k["zuwachs_vor_jahr"], -3),
        "SPITZE_NOM": komma(k["neubau_nom_spitze"] / 1000, 1), "NOM_2024": komma(k["neubau_nom_2024"] / 1000, 1),
        "NOM_RUECKGANG": komma(abs(k["neubau_nom_rueckgang_prozent"]), 0),
        "RUECKGANG_W": komma(abs(z["veraenderung_wohnungen_prozent"]), 1),
        "BEITRAG_PREIS": komma(abs(z["beitrag_baupreise_prozentpunkte"]), 1), "BEITRAG_NOM": komma(abs(z["beitrag_nominale_investitionen_prozentpunkte"]), 1),
        "REST": vz(z["rest_prozentpunkte"], 1),
        "JE_W_VOR": ganz(z["real_je_wohnung_vorher"], -3), "JE_W_NACH": ganz(z["real_je_wohnung_nachher"], -3),
        "UMBAU_2020": komma(k["umbau_nom_2020"] / 1000, 1), "UMBAU_2024": komma(k["umbau_nom_2024"] / 1000, 1),
        "UMBAU_ANTEIL_2016": komma(k["umbau_anteil_2016"] * 100, 0), "UMBAU_ANTEIL_2024": komma(k["umbau_anteil_2024"] * 100, 0),
        "KANTONE_TIEF": aufzaehlen(tief), "KANTONE_LUECKE": str(luecke),
        "PREIS_SPANNE": f"{komma(rob['beitrag_baupreise_prozentpunkte'].abs().min(), 0)} bis {komma(rob['beitrag_baupreise_prozentpunkte'].abs().max(), 0)}",
        "KOSTEN_SPANNE": f"{vz(rob['beitrag_kosten_je_wohnung_prozentpunkte'].min(), 1)} bis {vz(rob['beitrag_kosten_je_wohnung_prozentpunkte'].max(), 1)}",
        "PRIVAT": komma(k["privat_anteil_2024"] * 100, 0),
    }
    pruefen(e, regionen, kantone, rob, luecke, len(vergleichbar))
    daten = {"investitionen": investitionen, "zerlegung": zerlegung, "regionen": regionen_daten, "kantone": kantone_daten, "tabellen": tabellen}
    argumente = [x for x in sys.argv[1:] if not x.startswith("--soriono=")]
    ersatz = {"/*DATEN*/null": json.dumps(daten, ensure_ascii=False),
              "CODE_TEXT": argumente[0] if argumente else "Der Code ist auf Anfrage erhältlich."}
    html = erzeugen(ersatz, werte, "thema_artefakt.html", "", "")
    (HIER / "wohnungsbau.html").write_text(html, encoding="utf-8")
    print(f"wohnungsbau.html: {len(html):,} Zeichen")
    print({n: werte[n] for n in ("REAL_RUECKGANG", "PREIS_ANSTIEG", "VORRAT_RUECKGANG", "KANTONE_TIEF", "KANTONE_LUECKE", "PREIS_SPANNE", "KOSTEN_SPANNE")})
    for x in sys.argv[1:]:
        if x.startswith("--soriono="):
            ziel = Path(x.split("=", 1)[1]) / "analysen" / SEITENPFAD / "index.html"
            teil = erzeugen(ersatz, werte, "thema_soriono.html", (GEMEINSAM / "soriono_kopf.html").read_text(encoding="utf-8"),
                            (GEMEINSAM / "soriono_fuss.html").read_text(encoding="utf-8"))
            kopf, rumpf = teil.split("<!--RUMPF-->", 1)
            dokument = "\n".join([
                "<!doctype html>", '<html lang="de-CH">', "<head>", '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
                '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
                f'<link rel="canonical" href="https://soriono.ch/analysen/{SEITENPFAD}/">',
                '<meta property="og:type" content="article">', f'<meta property="og:title" content="{TITEL}">',
                f'<meta property="og:description" content="{BESCHREIBUNG}">',
                f'<meta property="og:url" content="https://soriono.ch/analysen/{SEITENPFAD}/">',
                kopf, "</head>", "<body>", rumpf, "</body>", "</html>", ""])
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(dokument, encoding="utf-8")
            print(f"{ziel}: {len(dokument):,} Zeichen")
    return 0


def erzeugen(ersatz: dict, werte: dict, thema: str, kopf: str, fuss: str) -> str:
    html = (HIER / "vorlage.html").read_text(encoding="utf-8")
    ersatz = {"/*THEMA*/": (GEMEINSAM / thema).read_text(encoding="utf-8"),
              "/*SITE_KOPF*/": "<!--RUMPF-->\n" + kopf, "/*SITE_FUSS*/": fuss, **ersatz}
    for marke, text in ersatz.items():
        if html.count(marke) != 1:
            raise ValueError(f"Marke {marke} nicht genau einmal in der Vorlage")
        html = html.replace(marke, text)
    for name, wert in werte.items():
        if f"[[{name}]]" not in html:
            raise ValueError(f"Wert {name} wird in der Vorlage nicht verwendet")
        html = html.replace(f"[[{name}]]", wert)
    rest = re.findall(r"\[\[[A-Z0-9_]+\]\]", html)
    if rest:
        raise ValueError(f"Nicht ersetzte Marken: {sorted(set(rest))}")
    return html


def pruefen(e: dict, regionen: pd.DataFrame, kantone: pd.DataFrame, rob: pd.DataFrame, luecke: int, vergleichbar: int) -> None:
    """Aussagen im Fliesstext, die nicht als Zahl eingesetzt werden, müssen zu den Ergebnissen passen."""
    k, z = e["kennzahlen"], e["zerlegung"]
    reg = regionen.set_index("grossregion")["neubau_real_veraenderung_prozent"]
    kt = kantone.set_index("kanton")
    aussagen = {
        "real um ein Viertel": 22 <= abs(k["neubau_real_rueckgang_prozent"]) <= 30,
        "real fast doppelt so stark wie nominal": 1.6 <= k["neubau_real_rueckgang_prozent"] / k["neubau_nom_rueckgang_prozent"] <= 2.2,
        "Baupreise mehr als die Hälfte": abs(z["beitrag_baupreise_prozentpunkte"]) > abs(z["veraenderung_wohnungen_prozent"]) / 2,
        "Kosten je Wohnung nicht gestiegen (alle Varianten)": (rob["beitrag_kosten_je_wohnung_prozentpunkte"] >= 0).all(),
        "Baupreise grösster Beitrag": abs(z["beitrag_baupreise_prozentpunkte"]) > abs(z["beitrag_nominale_investitionen_prozentpunkte"]),
        "Umbau wächst": k["umbau_nom_2024"] > k["umbau_nom_2020"] and k["umbau_anteil_2024"] > k["umbau_anteil_2016"],
        "Tessin und Espace Mittelland am stärksten": set(reg.nsmallest(2).index) == {"Tessin", "Espace Mittelland"},
        "Genferseeregion und Zürich um rund ein Zehntel, am wenigsten": set(reg.nlargest(2).index) == {"Zürich", "Genferseeregion"} and all(-13 < reg[n] < -7 for n in ("Zürich", "Genferseeregion")),
        "Genf real mehr": kt.loc["GE", "neubau_real_veraenderung_prozent"] > 0,
        "Genf vorher am tiefsten unter vergleichbaren": kt.drop(index=list(OHNE))["wohnungen_je_zuwachs_vor"].idxmin() == "GE",
        "Genf heute ähnlich wie die Schweiz": abs(kt.loc["GE", "wohnungen_je_zuwachs_nach"] - k["wohnungen_je_zuwachs_nach"]) < 0.08,
        "Lücke in den meisten Kantonen gewachsen": luecke >= vergleichbar * 0.75,
        "Bevölkerung wuchs schneller": k["zuwachs_nach_jahr"] > k["zuwachs_vor_jahr"],
        "Bis 2017 gestiegen": e["kennzahlen"]["neubau_real_spitze_jahr"] == 2017,
        "Auftragsbestand rund ein Fünftel tiefer": 15 <= abs(k["vorrat_real_rueckgang_prozent"]) <= 25,
    }
    falsch = [n for n, ok in aussagen.items() if not ok]
    if falsch:
        raise ValueError(f"Fliesstext passt nicht zu den Ergebnissen: {falsch}")


if __name__ == "__main__":
    raise SystemExit(main())
