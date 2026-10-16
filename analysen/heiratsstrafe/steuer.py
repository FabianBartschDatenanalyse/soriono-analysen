"""Direkte Bundessteuer 2026 für natürliche Personen (Einkommenssteuer), nach Art. 33–36 DBG.

Tarife: ESTV Formular 58c-2026 (quellen/kantone/ne-bareme-ifd-pp-2026.pdf), jede Stufe aus den
Tabellenwerten rekonstruiert. Abzüge: ESTV Rundschreiben 2-215-D-2025 (Steuerjahr 2026).
Der Rechner ist so eingestellt, dass er die Haushaltsbeispiele der ESTV zur Individualbesteuerung
(quellen/estv/tax-burden-*.xlsx) trifft; `pruefen.py` beweist das.

Einkommen bedeutet hier wie bei der ESTV das Reineinkommen vor Sozialabzügen und vor den
Abzügen für Versicherungsprämien und Zweiverdiener (Erwerbseinkommen nach Berufskosten).
"""
from __future__ import annotations

import math

# (Beginn der Stufe, Steuer bei Beginn, Franken je weitere 100 Franken)
GRUNDTARIF = [(15_200, 0.0, 0.77), (33_200, 138.60, 0.88), (43_500, 229.20, 2.64), (58_000, 612.00, 2.97),
              (76_200, 1_152.50, 5.94), (82_100, 1_502.95, 6.60), (108_900, 3_271.75, 8.80),
              (141_500, 6_140.55, 11.00), (185_100, 10_936.55, 13.20)]
VERHEIRATETENTARIF = [(29_700, 0.0, 1.00), (53_400, 237.0, 2.00), (61_300, 395.0, 3.00), (79_100, 929.0, 4.00),
                      (94_900, 1_561.0, 5.00), (108_700, 2_251.0, 6.00), (120_600, 2_965.0, 7.00),
                      (130_500, 3_658.0, 8.00), (138_400, 4_290.0, 9.00), (144_300, 4_821.0, 10.00),
                      (148_300, 5_221.0, 11.00), (150_400, 5_452.0, 12.00), (152_400, 5_692.0, 13.00)]
HOECHSTSATZ = 0.115
MINDESTBETRAG = 25.0
# Nur für die Prüfung gegen die ESTV-Beispiele: Deren Modell rechnet den Tarif stetig, ohne das
# Einkommen auf 100 Franken und die Steuer auf 5 Rappen abzurunden. Das Gesetz rundet ab (Standard).
STETIG = False

ABZUG_KIND = 6_800            # Art. 35 Abs. 1 Bst. a
ABZUG_VERHEIRATET = 2_800     # Art. 35 Abs. 1 Bst. c
ABZUG_STEUERBETRAG_KIND = 263  # Art. 36 Abs. 2bis
ZWEIVERDIENER_MIN, ZWEIVERDIENER_MAX = 8_600, 14_100  # Art. 33 Abs. 2
VERSICHERUNG_VERHEIRATET, VERSICHERUNG_UEBRIGE, VERSICHERUNG_KIND = 3_700, 1_800, 700  # Art. 33 Abs. 1 Bst. g


def tarif(steuerbar: float, stufen: list[tuple[int, float, float]]) -> float:
    """Jahressteuer nach Tarif: Einkommen auf 100 Franken abgerundet, Steuer auf 5 Rappen abgerundet."""
    y = round(max(steuerbar, 0), 2)  # Excel-Werte wie 329'999.9999 nicht eine Stufe tiefer
    if not STETIG:
        y = math.floor(y / 100) * 100
    steuer = 0.0
    for beginn, basis, satz in stufen:
        if y >= beginn:
            steuer = basis + satz * (y - beginn) / 100
    steuer = min(steuer, HOECHSTSATZ * y)
    return steuer if STETIG else math.floor(round(steuer * 20, 6)) / 20


