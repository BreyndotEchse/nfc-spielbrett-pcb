"""Erstaufbau der Modul-Platine (147 x 147 mm) aus der Schaltplan-Netzliste.

Mit KiCads eigenem Python ausfuehren, waehrend die Platine NICHT im PCB-Editor offen ist:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/build_board.py

Ablauf:
  1. Netzliste aus spielbrett.kicad_sch exportieren (kicad-cli)
  2. Alle Footprints laden, Referenz/Wert/Netze/Schaltplan-Verknuepfung setzen
  3. Platinenumriss 147 x 147 mm zeichnen
  4. Spulen in die Feldmitten (49-mm-Raster), Schaltergruppen rechts daneben,
     Elektronik-Gruppen in die Freiraeume zwischen den Spulen

Die Schaltplan-Verknuepfung (KIID-Pfad) ist gesetzt, damit "Platine aus Schaltplan
aktualisieren" (F8) die Bauteile spaeter wiedererkennt statt sie doppelt anzulegen.
"""
import re
import subprocess
import sys
from pathlib import Path

import pcbnew

PRJ = Path(__file__).resolve().parent.parent
KICAD = Path("C:/Program Files/KiCad/10.0")
SYS_FP = KICAD / "share/kicad/footprints"
PRJ_FP = {"spielbrett": PRJ / "lib/spielbrett.pretty"}
PCB = PRJ / "spielbrett.kicad_pcb"
OUT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PCB   # optional: Testausgabe
NET = PRJ / "output/spielbrett.net"

BOARD = 147.0
X0, Y0 = 30.0, 30.0          # linke obere Platinenecke auf dem Blatt
PITCH = 49.0                 # Feldraster


def mm(v):
    return pcbnew.FromMM(v)


def export_netlist():
    NET.parent.mkdir(exist_ok=True)
    subprocess.run([str(KICAD / "bin/kicad-cli.exe"), "sch", "export", "netlist", "--format", "kicadsexpr",
                    "-o", str(NET), str(PRJ / "spielbrett.kicad_sch")], check=True, capture_output=True)
    s = NET.read_text(encoding="utf-8")
    comps = {}
    std = {"Footprint", "Datasheet", "Description", "Reference", "Value"}
    for m in re.finditer(r'\(comp\s+\(ref "([^"]+)"\)\s+\(value "([^"]*)"\)\s+\(footprint "([^"]*)"\)(.*?)\(tstamps "([^"]+)"\)', s, re.S):
        ref, val, fp, body, ts = m.groups()
        fields = {k: v for k, v in re.findall(r'\(field\s+\(name "([^"]+)"\)\s*"([^"]*)"\)', body) if k not in std}
        dnp = bool(re.search(r'\(property\s+\(name "dnp"\)', body))
        comps[ref] = {"value": val, "footprint": fp, "uuid": ts, "fields": fields, "dnp": dnp}
    pins = {}
    nets_sec = s[s.index("(nets"):]
    for m in re.finditer(r'\(net\s+\(code "\d+"\)\s+\(name "([^"]*)"\)(.*?)\)\s*(?=\(net\s|\)\s*\)\s*$)', nets_sec, re.S):
        name, body = m.groups()
        for ref, pin in re.findall(r'\(ref "([^"]+)"\)\s*\(pin "([^"]+)"\)', body):
            pins[(ref, pin)] = name
    return comps, pins


def lib_path(nick):
    return str(PRJ_FP.get(nick, SYS_FP / f"{nick}.pretty"))


