"""Letzter Schritt fuer das 4x4-Brett: fertiges Board auf das Zeichenblatt schieben.

Alle Skripte rechnen im Kernrahmen des 3x3-Bretts (siehe geometrie.py); beim 4x4-Brett liegt
die Platinenoberkante deshalb bei y = -20 mm. Dieses Skript verschiebt alles um SHIFT_Y nach
unten (Platinenecke dann bei 30/30) und stellt das Blatt auf A3. Nur EINMAL am Ende der Kette
ausfuehren -- danach passen route_*.py nicht mehr auf das Board (Kette neu ab build_board).

  set SPIELBRETT=4x4
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/verschieben.py [platine.kicad_pcb]
"""
import re
import sys
from pathlib import Path

import pcbnew

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geometrie import NAME, SHIFT_Y, Y0  # noqa: E402

PRJ = Path(__file__).resolve().parent.parent
PCB = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else PRJ / f"{NAME}.kicad_pcb"


def main():
    if not SHIFT_Y:
        print("Nichts zu verschieben (3x3-Brett).")
        return
    board = pcbnew.LoadBoard(str(PCB))
    top = pcbnew.ToMM(board.GetBoardEdgesBoundingBox().GetTop())
    if abs(top - Y0) > 0.5:
        raise SystemExit(f"Platinenoberkante bei y = {top:.2f}, erwartet {Y0:.2f} -- schon verschoben?")
    d = pcbnew.VECTOR2I(0, pcbnew.FromMM(SHIFT_Y))
    for coll in (board.GetFootprints(), board.GetTracks(), board.GetDrawings(), board.Zones()):
        for item in coll:
            item.Move(d)
    board.BuildConnectivity()
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pro = PCB.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(PCB), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)
    # Blattgroesse direkt in der Datei (die Python-API bietet dafuer keinen Setter)
    text = PCB.read_text(encoding="utf-8")
    PCB.write_text(re.sub(r'\(paper "[^"]*"\)', '(paper "A3")', text, count=1), encoding="utf-8")
    print(f"{PCB.name}: um {SHIFT_Y:g} mm nach unten verschoben, Blatt A3")


if __name__ == "__main__":
    main()
