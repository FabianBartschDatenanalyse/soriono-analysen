# Heiratsstrafe-Initiative: Wer zahlt weniger, wer zahlt mehr?

Analyse zur Volksinitiative «Ja zu fairen Bundessteuern auch für Ehepaare» (Abstimmung 29. November 2026),
nur direkte Bundessteuer. Artikel: [soriono.ch/analysen/heiratsstrafe-initiative](https://soriono.ch/analysen/heiratsstrafe-initiative/).

## Bausteine

| Datei | Inhalt |
|---|---|
| `steuer.py` | Direkte Bundessteuer 2026 (Art. 33–36 DBG), Individualbesteuerung (BBl 2025 2033), Initiative in zwei Ausgestaltungen der Botschaft (BBl 2025 1092), unverheiratetes Paar |
| `pruefen.py` | Prüft den Rechner an allen 11'615 Haushaltsbeispielen der ESTV (höchstens 0.50 Fr. Abweichung) |
| `modell.py` | Schätzmodell aller Ehepaare: ESTV-Einkommensverteilung 2022 × BFS-Erwerbsmodelle (SAKE 2025), geeicht auf Zahlen der Bundesverwaltung |
| `auswertung.py` | Verteilung der Entlastung, Kennzahlen zu den Argumenten, Spannen, Robustheit (`--robust`) |
| `seite/bauen.py` | Artikel aus `seite/vorlage.html` und den Ergebnissen (Artefakt und soriono.ch) |
| `quellen/` | Unveränderte Quelldateien von ESTV, BFS, Bundesblatt |

## Hauptergebnisse

- Kosten der Initiative mit der vorgeschriebenen zweiten Berechnung: 0,6 bis 0,9 Mrd. Franken pro Jahr ohne
  Privileg, 1,0 bis 1,3 Mrd. mit Privileg (Botschaft: 0,7 bis 1,4 Mrd.).
- Rund 83 % der Entlastung gehen an Paare mit mehr als 150'000 Franken Einkommen, rund 1 % an das Drittel der
  Paare unter 75'000 Franken.
- In der Umsetzung ohne Privileg zahlten rund 820'000 Ehepaare mehr als heute.
- Mit der Individualbesteuerung zahlen rund 83 % der Einverdiener-Ehepaare mehr als heute.

## Prüfwerte des Modells

| Grösse | Modell | Bundesverwaltung |
|---|---:|---:|
| Mittleres steuerbares Einkommen 2022 | 101'801 | 101'848 |
| Paare mit Zweiverdienerabzug | 855'000 | 856'000 (geeicht) |
| Mehrbelastung ≥ 10 % | 663'000 | 672'000 (geeicht) |
| Minderbelastung ≥ 10 % | 626'000 | 652'000 (geeicht) |
| Kosten ohne / mit Privileg | 0,69 / 1,10 Mrd. | 0,7 / 1,4 Mrd. (nicht geeicht) |

## Nachrechnen

```bash
uv pip install --python state/analysen-venv/Scripts/python.exe pandas numpy openpyxl pyarrow
cd analysen/heiratsstrafe
python pruefen.py            # Rechner gegen ESTV
python modell.py             # Eichung und Simulation, etwa 2 Minuten
python auswertung.py         # Kennzahlen und Spannen
python auswertung.py --robust
python seite/bauen.py --soriono=<pfad>/soriono-web/public
```

Die Analyse entstand mit Claude Opus 5.5 (Anthropic) unter der Leitung von Fabian Bartsch.
