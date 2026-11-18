"""Restliche Signale mit Freerouting verlegen (ohne GUI), GND bleibt den Flaechen ueberlassen.

Letzter Schritt nach build_board -> route_hf -> route_power -> route_escape.
KiCad muss geschlossen sein:
  "C:/Program Files/KiCad/10.0/bin/python.exe" tools/autoroute.py [platine.kicad_pcb] [durchlaeufe]

Ablauf: Specctra-DSN exportieren -> GND-Netz aus der DSN entfernen (sonst zieht Freerouting
GND-Leiterbahnen und zerschneidet damit die Flaechen) -> Freerouting-JAR aus dem KiCad-Plugin
-> SES zurueckimportieren -> Flaechen fuellen -> speichern (Projektdatei bleibt unangetastet).
Gesperrte Vorverdrahtung (HF, Versorgung, Ausfaecherung) exportiert KiCad als "fix" -- Freerouting
laesst sie liegen.
"""
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import pcbnew

PRJ = Path(__file__).resolve().parent.parent
ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
POST = "--post" in sys.argv          # interner Zweitprozess fuer die Nacharbeit
PCB = Path(ARGS[0]).resolve() if ARGS else PRJ / "spielbrett.kicad_pcb"
PASSES = ARGS[1] if len(ARGS) > 1 else "100"
JAR = next((Path.home() / "OneDrive/Dokumente/KiCad/10.0/3rdparty/plugins"
            / "app_freerouting_kicad-plugin/jar").glob("freerouting-*.jar"), None)
JAVA_CANDIDATES = sorted(Path("C:/Program Files/OpenJDK").glob("jdk-*/bin/java.exe"), reverse=True)
SKIP_NETS = ["GND"]
KICAD_CLI = Path(sys.executable).parent / "kicad-cli.exe"


def complete_nets():
    """Netze mit mindestens zwei Pads, fuer die KiCads DRC keine offene Verbindung meldet."""
    d = drc()
    open_nets = {m for u in d["unconnected_items"] for i in u["items"]
                 for m in re.findall(r"\[([^\]]+)\]", i["description"])}
    board = pcbnew.LoadBoard(str(PCB))
    count = {}
    for p in board.GetPads():
        n = p.GetNetname()
        if n and not n.startswith("unconnected-"):
            count[n] = count.get(n, 0) + 1
    return sorted(n for n, c in count.items() if c >= 2 and n not in open_nets and n not in SKIP_NETS)


def strip_nets(dsn: str, nets) -> str:
    for n in nets:
        # (net GND (pins ...)) im network-Abschnitt entfernen
        m = re.search(r"\n\s*\(net " + re.escape(n) + r"\s*\n", dsn)
        if m:
            depth, i = 0, m.start() + 1
            while True:
                c = dsn[i]
                depth += c == "("
                depth -= c == ")"
                i += 1
                if depth == 0 and c == ")":
                    break
            dsn = dsn[:m.start()] + dsn[i:]
        # aus den Netzklassen-Listen streichen
        dsn = re.sub(r"(\(class [^\n(]*?)\s" + re.escape(n) + r"(?=[\s)])", r"\1", dsn)
    return dsn


def inset_boundary(dsn: str, inset_um: int = 300) -> str:
    """Freerouting haelt zum Platinenrand nur den normalen Abstand (0,2 mm) ein, die Platine
    verlangt 0,5 mm -> Umriss in der DSN um 0,3 mm nach innen ruecken (Rechteck)."""
    m = re.search(r"\(boundary\s*\(path pcb 0([^)]*)\)", dsn)
    nums = [int(v) for v in m.group(1).split()]
    xs, ys = nums[0::2], nums[1::2]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    pts = [(x1 - inset_um, y0 + inset_um), (x0 + inset_um, y0 + inset_um),
           (x0 + inset_um, y1 - inset_um), (x1 - inset_um, y1 - inset_um),
           (x1 - inset_um, y0 + inset_um)]
    path = "  ".join(f"{x} {y}" for x, y in pts)
    return dsn[:m.start(1)] + "  " + path + dsn[m.end(1):]


