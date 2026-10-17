# Wohnungsbau real geschrumpft

Warum entstehen in der Schweiz weniger neue Wohnungen? Zerlegung in nominale Investitionen, Baupreise und
reale Kosten je Wohnung, mit Grossregionen und Kantonen.
Artikel: [soriono.ch/analysen/wohnungsbau-real-geschrumpft](https://soriono.ch/analysen/wohnungsbau-real-geschrumpft/).

## Bausteine

| Datei | Inhalt |
|---|---|
| `bpi.py` | Baupreisindex aus Prelude (Neubau und Renovation Mehrfamilienhaus, Basis Oktober 2020) als Jahresmittel |
| `daten.py` | Panel Kanton × Jahr aus Prelude: Wohnbauinvestitionen nach Neubau und Umbau, Arbeitsvorrat, private Auftraggeber, neue Wohnungen, Bevölkerung |
| `analyse.py` | Zerlegung 2016–2019 gegenüber 2021–2024, Kennzahlen, Grossregionen, Kantone, Robustheit (Bauzeit 1–3 Jahre, Landesindex) |
| `seite/bauen.py` | Artikel aus `seite/vorlage.html` und den Ergebnissen (Artefakt und soriono.ch) |

## Hauptergebnisse

- Reale Investitionen in neue Wohnbauten 2017–2024: −27 % (nominal −14 %); Baupreise 2020–2024: +16 %.
- Neue Wohnungen 2021–2024 gegenüber 2016–2019: −12,5 %, davon Baupreise −9,7 und nominale Investitionen −7,6
  Prozentpunkte; die reale Investition je Wohnung sank leicht (+3,5 Punkte Beitrag).
- Neue Wohnungen je zusätzliche Person: 0,73 (2016–2019) auf 0,47 (2021–2024); in 20 von 23 vergleichbaren
  Kantonen gesunken. Umbauanteil 24 % (2016) auf 30 % (2024); realer Arbeitsvorrat Neubau −19 % gegenüber 2017.

## Nachrechnen

```bash
python analysen/gemeinsam/modell_laden.py wohnungsbau   # veröffentlichtes Prelude laden
cd analysen/wohnungsbau
python daten.py
python analyse.py
python seite/bauen.py --soriono=<pfad>/soriono-web/public
```

Die Analyse entstand mit Claude Opus 5.5 (Anthropic) unter der Leitung von Fabian Bartsch.
