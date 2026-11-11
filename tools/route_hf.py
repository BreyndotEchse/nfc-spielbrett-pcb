"""HF-Routing des Spielbrett-Moduls: Anpassnetzwerk am CLRC663 + Antennenbus zu den 9 Spulen.

Mit KiCads Python ausfuehren, waehrend die Platine NICHT im PCB-Editor offen ist:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/route_hf.py [ausgabe.kicad_pcb]

Alle hier erzeugten Leiterbahnen/Vias liegen in der Gruppe "HF_Routing" und sind gesperrt.
Ein erneuter Lauf loescht genau diese Gruppe und legt sie neu an -- von Hand verlegte
Leiterbahnen ausserhalb der Gruppe bleiben unberuehrt.

Topologie Antennenbus (ANT_P / ANT_N als Paar, 1 mm Raster):
  * Ast A (B.Cu) waagerecht zwischen Spulenreihe 1 und 2: N bei y=71, P bei y=72 (absolut)
  * Ast B (B.Cu) waagerecht zwischen Spulenreihe 2 und 3: N bei y=135, P bei y=136
  * Stamm (F.Cu) senkrecht rechts neben Spaltengruppe 1 (x=76 N / 77 P) verbindet A und B
  * je Spule: P von der Anschluss-Via ueber B.Cu nach rechts, dann senkrecht (F.Cu) zum Ast;
    N vom Drain des ANT_N-Schalters nach unten, rechts, dann senkrecht zum Ast
  * Einspeisung: Ausgang des Anpassnetzwerks (R10/R11) direkt auf Ast A
"""
import math
import sys
from pathlib import Path

import pcbnew

PRJ = Path(__file__).resolve().parent.parent
PCB = PRJ / "spielbrett.kicad_pcb"
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PCB
SRC = OUT if OUT.exists() else PCB

X0 = Y0 = 30.0
PITCH = 49.0
CX = [X0 + 24.5 + PITCH * i for i in range(3)]       # Spulenmitten (absolut, mm)
Y_A = (71.0, 72.0)                                    # (N, P) Ast A
Y_B = (135.0, 136.0)                                  # (N, P) Ast B
HF_W = 0.4
NECK_W = 0.25                                         # Einschnuerung an 0,5-mm-Pins
VIA = (0.6, 0.3)


def mm(v):
    return pcbnew.FromMM(v)


def V2(x, y):
    return pcbnew.VECTOR2I(mm(x), mm(y))


def xy(v):
    return pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)


class Router:
    def __init__(self, board, name="HF_Routing"):
        self.b = board
        self.grp = pcbnew.PCB_GROUP(board)
        self.grp.SetName(name)
        board.Add(self.grp)
        self.count = {"tracks": 0, "vias": 0}

    def net(self, name):
        n = self.b.FindNet(name)
        if n is None:
            raise SystemExit(f"Netz {name} nicht gefunden")
        return n

    def _add(self, item):
        item.SetLocked(True)
        self.b.Add(item)
        self.grp.AddItem(item)

    def track(self, pts, netname, layer=pcbnew.F_Cu, w=HF_W):
        n = self.net(netname)
        for a, b in zip(pts, pts[1:]):
            if math.dist(a, b) < 1e-6:
                continue
            t = pcbnew.PCB_TRACK(self.b)
            t.SetStart(V2(*a))
            t.SetEnd(V2(*b))
            t.SetLayer(layer)
            t.SetWidth(mm(w))
            t.SetNet(n)
            self._add(t)
            self.count["tracks"] += 1

    def via(self, p, netname, size=VIA):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(V2(*p))
        v.SetWidth(mm(size[0]))
        v.SetDrill(mm(size[1]))
        v.SetNet(self.net(netname))
        self._add(v)
        self.count["vias"] += 1

    def pad(self, ref, num):
        fp = self.b.FindFootprintByReference(ref)
        for p in fp.Pads():
            if p.GetNumber() == str(num):
                return xy(p.GetPosition())
        raise SystemExit(f"Pad {ref}.{num} fehlt")


