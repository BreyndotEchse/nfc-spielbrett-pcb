"""Schaltplan des 4x4-Moduls (spielbrett_4x4.kicad_sch) aus dem 3x3-Schaltplan erzeugen.

  python tools/schaltplan_4x4.py

Das 4x4-Brett entsteht aus dem 3x3-Brett, indem rechts eine Spalte und oben eine Reihe Felder
angesetzt werden. Die Spulen werden im 4x4-Raster zeilenweise neu nummeriert (ANT1 oben links,
ANT16 unten rechts); die bisherigen 9 Spulen liegen in den Reihen 2-4 / Spalten 1-3.

  * Referenzen je Spule k (1..16): L1kk Spule, Q1kk Schalter Spulenseite, Q2kk Schalter ANT_N,
    R2kk Gate-Widerstand, R3kk Source-Bezug, C3kk Gate-Kondensator (z. B. L101, Q216)
  * Netze je Spule: ANT_SELk, GATEk, SRCk, SWk; Spulenwert ANTk
  * Die 7 neuen Spulengruppen sind Kopien der bisherigen Gruppe 9 (unten auf dem Blatt)
  * Neue Auswahlleitungen an bisher freien MCU-Pins (PC15 bleibt frei):
      ANT_SEL1 PB9, ANT_SEL2 PB8, ANT_SEL3 PB7, ANT_SEL4 PB6 (obere Reihe),
      ANT_SEL8 PA15, ANT_SEL12 PA11, ANT_SEL16 PC14 (rechte Spalte)
"""
import re
import uuid
from pathlib import Path

PRJ = Path(__file__).resolve().parent.parent
SRC = PRJ / "spielbrett.kicad_sch"
DST = PRJ / "spielbrett_4x4.kicad_sch"

OLD_N, NEW_N = 3, 4


def new_k(k_old):
    r, c = divmod(k_old - 1, OLD_N)
    return (r + 1) * NEW_N + c + 1


MAP = {k: new_k(k) for k in range(1, OLD_N * OLD_N + 1)}           # 1->5 ... 9->15
NEW_COILS = sorted(set(range(1, NEW_N * NEW_N + 1)) - set(MAP.values()))
# MCU-Pin (Pin-Endpunkt im Schaltplan) je neuer Auswahlleitung; Seite L = links (Label nach links)
GPIO = {1: ("L", 102.87), 2: ("L", 100.33), 3: ("L", 97.79), 4: ("L", 95.25),
        8: ("R", 102.87), 12: ("R", 92.71), 16: ("L", 72.39)}
PIN_X = {"L": 62.23, "R": 82.55}


def refs(k):
    return {"L": f"L{100 + k}", "Q": f"Q{100 + k}", "QN": f"Q{200 + k}",
            "RG": f"R{200 + k}", "RS": f"R{300 + k}", "C": f"C{300 + k}"}


def old_refs(k):
    return {"L": f"L1{k}", "Q": f"Q{k}", "QN": f"Q1{k}", "RG": f"R2{k}", "RS": f"R3{k}", "C": f"C3{k}"}


def blocks(s):
    """Top-Level-Elemente (Einrueckung ein Tab) als (start, ende)."""
    out = []
    for m in re.finditer(r"^\t\(", s, re.M):
        a = m.start()
        b = s.find("\n\t)\n", a)
        nl = s.find("\n", a)
        if s[a:nl].rstrip().endswith(")"):        # einzeiliges Element
            b = nl
        else:
            b += 3
        out.append((a, b))
    return out


def pts(blk):
    p = re.findall(r"\(xy ([\d.\-]+) ([\d.\-]+)\)", blk) if blk.startswith("\t(wire") else []
    if not p:
        m = re.search(r"\(at ([\d.\-]+) ([\d.\-]+)", blk)
        p = [m.groups()] if m else []
    return [(float(x), float(y)) for x, y in p]


def fmt(v):
    r = round(v, 4)
    return str(int(r)) if r == int(r) else repr(r)


def shift(blk, dx, dy):
    def f(m):
        return f"({m.group(1)} {fmt(float(m.group(2)) + dx)} {fmt(float(m.group(3)) + dy)}"
    return re.sub(r"\((at|xy) ([\d.\-]+) ([\d.\-]+)", f, blk)


def fresh_uuids(blk):
    return re.sub(r'\(uuid "[0-9a-f-]{36}"\)', lambda m: f'(uuid "{uuid.uuid4()}")', blk)


