"""Modulkontakte J2 (Ost, Federseite) und J4 (West, Zielseite) auf eine Steckervariante umstellen.

  python tools/stecker.py              # Varianten auflisten
  python tools/stecker.py hc-cx-e      # Variante waehlen

Was passiert:
  1. Die Footprints aller Varianten werden aus der Tabelle unten neu erzeugt (lib/spielbrett.pretty),
     jeweils mit 3D-Modell lib/3d/<Footprint>.step (erzeugt von tools/stecker_3d.py, braucht build123d).
  2. Im Schaltplan bekommen J2/J4 Footprint, MPN und LCSC-Nummer der gewaehlten Variante.

Austausch ohne neues Routing: Alle Footprints haben dasselbe Lochbild mit Ursprung in Pin 1
(6 Bohrungen im 2,54-mm-Raster entlang +y, Kontaktseite zeigt nach +x). Deshalb kann man nach dem
Umstellen einfach in KiCad "Platine aus Schaltplan aktualisieren" (F8) ausfuehren: die Footprints
werden an Ort und Stelle getauscht, die Leiterbahnen bleiben angeschlossen. Alternativ die ganze
Pipeline neu laufen lassen (build_board -> ... -> autoroute).

Lage auf der Platine (build_board.py): Lochreihe EDGE_TO_PIN = 4,15 mm vom Platinenrand. Bei HC-CX
liegt die Kontaktflaeche 5,65 mm vor der Lochreihe, ragt also 1,5 mm ueber die Kante -- genau bis zur
Aussenseite des 150-mm-Modulgehaeuses (Platine 147 mm). Neue Varianten so eintragen, dass ihre
Kontaktflaeche ebenfalls dort liegt (face = 5,65), oder EDGE_TO_PIN anpassen.

Schaltplan und Platine muessen in KiCad geschlossen sein, waehrend das Skript laeuft.
"""
import re
import sys
import uuid
from pathlib import Path

PRJ = Path(__file__).resolve().parent.parent
SCH = PRJ / "spielbrett.kicad_sch"
LIB = PRJ / "lib/spielbrett.pretty"

PITCH = 2.54
PINS = 6

# Footprint-Geometrie in mm, Ursprung = Bohrung Pin 1, Kontaktseite in +x:
#   back   Rueckseite des Gehaeuses (Abstand Lochreihe -> Gehaeuse)
#   face   Kontaktflaeche
#   tip    Spitze der Federstifte (nur Federseite)
#   length Gehaeuselaenge entlang der Kontaktreihe (zentriert)
#   ears   Gesamtbreite mit Schraublaschen (None = ohne), ear_holes Lochabstand der Laschen
FOOTPRINTS = {
    "HC-CX-PH254-1x6PW-4050B-E": dict(kind="Feder", back=1.65, face=5.65, tip=6.65, length=24.66,
                                      ears=28.48, ear_holes=25.52, magnets=18.62),
    "HC-CX-FH254-1x6PW-4040B-E": dict(kind="Ziel", back=1.65, face=5.65, tip=None, length=24.66,
                                      ears=28.48, ear_holes=25.52, magnets=18.62),
    "HC-CX-PH254-1x6PW-4050B": dict(kind="Feder", back=1.65, face=5.65, tip=6.65, length=24.66,
                                    ears=None, ear_holes=None, magnets=18.62),
    "HC-CX-FH254-1x6PW-4040B": dict(kind="Ziel", back=1.65, face=5.65, tip=None, length=24.66,
                                    ears=None, ear_holes=None, magnets=18.62),
}