# ------------------------------------------------------------------ Nacharbeit
def mm(v):
    return pcbnew.FromMM(v)


def to_mm(p):
    return pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)


def fix_thin_tracks(board, min_w=0.2):
    n = 0
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK" and pcbnew.ToMM(t.GetWidth()) < 0.124:
            t.SetWidth(mm(min_w))
            n += 1
    return n


def drc():
    rep = PCB.parent / "output/_autoroute_drc.json"
    subprocess.run([str(KICAD_CLI), "pcb", "drc", "--format", "json", "-o", str(rep), str(PCB)],
                   check=True, capture_output=True)
    d = json.loads(rep.read_text(encoding="utf-8"))
    rep.unlink()
    return d


def dangling_vias(d):
    """UUIDs der Vias, die nur auf einer Lage angeschlossen sind (z. B. Ausfaecherungs-Vias,
    die Freerouting nicht benutzt hat) -- laut KiCads eigener DRC."""
    return [i["uuid"] for v in d["violations"] if v["type"] == "via_dangling" for i in v["items"]]


def strip_items(text, uuids):
    """Elemente per UUID direkt aus dem Dateitext entfernen (auch aus Gruppen-Mitgliederlisten).
    board.Remove() ueber Python hinterlaesst einen inkonsistenten Zustand (Absturz danach)."""
    for u in uuids:
        k = text.find(f'(uuid "{u}")')
        if k < 0:
            continue
        a = text.rfind("\n\t(via", 0, k)
        i = a + 2                       # auf der oeffnenden Klammer
        depth = 0
        while True:
            depth += text[i] == "("
            depth -= text[i] == ")"
            i += 1
            if depth == 0:
                break
        text = text[:a] + text[i:]
        text = text.replace(f' "{u}"', "").replace(f'"{u}" ', "").replace(f'"{u}"', "")
    return text


def stitch_gnd_islands(board, rounds=4):
    """GND-Flaecheninseln, die der Autorouter abgeschnitten hat, per Via an die jeweils andere
    Lage anbinden. Inseln, die sich nicht anbinden lassen, entfernt KiCad beim Fuellen."""
    zones = {z.GetLayer(): z for z in board.Zones() if z.GetNetname() == "GND" and not z.GetIsRuleArea()}
    F, B = pcbnew.F_Cu, pcbnew.B_Cu
    gnd = board.FindNet("GND")
    added = 0
    for z in zones.values():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_NEVER)
    for _ in range(rounds):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        polys = {L: z.GetFilledPolysList(L) for L, z in zones.items()}
        islands = [(L, i) for L in (F, B) for i in range(polys[L].OutlineCount())]

        def contains(L, i, x, y):
            return polys[L].Contains(pcbnew.VECTOR2I(mm(x), mm(y)), i)

        # Verbindungen zwischen Inseln: GND-Vias und GND-Durchsteckpads
        links = [to_mm(v.GetPosition()) for v in board.GetTracks()
                 if v.GetClass() == "PCB_VIA" and v.GetNetCode() == gnd.GetNetCode()]
        links += [to_mm(p.GetPosition()) for fp in board.GetFootprints() for p in fp.Pads()
                  if p.GetNetCode() == gnd.GetNetCode() and p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH]
        parent = {k: k for k in islands}

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        for x, y in links:
            hit = [k for k in islands if contains(*k, x, y)]
            for a in hit[1:]:
                parent[find(a)] = find(hit[0])
        size = {}
        for k in islands:
            bb = polys[k[0]].Outline(k[1]).BBox()
            size[find(k)] = size.get(find(k), 0) + bb.GetWidth() * bb.GetHeight()
        main = max(size, key=size.get)
        lonely = [k for k in islands if find(k) != main]
        if not lonely:
            break
        progress = False
        for L, i in lonely:
            if find((L, i)) == main:
                continue
            other = B if L == F else F
            bb = polys[L].Outline(i).BBox()
            x0, y0 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetTop())
            x1, y1 = pcbnew.ToMM(bb.GetRight()), pcbnew.ToMM(bb.GetBottom())
            mains = [j for (LL, j) in islands if LL == other and find((LL, j)) == main]
            best = None
            y = y0 + 0.4
            while y <= y1 - 0.4 and best is None:
                x = x0 + 0.4
                while x <= x1 - 0.4:
                    ring = [(x, y)] + [(x + 0.35 * dx, y + 0.35 * dy)
                                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1),
                                                      (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7))]
                    if all(contains(L, i, *p) for p in ring):
                        j = next((j for j in mains if all(contains(other, j, *p) for p in ring)), None)
                        if j is not None:
                            best = (x, y)
                            break
                    x += 0.25
                y += 0.25
            if best:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(mm(best[0]), mm(best[1])))
                v.SetWidth(mm(0.6))
                v.SetDrill(mm(0.3))
                v.SetNet(gnd)
                board.Add(v)
                parent[find((L, i))] = main
                added += 1
                progress = True
        if not progress:
            break
    for z in zones.values():
        z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    return added