def route_matching(r):
    """Anpassnetzwerk. Wegpunkte im lokalen Koordinatensystem von U1 (0 deg, Pins 9-16 unten),
    umgerechnet ueber Lage und Drehung von U1 -- die Geometrie bleibt bei Verschiebung gueltig."""
    u1 = r.b.FindFootprintByReference("U1")
    ox, oy = xy(u1.GetPosition())
    a = math.radians(u1.GetOrientationDegrees())

    def L(x, y):  # lokal -> absolut (KiCad: positive Drehung gegen den Uhrzeigersinn, y nach unten)
        return (ox + x * math.cos(a) + y * math.sin(a), oy - x * math.sin(a) + y * math.cos(a))

    P = r.pad
    # TX1 (Pin 17, rechts unten) -> L1 Pad 1; TX2 (Pin 15, unten rechts) -> L2 Pad 1
    r.track([P("U1", 17), L(3.2, 1.75)], "TX1", w=NECK_W)
    r.track([L(3.2, 1.75), L(3.7, 2.25)], "TX1", w=NECK_W)                       # Abstand zu TVDD
    r.track([L(3.7, 2.25), L(4.7, 3.25), L(5.4, 4.4), L(7.6, 4.4), P("L1", 1)], "TX1")   # frueh nach oben: TVDD/XTAL frei
    r.track([P("U1", 15), L(1.25, 3.6)], "TX2", w=NECK_W)
    r.track([L(1.25, 3.6), L(2.59, 4.94), P("L2", 1)], "TX2")
    # TVSS (Pin 16) direkt per Via auf die GND-Flaeche; Waermeleitung/Masse unter dem EP
    r.track([P("U1", 16), L(2.3, 3.2)], "GND", w=0.25)
    r.via(L(2.3, 3.2), "GND")
    for sx in (-0.7, 0.7):
        for sy in (-0.7, 0.7):
            r.via(L(sx, sy), "GND")

    def on_chain(shunt_pad, chain_pad):
        """Querglied-Pad waagerecht (lokal) auf die senkrechte Kette fuehren."""
        sx, sy = shunt_pad
        cx, cy = chain_pad
        # Kette verlaeuft lokal senkrecht -> Ziel hat die x-Lage der Kette, die y-Lage des Querglieds
        if abs(math.cos(a)) > 0.5:
            return (cx, sy)
        return (sx, cy)

    for side, chain, shunts, gnd_dx in (
        ("N", ("L2", "C19", "R11"), ("C17", "C21", "R13"), -0.95),
        ("P", ("L1", "C18", "R10"), ("C16", "C20", "R12"), +0.95),
    ):
        lc, cc, rc = chain
        emc, match, ant = f"EMC_{side}", f"MATCH_{side}", f"ANT_{side}"
        r.track([P(lc, 2), P(cc, 1)], emc)                     # L0 -> C1
        r.track([P(cc, 2), P(rc, 1)], match)                   # C1 -> Ra
        c0, c2, rb = shunts
        r.track([P(c0, 1), on_chain(P(c0, 1), P(lc, 2))], emc)     # C0 an EMC-Knoten
        r.track([P(c2, 1), on_chain(P(c2, 1), P(cc, 2))], match)   # C2 an MATCH-Knoten
        ext = on_chain(P(rb, 1), P(rc, 2))                          # Ausgang + Vorspannwiderstand
        r.track([P(rc, 2), ext], ant)
        r.track([P(rb, 1), ext], ant)
        for sh in shunts:                                           # Masse-Vias der Querglieder
            g = P(sh, 2)
            lx = (g[0] - ox) * math.cos(a) - (g[1] - oy) * math.sin(a)
            ly = (g[0] - ox) * math.sin(a) + (g[1] - oy) * math.cos(a)
            gv = L(lx + gnd_dx, ly)
            r.track([g, gv], "GND", w=0.4)
            r.via(gv, "GND")
        yield side, ext


