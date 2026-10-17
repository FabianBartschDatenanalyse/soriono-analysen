# Einbürgerung und Wohnort

Wie stark hängt die Einbürgerung seit dem Bürgerrechtsgesetz von 2018 vom Abstimmungsklima der Gemeinde ab?
Artikel: [soriono.ch/analysen/einbuergerung-und-wohnort](https://soriono.ch/analysen/einbuergerung-und-wohnort/).

## Bausteine

| Datei | Inhalt |
|---|---|
| `daten.py` | Panel Gemeinde × Jahr 2011–2025 aus Prelude: Einbürgerungen nach Herkunftsgruppe, ausländische Bevölkerung, Ja-Anteile zu fünf Vorlagen, Einwanderungswellen, Einkommen 2016 |
| `analyse.py` | Differenz der Differenzen mit stetiger Behandlung (Ja-Anteil 2014 × ab 2018), Ereignisstudie, Fünftel, Herkunft, Robustheit |
| `kontext.py` | Landeszahlen nach Staatsangehörigkeit und Art des Erwerbs direkt beim BFS (px-x-0103030100_101, noch nicht in Prelude) |
| `seite/bauen.py` | Artikel aus `seite/vorlage.html` und den Ergebnissen (Artefakt und soriono.ch) |

## Hauptergebnisse

- Bis 2017 kein Zusammenhang zwischen Ja-Anteil zur Masseneinwanderungsinitiative und Einbürgerungsquote
  innerhalb eines Kantons (Placebo-Bruch 2015: −0,05, Intervall enthält 0).
- Ab 2018 je 10 Prozentpunkte mehr Ja −0,16 Einbürgerungen je 100 Ausländerinnen und Ausländer (−9 %),
  in jedem Jahr 2018–2025.
- Der Unterschied entsteht ganz bei Personen aus EU/EFTA (−18 %); übriges Europa und ausserhalb Europas: 0.
- Etwa die Hälfte hängt mit Einkommen, Grösse und Ausländeranteil der Gemeinde zusammen; mit allen
  Kontrollen −0,065 (Intervall enthält knapp 0).

## Nachrechnen

```bash
python analysen/gemeinsam/modell_laden.py einbuergerung   # veröffentlichtes Prelude laden, etwa 2 Minuten
cd analysen/einbuergerung
python daten.py
python analyse.py
python kontext.py
python seite/bauen.py --soriono=<pfad>/soriono-web/public
```

Benötigt `duckdb`, `pandas`, `pyarrow`, `pyfixest`. Die Analyse entstand mit Claude Opus 5.5 (Anthropic)
unter der Leitung von Fabian Bartsch.
