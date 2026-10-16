"""Setzt den Artikel zur Heiratsstrafe-Initiative aus Vorlage, Rechner und Ergebnisdateien zusammen.

Alle Zahlen im Text kommen aus `../ausgabe/` (modell.py, auswertung.py) oder direkt aus steuer.py.
Schreibt `heiratsstrafe.html` (Artefakt) und mit `--soriono=<public>` die Seite für soriono.ch.

    python seite/bauen.py --soriono=../soriono-web/public
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

import pandas as pd

HIER = Path(__file__).resolve().parent
ANALYSE = HIER.parent
GEMEINSAM = ANALYSE.parent / "gemeinsam"
AUSGABE = ANALYSE / "ausgabe"
sys.path.insert(0, str(ANALYSE))
import steuer  # noqa: E402

SEITENPFAD = "heiratsstrafe-initiative"
DATUM = "Oktober 2026"


def zahl(v: float, stellen: int = 1) -> str:
    return f"{v:.{stellen}f}".replace(".", ",")


def tausend(v: float, runden: int = 10_000) -> str:
    return f"{round(v / runden) * runden:,.0f}".replace(",", "'")


def prozent(v: float) -> str:
    return f"{round(100 * v)} %"


def haushalte() -> list[dict]:
    zeilen = []
    for y in (120_000, 250_000):
        for kinder in (0, 2):
            for i in range(21):
                a = 0.5 + i * 0.025
                y1, y2 = y * a, y * (1 - a)
                zeilen.append({"einkommen": y, "kinder": kinder, "anteil": round(a, 3),
                               "heute": steuer.ehepaar(y1, y2, kinder), "konkubinat": steuer.konkubinat(y1, y2, kinder),
                               "individual": sum(steuer.ehepaar_individuell(y1, y2, kinder)),
                               "initiative_mit": steuer.ehepaar_initiative(y1, y2, kinder, "mit_privileg"),
                               "initiative_ohne": steuer.ehepaar_initiative(y1, y2, kinder, "ohne_privileg")})
    return zeilen


def spanne(a: float, b: float) -> str:
    return f"{zahl(a)} bis {zahl(b)}"


def grenz(e: dict, regel: str) -> str:
    """Spanne der Grenzbelastung auf Zweiteinkommen von 10'000 bis 90'000 Franken (Partnereinkommen 100'000, ohne Kinder)."""
    werte = [x["grenzsteuer_prozent"] for x in e[f"{regel}|100000|0"] if 10_000 <= x["zweiteinkommen"] <= 80_000]
    return f"{round(min(werte))} bis {round(max(werte))}"


def tabelle(kopf: list[str], zeilen: list[list[str]], klasse: str = "") -> str:
    k = "".join(f'<th scope="col">{html.escape(c)}</th>' for c in kopf)
    z = "".join("<tr>" + "".join((f'<th scope="row" style="font-weight:400">{c}</th>' if i == 0 else f"<td>{c}</td>")
                                 for i, c in enumerate(r)) + "</tr>" for r in zeilen)
    return f'<table class="{klasse}"><thead><tr>{k}</tr></thead><tbody>{z}</tbody></table>'


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    e = json.loads((AUSGABE / "ergebnisse.json").read_text(encoding="utf-8"))
    h, s, mk = e["haupt"], e["spanne"], e["modell"]
    rob = pd.read_csv(AUSGABE / "robustheit.csv")
    nach = pd.read_csv(AUSGABE / "nach_einkommen.csv")
    pruef = pd.read_csv(AUSGABE / "pruefung.csv")

    kosten_mit = (min(s["entlastung_mit_mrd"][0], rob.kosten_mit_mrd.min()), max(s["entlastung_mit_mrd"][1], rob.kosten_mit_mrd.max()))
    kosten_ohne = (min(s["entlastung_ohne_mrd"][0], rob.kosten_ohne_mrd.min()), max(s["entlastung_ohne_mrd"][1], rob.kosten_ohne_mrd.max()))
    hh = haushalte()
    strafe_250 = next(r for r in hh if r["einkommen"] == 250_000 and r["kinder"] == 0 and r["anteil"] == 0.5)
    k = mk["kennzahlen"]

    faktencheck = tabelle(["Aussage", "Wer", "Bewertung", "Was die Zahlen zeigen"], [
        ["Mit der Initiative zahlen Ehepaare nicht mehr als Unverheiratete in derselben wirtschaftlichen Situation.", "Die Mitte",
         '<span class="urteil stimmt">stimmt</span>',
         "Das ist der Kern der zweiten Berechnung: In beiden Umsetzungen zahlt kein Ehepaar mehr als ein vergleichbares unverheiratetes Paar."],
        ["Das Steueramt verrechnet automatisch den tieferen Betrag, niemand zahlt mehr.", "Die Mitte",
         '<span class="urteil">hängt von der Umsetzung ab</span>',
         f"Mit Privileg zahlt kein Ehepaar mehr als heute. Ohne Privileg zahlten rund {tausend(h['paare_ohne_privileg_mehr_tsd'] * 1e3)} Ehepaare mehr, "
         "weil Zweiverdiener- und Verheiratetenabzug wegfallen."],
        ["Die Initiative respektiert verschiedene Lebensmodelle, auch Einverdienerpaare.", "Die Mitte",
         '<span class="urteil">stimmt teilweise</span>',
         f"Mit Privileg behalten Einverdienerpaare ihren heutigen Bonus; mit der Individualbesteuerung zahlen {prozent(h['einverdiener_individual_mehr_anteil'])} "
         f"von ihnen mehr. Ohne Privileg zahlten aber {prozent(h['einverdiener_ohne_privileg_mehr_anteil'])} der Einverdienerpaare mehr als heute."],
        ["Die Initiative bevorzugt Verheiratete gegenüber Unverheirateten.", "Bundesrat",
         '<span class="urteil stimmt">stimmt</span>',
         f"Mit Privileg zahlen rund {tausend(h['paare_initiative_unter_konkubinat_tsd'] * 1e3)} Ehepaare weniger als ein unverheiratetes Paar in gleicher Lage, "
         "vor allem Einverdienerpaare. Kein Ehepaar zahlt mehr."],
        ["Die Heiratsstrafe ist mit der Individualbesteuerung bereits abgeschafft.", "Bundesrat",
         '<span class="urteil stimmt">stimmt, ab 2032</span>',
         f"Ab 2032 hängt die Bundessteuer nicht mehr vom Zivilstand ab. Dafür zahlen rund {tausend(h['paare_individual_mehr_tsd'] * 1e3)} Ehepaare mehr als heute, "
         f"darunter {prozent(h['einverdiener_individual_mehr_anteil'])} der Einverdienerpaare."],
        ["Je nach Umsetzung drohen Mindereinnahmen von bis zu 3 Milliarden Franken pro Jahr.", "Bundesrat",
         '<span class="urteil">stimmt teilweise</span>',
         f"Die zweite Berechnung, die die Initiative als Ersatzlösung selbst vorschreibt, kostet nach unserer Schätzung {spanne(*kosten_ohne)} "
         f"(ohne Privileg) bzw. {spanne(*kosten_mit)} Milliarden Franken (mit Privileg); die Botschaft nennt 0,7 bis 1,4. Bis 3 Milliarden kostete erst "
         "ein Splitting, das das Parlament stattdessen wählen könnte (Botschaft: 2,4 bis 3,1 Milliarden bei Vollsplitting)."],
        ["Die gemeinsame Besteuerung schwächt die Erwerbsanreize für Zweitverdienende.", "Bundesrat",
         '<span class="urteil stimmt">stimmt</span>',
         f"Verdient eine Person 100'000 Franken, gehen heute {grenz(e['grenzsteuer_zweiteinkommen'], 'heute')} Prozent eines zusätzlichen Zweiteinkommens an die "
         f"Bundessteuer, mit der Initiative mit Privileg {grenz(e['grenzsteuer_zweiteinkommen'], 'initiative_mit')} und mit der Individualbesteuerung "
         f"{grenz(e['grenzsteuer_zweiteinkommen'], 'individual')} Prozent. Die Initiative senkt die Belastung, die Individualbesteuerung stärker."],
        ["Unverheiratete könnten je nach Umsetzung schlechter gestellt werden.", "Gegnerschaft",
         '<span class="urteil">stimmt für eine Umsetzung</span>',
         "In der Umsetzung ohne Privileg verlieren unverheiratete Eltern und Alleinerziehende den günstigeren Elterntarif (Botschaft). "
         "Diese Analyse beziffert das nicht, weil sie nur Ehepaare rechnet."],
    ], "check")

    robust = tabelle(["Variante", "Kosten mit Privileg", "Kosten ohne Privileg", "Entlastung an Paare ab 150'000", "mehr zahlen ohne Privileg"],
                     [[r.szenario, zahl(r.kosten_mit_mrd, 2) + " Mrd.", zahl(r.kosten_ohne_mrd, 2) + " Mrd.", prozent(r.anteil_entlastung_ab_150k),
                       tausend(r.ohne_privileg_mehr_tsd * 1e3)] for r in rob.itertuples()])

    verteilung = [{"klasse": r.klasse, "paare": r.paare_tsd / nach.paare_tsd.sum(), "entlastung": r.anteil_initiative_mit} for r in nach.itertuples()]
    mittel = [{"klasse": r.klasse, "individual": r.mittel_individual, "initiative_mit": r.mittel_initiative_mit,
               "initiative_ohne": r.mittel_initiative_ohne, "heute": r.steuer_heute_mittel} for r in nach.itertuples()]

    werte = {
        "DATUM": DATUM,
        "KOSTEN_SPANNE": f"{zahl(kosten_ohne[0])}–{zahl(kosten_mit[1])}",
        "KOSTEN_MIT": spanne(*kosten_mit), "KOSTEN_OHNE": spanne(*kosten_ohne),
        "ANTEIL_150": prozent(h["anteil_entlastung_mit_ab_150k"]), "ANTEIL_250": prozent(h["anteil_entlastung_mit_ab_250k"]),
        "ANTEIL_75": f"{max(1, round(100 * h['anteil_entlastung_mit_unter_75k']))} %" if h["anteil_entlastung_mit_unter_75k"] >= 0.005 else "unter 1 %",
        "MEHR_OHNE": tausend(h["paare_ohne_privileg_mehr_tsd"] * 1e3),
        "EINV_OHNE": prozent(h["einverdiener_ohne_privileg_mehr_anteil"]),
        "INDIV_MEHR": tausend(h["paare_individual_mehr_tsd"] * 1e3), "INDIV_WENIGER": tausend(h["paare_individual_weniger_tsd"] * 1e3),
        "EINV_INDIV": prozent(h["einverdiener_individual_mehr_anteil"]),
        "GRENZ_HEUTE": grenz(e["grenzsteuer_zweiteinkommen"], "heute"),
        "GRENZ_INDIV": grenz(e["grenzsteuer_zweiteinkommen"], "individual"),
        "GRENZ_INIT": grenz(e["grenzsteuer_zweiteinkommen"], "initiative_mit"),
        "STRAFE_250": f"{strafe_250['heute'] - strafe_250['konkubinat']:,.0f}".replace(",", "'"),
        "PRUEF_FAELLE": f"{len(pruef):,}".replace(",", "'"), "PRUEF_ABW": zahl(pruef["diff"].abs().max(), 2),
        "ALPHA": zahl(mk["alpha"], 2), "MITTEL_MODELL": f"{mk['mittel_steuerbar_modell']:,}".replace(",", "'"),
        "RENTNER_TSD": str(round(k["rentner_tsd"])), "ZUSATZ": zahl(100 * mk["annahmen"]["einverdiener_zusatz"], 1),
        "ZV_MODELL": str(round(k["zweiverdiener_tsd"])), "ZV_ZIEL": str(round(mk["pruefwerte"]["zweiverdiener"] / 1e3)),
        "MEHR_MODELL": str(round(k["mehrbelastung_10_tsd"])), "MINDER_MODELL": str(round(k["minderbelastung_10_tsd"])),
        "FAKTENCHECK": faktencheck, "ROBUST": robust,
    }
    daten = json.dumps({"haushalte": hh, "verteilung": verteilung, "mittel": mittel}, ensure_ascii=False)

    def erzeugen(thema: str, kopf: str, fuss: str) -> str:
        t = (HIER / "vorlage.html").read_text(encoding="utf-8")
        for marke, text in (("/*THEMA*/", (GEMEINSAM / thema).read_text(encoding="utf-8")), ("/*SITE_KOPF*/", "<!--RUMPF-->\n" + kopf),
                            ("/*SITE_FUSS*/", fuss), ("/*DATEN*/null", daten)):
            if t.count(marke) != 1:
                raise ValueError(f"Marke {marke} nicht genau einmal")
            t = t.replace(marke, text)
        fehlend = sorted(set(re.findall(r"\[\[([A-Z_0-9]+)\]\]", t)) - set(werte))
        if fehlend:
            raise ValueError(f"Werte fehlen: {fehlend}")
        return re.sub(r"\[\[([A-Z_0-9]+)\]\]", lambda m: werte[m.group(1)], t)

    artefakt = erzeugen("thema_artefakt.html", "", "")
    (HIER / "heiratsstrafe.html").write_text(artefakt, encoding="utf-8")
    print(f"heiratsstrafe.html: {len(artefakt):,} Zeichen")
    for x in sys.argv[1:]:
        if x.startswith("--soriono="):
            teil = erzeugen("thema_soriono.html", (GEMEINSAM / "soriono_kopf.html").read_text(encoding="utf-8"),
                            (GEMEINSAM / "soriono_fuss.html").read_text(encoding="utf-8"))
            kopf, rumpf = teil.split("<!--RUMPF-->", 1)
            dokument = "\n".join([
                "<!doctype html>", '<html lang="de-CH">', "<head>", '<meta charset="utf-8">',
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">',
                '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
                f'<link rel="canonical" href="https://soriono.ch/analysen/{SEITENPFAD}/">',
                '<meta property="og:type" content="article">',
                '<meta property="og:title" content="Heiratsstrafe-Initiative: Wer zahlt weniger, wer zahlt mehr?">',
                '<meta property="og:description" content="Eine Nachrechnung mit amtlichen Daten zur Abstimmung vom 29. November 2026.">',
                f'<meta property="og:url" content="https://soriono.ch/analysen/{SEITENPFAD}/">',
                kopf, "</head>", "<body>", rumpf, "</body>", "</html>", ""])
            ziel = Path(x.split("=", 1)[1]) / "analysen" / SEITENPFAD / "index.html"
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_text(dokument, encoding="utf-8")
            print(f"{ziel}: {len(dokument):,} Zeichen")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
