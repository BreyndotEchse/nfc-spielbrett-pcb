"""Ausfaecherung am CLRC663 + GND-Vias -- alles, woran der Autorouter scheitert.

Nach tools/route_power.py ausfuehren, KiCad muss geschlossen sein:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/route_escape.py [ausgabe.kicad_pcb]

Alles landet gesperrt in der Gruppe "Escape_Routing"; ein erneuter Lauf ersetzt nur diese Gruppe.

RX     RXN (Pin 13) / RXP (Pin 12) per Via unter den VMID-Pads von R9/R7 hindurch auf B.Cu zum
       Knoten R.1/C.2 (eine Kreuzung VMID <-> RX ist bei dieser Pinfolge topologisch unvermeidbar).
VMID   Pin 14 -> R9.2 -> R7.2 -> rechts hoch -> C13.
AVDD   Pin 9 -> C12.1, DVDD Pin 7 -> C11.1.
SPI    Pins 28-32 gestaffelt nach rechts unten auf Vias (Weiterfuehrung uebernimmt der Autorouter).
GND    Jedes SMD-GND-Pad ohne nahes GND-Via bekommt eines (kurzer Stich), damit die GND-Flaechen
       auf F.Cu und B.Cu sicher zusammenhaengen. GND wird vom Autorouter NICHT verlegt.
"""
import math
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_hf import Router, strip_group, xy  # noqa: E402

PRJ = Path(__file__).resolve().parent.parent
PCB = PRJ / "spielbrett.kicad_pcb"
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PCB
SRC = OUT if OUT.exists() else PCB

F, B = pcbnew.F_Cu, pcbnew.B_Cu
SIG = 0.25
FINE = 0.2                 # zwischen den 0,5-mm-Pins
SMALL_VIA = (0.5, 0.3)     # Minimum laut Platinenregeln
VIA = (0.6, 0.3)
GND_VIA = (0.6, 0.3)
CLEAR = 0.2                # Default/HF-Abstand
HOLE_CLEAR = 0.25


def route_u1(r):
    P, t = r.pad, r.track

    # ---------- VMID: Pin 14 -> R9.2 -> R7.2 -> C13.1 ----------
    p14, r9v, r7v, c13v = P("U1", 14), P("R9", 2), P("R7", 2), P("C13", 1)
    xr = 135.95                                      # Gasse zwischen R7 und C12
    xv = p14[0] + 0.05                               # mittig zwischen TX2 (0,4 mm) und RXN
    t([p14, (xv, 84.0), (xv, r9v[1]), r9v], "RC_VMID", w=FINE)
    t([r9v, r7v, (xr, r7v[1]), (xr, c13v[1]), c13v], "RC_VMID", w=SIG)

    # ---------- RXN: Pin 13 -> Via -> B.Cu -> Via zwischen C23.2 und R9.1 ----------
    p13, r9n, c23n = P("U1", 13), P("R9", 1), P("C23", 2)
    vn = (p13[0] + 0.1, 83.45)
    vn2 = (r9n[0], (r9n[1] + c23n[1]) / 2)
    t([p13, (p13[0], 83.95), vn], "RXN", w=FINE)
    r.via(vn, "RXN", SMALL_VIA)
    t([vn, (vn[0], 82.6), (vn2[0], 82.1), vn2], "RXN", layer=B, w=SIG)
    r.via(vn2, "RXN", SMALL_VIA)
    t([r9n, vn2, c23n], "RXN", w=SIG)

    # ---------- RXP: Pin 12 -> Via -> B.Cu -> Via zwischen C22.2 und R7.1 ----------
    p12, r7p, c22p = P("U1", 12), P("R7", 1), P("C22", 2)
    vp = (p12[0] + 0.35, 83.45)
    vp2 = (r7p[0], (r7p[1] + c22p[1]) / 2)
    t([p12, (p12[0], 83.95), vp], "RXP", w=FINE)
    r.via(vp, "RXP", SMALL_VIA)
    t([vp, (vp2[0], vp[1] - (vp2[0] - vp[0])), vp2], "RXP", layer=B, w=SIG)
    r.via(vp2, "RXP", SMALL_VIA)
    t([r7p, vp2, c22p], "RXP", w=SIG)

    # ---------- AVDD: Pin 9 -> C12.1 (unter der VMID-Gasse durch) ----------
    p9, c12 = P("U1", 9), P("C12", 1)
    t([p9, (p9[0], 83.95), (p9[0] + 0.65, 83.3), (c12[0] - 0.3, 83.3), c12], "RC_AVDD", w=SIG)

    # ---------- DVDD: Pin 7 -> C11.1 (zwischen Pin 6 und C7.2) ----------
    p7, c11 = P("U1", 7), P("C11", 1)
    t([p7, (136.2, p7[1]), (136.2, 86.7), c11], "RC_DVDD", w=FINE)

    # ---------- GND-Pin 26 direkt auf das Masse-Pad (dort sitzen die Vias) ----------
    p26, ep = P("U1", 26), P("U1", 33)
    t([p26, (p26[0], ep[1] + 1.2)], "GND", w=SIG)

    # ---------- SPI/IRQ: gestaffelte Ausfaecherung nach rechts unten ----------
    for i, (pin, net) in enumerate([(32, "RC_IRQ"), (31, "SPI_NSS"), (30, "SPI_MISO"),
                                    (29, "SPI_SCK"), (28, "SPI_MOSI")]):
        p = P("U1", pin)
        y = 90.35 + 0.65 * i
        v = (135.4 + 0.55 * i, y)
        t([p, (p[0], y), v], net, w=SIG)
        r.via(v, net, VIA)


