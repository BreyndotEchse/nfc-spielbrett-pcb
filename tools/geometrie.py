"""Gemeinsame Geometrie der Modul-Platine (build_board, route_hf, route_power, route_escape).

Zwei Varianten, Auswahl ueber die Umgebungsvariable SPIELBRETT (Standard "3x3"):
  3x3  spielbrett.kicad_*      Gehaeuse 150 x 150 mm, Platine 147 x 147 mm
  4x4  spielbrett_4x4.kicad_*  Gehaeuse 200 x 200 mm, Platine 197 x 197 mm

Felder zu 50 mm, die Platine sitzt mittig im Gehaeuse (1,5 mm Gehaeusewand je Seite). Die Spulen
liegen genau unter den Feldmitten: in Platinenkoordinaten bei 23,5 / 73,5 / 123,5 (/ 173,5) mm.

Das 4x4-Brett ist das 3x3-Brett mit einer zusaetzlichen Spalte rechts und Reihe oben. Die gesamte
Elektronik (NFC-Frontend, MCU, Versorgung, RS485) bleibt an ihrem Platz relativ zum 3x3-Kern.
Alle Skripte rechnen im "Kernrahmen": dessen linke obere Ecke liegt immer bei (XF, YF) = (30, 30)
absolut, die Platine reicht beim 4x4-Brett oben 50 mm darueber hinaus (Y0 = -20). Der letzte
Schritt tools/verschieben.py schiebt das fertige 4x4-Board dann auf (30, 30).
"""
import os

VARIANTE = os.environ.get("SPIELBRETT", "3x3")
if VARIANTE not in ("3x3", "4x4"):
    raise SystemExit(f"SPIELBRETT={VARIANTE!r}: erlaubt sind 3x3 und 4x4")
FIELDS = int(VARIANTE[0])                # Felder je Seite
NAME = "spielbrett" if FIELDS == 3 else f"spielbrett_{VARIANTE}"   # Projekt-/Dateiname
PITCH = 50.0                             # Feldraster im Gehaeuse
BOARD = FIELDS * PITCH - 3.0             # Platinenkante (147 / 197)
EXTRA = FIELDS - 3                       # zusaetzliche Reihen oben / Spalten rechts
XF, YF = 30.0, 30.0                      # linke obere Ecke des 3x3-Kerns (absolut)
X0, Y0 = XF, YF - PITCH * EXTRA          # linke obere Platinenecke (absolut)
FIELD0 = PITCH / 2 - (FIELDS * PITCH - BOARD) / 2    # erste Feldmitte auf der Platine (23,5)
SHIFT_Y = YF - Y0                        # Endverschiebung (tools/verschieben.py)

# Spule (tools/nfc_coil_gen.py): 30 mm Aussendurchmesser, 4 Windungen, Anschlusspads rechts
COIL = "NFC_Coil_D30_N4_W0.4_S0.4"
COIL_PAD = 16.4                # Anschlusspads bei x = +16,4 mm, y = -1,1 (Pad 1) / +1,1 (Pad 2)

# Schaltergruppe rechts neben jeder Spule (Abstand der Bauteile zur Spulenmitte).
# Die rechte Spalte endet 23,5 mm neben der Spulenmitte an der Platinenkante, deshalb laufen
# die Antennenbus-Senkrechten auf B.Cu UNTER der Schaltergruppe (nicht mehr rechts daneben).
SW_Q = 19.2                    # BSS138 (Drain fluchtet mit Spulen-Pad 2)
SW_RC = 22.4                   # R3k / C3k / R2k
BUS_P = 18.0                   # ANT_P-Senkrechte (B.Cu) = x der Anschluss-Via an Pad 1
P_VIA_DY = -3.5                # y der Anschluss-Via relativ zur Spulenmitte
BUS_N = 20.5                   # ANT_N-Senkrechte (B.Cu), Via unterhalb des ANT_N-Schalters
N_DY = 8.0                     # y der ANT_N-Querbahn/Via unter der Schaltergruppe


def field_center(i):
    """Mitte von Feld i (0..FIELDS-1) in Platinenkoordinaten."""
    return FIELD0 + PITCH * i


def coil_center(k):
    """Spule k (1..FIELDS*FIELDS, zeilenweise von oben links) in Platinenkoordinaten."""
    return field_center((k - 1) % FIELDS), field_center((k - 1) // FIELDS)


CX = [X0 + field_center(i) for i in range(FIELDS)]    # Spulenmitten absolut, Spalten
CY = [Y0 + field_center(j) for j in range(FIELDS)]    # Spulenmitten absolut, Reihen
STAMM_N = CX[0] + BUS_N        # Bus-Stamm links (absolut, B.Cu)
STAMM_P = CX[0] + BUS_P


def refs(k):
    """Referenzen der Spulengruppe k: Spule, Schalter Spulenseite, Schalter ANT_N,
    Gate-Widerstand, Source-Widerstand, Gate-Kondensator."""
    if FIELDS == 3:
        return {"L": f"L1{k}", "Q": f"Q{k}", "QN": f"Q1{k}", "RG": f"R2{k}", "RS": f"R3{k}", "C": f"C3{k}"}
    return {"L": f"L{100 + k}", "Q": f"Q{100 + k}", "QN": f"Q{200 + k}",
            "RG": f"R{200 + k}", "RS": f"R{300 + k}", "C": f"C{300 + k}"}
