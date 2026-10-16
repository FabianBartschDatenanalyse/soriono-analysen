# Soriono Analysen

Code und Ergebnisse der Analysen auf [soriono.ch/analysen](https://soriono.ch/analysen/).
Jede Analyse liest nur aus dem offenen Datenmodell der Schweiz, [Prelude](https://soriono.ch/prelude/)
und lässt sich damit vollständig nachrechnen.

| Analyse | Ordner | Artikel |
|---|---|---|
| Gemeindefusionen und Stimmbeteiligung | [`analysen/fusionen-wahlbeteiligung`](analysen/fusionen-wahlbeteiligung) | [Artikel](https://soriono.ch/analysen/fusionen-und-stimmbeteiligung/) |

## Nachrechnen

```bash
uv venv state/analysen-venv --python 3.12
uv pip install --python state/analysen-venv/Scripts/python.exe duckdb==1.4.3 pandas numpy pyfixest matplotlib
state/analysen-venv/Scripts/python analysen/fusionen-wahlbeteiligung/modell_laden.py
```

Die weiteren Schritte stehen im README der jeweiligen Analyse. `modell_laden.py` lädt den aktuellen Stand des
Datenmodells; welcher Stand für die veröffentlichten Ergebnisse verwendet wurde, steht in `ausgabe/modellstand.txt`.

Die Analysen entstehen mit Claude Opus 5.5 (Anthropic) unter der Leitung von Fabian Bartsch; wer was beigetragen
hat, steht in jedem Artikel. Lizenz des Codes: Apache 2.0. Daten: Bundesamt für Statistik.