def erheben(steuer: float) -> float:
    """Steuerbeträge unter 25 Franken werden nicht erhoben (Art. 36 Abs. 3 DBG)."""
    return 0.0 if steuer < MINDESTBETRAG else steuer


def zweiverdienerabzug(zweiteinkommen: float) -> float:
    """50 % des niedrigeren Erwerbseinkommens, mindestens 8'600 und höchstens 14'100 Franken; nie mehr als das Einkommen."""
    if zweiteinkommen <= 0:
        return 0.0
    return min(zweiteinkommen, max(ZWEIVERDIENER_MIN, min(ZWEIVERDIENER_MAX, 0.5 * zweiteinkommen)))


def ehepaar(einkommen_1: float, einkommen_2: float, kinder: int = 0, zweiverdiener: bool = True) -> float:
    """Gemeinsame Veranlagung nach geltendem Recht (Verheiratetentarif, Elterntarif mit Kindern)."""
    y = round(einkommen_1 + einkommen_2, 2)
    abzuege = (VERSICHERUNG_VERHEIRATET + VERSICHERUNG_KIND * kinder + ABZUG_VERHEIRATET + ABZUG_KIND * kinder
               + (zweiverdienerabzug(min(einkommen_1, einkommen_2)) if zweiverdiener else 0))
    steuer = tarif(y - abzuege, VERHEIRATETENTARIF)
    return erheben(max(0.0, steuer - ABZUG_STEUERBETRAG_KIND * kinder))


def unverheiratet(einkommen: float, kinder: float = 0, elterntarif: bool | None = None,
                  steuerbetrag_kinder: float | None = None) -> float:
    """Einzelperson nach geltendem Recht.

    kinder: Kinder, für die diese Person den Kinderabzug geltend macht (bei hälftiger Aufteilung 0.5 je Kind).
    elterntarif: Verheiratetentarif für Personen mit Kindern im Haushalt (Standard: wenn kinder > 0).
    steuerbetrag_kinder: Kinder für den Abzug vom Steuerbetrag (Standard: kinder, falls Elterntarif).
    """
    if elterntarif is None:
        elterntarif = kinder > 0
    abzuege = VERSICHERUNG_UEBRIGE + VERSICHERUNG_KIND * kinder + ABZUG_KIND * kinder
    steuer = tarif(einkommen - abzuege, VERHEIRATETENTARIF if elterntarif else GRUNDTARIF)
    if steuerbetrag_kinder is None:
        steuerbetrag_kinder = kinder if elterntarif else 0
    return erheben(max(0.0, steuer - ABZUG_STEUERBETRAG_KIND * steuerbetrag_kinder))


# Individualbesteuerung (BG vom 20. Juni 2025, BBl 2025 2033; in Kraft ab 2032), Stand der Beträge wie
# im Gesetz. Ein Einheitstarif für alle; Kinderabzug und Abzug vom Steuerbetrag je hälftig auf die Eltern.
EINHEITSTARIF = [(20_000, 0.0, 0.70), (34_300, 100.10, 0.90), (44_800, 194.60, 2.00), (59_800, 494.60, 3.30),
                 (78_600, 1_115.0, 7.00), (84_600, 1_535.0, 8.00), (112_200, 3_743.0, 9.50), (145_800, 6_935.0, 11.70),
                 (190_800, 12_200.0, 13.30), (732_100, 84_191.50, 11.50)]
NEU_ABZUG_KIND = 12_000
NEU_ABZUG_STEUERBETRAG_KIND = 259
NEU_VERSICHERUNG, NEU_VERSICHERUNG_KIND = 1_800, 700


def individuell(einkommen: float, kinder_anteil: float = 0) -> float:
    """Eine Person unter der Individualbesteuerung; kinder_anteil = Kinder × Anteil am Abzug (0.5 bei hälftiger Teilung)."""
    abzuege = NEU_VERSICHERUNG + (NEU_VERSICHERUNG_KIND + NEU_ABZUG_KIND) * kinder_anteil
    steuer = tarif(einkommen - abzuege, EINHEITSTARIF)
    return erheben(max(0.0, steuer - NEU_ABZUG_STEUERBETRAG_KIND * kinder_anteil))