def main():
    s = SRC.read_text(encoding="utf-8").replace("\r\n", "\n")

    # 1) bestehende 9 Spulengruppen umbenennen (gleichzeitig, ohne Verkettung)
    ref_map = {}
    for k_old, k in MAP.items():
        for key, old in old_refs(k_old).items():
            ref_map[old] = refs(k)[key]
    s = re.sub(r'(\(property "Reference" |\(reference )"([^"]+)"',
               lambda m: f'{m.group(1)}"{ref_map.get(m.group(2), m.group(2))}"', s)
    s = re.sub(r'\(global_label "(ANT_SEL|GATE|SRC|SW)(\d+)"',
               lambda m: f'(global_label "{m.group(1)}{MAP[int(m.group(2))]}"', s)
    s = re.sub(r'\(property "Value" "ANT(\d)"', lambda m: f'(property "Value" "ANT{MAP[int(m.group(1))]}"', s)
    s = s.replace('(project "spielbrett"', '(project "spielbrett_4x4"')
    s = re.sub(r'\(title "[^"]*"\)', '(title "Spielbrett-Modul 4x4")', s, count=1)

    # 2) Vorlage: Gruppe der bisherigen Spule 9 (jetzt 15) -- je Bauteil Symbol + Draehte + Labels
    bl = blocks(s)
    tpl_k = MAP[9]
    tpl = {}
    for key, ref in refs(tpl_k).items():
        sym = next((a, b) for a, b in bl if s[a:b].startswith("\t(symbol")
                   and f'(property "Reference" "{ref}"' in s[a:b])
        c = pts(s[sym[0]:sym[1]])[0]
        members = [s[a:b] for a, b in bl
                   if not s[a:b].startswith("\t(lib_symbols")
                   and any(abs(x - c[0]) < 13 and abs(y - c[1]) < 13 for x, y in pts(s[a:b]))]
        tpl[key] = (c, members)

    pwr = max(int(n) for n in re.findall(r'"#PWR(\d+)"', s))
    G = 1.27
    slots = {"RG": (0, 260), "C": (20, 260), "RS": (56, 260), "Q": (0, 292), "QN": (32, 292), "L": (56, 292)}
    add = []
    for j, k in enumerate(NEW_COILS):
        bx = 32 + 88 * j                                          # Rastereinheiten (1,27 mm)
        for key, (c, members) in tpl.items():
            sx, sy = slots[key]
            dx, dy = (bx + sx) * G - c[0], sy * G - c[1]
            for blk in members:
                b = shift(fresh_uuids(blk), dx, dy)
                for kk, ref in refs(tpl_k).items():
                    b = b.replace(f'"{ref}"', f'"{refs(k)[kk]}"')
                b = re.sub(r'"(ANT_SEL|GATE|SRC|SW)%d"' % tpl_k, lambda m: f'"{m.group(1)}{k}"', b)
                b = b.replace(f'"ANT{tpl_k}"', f'"ANT{k}"')
                if '"#PWR' in b:
                    pwr += 1
                    b = re.sub(r'"#PWR\d+"', f'"#PWR{pwr:03d}"', b)
                add.append(b)

    # 3) MCU: freie Pins (No-Connect) durch Draht + Label ANT_SELk ersetzen
    lab = {}
    for side, name in (("L", "ANT_SEL15"), ("R", "ANT_SEL14")):   # vorhandene Labels als Vorlage
        m = re.search(r'\t\(global_label "%s"\n\t\t\(shape bidirectional\)\n\t\t\(at (%s) ([\d.]+)' %
                      (name, "55.88" if side == "L" else "88.9"), s)
        a = m.start()
        lab[side] = (s[a:s.find("\n\t)\n", a) + 3], float(m.group(2)))
    for k, (side, y) in GPIO.items():
        px = PIN_X[side]
        nc = re.search(r'\t\(no_connect\n\t\t\(at %s %s\)\n.*?\n\t\)\n' % (re.escape(f"{px:g}"), re.escape(f"{y:g}")), s)
        if not nc:
            raise SystemExit(f"Kein No-Connect an MCU-Pin {side} y={y}")
        s = s[:nc.start()] + s[nc.end():]
        lx = px - 6.35 if side == "L" else px + 6.35
        add.append(f'\t(wire\n\t\t(pts (xy {px:g} {y:g}) (xy {lx:g} {y:g}))\n'
                   f'\t\t(stroke (width 0) (type solid))\n\t\t(uuid "{uuid.uuid4()}")\n\t)\n')
        blk, y0 = lab[side]
        b = shift(fresh_uuids(blk), 0, y - y0)
        b = re.sub(r'\(global_label "ANT_SEL\d+"', f'(global_label "ANT_SEL{k}"', b)
        add.append(b)

    i = s.index("\t(sheet_instances")
    s = s[:i] + "".join(a if a.endswith("\n") else a + "\n" for a in add) + s[i:]
    DST.write_bytes(s.replace("\n", "\r\n").encode("utf-8"))
    print(f"{DST.name}: {len(NEW_COILS)} neue Spulengruppen ({NEW_COILS}), Umbenennung {MAP}")


if __name__ == "__main__":
    main()