# ------------------------------------------------------------------ GND-Vias
class Obstacles:
    """Grobe Kollisionspruefung: Pads als Rechtecke (Bounding Box), Bahnen als Segmente,
    Vias als Kreise. Konservativ -- lieber ein Via weniger als ein DRC-Fehler."""

    def __init__(self, board):
        self.items = []       # (kind, net, layerset, geom)
        for fp in board.GetFootprints():
            for p in fp.Pads():
                bb = p.GetBoundingBox()
                layers = {L for L in (F, B) if p.IsOnLayer(L)}
                box = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                       pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
                self.items.append(("pad", p.GetNetname(), layers, box))
            for z in fp.Zones():          # Sperrflaechen der Spulen (rund): echte Kontur meiden
                self.items.append(("keep", None, {F, B}, z.Outline()))
        for tr in board.GetTracks():
            self.add_track(tr)
        self.edge = (30.0, 30.0, 177.0, 177.0)

    def add_track(self, tr):
        if tr.GetClass() == "PCB_VIA":
            self.items.append(("via", tr.GetNetname(), {F, B},
                               (*xy(tr.GetPosition()), pcbnew.ToMM(tr.GetWidth(F)) / 2)))
        else:
            self.items.append(("seg", tr.GetNetname(), {tr.GetLayer()},
                               (*xy(tr.GetStart()), *xy(tr.GetEnd()), pcbnew.ToMM(tr.GetWidth()) / 2)))

    @staticmethod
    def _pt_box(px, py, box):
        dx = max(box[0] - px, 0, px - box[2])
        dy = max(box[1] - py, 0, py - box[3])
        return math.hypot(dx, dy)

    @staticmethod
    def _pt_seg(px, py, ax, ay, bx, by):
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy
        u = 0 if L2 == 0 else max(0, min(1, ((px - ax) * vx + (py - ay) * vy) / L2))
        return math.hypot(px - ax - u * vx, py - ay - u * vy)

    def clear_circle(self, c, rad, net, layers, clearance=CLEAR):
        x, y = c
        if not (self.edge[0] + 0.5 + rad <= x <= self.edge[2] - 0.5 - rad and
                self.edge[1] + 0.5 + rad <= y <= self.edge[3] - 0.5 - rad):
            return False
        for kind, n, ls, g in self.items:
            if not (ls & layers):
                continue
            if kind == "keep":
                if g.Collide(pcbnew.VECTOR2I(pcbnew.FromMM(x), pcbnew.FromMM(y)),
                             pcbnew.FromMM(rad + 0.5)):
                    return False
                continue
            if n == net:
                continue
            if kind == "pad":
                d = self._pt_box(x, y, g)
            elif kind == "via":
                d = math.hypot(x - g[0], y - g[1]) - g[2]
            else:
                d = self._pt_seg(x, y, *g[:4]) - g[4]
            if d < rad + clearance:
                return False
        return True

    def clear_segment(self, a, b, half, net, layer):
        n = max(2, int(math.dist(a, b) / 0.05))
        return all(self.clear_circle((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n),
                                     half, net, {layer}) for i in range(n + 1))


