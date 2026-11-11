"""Versorgungs-Routing + enge Stellen am CLRC663 (TVDD, Quarz).

Nach tools/route_hf.py ausfuehren, KiCad muss geschlossen sein:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/route_power.py [ausgabe.kicad_pcb]

Alles landet gesperrt in der Gruppe "Power_Routing"; ein erneuter Lauf ersetzt nur diese Gruppe.
GND wird NICHT verlegt -- das uebernimmt die B.Cu-Flaeche (Freerouting setzt die Vias).

+5V   Ring am Platinenrand (0,8 mm) verbindet alle vier Modulstecker (Durchschleifen zwischen
      Modulen), Abzweig zum Regler U4 und zur TVDD-Option R5.
+3V3  vom Regler zu RS485-Treiber, Mikrocontroller (links) und NFC-Frontend (rechts).
TVDD  R4/R5/C10 -> Via -> B.Cu -> C9 -> Pin 18.
XTAL  Pins 19/20 parallel nach links zum Quarz Y1 und den Lastkondensatoren C14/C15.
Kreuzungen mit dem Antennenbus-Stamm (x = 76/77 mm) und untereinander laufen als kurze
B.Cu-Bruecken.
"""
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from route_hf import Router, strip_group  # noqa: E402

PRJ = Path(__file__).resolve().parent.parent
PCB = PRJ / "spielbrett.kicad_pcb"
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PCB
SRC = OUT if OUT.exists() else PCB

RING = 0.8
PWR = 0.5
NECK = 0.25
PVIA = (0.8, 0.4)
F, B = pcbnew.F_Cu, pcbnew.B_Cu