def main():
    if JAR is None:
        raise SystemExit("Freerouting-JAR nicht gefunden (KiCad-Plugin installiert?)")
    java = str(JAVA_CANDIDATES[0]) if JAVA_CANDIDATES else "java"
    work = PRJ / "output"
    work.mkdir(exist_ok=True)
    dsn, ses = work / "autoroute.dsn", work / "autoroute.ses"

    # Netze, die die Skripte davor schon vollstaendig verlegt haben, aus der Netzliste nehmen
    # (ihre Bahnen bleiben als feste Hindernisse in der DSN). Freerouting erkennt manche dieser
    # vorverlegten Verbindungen nicht als verbunden, haelt das Board dann fuer unvollstaendig und
    # ueberspringt seine Optimierung -> Zickzack-Reste und unnoetige Vias bleiben stehen.
    done = complete_nets()
    print(f"Bereits fertig verlegt (nicht an Freerouting): {len(done)} Netze", flush=True)
    board = pcbnew.LoadBoard(str(PCB))
    if not pcbnew.ExportSpecctraDSN(board, str(dsn)):
        raise SystemExit("DSN-Export fehlgeschlagen")
    text = inset_boundary(strip_nets(dsn.read_text(encoding="utf-8"), SKIP_NETS + done))
    dsn.write_text(text, encoding="utf-8")

    ses.unlink(missing_ok=True)
    cmd = [java, "-jar", str(JAR), "-de", str(dsn), "-do", str(ses), "-mp", PASSES,
           "--gui.enabled=false", "--api_server.enabled=false", "--mcp_server.enabled=false"]
    print("Freerouting laeuft ...", flush=True)
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [ln for ln in res.stdout.splitlines() + res.stderr.splitlines()
            if any(w in ln.lower() for w in ("unrouted", "completed", "error", "optimiz"))]
    print("\n".join(tail[-8:]), flush=True)
    if not ses.exists():
        raise SystemExit(f"Freerouting hat keine SES geschrieben (Exit {res.returncode})")

    if not pcbnew.ImportSpecctraSES(board, str(ses)):
        raise SystemExit("SES-Import fehlgeschlagen")
    save(board)
    print(f"Autorouting importiert -> {PCB.name}", flush=True)
    # Nacharbeit in einem frischen Prozess: nach dem SES-Import ist pcbnew intern nicht mehr
    # stabil (jeder spaetere Zonenzugriff stuerzt ab, auch auf einer neu geladenen Platine).
    subprocess.run([sys.executable, __file__, str(PCB), "--post"], check=True)


def save(board):
    pro = PCB.with_suffix(".kicad_pro")
    pro_bak = pro.read_bytes() if pro.exists() else None
    pcbnew.SaveBoard(str(PCB), board)
    if pro_bak is not None:
        pro.write_bytes(pro_bak)