# Variante -> (J2 Ost/Feder, J4 West/Ziel): (Footprint, MPN, LCSC)
VARIANTS = {
    "hc-cx-e": ("Hong Cheng HC-CX mit Schraublaschen (magnetisch, 3 A)",
                ("spielbrett:HC-CX-PH254-1x6PW-4050B-E", "HC-CX-PH254-1x6PW-4050B-E", "C56314391"),
                ("spielbrett:HC-CX-FH254-1x6PW-4040B-E", "HC-CX-FH254-1x6PW-4040B-E", "C56314419")),
    "hc-cx": ("Hong Cheng HC-CX ohne Laschen (magnetisch, 3 A)",
              ("spielbrett:HC-CX-PH254-1x6PW-4050B", "HC-CX-PH254-1x6PW-4050B", "C56314284"),
              ("spielbrett:HC-CX-FH254-1x6PW-4040B", "HC-CX-FH254-1x6PW-4040B", "C56314412")),
    "platzhalter": ("Platzhalter mit Stiftleisten-Geometrie (kein konkretes Teil)",
                    ("spielbrett:Pogo_Edge_1x06_P2.54mm_Horizontal", "", ""),
                    ("spielbrett:Pogo_Edge_1x06_P2.54mm_Horizontal", "", "")),
}