def route_bus(r, feeds):
    p_ast_vias = set()
    for i, cx in enumerate(CX):
        for j, cy in enumerate(CX):
            k = 3 * j + i + 1
            p_via = (cx + 15.0, cy - 3.5)                     # vom Aufbauskript gesetzte Via
            drain = r.pad(f"Q1{k}", 3)                        # ANT_N-Schalter
            yN, yP = Y_A if j == 0 else Y_B
            px = cx + 22.5
            nx = cx + 21.5 if j < 2 else cx + 23.5
            # P: Via -> B.Cu nach rechts -> Via -> F.Cu senkrecht zum Ast -> Via
            r.track([p_via, (px, p_via[1])], "ANT_P", layer=pcbnew.B_Cu)
            r.via((px, p_via[1]), "ANT_P")
            r.track([(px, p_via[1]), (px, yP)], "ANT_P")
            # N: Drain -> nach unten -> nach rechts -> senkrecht zum Ast
            r.track([drain, (drain[0], cy + 8.0), (nx, cy + 8.0), (nx, yN)], "ANT_N")
            r.via((nx, yN), "ANT_N")
            p_ast_vias.add((px, yP))                          # Reihe 2+3 teilen sich eine Via
    for p in sorted(p_ast_vias):
        r.via(p, "ANT_P")

    # Stamm links: verbindet Ast A und Ast B (F.Cu)
    r.track([(CX[0] + 21.5, Y_A[0]), (CX[0] + 21.5, CX[1] + 8.0)], "ANT_N")
    r.track([(CX[0] + 22.5, Y_A[1]), (CX[0] + 22.5, CX[1] - 3.5)], "ANT_P")

    # Aeste (B.Cu)
    for (yN, yP) in (Y_A, Y_B):
        n_xs = [CX[0] + 21.5] + [cx + 21.5 for cx in CX] + ([cx + 23.5 for cx in CX] if yN == Y_B[0] else [])
        r.track([(min(n_xs), yN), (max(n_xs), yN)], "ANT_N", layer=pcbnew.B_Cu)
        r.track([(CX[0] + 22.5, yP), (CX[2] + 22.5, yP)], "ANT_P", layer=pcbnew.B_Cu)

    # Einspeisung vom Anpassnetzwerk auf Ast A
    for side, ext in feeds:
        if side == "N":
            tgt = (ext[0], Y_A[0])
            r.track([ext, tgt], "ANT_N")
            r.via(tgt, "ANT_N")
        else:
            r.track([ext, (CX[1] + 22.5, Y_A[1])], "ANT_P")   # auf die vorhandene P-Via der Mitte


def _blocks(s):
    """Top-Level-Bloecke im kicad_pcb (Start, Ende) -- einfache Klammerzaehlung, Strings beachtet."""
    depth, i, start, n = 0, 0, None, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            i += 1
            while i < n and s[i] != '"':
                i += 2 if s[i] == "\\" else 1
        elif c == "(":
            depth += 1
            if depth == 2:
                start = i
        elif c == ")":
            if depth == 2:
                yield start, i + 1
            depth -= 1
        i += 1


def strip_group(text, name):
    """Gruppe `name` samt ihrer Mitglieder aus dem Dateitext entfernen. (Ueber die Python-API
    stuerzt KiCad 10 beim Durchlaufen von Gruppenmitgliedern reproduzierbar ab.)"""
    import re
    cut, members = [], set()
    for a, b in _blocks(text):
        blk = text[a:b]
        if blk.startswith(f'(group "{name}"'):
            cut.append((a, b))
            m = re.search(r"\(members(.*?)\)", blk, re.S)
            members |= set(re.findall(r'"([0-9a-f-]{36})"', m.group(1))) if m else set()
    if not cut:
        return text, 0
    for a, b in _blocks(text):
        blk = text[a:b]
        if blk.startswith(("(segment", "(via", "(arc")):
            u = re.search(r'\(uuid "([0-9a-f-]{36})"\)', blk)
            if u and u.group(1) in members:
                cut.append((a, b))
    for a, b in sorted(cut, reverse=True):
        text = text[:a] + text[b:]
    return text, len(cut) - 1


def main():
    tmp = PRJ / "output/_route_src.kicad_pcb"
    text, removed = strip_group(SRC.read_text(encoding="utf-8"), "HF_Routing")
    if removed:
        print(f"Alte HF_Routing-Gruppe entfernt ({removed} Elemente)")
    tmp.write_text(text, encoding="utf-8")
    board = pcbnew.LoadBoard(str(tmp))
    r = Router(board)
    feeds = list(route_matching(r))
    route_bus(r, feeds)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # SaveBoard schreibt auch die .kicad_pro neu (mit den Einstellungen der geladenen
    # Ausgangsplatine) -> Netzklassen/Regeln gingen verloren. Projektdatei sichern + zuruecklegen.
    pro = OUT.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(OUT), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)
    tmp.unlink()
    print(f"HF_Routing: {r.count['tracks']} Leiterbahnstuecke, {r.count['vias']} Vias -> {OUT.name}")


if __name__ == "__main__":
    main()
