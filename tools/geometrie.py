"""Gemeinsame Geometrie der Modul-Platine (build_board, route_hf, route_power).

Das Modulgehaeuse ist 150 x 150 mm mit 3 x 3 Feldern zu 50 mm, die Platine 147 x 147 mm sitzt
mittig darin (1,5 mm Gehaeusewand je Seite). Die Spulen liegen genau unter den Feldmitten:
in Platinenkoordinaten bei 23,5 / 73,5 / 123,5 mm.
"""
X0, Y0 = 30.0, 30.0            # linke obere Platinenecke auf dem Blatt (absolut)
BOARD = 147.0                  # Platinenkante
FIELDS = 3                     # Felder je Seite
PITCH = 50.0                   # Feldraster im Gehaeuse
FIELD0 = PITCH / 2 - (FIELDS * PITCH - BOARD) / 2    # erste Feldmitte auf der Platine (23,5)

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
    """Spule k (1..9, zeilenweise) in Platinenkoordinaten."""
    return field_center((k - 1) % FIELDS), field_center((k - 1) // FIELDS)


CX = [X0 + field_center(i) for i in range(FIELDS)]    # Spulenmitten absolut (x, gleich fuer y)
STAMM_N = CX[0] + BUS_N        # Bus-Stamm links (absolut, B.Cu)
STAMM_P = CX[0] + BUS_P
