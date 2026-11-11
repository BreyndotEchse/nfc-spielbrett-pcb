#!/usr/bin/env python3
"""NFC-Spulen-Footprint-Generator fuer das Spielbrett-Modul.

Erzeugt eine runde (archimedische) Leiterbahnspule als KiCad-Footprint:
  * Spirale auf F.Cu (Oberseite, Richtung Spielfigur)
  * Rueckleitung vom inneren Ende auf B.Cu zum aeusseren Anschluss (als Leiterbahn auf der
    Platine, angelegt von tools/build_board.py)
  * Pad 1 = aeusseres Spiralende, Pad 2 = Rueckleitung (aussen) + Durchkontaktierung innen
  * net_tie_pad_groups "1,2", damit DRC die Kupfergrafik zwischen den Pads akzeptiert
  * Sperrflaeche (keine Kupferflaechen/Masse) unter der Spule auf beiden Lagen

Aufruf:
  python nfc_coil_gen.py                       # Standardwerte
  python nfc_coil_gen.py --d-out 24 --turns 5 --width 0.4 --gap 0.4
"""
import argparse
import math
import uuid
from pathlib import Path

MU0 = 4e-7 * math.pi


def inductance_mohan_circular(d_out_mm, d_in_mm, turns):
    """Mohan current-sheet approximation for circular planar spirals [H]."""
    d_avg = (d_out_mm + d_in_mm) / 2 * 1e-3
    rho = (d_out_mm - d_in_mm) / (d_out_mm + d_in_mm)
    c1, c2, c3, c4 = 1.00, 2.46, 0.00, 0.20
    return MU0 * turns**2 * d_avg * c1 / 2 * (math.log(c2 / rho) + c3 * rho + c4 * rho**2)


def inductance_nxp(d_avg_mm, width_mm, turns, k=1.07):
    """Naeherungsformel aus dem CLRC663-Datenblatt (Kap. 14.1.4) [H].
    L1[nH] = 2 * l1 * (ln(l1/D1) - K) * N1^1.8, l1 und D1 in cm."""
    l1 = math.pi * d_avg_mm / 10.0
    d1 = width_mm / 10.0
    return 2 * l1 * (math.log(l1 / d1) - k) * turns**1.8 * 1e-9


