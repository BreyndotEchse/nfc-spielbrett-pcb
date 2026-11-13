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

# Schaltergruppe rechts neben jeder Spule (Abstand der Bauteile zur Spulenmitte).
# Gegenueber dem ersten Entwurf 1 mm naeher an der Spule, damit der Antennenbus neben der
# rechten Spalte noch vor die Platinenkante passt.
SW_Q = 16.2                    # BSS138 (Drain fluchtet mit Spulen-Pad 2)
SW_RC = 19.4                   # R3k / C3k / R2k
BUS_N = 20.5                   # Antennenbus-Senkrechte ANT_N (Reihe 1+2)
BUS_P = 21.5                   # Antennenbus-Senkrechte ANT_P
BUS_N3 = 22.5                  # ANT_N der Reihe 3 (eigene Spur neben P)


def field_center(i):
    """Mitte von Feld i (0..FIELDS-1) in Platinenkoordinaten."""
    return FIELD0 + PITCH * i


def coil_center(k):
    """Spule k (1..9, zeilenweise) in Platinenkoordinaten."""
    return field_center((k - 1) % FIELDS), field_center((k - 1) // FIELDS)


CX = [X0 + field_center(i) for i in range(FIELDS)]    # Spulenmitten absolut (x, gleich fuer y)
STAMM_N = CX[0] + BUS_N        # Bus-Stamm links (absolut), Kreuzungen per B.Cu-Bruecke
STAMM_P = CX[0] + BUS_P
