"""Netzklassen und Design-Regeln in spielbrett.kicad_pro eintragen.

Nur ausfuehren, wenn das Projekt in KiCad GESCHLOSSEN ist (KiCad ueberschreibt die
.kicad_pro beim Schliessen). Werte fuer guenstige Standardfertigung (2 Lagen, 1,6 mm).

  python tools/apply_rules.py
"""
import json
import sys
from pathlib import Path

PRO = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "spielbrett.kicad_pro"

# name: (Leiterbahn, Abstand, Via-Durchmesser, Via-Bohrung, Netzmuster, Prioritaet)
CLASSES = {
    "HF": (0.4, 0.2, 0.6, 0.3,   # Abstand 0,2: CLRC663-Pins haben selbst nur 0,23 mm Luft
           ["TX1", "TX2", "EMC_P", "EMC_N", "MATCH_P", "MATCH_N", "ANT_P", "ANT_N", "SW*"], 1),
    "Versorgung": (0.5, 0.2, 0.8, 0.4, ["VBUS", "+5V", "+3V3", "GND", "TVDD"], 2),
    "RS485": (0.3, 0.2, 0.6, 0.3, ["RS485_A", "RS485_B", "RS485_A_RET", "RS485_B_RET"], 3),
}


def main():
    d = json.loads(PRO.read_text(encoding="utf-8"))
    ns = d.setdefault("net_settings", {})
    default = next(c for c in ns["classes"] if c["name"] == "Default")
    default.update({"track_width": 0.25, "clearance": 0.2, "via_diameter": 0.6, "via_drill": 0.3})

    classes = [default]
    patterns = []
    for name, (tw, cl, vd, vdr, pats, prio) in CLASSES.items():
        c = dict(default)
        c.update({"name": name, "track_width": tw, "clearance": cl,
                  "via_diameter": vd, "via_drill": vdr, "priority": prio})
        classes.append(c)
        patterns += [{"netclass": name, "pattern": p} for p in pats]
    ns["classes"] = classes
    ns["netclass_patterns"] = patterns

    rules = d["board"]["design_settings"]["rules"]
    rules.update({
        "min_clearance": 0.15,
        "min_track_width": 0.125,   # 5 mil: Standardfertigung, Freerouting nutzt das an engen Pins
        "min_copper_edge_clearance": 0.5,
        "min_through_hole_diameter": 0.3,
        "min_via_diameter": 0.5,
        "min_via_annular_width": 0.1,
        "min_hole_clearance": 0.25,
    })
    PRO.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for c in classes:
        print(f"{c['name']:<11} Bahn {c['track_width']} mm, Abstand {c['clearance']} mm, "
              f"Via {c['via_diameter']}/{c['via_drill']} mm")
    print(f"{len(patterns)} Netzmuster zugeordnet")


if __name__ == "__main__":
    main()
