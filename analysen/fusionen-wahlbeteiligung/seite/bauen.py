"""Setzt die Artikelseite aus der Vorlage und den Ergebnisdateien in `../ausgabe/` zusammen.

Jede Zahl in Diagrammen und Tabellen kommt aus den Ergebnisdateien; Zahlen im Fliesstext
sind in der Vorlage und hier geprüft (siehe `pruefen`). Schreibt `fusionen.html`.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb
import pandas as pd

HIER = Path(__file__).resolve().parent
GEMEINSAM = HIER.parents[1] / "gemeinsam"  # Thema, Seitenkopf und -fuss aller Analysen
AUSGABE = HIER.parent / "ausgabe"
MODELL = HIER.parents[2] / "state" / "analysen" / "modell.duckdb"


def lesen(name: str) -> dict:
    return json.loads((AUSGABE / name).read_text(encoding="utf-8"))


def ereignis(datei: str) -> list:
    d = pd.read_csv(AUSGABE / datei)
    return [[int(r.rel), round(r.schaetzung, 2), round(r.unten, 2), round(r.oben, 2)] for r in d.itertuples()]


def gemeinden_je_jahr() -> list:
    with duckdb.connect(str(MODELL), read_only=True) as con:
        return [list(r) for r in con.sql(
            "select y, (select count(*) from model.agvch_historisch_gemeinden where GDE_GARTE='11' "
            "and GDE_GINIDAT<=make_date(y,1,1) and (GDE_GFINDAT is null or GDE_GFINDAT>=make_date(y,1,1))) "
            "from range(1960,2027) t(y) order by y").fetchall()]


def zahl(v: float, d: int = 2) -> str:
    return ("−" if v < 0 else "+" if v > 0 else "") + f"{abs(v):.{d}f}".replace(".", ",")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    w, a, r = lesen("ergebnisse.json"), lesen("ergebnisse_abstimmungen.json"), lesen("robustheit.json")
    ra, rw = r["abstimmungen"], r["wahlen"]
    groesse = {"zeilen": [
        {"name": "unter 1'000 Stimmberechtigte", "a": a["groesse"]["a_unter_1000"], "w": w["groesse"]["a_unter_1000"]},
        {"name": "1'000 bis 4'999", "a": a["groesse"]["b_1000_bis_4999"], "w": w["groesse"]["b_1000_bis_4999"]},
        {"name": "ab 5'000", "a": a["groesse"]["c_ab_5000"], "w": w["groesse"]["c_ab_5000"]},
        {"name": "Eingemeindung (unter 20 % aufgegangen)", "a": a["anteil_aufgegangen"]["a_unter_20_prozent"], "w": w["anteil_aufgegangen"]["a_unter_20_prozent"]},
        {"name": "Fusion unter Gleichen (ab 40 %)", "a": a["anteil_aufgegangen"]["c_ab_40_prozent"], "w": w["anteil_aufgegangen"]["c_ab_40_prozent"]},
    ], "bereich": [-4, 1], "titel": "Wirkung nach Grösse und Art der Fusion"}
    punkt = lambda v: {"schaetzung": v}  # noqa: E731 – Punktschätzung ohne Intervall
    robust = {"zeilen": [
        {"name": "Hauptschätzung", "a": ra["haupt"], "w": rw["haupt"], "hinweis": "Gemeinde und Kanton × Termin"},
        {"name": "Vergleich im selben Bezirk", "a": ra["bezirk_termin"], "w": rw["bezirk_termin"], "hinweis": "Bezirk × Termin"},
        {"name": "Unsicherheit je Bezirk", "a": ra["cluster_bezirk"], "w": rw["cluster_bezirk"], "hinweis": "Bootstrap über Bezirke"},
        {"name": "Nur eine Fusion", "a": ra["eine_fusion"], "w": rw["eine_fusion"], "hinweis": "Gemeinden mit genau einer Fusion"},
        {"name": "Vollständig beobachtet", "a": ra["ausgewogen"], "w": rw["ausgewogen"],
         "hinweis": "jedes Jahr von " + ra["ausgewogen"]["fenster"].replace("..", " bis ").replace("-", "−")
                     + " bzw. jede Wahl von " + rw["ausgewogen"]["fenster"].replace("..", " bis ").replace("-", "−") + " beobachtet"},
        {"name": "Anderer Schätzer (gestapelt)", "a": ra["gestapelt"], "hinweis": "Cengiz et al. 2019, Gemeinde × Jahr, Fenster ±5 Jahre"},
        {"name": "Vortrend fortgeschrieben", "a": punkt(ra["vortrend_linear"]["wirkung_ohne_vortrend"]),
         "w": punkt(rw["vortrend_linear"]["wirkung_ohne_vortrend"]), "hinweis": "linearer Trend der Vorperioden abgezogen; Punktschätzung"},
        {"name": "Jahr vor der Fusion ausgelassen", "a": punkt(a["vorwegnahme"]["wirkung"]), "hinweis": "Vorwegnahme erlaubt; Punktschätzung"},
        {"name": "Placebo: Fusion 4 Jahre zu früh", "a": ra["placebo"], "w": rw["placebo"], "hinweis": "nur Beobachtungen vor der echten Fusion"},
    ], "bereich": [-4, 1], "titel": "Wirkung unter verschiedenen Annahmen"}
    werte = [z[k]["schaetzung"] for z in robust["zeilen"] if not z["name"].startswith("Placebo") for k in ("a", "w") if k in z]
    unten, oben = min(werte), max(werte)
    robust_text = (
        f"Unter allen anderen Annahmen bleibt die Wirkung deutlich negativ, zwischen {zahl(oben, 1)} und {zahl(unten, 1)} Prozentpunkten. "
        "Die Spanne kommt vor allem vom leichten Anstieg kurz vor der Fusion. Wer ihn als vorübergehende Mobilisierung liest, "
        "kommt auf eine etwas kleinere Wirkung; wer ihn als Trend liest, der ohne Fusion weitergegangen wäre, auf eine etwas grössere. "
        "Bei den Wahlen, die diesen Anstieg nicht zeigen, liegen alle Schätzungen nahe beieinander. Ein Vergleich nur mit Gemeinden "
        "desselben Bezirks, also mit den direkten Nachbarn, ändert wenig."
    )
    ziehungen = r["ziehungen"]
    robust_methode = (
        f"Alle Zeilen mit Intervall: Gardner-Schätzer, Cluster-Bootstrap mit {ziehungen} Ziehungen (Hauptschätzung im Text: 200). "
        f"Placebo: Für Fusionsgemeinden zählen nur Beobachtungen vor der echten Fusion, das Fusionsdatum wird um 4 Jahre "
        f"(Wahlen: 2 Wahlen) vorverlegt. Gestapelte Schätzung: je Fusionsjahr ein Stapel aus den Gemeinden dieses Jahres und "
        f"Gemeinden ohne Fusion im Fenster von ±5 Jahren ({ra['gestapelt']['stapel']} Stapel, {ra['gestapelt']['zeilen']:,} Zeilen), "
        "feste Effekte Gemeinde × Stapel und Kanton × Jahr × Stapel, Standardfehler nach Gemeinde. Vortrend: lineare Regression der "
        f"Ereigniszeit-Schätzungen vor der Fusion (Steigung {zahl(ra['vortrend_linear']['steigung_je_periode'], 3)} Punkte je Jahr "
        f"bei den Abstimmungen, {zahl(rw['vortrend_linear']['steigung_je_periode'], 3)} je Wahl), fortgeschrieben und von den "
        f"Nachperioden abgezogen. Lässt man das Jahr vor der Fusion als Vergleich weg, liegt es {zahl(a['vorwegnahme']['jahr_vorher'], 2)} "
        f"Punkte über dem Mittel; gemessen an den Jahren −7 bis −4 beträgt die Wirkung {zahl(a['vorwegnahme']['wirkung_gegen_jahre_minus7_bis_minus4'], 2)}. "
        "Ohne jeden einzelnen Kanton mit mindestens zehn Fusionen liegt die Wirkung zwischen "
        f"{zahl(max(a['ohne_kanton'].values()), 2)} und {zahl(min(a['ohne_kanton'].values()), 2)} (Abstimmungen) bzw. "
        f"{zahl(max(v['schaetzung'] for v in w['ohne_kanton'].values()), 2)} und {zahl(min(v['schaetzung'] for v in w['ohne_kanton'].values()), 2)} (Wahlen)."
    )
    robust_methode = robust_methode.replace(f"{ra['gestapelt']['zeilen']:,}", f"{ra['gestapelt']['zeilen']:,}".replace(",", "'"))
    daten = {"gemeinden": gemeinden_je_jahr(), "ereignis": {"abst": ereignis("ereignisstudie_abstimmungen_did2s.csv"),
             "wahl": ereignis("ereignisstudie_did2s.csv")}, "groesse": groesse, "robust": robust}
    argumente = [x for x in sys.argv[1:] if not x.startswith("--soriono=")]
    code_text = argumente[0] if argumente else "Der Code ist auf Anfrage erhältlich."
    ersatz = {"/*DATEN*/null": json.dumps(daten, ensure_ascii=False), "ROBUST_TEXT": robust_text,
              "ROBUST_METHODE": robust_methode, "CODE_TEXT": code_text}
    # Artefakt: eigene Gestaltung, ohne Seitenkopf.
    html = erzeugen(ersatz, "thema_artefakt.html", "", "")
    pruefen(html, w, a)
    (HIER / "fusionen.html").write_text(html, encoding="utf-8")
    print(f"fusionen.html: {len(html):,} Zeichen; Spanne {zahl(oben, 2)} bis {zahl(unten, 2)}")
    # Website soriono.ch: Soriono-Gestaltung, vollständiges Dokument.
    for x in sys.argv[1:]:
        if x.startswith("--soriono="):
            ziel = Path(x.split("=", 1)[1]) / "analysen" / SEITENPFAD / "index.html"
            teil = erzeugen(ersatz, "thema_soriono.html", (GEMEINSAM / "soriono_kopf.html").read_text(encoding="utf-8"),
                            (GEMEINSAM / "soriono_fuss.html").read_text(encoding="utf-8"))
            pruefen(teil, w, a)
            kopf, rumpf = teil.split("<!--RUMPF-->", 1)
            dokument = "\n".join([
                "<!doctype html>", '<html lang="de-CH">', "<head>", '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
                '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
                f'<link rel="canonical" href="https://soriono.ch/analysen/{SEITENPFAD}/">',
                '<meta property="og:type" content="article">',
                '<meta property="og:title" content="Nach einer Gemeindefusion gehen weniger Menschen abstimmen">',
                '<meta property="og:description" content="Nach Gemeindefusionen sinkt die Beteiligung an eidgenössischen '
                'Abstimmungen und Nationalratswahlen um knapp zwei Prozentpunkte, dauerhaft.">',
                f'<meta property="og:url" content="https://soriono.ch/analysen/{SEITENPFAD}/">',
                kopf, "</head>", "<body>", rumpf, "</body>", "</html>", ""])
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(dokument, encoding="utf-8")
            print(f"{ziel}: {len(dokument):,} Zeichen")
    return 0


SEITENPFAD = "fusionen-und-stimmbeteiligung"


def erzeugen(ersatz: dict, thema: str, kopf: str, fuss: str) -> str:
    html = (HIER / "vorlage.html").read_text(encoding="utf-8")
    ersatz = {"/*THEMA*/": (GEMEINSAM / thema).read_text(encoding="utf-8"),
              "/*SITE_KOPF*/": "<!--RUMPF-->\n" + kopf, "/*SITE_FUSS*/": fuss, **ersatz}
    for marke, text in ersatz.items():
        if html.count(marke) != 1:
            raise ValueError(f"Marke {marke} nicht genau einmal in der Vorlage")
        html = html.replace(marke, text)
    return html


def pruefen(html: str, w: dict, a: dict) -> None:
    """Zahlen im Fliesstext der Vorlage müssen zu den Ergebnissen passen."""
    erwartet = {
        "−1,9": round(a["alle"]["schaetzung"], 1) == -1.9, "−1,7": round(w["alle"]["schaetzung"], 1) == -1.7,
        "328": a["alle"]["gemeinden"] == 328, "316": w["alle"]["gemeinden"] == 316,
        "46 Prozent": round(a["vorher_beteiligung_mittel"]) == 46,
        "0,4 Punkte": round(a["vorwegnahme"]["jahr_vorher"], 1) == 0.4,
    }
    falsch = [k for k, ok in erwartet.items() if not ok or k not in html]
    if falsch:
        raise ValueError(f"Fliesstext passt nicht zu den Ergebnissen: {falsch}")


if __name__ == "__main__":
    raise SystemExit(main())
