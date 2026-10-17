"""Setzt die Artikelseite aus der Vorlage und den Ergebnisdateien in `../ausgabe/` zusammen.

Jede Zahl in Text, Diagrammen und Tabellen kommt aus den Ergebnisdateien; `[[NAME]]` in der
Vorlage wird hier ersetzt, eine unbekannte oder nicht ersetzte Marke bricht ab. Schreibt
`einbuergerung.html` (Artefakt) und mit `--soriono=<public>` die Seite für soriono.ch.
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
SEITENPFAD = "einbuergerung-und-wohnort"
DATUM = "17. Oktober 2026"
TITEL = "Seit dem neuen Bürgerrecht entscheidet der Wohnort mehr über die Einbürgerung"
BESCHREIBUNG = ("Seit dem Bürgerrechtsgesetz von 2018 bürgern Gemeinden, die für Zuwanderungsbeschränkungen stimmen, "
                "weniger ein als ihre Nachbarn im selben Kanton. Vorher gab es diesen Unterschied nicht.")
FARBEN = {"Deutschland": "#1f5a8c", "Frankreich": "#1baf7a", "Italien": "#eb6834", "Portugal": "#b8862f"}


def komma(v: float, d: int = 1) -> str:
    return f"{v:,.{d}f}".replace(",", "'").replace(".", ",").replace("'", "'")


def ganz(v: float) -> str:
    return f"{round(v):,}".replace(",", "'")


def vorzeichen(v: float, d: int = 2) -> str:
    return ("−" if v < 0 else "+" if v > 0 else "") + komma(abs(v), d)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    e = json.loads((AUSGABE / "ergebnisse.json").read_text(encoding="utf-8"))
    rob = pd.read_csv(AUSGABE / "robustheit.csv")
    ereignis = pd.read_csv(AUSGABE / "ereignis.csv")
    gruppen = pd.read_csv(AUSGABE / "gruppen.csv")
    kontext = pd.read_csv(AUSGABE / "kontext.csv")

    jahre = sorted(gruppen["jahr"].unique().tolist())
    q = gruppen.pivot(index="jahr", columns="fuenftel", values="quote")
    vor = q[q.index < 2017].mean()
    nach = q[q.index >= 2018].mean()
    namen = {1: "Tiefster Ja-Anteil", 2: "2. Fünftel", 3: "3. Fünftel", 4: "4. Fünftel", 5: "Höchster Ja-Anteil"}
    fuenftel = {"titel": "Einbürgerungsquote nach Fünftel des Ja-Anteils 2014, 2011 bis 2025", "jahre": jahre,
                "y": [1.0, 2.6], "ticks": [1.0, 1.4, 1.8, 2.2, 2.6], "dezimalen": 2,
                "reihen": [{"name": namen[k], "kurz": {1: "tiefstes Ja", 5: "höchstes Ja"}.get(k),
                            "farbe": {1: "var(--series-1)", 5: "var(--series-2)"}.get(k),
                            "werte": [round(v, 3) for v in q[k].tolist()]} for k in range(1, 6)]}

    ordentlich = kontext[kontext["art"] == "Ordentliche Einbürgerung"].pivot(index="jahr", columns="staat", values="wert")
    staaten = {"titel": "Ordentliche Einbürgerungen von Deutschen, Französinnen, Italienern und Portugiesinnen 2011 bis 2025",
               "jahre": ordentlich.index.tolist(), "y": [0, 8000], "ticks": [0, 2000, 4000, 6000, 8000], "dezimalen": 0,
               "reihen": [{"name": s, "farbe": f, "werte": ordentlich[s].astype(int).tolist()} for s, f in FARBEN.items()]}
    alle = kontext[(kontext["staat"] == "Total") & kontext["jahr"].between(2018, 2025)].pivot(index="jahr", columns="art", values="wert").sum()
    anteil_erleichtert = alle["Erleichterte Einbürgerung"] / alle["Art des Erwerbs - Total"] * 100

    h = e["herkunft"]
    herkunft = {"titel": "Unterschied seit 2018 nach früherer Staatsangehörigkeit", "bereich": [-30, 15], "ticks": [-30, -20, -10, 0, 10],
                "dezimalen": 0, "einheit": " %", "achse": "Veränderung in Prozent der Quote der Gruppe",
                "zeilen": [{"name": n, "schaetzung": h[k]["relativ_prozent"],
                            "unten": h[k]["unten"] / h[k]["mittel_vorher"] * 100, "oben": h[k]["oben"] / h[k]["mittel_vorher"] * 100,
                            "se": h[k]["se"] / h[k]["mittel_vorher"] * 100}
                           for k, n in (("eu_efta", "EU und EFTA"), ("uebriges_europa", "Übriges Europa"), ("ausserhalb_europas", "Ausserhalb Europas"))]}

    robust = {"titel": "Unterschied seit 2018 unter verschiedenen Annahmen", "bereich": [-0.3, 0.05], "ticks": [-0.3, -0.2, -0.1, 0],
              "dezimalen": 1, "einheit": " je 100", "achse": "Einbürgerungen je 100 Ausländerinnen und Ausländer, je 10 Punkte Ja", "zeilen": []}
    for r in rob.itertuples():
        robust["zeilen"].append({"name": r.name, "hinweis": r.hinweis, "schaetzung": r.schaetzung, "unten": r.unten, "oben": r.oben,
                                 "se": None if pd.isna(r.se) else r.se, "placebo": r.name.startswith("Placebo"),
                                 "nur_tabelle": r.name.startswith("Poisson"),
                                 "einheit_tabelle": " %" if r.name.startswith("Poisson") else ""})

    zeile = {z: rob.set_index("name").loc[z, "schaetzung"] for z in ("Hauptschätzung", "Einwanderungswellen", "Wohlstand und Grösse", "Alle Kontrollen")}
    haupt = e["haupt"]["schaetzung"]
    spanne = haupt * (e["ja_2014_p90"] - e["ja_2014_p10"]) / 10 / e["quote_nachher"] * 100
    werte = {
        "DATUM": DATUM, "RELATIV": vorzeichen(e["relativ_prozent"], 0), "RELATIV_POS": komma(abs(e["relativ_prozent"]), 0),
        "FEHLEND": ganz(e["fehlende"]["weniger_ueber_mitte"]), "EINB_UEBER": ganz(e["fehlende"]["einbuergerungen_ueber_mitte"]),
        "GEMEINDEN": ganz(e["gemeinden"]), "GEMEINDE_JAHRE": ganz(e["gemeinde_jahre"]), "EINB_SUMME": ganz(e["einbuergerungen"]),
        "ANTEIL": komma(e["anteil_einbuergerungen_schweiz"] * 100, 1),
        "JA_P10": komma(e["ja_2014_p10"], 0), "JA_P90": komma(e["ja_2014_p90"], 0),
        "Q1_VOR": komma(vor[1], 2), "Q1_NACH": komma(nach[1], 2), "Q5_VOR": komma(vor[5], 2), "Q5_NACH": komma(nach[5], 2),
        "EREIGNIS_NACH": vorzeichen(e["ereignis_nachher_mittel"], 2), "WIRKUNG": komma(abs(haupt), 2),
        "SPANNE": komma(abs(spanne), 0), "EU_RELATIV": komma(abs(h["eu_efta"]["relativ_prozent"]), 0),
        "HAUPT": vorzeichen(zeile["Hauptschätzung"], 2), "WELLEN": vorzeichen(zeile["Einwanderungswellen"], 2),
        "WOHLSTAND": vorzeichen(zeile["Wohlstand und Grösse"], 2), "ALLE": vorzeichen(zeile["Alle Kontrollen"], 2),
        "ABSTAND_VOR": komma(vor[1] - vor[5], 2), "ABSTAND_NACH": komma(nach[1] - nach[5], 2),
        "QUOTE_NACH": komma(e["quote_nachher"], 2), "ANTEIL_ERLEICHTERT": komma(anteil_erleichtert, 0),
    }
    pruefen(e, rob, vor, nach)
    if not 15.5 < anteil_erleichtert < 18.5:
        raise ValueError(f"«jede sechste Einbürgerung» passt nicht zu {anteil_erleichtert:.1f} Prozent")
    daten = {"fuenftel": fuenftel, "staaten": staaten, "herkunft": herkunft, "robust": robust,
             "ereignis": [[int(r.jahr), round(r.schaetzung, 4), round(r.unten, 4), round(r.oben, 4)] for r in ereignis.itertuples()]}
    argumente = [x for x in sys.argv[1:] if not x.startswith("--soriono=")]
    code = argumente[0] if argumente else "Der Code ist auf Anfrage erhältlich."
    ersatz = {"/*DATEN*/null": json.dumps(daten, ensure_ascii=False), "CODE_TEXT": code}

    html = erzeugen(ersatz, werte, "thema_artefakt.html", "", "")
    (HIER / "einbuergerung.html").write_text(html, encoding="utf-8")
    print(f"einbuergerung.html: {len(html):,} Zeichen")
    print({k: werte[k] for k in ("RELATIV", "FEHLEND", "Q1_VOR", "Q1_NACH", "Q5_VOR", "Q5_NACH", "SPANNE", "EU_RELATIV", "ANTEIL_ERLEICHTERT")})
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


def pruefen(e: dict, rob: pd.DataFrame, vor: pd.Series, nach: pd.Series) -> None:
    """Aussagen im Fliesstext, die nicht als Zahl eingesetzt werden, müssen zu den Ergebnissen passen."""
    r = rob.set_index("name")
    aussagen = {
        "vor 2018 kein Unterschied (Placebo-Intervall enthält 0)": r.loc["Placebo: Bruch 2015", "unten"] < 0 < r.loc["Placebo: Bruch 2015", "oben"],
        "vor 2018 Werte um null": abs(e["ereignis_vorher_mittel"]) < 0.03,
        "Hauptschätzung sicher negativ": e["haupt"]["oben"] < 0,
        "EU-Effekt sicher negativ": e["herkunft"]["eu_efta"]["oben"] < 0,
        "übriges Europa und ausserhalb kein Effekt": all(e["herkunft"][k]["unten"] < 0 < e["herkunft"][k]["oben"] for k in ("uebriges_europa", "ausserhalb_europas")),
        "tiefstes Fünftel bleibt etwa gleich": abs(nach[1] - vor[1]) < 0.15,
        "höchstes Fünftel fällt": nach[5] < vor[5] - 0.2,
        "Abstand vorher klein, nachher mindestens doppelt": 0 < vor[1] - vor[5] < 0.3 and nach[1] - nach[5] > 2 * (vor[1] - vor[5]),
        "Wellen erklären wenig": r.loc["Einwanderungswellen", "schaetzung"] < 0.75 * r.loc["Hauptschätzung", "schaetzung"],
        "Kontrollen halbieren etwa": 0.3 < r.loc["Alle Kontrollen", "schaetzung"] / r.loc["Hauptschätzung", "schaetzung"] < 0.6,
        "alle Kontrollen nicht sicher von null verschieden": r.loc["Alle Kontrollen", "oben"] > 0,
        "andere Abstimmungen ähnlich": all(r.loc[n, "oben"] < 0 for n in r.index if n.startswith("Klima:")),
        "ohne 2017/2018 bleibt": r.loc["Ohne 2017 und 2018", "oben"] < 0,
        "ohne je Kanton bleibt": r.loc["Ohne je einen Kanton", "oben"] < 0,
        "ungewichtet unsicherer": r.loc["Ungewichtet", "oben"] > 0,
    }
    falsch = [k for k, ok in aussagen.items() if not ok]
    if falsch:
        raise ValueError(f"Fliesstext passt nicht zu den Ergebnissen: {falsch}")


if __name__ == "__main__":
    raise SystemExit(main())