def remove_dangling_vias():
    """Vias entfernen, die laut DRC nur auf einer Lage angeschlossen sind."""
    before = drc()
    gone = []
    for u in dangling_vias(before):
        # Einzeln entfernen und nachpruefen: ein "nur auf einer Lage" angeschlossenes Via kann
        # trotzdem der einzige Knotenpunkt zweier Bahnen derselben Lage sein -> dann zuruecknehmen.
        old = PCB.read_text(encoding="utf-8")
        PCB.write_text(strip_items(old, [u]), encoding="utf-8")
        if len(drc()["unconnected_items"]) > len(before["unconnected_items"]):
            PCB.write_text(old, encoding="utf-8")
        else:
            gone.append(u)
    return gone


def _segments(text):
    """uuid -> (start, end, Blockanfang, Blockende) aller (segment ...)-Bloecke im Dateitext."""
    out = {}
    for m in re.finditer(r"\n\t\(segment\n(.*?)\n\t\)", text, re.S):
        blk = m.group(1)
        st = re.search(r"\(start ([-\d.]+) ([-\d.]+)\)", blk)
        en = re.search(r"\(end ([-\d.]+) ([-\d.]+)\)", blk)
        u = re.search(r'\(uuid "([^"]+)"\)', blk)
        out[u.group(1)] = ((float(st.group(1)), float(st.group(2))),
                           (float(en.group(1)), float(en.group(2))), m.start(), m.end())
    return out


def smooth_kinks(board, tol=0.3):
    """Kleine Zickzack-Knicke in den Autorouter-Bahnen begradigen.

    Freerouting hinterlaesst an Rasterspruengen V-foermige Knicke von wenigen Zehntel Millimetern.
    Seine eigene Optimierung, die das glaettet, laeuft nur bei aus seiner Sicht vollstaendig
    verlegtem Board -- und es haelt (anders als KiCad) fast immer 1-2 Verbindungen fuer offen.
    Hier: Stossen genau zwei ungesperrte Bahnen derselben Lage an einem Punkt ohne Via/Pad
    zusammen und weicht dieser Punkt weniger als `tol` mm von der Geraden zwischen den beiden
    Aussenenden ab, werden sie zu einer Bahn verschmolzen. Wiederholt bis nichts mehr geht.
    Liefert Liste der Verschmelzungen [(behaltene uuid, neue Enden, entfernte uuid)]."""
    key = lambda p: (round(p[0], 4), round(p[1], 4))      # noqa: E731
    segs, locked = {}, set()
    for t in board.GetTracks():
        if t.GetClass() == "PCB_TRACK":
            u = t.m_Uuid.AsString()
            segs[u] = [to_mm(t.GetStart()), to_mm(t.GetEnd()), t.GetLayer(), t.GetNetCode(),
                       pcbnew.ToMM(t.GetWidth())]
            if t.IsLocked():
                locked.add(u)
    blocked = set()                                       # Punkte mit Via oder Pad
    for t in board.GetTracks():
        if t.GetClass() == "PCB_VIA":
            blocked.add(key(to_mm(t.GetPosition())))
    pads = list(board.GetPads())
    merges = []
    changed = True
    while changed:
        changed = False
        ends = {}
        for u, (a, b, lay, net, w) in segs.items():
            for i, p in enumerate((a, b)):
                ends.setdefault((key(p), lay, net), []).append((u, i))
        for (pk, lay, net), lst in ends.items():
            if len(lst) != 2 or pk in blocked:
                continue
            (u1, i1), (u2, i2) = lst
            if u1 == u2 or u1 in locked or u2 in locked:
                continue
            s1, s2 = segs[u1], segs[u2]
            if s1[4] != s2[4]:
                continue
            q0, q2, pm = s1[1 - i1], s2[1 - i2], s1[i1]
            dx, dy = q2[0] - q0[0], q2[1] - q0[1]
            ln = math.hypot(dx, dy)
            if ln < 1e-6:
                continue
            dev = abs(dx * (pm[1] - q0[1]) - dy * (pm[0] - q0[0])) / ln
            if dev >= tol:
                continue
            v = pcbnew.VECTOR2I(mm(pm[0]), mm(pm[1]))
            if any(pd.HitTest(v) and pd.IsOnLayer(lay) for pd in pads):
                blocked.add(pk)
                continue
            segs[u1] = [q0, q2, lay, net, s1[4]]
            del segs[u2]
            merges.append((u1, (q0, q2), u2))
            changed = True
            break
    return merges


