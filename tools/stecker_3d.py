"""Vereinfachte 3D-Modelle (STEP) der Modulkontakte aus der Tabelle FOOTPRINTS in stecker.py.

Benoetigt build123d (nicht in KiCads Python enthalten):
  python -m pip install build123d
  python tools/stecker_3d.py            # schreibt lib/3d/<Footprint>.step

Die Masse stammen aus den Hong-Cheng-Datenblattzeichnungen (HC-CX-*H254-1x6PW-40x0B[-E]).
Das Modell ist eine Naeherung fuer Gehaeusekonstruktion und 3D-Ansicht, kein Herstellermodell:
  * Kontaktteil (vordere 2 mm) als Langloch 24,66 x 4,0 mm mit den zwei Magneten (Ø3)
  * hinterer Teil schmaler, bei -E mit Schraublaschen (Ø1,5, Abstand 25,52) an der Rueckseite
  * Federstifte Ø1,0 mit 1 mm Ueberstand (Federseite) bzw. buendige Kontaktflaechen (Zielseite)
  * Beinchen Ø0,7: aus der Rueckseite auf halber Hoehe, dann 90 deg in die Bohrung
Koordinaten wie im Footprint: Ursprung Bohrung Pin 1, Kontaktseite +x, Pins entlang -y
(KiCad-3D: y zeigt nach oben, im Footprint nach unten), z = 0 Platinenoberseite.
"""
import re
import sys
from pathlib import Path

from build123d import (Axis, Box, Color, Compound, Cylinder, Location, Plane, Pos, Rot,
                       SlotOverall, Sphere, export_step, extrude)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from stecker import FOOTPRINTS, PINS, PITCH  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "lib/3d"
H = 4.0          # Bauhoehe
ZC = H / 2       # Kontakt-/Beinchenachse
FRONT = 2.0      # Tiefe des breiten Kontaktteils
BACK_LEN = 21.5  # Laenge des schmaleren hinteren Teils
BOARD = 1.6


def x_cyl(d, x0, x1, y, z):
    """Zylinder mit Achse x von x0 bis x1."""
    c = Cylinder(d / 2, x1 - x0, rotation=(0, 90, 0))
    return Pos((x0 + x1) / 2, y, z) * c


def model(g):
    yc = -(PINS - 1) * PITCH / 2
    face, back = g["face"], g["back"]
    # Kontaktteil: Langloch in der y-z-Ebene, um FRONT nach -x extrudiert
    plane = Plane(origin=(face - FRONT, yc, ZC), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    body = extrude(plane * SlotOverall(g["length"], H), amount=FRONT)
    body += Pos((back + face - FRONT) / 2, yc, ZC) * Box(face - FRONT - back, BACK_LEN, H)
    if g["ears"]:
        for m in (-1, 1):
            ear_w = (g["ears"] - BACK_LEN) / 2
            ear = Pos(back + 0.5, yc + m * (BACK_LEN / 2 + ear_w / 2), ZC) * Box(1.0, ear_w, H - 1.0)
            body += ear
            body -= x_cyl(1.5, back - 0.1, back + 1.1, yc + m * g["ear_holes"] / 2, ZC)
    magnets = []
    for m in (-1, 1):
        body -= x_cyl(3.0, face - 1.0, face + 0.1, yc + m * g["magnets"] / 2, ZC)
        magnets.append(x_cyl(3.0, face - 1.0, face - 0.05, yc + m * g["magnets"] / 2, ZC))
    metal = []
    for i in range(PINS):
        y = -i * PITCH
        if g["tip"]:
            metal.append(x_cyl(1.0, face - 0.5, g["tip"] - 0.5, y, ZC))
            metal.append(Pos(g["tip"] - 0.5, y, ZC) * Sphere(0.5))
        else:
            metal.append(x_cyl(1.4, face - 0.3, face + 0.02, y, ZC))
        # Beinchen: Rueckseite -> Bohrung -> durch die Platine
        metal.append(x_cyl(0.7, 0, back + 0.3, y, ZC))
        metal.append(Pos(0, y, (ZC - BOARD - 0.3) / 2) * Cylinder(0.35, ZC + BOARD + 0.3))
    body.color = Color(0.08, 0.08, 0.08)
    for s in magnets:
        s.color = Color(0.75, 0.75, 0.78)
    for s in metal:
        s.color = Color(0.85, 0.65, 0.13)
    return Compound(children=[body] + magnets + metal)


_STYLES = "MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION"


def _same(a, b):
    """Gleiche Geometrie und gleiche Farben?

    OpenCascade schreibt die Farbzuordnungen am Dateiende bei jedem Lauf in anderer Reihenfolge
    (und damit mit anderen #-Nummern). Verglichen wird deshalb die Geometrie exakt und der
    Farbteil nur als Menge der Farbwerte."""
    ga, _, sa = a.partition(_STYLES)
    gb, _, sb = b.partition(_STYLES)
    rgb = re.compile(r"COLOUR_RGB\('',([^)]*)\)")
    norm = lambda s: sorted(re.sub(r"\s+", "", m) for m in rgb.findall(s))  # noqa: E731
    return ga == gb and norm(sa) == norm(sb)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, g in FOOTPRINTS.items():
        path = OUT / f"{name}.step"
        tmp = path.with_suffix(".tmp")
        export_step(model(g), str(tmp))
        txt = tmp.read_text(encoding="utf-8")
        tmp.unlink()
        # Zeitstempel im STEP-Kopf festsetzen, damit ein erneuter Lauf identische Dateien erzeugt
        txt = re.sub(r"(FILE_NAME\('[^']*',)'[^']*'", r"\1'2000-01-01T00:00:00'", txt, count=1)
        old = path.read_text(encoding="utf-8") if path.exists() else None
        rel = path.relative_to(OUT.parent.parent)
        if old is not None and _same(old, txt):
            print(f"{rel} (unveraendert)")
            continue
        path.write_text(txt, encoding="utf-8", newline="")
        print(rel)


if __name__ == "__main__":
    main()