def fmt(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def build(args):
    w, gap = args.width, args.gap
    pitch = w + gap
    r_out = args.d_out / 2 - w / 2            # Mittellinie aeussere Windung
    r_in = r_out - args.turns * pitch          # Mittellinie inneres Ende
    if r_in < 2.0:
        raise SystemExit("Zu viele Windungen fuer diesen Durchmesser")
    d_in_edge = 2 * (r_in - w / 2)

    lines = []

    def seg(x1, y1, x2, y2, layer):
        lines.append(
            f'\t(fp_line (start {fmt(x1)} {fmt(y1)}) (end {fmt(x2)} {fmt(y2)})'
            f' (stroke (width {fmt(w)}) (type solid)) (layer "{layer}") (uuid "{uuid.uuid4()}"))'
        )

    # Spirale: r(theta) = r_out - pitch * theta / 2pi
    n = int(args.turns * args.segments)
    pts = []
    for i in range(n + 1):
        th = 2 * math.pi * i / args.segments
        r = r_out - pitch * th / (2 * math.pi)
        pts.append((r * math.cos(th), r * math.sin(th)))
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        seg(x1, y1, x2, y2, "F.Cu")

    pad_r_out = r_out + args.lead            # Abstand der Anschlusspads nach aussen
    via_x = r_in - args.lead_in              # innere Durchkontaktierung
    p1 = (pad_r_out, -args.pad_offset)
    p2 = (pad_r_out, +args.pad_offset)
    pv = (via_x, 0.0)

    seg(pts[0][0], pts[0][1], *p1, "F.Cu")    # Zuleitung aussen -> Pad 1
    seg(pts[-1][0], pts[-1][1], *pv, "F.Cu")  # inneres Ende -> Via
    # Die Rueckleitung (Via innen -> Pad 2 aussen, B.Cu) ist bewusst KEINE Footprint-Grafik:
    # Grafik zaehlt nicht als Verbindung und blockiert Router. tools/build_board.py legt sie
    # als echte, gesperrte Leiterbahn im Netz von Pad 2 an.

    pad = lambda num, x, y: (
        f'\t(pad "{num}" thru_hole circle (at {fmt(x)} {fmt(y)}) (size {fmt(args.pad)} {fmt(args.pad)})'
        f' (drill {fmt(args.drill)}) (layers "*.Cu") (remove_unused_layers no) (uuid "{uuid.uuid4()}"))'
    )

    keep_r = args.d_out / 2 + args.keepout_margin
    poly = " ".join(
        f"(xy {fmt(keep_r * math.cos(2 * math.pi * k / 48))} {fmt(keep_r * math.sin(2 * math.pi * k / 48))})"
        for k in range(48)
    )
    crt_r = pad_r_out + args.pad / 2 + 0.25
    l_mohan = inductance_mohan_circular(args.d_out, d_in_edge, args.turns)
    l_nxp = inductance_nxp((args.d_out + d_in_edge) / 2, w, args.turns)
    name = args.name or f"NFC_Coil_D{fmt(args.d_out)}_N{fmt(args.turns)}_W{fmt(w)}_S{fmt(gap)}"

    body = "\n".join([
        f'(footprint "{name}" (version 20240108) (generator "nfc_coil_gen") (layer "F.Cu")',
        f'\t(descr "NFC-Leiterbahnspule rund, Da={fmt(args.d_out)}mm, Di={fmt(d_in_edge)}mm, N={fmt(args.turns)},'
        f' b={fmt(w)}mm, s={fmt(gap)}mm, L~{l_mohan*1e6:.2f}uH (Mohan) / {l_nxp*1e6:.2f}uH (NXP)")',
        '\t(tags "NFC antenna coil 13.56MHz CLRC663")',
        f'\t(property "Reference" "REF**" (at 0 {fmt(-(crt_r + 1.5))} 0) (layer "F.Fab") (uuid "{uuid.uuid4()}")'
        ' (effects (font (size 1 1) (thickness 0.15))))',
        f'\t(property "Value" "{name}" (at 0 {fmt(crt_r + 1.5)} 0) (layer "F.Fab") (uuid "{uuid.uuid4()}")'
        ' (effects (font (size 1 1) (thickness 0.15))))',
        '\t(attr through_hole exclude_from_pos_files exclude_from_bom)',
        '\t(net_tie_pad_groups "1,2")',
        f'\t(fp_circle (center 0 0) (end {fmt(crt_r)} 0) (stroke (width 0.05) (type solid)) (fill no)'
        f' (layer "F.CrtYd") (uuid "{uuid.uuid4()}"))',
        f'\t(fp_circle (center 0 0) (end {fmt(args.d_out/2)} 0) (stroke (width 0.1) (type solid)) (fill no)'
        f' (layer "F.Fab") (uuid "{uuid.uuid4()}"))',
        *lines,
        pad("1", *p1),
        pad("2", *p2),
        pad("2", *pv),
        '\t(zone (net 0) (net_name "") (layers "F.Cu" "B.Cu") (name "NFC_Spule_Sperrflaeche")'
        ' (hatch edge 0.5) (connect_pads (clearance 0)) (min_thickness 0.25) (filled_areas_thickness no)'
        ' (keepout (tracks allowed) (vias allowed) (pads allowed) (copperpour not_allowed) (footprints allowed))'
        f' (fill (thermal_gap 0.5) (thermal_bridge_width 0.5)) (polygon (pts {poly})))',
        ")",
        "",
    ])
    out = Path(args.out) / f"{name}.kicad_mod"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")

    length = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
    print(f"Footprint:        {out}")
    print(f"Aussen-/Innen-D:  {args.d_out:.2f} / {d_in_edge:.2f} mm, {args.turns} Windungen, b={w} s={gap}")
    print(f"Induktivitaet:    {l_mohan*1e6:.3f} uH (Mohan)  |  {l_nxp*1e6:.3f} uH (NXP-Formel)")
    print(f"Leiterlaenge:     {length:.0f} mm Spirale")
    print(f"Sperrflaeche:     Radius {keep_r:.1f} mm")
    return name


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--d-out", type=float, default=24.0, help="Aussendurchmesser Kupfer [mm]")
    ap.add_argument("--turns", type=float, default=5, help="Windungszahl (ganzzahlig empfohlen)")
    ap.add_argument("--width", type=float, default=0.4, help="Leiterbahnbreite [mm]")
    ap.add_argument("--gap", type=float, default=0.4, help="Abstand zwischen Windungen [mm]")
    ap.add_argument("--segments", type=int, default=96, help="Segmente pro Windung")
    ap.add_argument("--pad", type=float, default=1.0, help="Pad-Durchmesser [mm]")
    ap.add_argument("--drill", type=float, default=0.5, help="Bohrung [mm]")
    ap.add_argument("--lead", type=float, default=1.6, help="Abstand Anschlusspads ausserhalb der Spirale [mm]")
    ap.add_argument("--lead-in", type=float, default=1.2, help="Abstand innere Durchkontaktierung [mm]")
    ap.add_argument("--pad-offset", type=float, default=1.1, help="Halber Abstand der zwei Anschlusspads [mm]")
    ap.add_argument("--keepout-margin", type=float, default=3.0, help="Sperrflaeche ueber Spule hinaus [mm]")
    ap.add_argument("--name", default="", help="Footprint-Name (Standard: aus Parametern)")
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "lib" / "spielbrett.pretty"))
    build(ap.parse_args())


if __name__ == "__main__":
    main()