def ehepaar_individuell(einkommen_1: float, einkommen_2: float, kinder: int = 0) -> tuple[float, float]:
    """Ehepaar unter der Individualbesteuerung: beide getrennt, gemeinsame Kinder je hälftig."""
    return individuell(einkommen_1, kinder / 2), individuell(einkommen_2, kinder / 2)


# Initiative «Ja zu fairen Bundessteuern auch für Ehepaare» (Abstimmung 29. November 2026):
# Das Ehepaar zahlt den tieferen von zwei Beträgen, der gemeinsamen Veranlagung oder einer alternativen
# Berechnung wie für zwei Unverheiratete (Art. 197 Ziff. 15 BV-Entwurf; Botschaft BBl 2025 1092, Ziff. 4.2.3).
# Die Botschaft rechnet mit zwei Ausgestaltungen, die die Spanne der Kosten bestimmen:
#   «mit_privileg»  (≈ 1,4 Mrd. Mindereinnahmen): geltende Abzüge der Ehepaare bleiben; in der alternativen
#                   Berechnung erhält die Person mit dem höheren Einkommen den Elterntarif und den Kinderabzug,
#                   so wie heute bei einem unverheirateten Paar mit gemeinsamen Kindern.
#   «ohne_privileg» (≈ 0,7 Mrd.): Zweiverdiener- und Verheiratetenabzug fallen weg; alle Unverheirateten
#                   zahlen den Grundtarif, Kinderabzug und Abzug vom Steuerbetrag je hälftig.
# Den neuen Einverdienerabzug der Variante mit Privileg beziffert die Botschaft nicht; er fehlt hier
# (das unterschätzt die Entlastung von Einverdiener-Ehepaaren in dieser Variante leicht).


def alternative_berechnung(einkommen_1: float, einkommen_2: float, kinder: int, variante: str) -> float:
    hoch, tief = max(einkommen_1, einkommen_2), min(einkommen_1, einkommen_2)
    if variante == "mit_privileg":
        return unverheiratet(hoch, kinder) + unverheiratet(tief, 0)
    if variante == "ohne_privileg":
        halb = kinder / 2
        return (unverheiratet(hoch, halb, elterntarif=False, steuerbetrag_kinder=halb)
                + unverheiratet(tief, halb, elterntarif=False, steuerbetrag_kinder=halb))
    raise ValueError(variante)


def ehepaar_initiative(einkommen_1: float, einkommen_2: float, kinder: int = 0, variante: str = "mit_privileg",
                       zweiverdiener: bool = True) -> float:
    """Steuer eines Ehepaars mit der Initiative: das Minimum aus gemeinsamer und alternativer Berechnung."""
    if variante == "mit_privileg":
        gemeinsam = ehepaar(einkommen_1, einkommen_2, kinder, zweiverdiener)
    else:  # Ehepaar-Abzüge (Zweiverdiener, Verheiratet) fallen weg
        y = round(einkommen_1 + einkommen_2, 2)
        abzuege = VERSICHERUNG_VERHEIRATET + VERSICHERUNG_KIND * kinder + ABZUG_KIND * kinder
        gemeinsam = erheben(max(0.0, tarif(y - abzuege, VERHEIRATETENTARIF) - ABZUG_STEUERBETRAG_KIND * kinder))
    return min(gemeinsam, alternative_berechnung(einkommen_1, einkommen_2, kinder, variante))


def konkubinat(einkommen_1: float, einkommen_2: float, kinder: int = 0) -> float:
    """Unverheiratetes Paar in gleichen Verhältnissen nach geltendem Recht (gemeinsame Kinder beim höheren Einkommen)."""
    hoch, tief = max(einkommen_1, einkommen_2), min(einkommen_1, einkommen_2)
    return unverheiratet(hoch, kinder) + unverheiratet(tief, 0)
