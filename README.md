# Soriono Analysen

Code und Ergebnisse der Analysen auf [soriono.ch/analysen](https://soriono.ch/analysen/).
Die Analysen lesen aus dem offenen Datenmodell der Schweiz, [Prelude](https://soriono.ch/prelude/), oder aus
den amtlichen Quelldateien im jeweiligen Ordner, und lassen sich damit vollständig nachrechnen.

| Analyse | Ordner | Artikel |
|---|---|---|
| Wohnungsbau real um ein Viertel geschrumpft (Wirtschaft) | [`analysen/wohnungsbau`](analysen/wohnungsbau) | [Artikel](https://soriono.ch/analysen/wohnungsbau-real-geschrumpft/) |
| Einbürgerung und Wohnort seit dem Bürgerrecht 2018 (Gesellschaft) | [`analysen/einbuergerung`](analysen/einbuergerung) | [Artikel](https://soriono.ch/analysen/einbuergerung-und-wohnort/) |
| Heiratsstrafe-Initiative: Wer zahlt weniger, wer zahlt mehr? | [`analysen/heiratsstrafe`](analysen/heiratsstrafe) | [Artikel](https://soriono.ch/analysen/heiratsstrafe-initiative/) |
| Gemeindefusionen und Stimmbeteiligung | [`analysen/fusionen-wahlbeteiligung`](analysen/fusionen-wahlbeteiligung) | [Artikel](https://soriono.ch/analysen/fusionen-und-stimmbeteiligung/) |

## Nachrechnen

```bash
uv venv state/analysen-venv --python 3.12
uv pip install --python state/analysen-venv/Scripts/python.exe duckdb==1.4.3 pandas numpy pyfixest matplotlib
state/analysen-venv/Scripts/python analysen/gemeinsam/modell_laden.py einbuergerung   # Ordnername der Analyse
```

Die weiteren Schritte stehen im README der jeweiligen Analyse. `modell_laden.py` lädt den aktuellen Stand des
Datenmodells; welcher Stand für die veröffentlichten Ergebnisse verwendet wurde, steht in `ausgabe/modellstand.txt`.

Die Analysen entstehen mit Claude Opus 5.5 (Anthropic) unter der Leitung von Fabian Bartsch; wer was beigetragen
hat, steht in jedem Artikel. Lizenz des Codes: Apache 2.0. Daten: Bundesamt für Statistik, Eidgenössische Steuerverwaltung.