def add_gnd_vias(r):
    board = r.b
    obs = Obstacles(board)
    gnd_vias = [xy(v.GetPosition()) for v in board.GetTracks()
                if v.GetClass() == "PCB_VIA" and v.GetNetname() == "GND"]
    added, failed = 0, []
    add = r._add

    def add_and_track(item):           # neue Stiche sofort als Hindernis fuehren
        add(item)
        obs.add_track(item)
    r._add = add_and_track
    for fp in sorted(board.GetFootprints(), key=lambda f: f.GetReference()):
        if fp.GetReference().startswith("L1") and len(fp.GetReference()) == 3:
            continue
        for p in fp.Pads():
            if p.GetNetname() != "GND" or p.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            c = xy(p.GetPosition())
            bb = p.GetBoundingBox()
            own = (pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop()),
                   pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom()))
            reach = max(own[2] - own[0], own[3] - own[1]) / 2 + 0.9
            if any(math.dist(c, v) <= reach for v in gnd_vias):
                continue
            done = False
            rad = GND_VIA[0] / 2
            for i in range(18):                       # naechstgelegene freie Stelle zuerst
                off = 0.5 + 0.15 * i
                for k in range(24):
                    a = 2 * math.pi * k / 24
                    v = (round(c[0] + off * math.cos(a), 3), round(c[1] + off * math.sin(a), 3))
                    if Obstacles._pt_box(*v, own) < rad:      # kein Via im Loetpad
                        continue
                    if not obs.clear_circle(v, rad, "GND", {F, B}, HOLE_CLEAR):
                        continue
                    if not obs.clear_segment(c, v, 0.2, "GND", F):
                        continue
                    r.track([c, v], "GND", layer=F, w=0.4)
                    r.via(v, "GND", GND_VIA)
                    gnd_vias.append(v)
                    added += 1
                    done = True
                    break
                if done:
                    break
            if not done:
                failed.append(f"{fp.GetReference()}.{p.GetNumber()}")
    return added, failed


def main():
    tmp = PRJ / "output/_route_src.kicad_pcb"
    tmp.parent.mkdir(exist_ok=True)
    text, removed = strip_group(SRC.read_text(encoding="utf-8"), "Escape_Routing")
    if removed:
        print(f"Alte Escape_Routing-Gruppe entfernt ({removed} Elemente)")
    tmp.write_text(text, encoding="utf-8")
    board = pcbnew.LoadBoard(str(tmp))
    r = Router(board, "Escape_Routing")
    route_u1(r)
    added, failed = add_gnd_vias(r)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pro = OUT.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(OUT), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)
    tmp.unlink()
    print(f"Escape_Routing: {r.count['tracks']} Leiterbahnstuecke, {r.count['vias']} Vias "
          f"(davon {added} GND-Vias) -> {OUT.name}")
    if failed:
        print("Kein Platz fuer GND-Via an:", ", ".join(failed))


if __name__ == "__main__":
    main()