# ----------------------------------------------------------------------------- Footprints
def _f(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


# UUIDs reproduzierbar aus Footprint-Name + laufender Nummer, damit ein erneuter Lauf
# identische Dateien erzeugt (sonst aendert jeder Lauf alle .kicad_mod im Repo).
_UID = {"name": "", "n": 0}


def _uid():
    _UID["n"] += 1
    return uuid.uuid5(uuid.NAMESPACE_URL, f"spielbrett/{_UID['name']}/{_UID['n']}")


def _line(x1, y1, x2, y2, layer, w=0.1):
    return (f'\t(fp_line (start {_f(x1)} {_f(y1)}) (end {_f(x2)} {_f(y2)}) '
            f'(stroke (width {w}) (type solid)) (layer "{layer}") (uuid "{_uid()}"))\n')


def _rect(x1, y1, x2, y2, layer, w=0.1):
    return (_line(x1, y1, x2, y1, layer, w) + _line(x2, y1, x2, y2, layer, w)
            + _line(x2, y2, x1, y2, layer, w) + _line(x1, y2, x1, y1, layer, w))


def _circle(x, y, r, layer, w=0.1):
    return (f'\t(fp_circle (center {_f(x)} {_f(y)}) (end {_f(x + r)} {_f(y)}) '
            f'(stroke (width {w}) (type solid)) (fill no) (layer "{layer}") (uuid "{_uid()}"))\n')


def _text(kind, txt, x, y, layer, rot=0, hide=False, size=1.0):
    h = " (hide yes)" if hide else ""
    return (f'\t(property "{kind}" "{txt}" (at {_f(x)} {_f(y)} {rot}) (layer "{layer}"){h} '
            f'(uuid "{_uid()}") (effects (font (size {size} {size}) (thickness 0.15))))\n')


def footprint(name, g):
    _UID.update(name=name, n=0)
    yc =(PINS - 1) * PITCH / 2
    half = g["length"] / 2
    half_c = (g["ears"] or g["length"]) / 2
    front = g["tip"] or g["face"]
    s = f'(footprint "{name}"\n\t(version 20240108)\n\t(generator "spielbrett_stecker_py")\n\t(layer "F.Cu")\n'
    s += (f'\t(descr "{g["kind"]}seite, gewinkelt, 1x{PINS} Raster 2,54 mm, magnetisch (Hong Cheng {name}). '
          f'Ursprung Pin 1, Kontaktseite +x, Kontaktflaeche {_f(g["face"])} mm vor der Lochreihe. '
          f'Erzeugt von tools/stecker.py")\n')
    s += '\t(tags "pogo magnetic connector right angle edge")\n'
    s += _text("Reference", "REF**", -2.4, yc, "F.SilkS", rot=90)
    s += _text("Value", name, g["face"] - 2.0, yc, "F.Fab", rot=90, size=0.8)
    s += _text("Datasheet", "", 0, 0, "F.Fab", hide=True)
    s += _text("Description", "", 0, 0, "F.Fab", hide=True)
    s += "\t(attr through_hole)\n"
    # Gehaeuse, Kontaktflaeche, Magnete, Laschen (F.Fab)
    s += _rect(g["back"], yc - half, g["face"], yc + half, "F.Fab")
    for m in (-1, 1):
        s += _circle(g["face"] - 0.3, yc + m * g["magnets"] / 2, 0.3, "F.Fab")
    if g["ears"]:
        for m in (-1, 1):
            s += _rect(g["back"], yc + m * half, g["back"] + 2.0, yc + m * g["ears"] / 2, "F.Fab")
            s += _line(g["back"] + 1.0, yc + m * g["ear_holes"] / 2 - 0.75,
                       g["back"] + 1.0, yc + m * g["ear_holes"] / 2 + 0.75, "F.Fab")
    if g["tip"]:
        for i in range(PINS):
            s += _line(g["face"], i * PITCH, g["tip"], i * PITCH, "F.Fab", 0.2)
    # Kontaktflaeche als Kantenmarke (Dwgs.User): soll 1,5 mm vor der Platinenkante liegen
    s += _line(g["face"], yc - half, g["face"], yc + half, "Dwgs.User", 0.15)
    # Bestueckungsdruck nur innerhalb der Platine: Pin-1-Marke
    s += _line(-1.3, -0.9, -1.3, 0.9, "F.SilkS", 0.15)
    # Courtyard
    s += _rect(-1.25, yc - half_c - 0.25, front + 0.25, yc + half_c + 0.25, "F.CrtYd", 0.05)
    for i in range(PINS):
        shape = "rect" if i == 0 else "circle"
        s += (f'\t(pad "{i + 1}" thru_hole {shape} (at 0 {_f(i * PITCH)}) (size 1.7 1.7) (drill 1) '
              f'(layers "*.Cu" "*.Mask") (remove_unused_layers no) (uuid "{_uid()}"))\n')
    # 3D-Modell aus tools/stecker_3d.py (gleiche Koordinaten wie der Footprint, kein Versatz)
    s += (f'\t(model "${{KIPRJMOD}}/lib/3d/{name}.step"\n\t\t(offset (xyz 0 0 0))\n'
          '\t\t(scale (xyz 1 1 1))\n\t\t(rotate (xyz 0 0 0))\n\t)\n')
    s += ")\n"
    return s


def write_footprints():
    for name, g in FOOTPRINTS.items():
        (LIB / f"{name}.kicad_mod").write_text(footprint(name, g), encoding="utf-8")


# ----------------------------------------------------------------------------- Schaltplan
def _set_prop(block, name, value, at):
    pat = re.compile(r'(\(property "' + re.escape(name) + r'" )"[^"]*"')
    if pat.search(block):
        return pat.sub(lambda m: m.group(1) + '"' + value + '"', block, count=1)
    prop = (f'\t\t(property "{name}" "{value}"\n\t\t\t(at {at})\n'
            f'\t\t\t(effects (font (size 1.27 1.27)) (hide yes))\n\t\t)\n')
    i = block.index("\t\t(instances")
    return block[:i] + prop + block[i:]


def set_schematic(variant):
    s = SCH.read_text(encoding="utf-8")
    _, j2, j4 = VARIANTS[variant]
    for ref, (fp, mpn, lcsc) in (("J2", j2), ("J4", j4)):
        m = None
        for m in re.finditer(r'\n\t\(symbol\n\t\t\(lib_id "[^"]+"\)\n\t\t\(at ([\d.\- ]+)\).*?\n\t\)', s, re.S):
            if f'(property "Reference" "{ref}"' in m.group(0):
                break
        else:
            raise SystemExit(f"{ref} nicht im Schaltplan gefunden")
        block = m.group(0)
        at = m.group(1)
        block = _set_prop(block, "Footprint", fp, at)
        block = _set_prop(block, "MPN", mpn, at)
        block = _set_prop(block, "LCSC", lcsc, at)
        s = s[:m.start()] + block + s[m.end():]
        print(f"{ref}: {fp}  MPN {mpn or '-'}  LCSC {lcsc or '-'}")
    SCH.write_text(s, encoding="utf-8")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in VARIANTS:
        print("Varianten:")
        for k, (desc, *_) in VARIANTS.items():
            print(f"  {k:<12} {desc}")
        return 1
    write_footprints()
    set_schematic(sys.argv[1])
    print("Footprints erzeugt in lib/spielbrett.pretty. In KiCad: Platine aus Schaltplan aktualisieren (F8).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