def coil_center(k):
    return 24.5 + PITCH * ((k - 1) % 3), 24.5 + PITCH * ((k - 1) // 3)


def placement():
    """Ref -> (x, y, rot) in Platinenkoordinaten (relativ zur oberen linken Ecke)."""
    p = {}
    for k in range(1, 10):
        cx, cy = coil_center(k)
        p[f"L1{k}"] = (cx, cy, 0)
        # Schaltergruppe kompakt rechts der Spulenanschluesse (Pads bei x = +13,4 mm).
        # SOT-23 um 180 deg gedreht: Drain (Pin 3) zeigt zur Spule, Gate/Source nach rechts.
        p[f"Q{k}"] = (cx + 17.2, cy + 1.1, 180)    # Drain fluchtet mit Spulen-Pad 2
        p[f"Q1{k}"] = (cx + 17.2, cy + 4.6, 180)   # Drain -> ANT_N
        p[f"R3{k}"] = (cx + 20.4, cy - 0.6, 90)    # Source-Bezug
        p[f"C3{k}"] = (cx + 20.4, cy + 2.6, 90)    # Gate-Source-Kondensator
        p[f"R2{k}"] = (cx + 20.4, cy + 5.8, 90)    # Gate-Widerstand

    def group(ox, oy, items, turn=0):
        """Gruppe mit lokalen Offsets; turn=180 dreht die ganze Gruppe um ihren Ursprung."""
        for ref, (dx, dy, rot) in items.items():
            if turn == 180:
                dx, dy = -dx, -dy
            p[ref] = (ox + dx, oy + dy, (rot + turn) % 360)

    # NFC-Frontend. HVQFN32 bei 0 deg: Pins 1-8 links, 9-16 unten, 17-24 rechts, 25-32 oben.
    # TX2 (15) unten rechts, TX1 (17) rechts unten -> Anpassnetzwerk als zwei senkrechte,
    # symmetrische Ketten darunter (N-Zweig x=+4,0, P-Zweig x=+7,6, Querglieder aussen),
    # Empfangsteiler direkt unter RXP/RXN/VMID, Quarz rechts oben, TVDD-Zufuehrung oben.
    # Raster nach Courtyard-Groessen: 0603 1,46 x 2,96 mm, 0805 1,9 x 3,4 mm (jeweils 90 deg).
    # Lage: oberer Mittelstreifen (zwischen Spulenreihe 1 und 2), um 180 deg gedreht, sodass die
    # Kette nach oben direkt auf den Antennenbus-Ast A (y = 41/42 mm) muendet.
    # Serienglieder (L, C1, Ra) mit 270 deg lokal: Pad 1 zeigt zum Chip.
    group(103.0, 57.0, {
        "U1": (0, 0, 0),
        "C11": (-4.0, -1.1, 90),   # DVDD (Pin 7)
        "C7": (-4.0, 2.0, 90),     # VDD (Pin 8)
        "C12": (-4.0, 5.2, 90),    # AVDD (Pin 9)
        "C8": (1.9, -4.2, 0),      # PVDD (Pin 25)
        "C9": (6.0, 2.5, 270),     # TVDD (Pin 18), oberhalb der XTAL-Ausfuehrung
        "R4": (2.4, -6.6, 0), "R5": (2.4, -8.6, 0), "C10": (6.0, -8.0, 90),
        "Y1": (7.2, -2.6, 180), "C14": (10.4, -5.0, 90), "C15": (4.1, -0.9, 90),
        # Empfangsteiler: Spalte A (x=-0,35) unter RXP, Spalte B (x=-1,9) mit VMID-Kondensator
        "R7": (-0.35, 5.3, 90), "C22": (-0.35, 8.5, 90), "R6": (-0.35, 11.7, 90),
        "C13": (-1.9, 5.3, 90), "R9": (-1.9, 8.5, 90), "C23": (-1.9, 11.7, 90), "R8": (-1.9, 14.9, 90),
        # Anpassnetzwerk: EMV-Filter (L0/C0) -> Serien-C1 -> Parallel-C2 -> Ra -> Antennenbus
        "L2": (4.0, 6.0, 270), "C19": (4.0, 9.6, 270), "R11": (4.0, 12.8, 270),
        "L1": (7.6, 6.0, 270), "C18": (7.6, 9.6, 270), "R10": (7.6, 12.8, 270),
        "C17": (1.9, 7.8, 90), "C21": (1.9, 11.0, 90), "R13": (1.9, 14.2, 90),
        "C16": (9.8, 7.8, 90), "C20": (9.8, 11.0, 90), "R12": (9.8, 14.2, 90),
    }, turn=180)
    # Mikrocontroller. LQFP32: VDD Pin 4, VSS Pin 5, NRST Pin 6 links.
    # Lage: unterer Streifen unter Spule 4 (links vom Bus-Stamm x = 46/47 mm).
    group(25.0, 98.0, {
        "U2": (0, 0, 0),
        "C3": (-6.0, 0.0, 270),    # 100 nF, Pad 1 (+3V3) oben an VDD (Pin 4)
        "C4": (-7.6, 0.0, 270),    # 4,7 uF
        "C5": (-6.0, 3.2, 90),     # NRST
        "R2": (7.5, -4, 90),
        "J5": (-10.5, 4.0, 0), "R1": (6, 7, 0), "D1": (9.5, 7, 0),
    })
    # Versorgung + RS485. SOT-223: VI/GND links, VO rechts (Lasche). SOIC-8: A/B rechts.
    # Lage: linker Senkrechtstreifen rechts neben dem Bus-Stamm.
    group(56.0, 50.0, {
        "U4": (0, -2, 0), "C1": (-5.6, 0.8, 90), "C2": (5.6, -2, 90),
        "U3": (0, 9, 0), "C6": (4.8, 7.1, 90), "R3": (5.0, 10.6, 90), "JP1": (3.0, 14.6, 90),
    })
    # Modulstecker auf den Rasterlinien, gegenueberliegende Seiten fluchten
    p["J1"] = (49.0 - 3.81, 3.0, 270)           # Nord, waagerecht
    p["J3"] = (49.0 - 3.81, BOARD - 3.0, 270)   # Sued, waagerecht
    p["J4"] = (3.0, 49.0 - 3.81, 0)             # West, senkrecht
    p["J2"] = (BOARD - 3.0, 49.0 - 3.81, 0)     # Ost, senkrecht
    return p


def _track(board, a, b, layer, net, width=0.4):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(a)
    t.SetEnd(b)
    t.SetLayer(layer)
    t.SetWidth(mm(width))
    t.SetNet(net)
    t.SetLocked(True)
    board.Add(t)


def add_coil_stubs(board):
    """Feste, gesperrte Anschlussstuecke je Spule, damit Router die Spule nicht anfassen muessen:
       * B.Cu-Rueckleitung: innere Durchkontaktierung (Pad 2) -> aeusseres Pad 2
       * F.Cu: aeusseres Pad 2 -> Drain des spulenseitigen Schalters Qk
       * F.Cu: Pad 1 -> Via ausserhalb der Spule (Anschlusspunkt fuer den ANT_P-Bus)
    """
    for k in range(1, 10):
        coil = board.FindFootprintByReference(f"L1{k}")
        q = board.FindFootprintByReference(f"Q{k}")
        p1 = [p for p in coil.Pads() if p.GetNumber() == "1"][0]
        p2 = sorted([p for p in coil.Pads() if p.GetNumber() == "2"], key=lambda p: p.GetPosition().x)
        inner, outer = p2[0], p2[-1]
        sw = outer.GetNet()
        _track(board, inner.GetPosition(), outer.GetPosition(), pcbnew.B_Cu, sw)
        drain = [p for p in q.Pads() if p.GetNumber() == "3"][0]
        _track(board, outer.GetPosition(), drain.GetPosition(), pcbnew.F_Cu, sw)

        a = p1.GetPosition()
        via_pos = pcbnew.VECTOR2I(a.x + mm(1.6), a.y - mm(2.4))
        _track(board, a, via_pos, pcbnew.F_Cu, p1.GetNet())
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(via_pos)
        v.SetWidth(mm(0.6))
        v.SetDrill(mm(0.3))
        v.SetNet(p1.GetNet())
        v.SetLocked(True)
        board.Add(v)


def add_ground_plane(board, gnd):
    """GND-Flaeche auf B.Cu ueber die ganze Platine. Unter den Spulen verhindern die
    Sperrflaechen der Spulen-Footprints das Fuellen."""
    z = pcbnew.ZONE(board)
    z.SetLayer(pcbnew.B_Cu)
    z.SetNet(gnd)
    z.SetZoneName("GND_B")
    z.SetLocalClearance(mm(0.3))
    z.SetMinThickness(mm(0.25))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    ol = z.Outline()
    ol.NewOutline()
    m = 0.5
    for x, y in [(m, m), (BOARD - m, m), (BOARD - m, BOARD - m), (m, BOARD - m)]:
        ol.Append(mm(X0 + x), mm(Y0 + y))
    board.Add(z)


def main():
    comps, pins = export_netlist()
    # Immer von der leeren Ausgangsplatine (versioniert in tools/) starten, damit das Skript
    # beliebig oft laufen kann. ACHTUNG: verwirft alle Leiterbahnen auf der Projektplatine.
    base = Path(__file__).resolve().parent / "leere_platine.kicad_pcb"
    if not base.exists():
        raise SystemExit(f"Leere Ausgangsplatine fehlt: {base}")
    board = pcbnew.LoadBoard(str(base))
    if board is None:
        raise SystemExit(f"Konnte Ausgangsplatine nicht laden: {base}")

    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    pos = placement()
    missing = []
    for ref, c in sorted(comps.items()):
        nick, name = c["footprint"].split(":", 1)
        fp = pcbnew.FootprintLoad(lib_path(nick), name)
        if fp is None:
            missing.append(f"{ref}: {c['footprint']}")
            continue
        fp.SetFPID(pcbnew.LIB_ID(nick, name))
        fp.SetReference(ref)
        fp.SetValue(c["value"])
        fp.SetPath(pcbnew.KIID_PATH("/" + c["uuid"]))
        for fname, fval in c["fields"].items():
            fp.SetField(fname, fval)
            for fld in fp.GetFields():
                if fld.GetName() == fname:
                    fld.SetVisible(False)          # MPN/LCSC usw. nicht auf den Bestueckungsdruck
        fp.SetDNP(c["dnp"])
        is_coil = len(ref) == 3 and ref.startswith("L1")   # L11..L19 (nicht L1!)
        if not is_coil and not ref.startswith("J"):
            fp.Value().SetVisible(False)               # Werte stehen in Stueckliste/Schaltplan
        if ref == "U1":                                # Druck-Bezeichner kollidiert mit C8
            fp.Reference().SetVisible(False)
        if ref[0] in "RCLQYD" and not is_coil:
            # Kleine Bauteile: Bezeichner- und Wertfeld ausblenden. Sichtbar bleibt nur die
            # kleine ${REFERENCE}-Beschriftung, die die Standard-Footprints im Bauteilkoerper
            # auf F.Fab mitbringen -> keine uebereinanderliegenden Texte im dichten HF-Block.
            fp.Reference().SetVisible(False)
            fp.Value().SetVisible(False)
        board.Add(fp)
        for pad in fp.Pads():
            key = (ref, pad.GetNumber())
            if key in pins:
                pad.SetNet(net(pins[key]))
        x, y, rot = pos.get(ref, (BOARD + 15, 10 + 3 * len(missing), 0))
        if ref not in pos:
            missing.append(f"{ref}: keine Platzierung (neben der Platine abgelegt)")
        fp.SetPosition(pcbnew.VECTOR2I(mm(X0 + x), mm(Y0 + y)))
        fp.SetOrientationDegrees(rot)

    corners = [(0, 0), (BOARD, 0), (BOARD, BOARD), (0, BOARD)]
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_SEGMENT)
        s.SetStart(pcbnew.VECTOR2I(mm(X0 + ax), mm(Y0 + ay)))
        s.SetEnd(pcbnew.VECTOR2I(mm(X0 + bx), mm(Y0 + by)))
        s.SetLayer(pcbnew.Edge_Cuts)
        s.SetWidth(mm(0.1))
        board.Add(s)

    add_coil_stubs(board)
    add_ground_plane(board, net("GND"))

    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    # SaveBoard schreibt auch die .kicad_pro neu (mit den Einstellungen der geladenen
    # Ausgangsplatine) -> Netzklassen/Regeln gingen verloren. Projektdatei sichern + zuruecklegen.
    pro = OUT.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(OUT), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)
    print(f"Footprints: {len(board.GetFootprints())} | Netze: {len(nets)} | Umriss {BOARD}x{BOARD} mm")
    for m in missing:
        print("WARNUNG", m)
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