def apply_merges(text, merges):
    """Verschmelzungen in den Dateitext schreiben (Bahn u1 neue Enden, Bahn u2 entfernen)."""
    final, gone = {}, set()
    for u1, ends, u2 in merges:
        final[u1] = ends
        gone.add(u2)
        final.pop(u2, None)
    segs = _segments(text)
    edits = []
    for u, (q0, q2) in final.items():
        if u in gone or u not in segs:
            continue
        _, _, a, b = segs[u]
        blk = text[a:b]
        blk = re.sub(r"\(start [-\d.]+ [-\d.]+\)", f"(start {q0[0]:.6g} {q0[1]:.6g})", blk, count=1)
        blk = re.sub(r"\(end [-\d.]+ [-\d.]+\)", f"(end {q2[0]:.6g} {q2[1]:.6g})", blk, count=1)
        edits.append((a, b, blk))
    for u in gone:
        if u in segs:
            _, _, a, b = segs[u]
            edits.append((a, b, ""))
    for a, b, blk in sorted(edits, reverse=True):
        text = text[:a] + blk + text[b:]
    return text


def smooth_with_check():
    """Glaetten, per DRC pruefen; Verschmelzungen an Problemstellen zuruecknehmen."""
    board = pcbnew.LoadBoard(str(PCB))
    merges = smooth_kinks(board)
    if not merges:
        return 0
    # Vergleichsstand mit frisch gefuellten Flaechen (nach dem SES-Import sind sie veraltet und
    # die DRC meldete sonst schon vorher viele Abstandsfehler -> Pruefung waere wirkungslos)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    save(board)
    orig = PCB.read_text(encoding="utf-8")
    ref = drc()
    n_ref = len(ref["violations"]) + len(ref["unconnected_items"])
    for _ in range(4):
        PCB.write_text(apply_merges(orig, merges), encoding="utf-8")
        b2 = pcbnew.LoadBoard(str(PCB))                  # Flaechen an die neuen Bahnen anpassen
        pcbnew.ZONE_FILLER(b2).Fill(b2.Zones())
        save(b2)
        d = drc()
        if len(d["violations"]) + len(d["unconnected_items"]) <= n_ref:
            return len(merges)
        bad = {i.get("uuid") for v in d["violations"] + d["unconnected_items"] for i in v["items"]}
        keep = [m for m in merges if m[0] not in bad and m[2] not in bad]
        if len(keep) == len(merges):
            break
        merges = keep
    PCB.write_text(orig, encoding="utf-8")
    return 0


def post():
    board = pcbnew.LoadBoard(str(PCB))
    thin = fix_thin_tracks(board)
    save(board)
    gone = remove_dangling_vias()
    smoothed = smooth_with_check()                     # vor dem Nachheften: Inseln danach final
    board = pcbnew.LoadBoard(str(PCB))
    stitched = stitch_gnd_islands(board)
    save(board)
    # Nach dem GND-Nachheften meldet die DRC haeufig weitere einseitig angeschlossene Vias
    # (Freerouting-Knotenpunkte), die der erste Durchgang noch nicht erfasst -> zweiter Durchgang.
    gone += remove_dangling_vias()
    print(f"Nacharbeit: {smoothed} Knicke begradigt, {thin} zu duenne Bahnen verbreitert, {len(gone)} ungenutzte Vias entfernt, "
          f"{stitched} GND-Vias fuer abgeschnittene Flaecheninseln", flush=True)


if __name__ == "__main__":
    post() if POST else main()
    os._exit(0)               # pcbnew-Aufraeumen am Prozessende stuerzt gelegentlich ab