def route(r):
    P = r.pad
    t = r.track

    def bridge(a, b, net, w=PWR):
        """Kurze B.Cu-Bruecke von a nach b mit Vias an beiden Enden."""
        r.via(a, net, PVIA)
        t([a, b], net, layer=B, w=w)
        r.via(b, net, PVIA)

    # ---------------- +5V ----------------
    j1, j2, j3, j4 = P("J1", 1), P("J2", 1), P("J3", 1), P("J4", 1)
    top, left, bottom, right = 31.0, 31.0, 176.0, 176.1
    t([j1, (j1[0], top)], "+5V", w=RING)
    t([(left, top), (j1[0], top), (right, top), (right, j2[1]), j2], "+5V", w=RING)
    t([(left, top), (left, bottom), (j3[0], bottom), j3], "+5V", w=RING)
    t([j4, (left, j4[1])], "+5V", w=RING)
    # Abzweig zum Regler: unter dem Bus-Stamm per B.Cu-Bruecke
    c1, u4_vi = P("C1", 1), P("U4", 3)
    a, b = (74.6, j4[1]), (79.0, j4[1])
    t([j4, a], "+5V", w=RING)
    bridge(a, b, "+5V", w=RING)
    t([b, (b[0], c1[1] + 0.45), (c1[0], c1[1])], "+5V")
    t([c1, u4_vi], "+5V")
    # zur TVDD-Option R5 (unbestueckt): ostwaerts unter dem Regler, dann B.Cu-Bruecke ueber +3V3
    r5 = P("R5", 1)
    y5 = 82.6
    t([(b[0], c1[1] + 0.45), (b[0] + 0.4, y5), (117.5, y5), (117.5, 97.6)], "+5V")
    bridge((117.5, 97.6), (121.0, 97.6), "+5V")
    t([(121.0, 97.6), (r5[0], 97.6), r5], "+5V")

    # ---------------- +3V3 ----------------
    tab = [p for p in r.b.FindFootprintByReference("U4").Pads()
           if p.GetNumber() == "2"]
    tab = max((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)) for p in tab)
    u4_vo = min((pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y))
                for p in r.b.FindFootprintByReference("U4").Pads() if p.GetNumber() == "2")
    c2 = P("C2", 1)
    t([u4_vo, tab], "+3V3")                       # Pin 2 <-> Kuehllasche (gleiches Pad, getrennte Kupferflaechen)
    t([tab, c2], "+3V3")
    # Ostast: zum NFC-Frontend
    y3 = c2[1]
    t([c2, (119.5, y3), (119.5, 98.8), (138.5, 98.8), (138.5, P("C7", 1)[1]), P("C7", 1)], "+3V3")
    c7, pin8 = P("C7", 1), P("U1", 8)
    t([c7, (c7[0] - 0.9, pin8[1]), pin8], "+3V3", w=NECK)
    r4, c8 = P("R4", 1), P("C8", 1)
    t([(133.2, 98.8), (133.2, r4[1]), r4], "+3V3")
    t([(133.2, r4[1]), (133.2, c8[1]), c8], "+3V3")
    p25, p27 = P("U1", 25), P("U1", 27)
    t([p27, (p27[0], c8[1] - 0.3)], "+3V3", w=NECK)
    t([p25, (p25[0], p25[1] + 0.86), (c8[0] - 0.38, c8[1] - 0.3)], "+3V3", w=NECK)
    # RS485-Treiber: B.Cu-Bruecke unter dem +5V-Abzweig hindurch zu C6/U3
    c6, u3_vcc = P("C6", 1), P("U3", 8)
    v1, v2 = (c2[0] + 0.9, c2[1] + 0.85), (c6[0] + 1.3, c6[1])
    t([c2, v1], "+3V3")
    bridge(v1, v2, "+3V3")
    t([v2, c6], "+3V3")
    t([c6, (c6[0] - 0.9, c6[1]), (c6[0] - 1.2, u3_vcc[1]), u3_vcc], "+3V3")
    # Westast: zum Mikrocontroller (unter dem Bus-Stamm per B.Cu-Bruecke)
    w1, w2 = (u4_vo[0] - 1.85, u4_vo[1]), (74.6, u4_vo[1])
    t([u4_vo, w1], "+3V3")
    bridge(w1, w2, "+3V3")
    c4, c3, pin4, j5, r2 = P("C4", 1), P("C3", 1), P("U2", 4), P("J5", 1), P("R2", 1)
    xw = 38.0
    t([w2, (xw, w2[1]), (xw, j5[1]), j5], "+3V3")
    t([(xw, c4[1]), c4, c3], "+3V3")
    t([(c3[0] + 0.47, c3[1] + 0.08), (pin4[0] - 0.73, pin4[1]), pin4], "+3V3", w=NECK)
    t([(xw, 121.0), (r2[0] + 1.1, 121.0), (r2[0] + 1.1, r2[1]), r2], "+3V3")

    # ---------------- TVDD ----------------
    c9, p18, c10, r4b, r5b = P("C9", 1), P("U1", 18), P("C10", 1), P("R4", 2), P("R5", 2)
    t([p18, (c9[0] + 0.3, p18[1]), c9], "TVDD", w=NECK)
    tv1, tv2 = (c9[0] - 1.1, c9[1]), (128.0, r4b[1])
    t([c9, tv1], "TVDD")
    r.via(tv1, "TVDD", PVIA)
    t([tv1, (tv1[0], tv2[1]), tv2], "TVDD", layer=B)
    r.via(tv2, "TVDD", PVIA)
    t([tv2, r4b], "TVDD")
    t([tv2, c10], "TVDD")
    t([r4b, r5b], "TVDD")

    # ---------------- Quarz ----------------
    p19, p20 = P("U1", 19), P("U1", 20)
    y1_1, y1_3, c14, c15 = P("Y1", 1), P("Y1", 3), P("C14", 1), P("C15", 1)
    xl = y1_1[0] - 1.1                                   # links am Quarz vorbei
    t([p19, (xl, p19[1]), (xl, max(y1_1[1], c14[1]))], "XTAL1", w=NECK)
    t([(xl, y1_1[1]), y1_1], "XTAL1", w=NECK)
    t([(xl, c14[1]), c14], "XTAL1", w=NECK)
    t([p20, (y1_3[0], p20[1]), y1_3], "XTAL2", w=NECK)
    t([(c15[0], p20[1]), c15], "XTAL2", w=NECK)


def main():
    tmp = PRJ / "output/_route_src.kicad_pcb"
    text, removed = strip_group(SRC.read_text(encoding="utf-8"), "Power_Routing")
    if removed:
        print(f"Alte Power_Routing-Gruppe entfernt ({removed} Elemente)")
    tmp.write_text(text, encoding="utf-8")
    board = pcbnew.LoadBoard(str(tmp))
    r = Router(board, "Power_Routing")
    route(r)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pro = OUT.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(OUT), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)
    tmp.unlink()
    print(f"Power_Routing: {r.count['tracks']} Leiterbahnstuecke, {r.count['vias']} Vias -> {OUT.name}")


if __name__ == "__main__":
    main()
