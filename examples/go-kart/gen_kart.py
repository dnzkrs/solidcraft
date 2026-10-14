"""SolidCraft script generator for a youth off-road go-kart (welded 25x2 steel tube frame).

Frame: X forward (driver faces +X), Y left, Z up, ground at Z = 0, rear axle on the Y axis
at X = 0. All dimensions in millimetres.

Writes:
  go_kart.json       the SolidCraft command script (solvecraft-cli run/eval/snapshot)
  cut_list.csv       tube cut list with cope/mitre end preparation
  bom.csv            bill of materials, checked against the model
"""
import argparse
import csv
import json
import math
import os
import shutil
import subprocess

_here = os.path.dirname(os.path.abspath(__file__))
_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument("--engine-step", help="vendor STEP/IGES file (or STL/3MF mesh) of the engine, used instead of the envelope")
_ap.add_argument("--engine-rot", default="", help='rotations into kart axes, e.g. "Z:90" or "X:90,Z:-90"')
_ap.add_argument("--engine-pto", help='a point on the PTO shaft axis in the STEP file\'s own coordinates, "x,y,z": '
                 "puts the shaft on the clutch axis (without it the engine is centred by its bounding box)")
_ap.add_argument("--seat-step", help="vendor STEP/IGES file (or STL/3MF mesh) of the seat, used instead of the modelled shell")
_ap.add_argument("--seat-rot", default="", help="rotations into kart axes (multiples of 90 degrees)")
_ap.add_argument("--cli", default=os.environ.get("SOLVECRAFT_CLI") or shutil.which("solvecraft-cli")
                 or os.path.join(_here, "..", "..", "target", "release", "solvecraft-cli"),
                 help="solvecraft-cli used to read the STEP files")
_ap.add_argument("--config", help="JSON file of parameter overrides (names as in the parameter block)")
_ap.add_argument("--out", default="go_kart.json", help="script to write")
ARGS = _ap.parse_args()

# ----------------------------------------------------------------------------- parameters
TUBE_OD, TUBE_WALL = 25.0, 2.0          # frame tube EN 10305-3 E235 25 x 2
R = TUBE_OD / 2
R_TIRE, W_TIRE, R_BEAD = 165.0, 127.0, 76.0   # 13x5.00-6 tyre on 6" x 4.5" rim
ZA = R_TIRE                              # axle height
WB = 900.0                               # wheelbase
TRACK_R, TRACK_F = 760.0, 640.0          # wheel centre to wheel centre
KP_Y = 220.0                             # kingpin lateral position
Z_RAIL, Z_DECK = 90.0, 245.0             # frame tube centre heights
AXLE_D, AXLE_HALF = 25.0, 430.0          # rear live axle 25 h9, length 860
CHAIN_Y = 180.0                          # chain plane (left side, +Y)
BRAKE_Y = -180.0                         # brake disc plane (right side)
P35 = 9.525                              # ANSI 35 chain pitch
Z_SPROCKET, Z_CLUTCH = 72, 10
# Engine: Honda GX200 QX (5.5 hp @ 3600 rpm governed, 3/4" x 2-7/16" keyed shaft, 16.1 kg dry,
# 313 x 376 x 346 mm). Clones with the same base (e.g. Predator 212 non-hemi, Loncin G200F) fit.
ENGINE_BASE_Z = 262.5                    # top of the engine plate
CRANK_H = 106.0                          # PTO shaft centre above the base (4.17 in)
ENGINE_Y = 15.0                          # centre of the mounting pattern in Y
PTO_FACE = 105.0                         # crankcase PTO face from the pattern centre (+Y)
SHAFT_D, SHAFT_L = 19.05, 61.9           # 3/4" x 2-7/16"
MOUNT_Y, MOUNT_X = 162.0, 75.5           # 4 x M8 mounting pattern (verify the orientation on the engine)
ENGINE_FRONT_MAX = 105.0                 # air cleaner must stay this far behind the seat back
ENGINE_HALF_W = 188.0                    # half of the 376 mm width (air cleaner to muffler)
ENGINE_FRONT_EXT = None                  # engine extent ahead of the crank axis; default ENGINE_HALF_W

WHEEL_C = (540.0, 460.0)                 # steering wheel centre (x, z)
X_DF = 140.0                             # deck front station: uprights F14, cross F16, brace and side rail start
# Seat: universal high-back plastic (HDPE) go-kart bucket seat, 450 W x 355 H x 370 D, 4 mounting
# holes 254 (side to side) x 273 (front to back), 10 degree back recline. Upright enough to sit in
# front of the engine (a racing seat with a 58 degree back would reach it).
SEAT_W, SEAT_H, SEAT_D = 450.0, 355.0, 370.0
SEAT_HOLES = (254.0, 273.0)
SEAT_RECLINE = 10.0                      # degrees from vertical
SEAT_REAR = 185.0                        # x of the back's outside at the base
SEAT_TABS = None                         # [[x, y, height above the cross tops], ...]; default: under the holes
SEAT_BASE_Z = None                       # lowest point of the seat; default: on 4 mm tabs on the crosses
SEAT_CROSS_X = None                      # [rear, front] seat cross stations; default: under the holes

# --config FILE.json overrides any of the parameters above (e.g. for a vendor seat or engine)
if ARGS.config:
    for _k, _v in json.load(open(ARGS.config)).items():
        if _k not in globals() or _k.startswith("_"):
            raise SystemExit(f"--config: unknown parameter {_k}")
        globals()[_k] = tuple(_v) if isinstance(_v, list) and isinstance(globals()[_k], tuple) else _v

SEAT_FRONT = SEAT_REAR + SEAT_D
SEAT_HOLE_X = (SEAT_REAR + SEAT_D / 2 - SEAT_HOLES[1] / 2, SEAT_REAR + SEAT_D / 2 + SEAT_HOLES[1] / 2)
if SEAT_CROSS_X is None:
    SEAT_CROSS_X = SEAT_HOLE_X
if SEAT_BASE_Z is None:
    SEAT_BASE_Z = Z_RAIL + TUBE_OD / 2 + 4
if SEAT_TABS is None:
    SEAT_TABS = [[x, y, 0.0] for x in SEAT_HOLE_X for y in (-SEAT_HOLES[0] / 2, SEAT_HOLES[0] / 2)]

if ENGINE_FRONT_EXT is None:
    ENGINE_FRONT_EXT = ENGINE_HALF_W

# Chain: choose the smallest even link count that keeps the engine behind the seat, then put the
# engine where that chain fits with the mounting slots centred (+/-15 mm for tension and wear).
_P35 = 9.525
_z1, _z2 = 10, 72
_dz = ENGINE_BASE_Z + CRANK_H - R_TIRE


def _centres(n):
    k = n - (_z1 + _z2) / 2
    return _P35 / 4 * (k + math.sqrt(k * k - 8 * ((_z2 - _z1) / (2 * math.pi)) ** 2))


CHAIN_LINKS = 80
while not (_centres(CHAIN_LINKS) > _dz and
           -math.sqrt(_centres(CHAIN_LINKS) ** 2 - _dz ** 2) + ENGINE_FRONT_EXT <= ENGINE_FRONT_MAX):
    CHAIN_LINKS += 2
ENGINE_X = -math.sqrt(_centres(CHAIN_LINKS) ** 2 - _dz ** 2)
CLUTCH = (ENGINE_X, ENGINE_BASE_Z + CRANK_H)      # (x, z) in the chain plane
COL_BOTTOM = (953.6, 196.9)              # steering column lower end (x, z)

cmds = []


def c(command, **params):
    cmds.append({"command": command, "params": params})


def v_sub(a, b):
    return [a[i] - b[i] for i in range(3)]


def v_add(a, b):
    return [a[i] + b[i] for i in range(3)]


def v_mul(a, s):
    return [x * s for x in a]


def dot(a, b):
    return sum(a[i] * b[i] for i in range(3))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def norm(a):
    return math.sqrt(dot(a, a))


def unit(a):
    n = norm(a)
    return [x / n for x in a]


def r6(p):
    return [round(x, 6) for x in p]


# ----------------------------------------------------------------------------- helpers
def cylinder(name, base, axis, d, h, op="new", targets=None):
    p = {"diameter": d, "height": round(h, 6), "base": r6(base), "axis": r6(axis), "operation": op}
    if op == "new":
        p["body_name"] = name
    else:
        p["targets"] = targets
    c("solid.cylinder", **p)


def tube_body(name, p0, p1, od=TUBE_OD, wall=TUBE_WALL):
    axis = v_sub(p1, p0)
    L = norm(axis)
    cylinder(name, p0, axis, od, L)
    if wall:
        cylinder(name, p0, axis, od - 2 * wall, L, op="cut", targets=[name])


def box(name, lo, hi, op="new", targets=None):
    p = {"length": hi[0] - lo[0], "width": hi[1] - lo[1], "height": hi[2] - lo[2],
         "corner": r6(lo), "operation": op}
    if op == "new":
        p["body_name"] = name
    else:
        p["targets"] = targets
    c("solid.box", **p)


def plane(origin, xd, yd):
    return {"origin": r6(origin), "x_dir": r6(unit(xd)), "y_dir": r6(unit(yd))}


SK = [0]


def draw_loop(segs):
    """segs: ("L", [pts...]) polyline or ("A", center, start, end) CCW arc, sketch coords."""
    for s in segs:
        if s[0] == "L":
            c("sketch.line", points=[[round(x, 6), round(y, 6)] for x, y in s[1]])
        else:
            # three-point arc: both ends land exactly on the neighbouring lines after rounding
            _, cen, st, en = s
            a0 = math.atan2(st[1] - cen[1], st[0] - cen[0])
            a1 = math.atan2(en[1] - cen[1], en[0] - cen[0])
            while a1 <= a0:
                a1 += 2 * math.pi
            am, rr = (a0 + a1) / 2, math.hypot(st[0] - cen[0], st[1] - cen[1])
            c("sketch.arc.three_point", start=[round(st[0], 6), round(st[1], 6)],
              end=[round(en[0], 6), round(en[1], 6)],
              through=[round(cen[0] + rr * math.cos(am), 6), round(cen[1] + rr * math.sin(am), 6)])


def sketch_on(pl, name):
    SK[0] += 1
    c("sketch.create", plane=pl, name=name)


def extrude(name, dist, direction="positive", op="new", targets=None, pick=None, feature=None):
    p = {"distance": round(dist, 6), "direction": direction, "operation": op}
    if pick is not None:
        p["profiles"] = [{"point": [round(pick[0], 6), round(pick[1], 6)]}]
    else:
        p["profiles"] = "all"
    if op == "new":
        p["body_name"] = name
    else:
        p["targets"] = targets
    if feature:
        p["name"] = feature
    c("solid.extrude", **p)


def plate(name, pl, outline, t, holes=(), pick=None, direction="positive", segs=None):
    """Flat plate: outline polygon (or segs) in sketch coords, holes = [(x, y, d)]."""
    sketch_on(pl, name)
    if segs:
        draw_loop(segs)
    else:
        c("sketch.line", points=[r6(p) for p in outline], closed=True)
    for hx, hy, hd in holes:
        c("sketch.circle.center", center=[round(hx, 6), round(hy, 6)], diameter=hd)
    c("sketch.finish")
    extrude(name, t / 2 if direction == "symmetric" else t, direction, pick=pick if holes else None)


def revolve(name, origin, axis_dir, radial_dir, profile, op="new", targets=None):
    """profile: closed polygon [(a, r)] with a along axis_dir, r along radial_dir."""
    sketch_on(plane(origin, axis_dir, radial_dir), name)
    c("sketch.line", points=[r6(p) for p in profile], closed=True)
    c("sketch.finish")
    p = {"axis": "x", "operation": op}
    if op == "new":
        p["body_name"] = name
    else:
        p["targets"] = targets
    c("solid.revolve", **p)


def ring(a0, a1, r0, r1):
    return [(a0, r0), (a1, r0), (a1, r1), (a0, r1)]


IMPORTED = {}          # part id -> number of bodies imported from a STEP file


def _rot90(p, axis, deg):
    q = round(deg / 90) % 4
    x, y, z = p
    for _ in range(q):
        if axis == "X":
            y, z = -z, y
        elif axis == "Y":
            x, z = z, -x
        else:
            x, y = -y, x
    return [x, y, z]


def import_step(pid, label, path, rot_spec, align, ref=None):
    """Insert a vendor CAD file (STEP/IGES as exact geometry, STL/3MF as a mesh body), turn it into
    kart axes (90-degree steps about the world axes) and move it so its bounding box meets the
    mounting datums: align(lo, hi, ref) -> translation."""
    path = os.path.abspath(path)
    mesh = path.lower().endswith((".stl", ".3mf"))
    insert = ("file.insert_mesh" if mesh else "file.insert_step", {"path": path, "name": f"{pid} {label}"})
    probe = os.path.join(os.path.dirname(os.path.abspath(ARGS.out)), f".probe_{pid}.json")
    json.dump({"commands": [{"command": insert[0], "params": insert[1]}]}, open(probe, "w"))
    try:
        out = subprocess.run([ARGS.cli, "eval", probe], capture_output=True, text=True, check=True).stdout
    finally:
        os.remove(probe)
    bodies = json.loads(out)["bodies"]
    names = [b["name"] for b in bodies]
    rots = []
    for tok in filter(None, (t.strip() for t in rot_spec.split(","))):
        ax, deg = tok.split(":")
        if float(deg) % 90:
            raise SystemExit(f"{pid}: rotations must be multiples of 90 degrees ({tok})")
        rots.append((ax.upper(), float(deg)))
    corners = []
    for b in bodies:
        lo, hi = b["bbox"]["min"], b["bbox"]["max"]
        corners += [[(lo, hi)[i >> k & 1][k] for k in range(3)] for i in range(8)]
    for ax, deg in rots:
        corners = [_rot90(p, ax, deg) for p in corners]
    lo = [min(p[k] for p in corners) for k in range(3)]
    hi = [max(p[k] for p in corners) for k in range(3)]
    if ref is not None:
        for ax, deg in rots:
            ref = _rot90(ref, ax, deg)
        if pid == "C13" and abs(ref[2] - lo[2] - CRANK_H) > 1:
            print(f"C13: the STEP shaft is {ref[2] - lo[2]:.1f} mm above the base, not CRANK_H = {CRANK_H}: "
                  "set CRANK_H to it so the chain and clutch line up")
    t = align(lo, hi, ref)
    c(insert[0], **insert[1])
    for ax, deg in rots:
        c("solid.move", bodies=names, axis={"X": [1, 0, 0], "Y": [0, 1, 0], "Z": [0, 0, 1]}[ax],
          angle=f"{deg} deg")
    c("solid.move", bodies=names, translate=r6(t))
    final = []
    for i, n in enumerate(names):
        new = f"{pid} {label}" if len(names) == 1 else f"{pid} {label} - {i + 1:02d} {n}"
        c("body.rename", body=n, name=new)
        final.append(new)
    IMPORTED[pid] = len(final)
    size = [round(hi[k] - lo[k], 1) for k in range(3)]
    print(f"{pid}: imported {len(final)} bodies from {os.path.basename(path)}, size in kart axes {size} mm")
    return final


# ============================================================================= FRAME
# nodes (left side; right side mirrored in Y)
RC = (-260.0, 250.0, Z_RAIL)        # rear corner
M1 = (560.0, 250.0, Z_RAIL)         # start of front taper (ahead of the seat's front cross)
M2 = (630.0, 150.0, Z_RAIL)         # foot-box start
F1 = (925.0, 150.0, Z_RAIL)         # foot-box / nose mitre (25 mm ahead of the front axle station)
N1 = (1060.0, 95.0, Z_RAIL)         # nose corner
FA = 195.0                          # front axle cross half length (to kingpin brackets)
HOOP_B = (660.0, 150.0, Z_RAIL)
HOOP_K = (680.0, 150.0, 330.0)
HOOP_T = (700.0, 40.0, 420.0)
Z_SIDE = 220.0                      # side rail height (kept off the deck corner node)
X_RU = -230.0                       # rear deck uprights (kept 30 mm off the rear cross)
SIDE_F = (HOOP_B[0] + (HOOP_K[0] - HOOP_B[0]) * (Z_SIDE - Z_RAIL) / (HOOP_K[2] - HOOP_B[2]),
          150.0, Z_SIDE)


def m(p, s):
    return [p[0], p[1] * s, p[2]]


MEMBERS = []   # (id, name, p0, p1, end0, end1); end = ("cope", member) | ("mitre", member) | ("sq", note)


def member(mid, name, p0, p1, e0, e1):
    MEMBERS.append((mid, name, list(p0), list(p1), e0, e1))


for s, side in ((1, "L"), (-1, "R")):
    member(f"F01{side}", f"Rail rear {side}", m(RC, s), m(M1, s), ("cap", "runs 12.5 past the rear cross, end plug"), ("mitre", f"F02{side}"))
    member(f"F02{side}", f"Rail taper {side}", m(M1, s), m(M2, s), ("mitre", f"F01{side}"), ("mitre", f"F03{side}"))
    member(f"F03{side}", f"Rail foot-box {side}", m(M2, s), m(F1, s), ("mitre", f"F02{side}"), ("mitre", f"F04{side}"))
    member(f"F04{side}", f"Nose rail {side}", m(F1, s), m(N1, s), ("mitre", f"F03{side}"), ("mitre", "F05"))
    member(f"F11{side}", f"Front upright {side}", [WB, 150.0 * s, Z_RAIL], [WB, 150.0 * s, ZA], ("cope", f"F03{side}"), ("cope", "F12"))
    member(f"F13{side}", f"Rear upright {side}", [X_RU, 250.0 * s, Z_RAIL], [X_RU, 250.0 * s, Z_DECK], ("cope", f"F01{side}"), ("cope", "F15"))
    member(f"F14{side}", f"Deck front upright {side}", [X_DF, 250.0 * s, Z_RAIL], [X_DF, 250.0 * s, Z_DECK], ("cope", f"F01{side}"), ("cope", "F16"))
    member(f"F17{side}", f"Deck rail {side}", [X_RU, 140.0 * s, Z_DECK], [X_DF, 140.0 * s, Z_DECK], ("cope", "F15"), ("cope", "F16"))
    member(f"F18{side}", f"Rear diagonal {side}", [X_RU, 250.0 * s, 200.0], [-160.0, 250.0 * s, Z_RAIL], ("cope", f"F13{side}"), ("cope", f"F01{side}"))
    member(f"F19{side}", f"Deck front brace {side}", [X_DF, 250.0 * s, 175.0], [X_DF + 160, 250.0 * s, Z_RAIL], ("cope", f"F14{side}"), ("cope", f"F01{side}"))
    member(f"F20{side}", f"Hoop upright {side}", m(HOOP_B, s), m(HOOP_K, s), ("cope", f"F03{side}"), ("mitre", f"F21{side}"))
    member(f"F21{side}", f"Hoop shoulder {side}", m(HOOP_K, s), m(HOOP_T, s), ("mitre", f"F20{side}"), ("mitre", "F22"))
    member(f"F23{side}", f"Side rail {side}", [X_DF, 250.0 * s, Z_SIDE], [SEAT_FRONT - 5, 250.0 * s, Z_SIDE], ("cope", f"F14{side}"), ("mitre", f"F24{side}"))
    member(f"F24{side}", f"Side rail front {side}", [SEAT_FRONT - 5, 250.0 * s, Z_SIDE], m(SIDE_F, s), ("mitre", f"F23{side}"), ("cope", f"F20{side}"))

member("F05", "Nose cross", m(N1, 1), m(N1, -1), ("mitre", "F04L"), ("mitre", "F04R"))
member("F06", "Rear cross", m(RC, 1), m(RC, -1), ("cope", "F01L"), ("cope", "F01R"))
member("F07", "Seat cross front", [SEAT_CROSS_X[1], 250.0, Z_RAIL], [SEAT_CROSS_X[1], -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F08", "Seat cross rear", [SEAT_CROSS_X[0], 250.0, Z_RAIL], [SEAT_CROSS_X[0], -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F09", "Brake cross", [-120.0, 250.0, Z_RAIL], [-120.0, -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F10", "Pedal cross", [850.0, 150.0, Z_RAIL], [850.0, -150.0, Z_RAIL], ("cope", "F03L"), ("cope", "F03R"))
member("F12", "Front axle beam", [WB, FA, ZA], [WB, -FA, ZA], ("sq", "welds to kingpin bracket back plate"), ("sq", "welds to kingpin bracket back plate"))
member("F15", "Deck rear cross", [X_RU, 250.0, Z_DECK], [X_RU, -250.0, Z_DECK], ("cap", "runs 12.5 past F13L, end plug"), ("cap", "runs 12.5 past F13R, end plug"))
member("F16", "Deck front cross", [X_DF, 250.0, Z_DECK], [X_DF, -250.0, Z_DECK], ("cap", "runs 12.5 past F14L, end plug"), ("cap", "runs 12.5 past F14R, end plug"))
member("F22", "Hoop top", m(HOOP_T, 1), m(HOOP_T, -1), ("mitre", "F21L"), ("mitre", "F21R"))

def ext_ends(p0, p1, e0, e1):
    d = unit(v_sub(p1, p0))
    a = v_sub(p0, v_mul(d, R)) if e0[0] == "cap" else p0
    b = v_add(p1, v_mul(d, R)) if e1[0] == "cap" else p1
    return a, b


for mid, name, p0, p1, e0, e1 in MEMBERS:
    a, b = ext_ends(p0, p1, e0, e1)
    tube_body(f"{mid} {name}", a, b)

# ----------------------------------------------------------------------------- cut list maths
MEMBER_BY_ID = {mm[0]: mm for mm in MEMBERS}


def dist_to_line(p, a, d):
    w = v_sub(p, a)
    return norm(v_sub(w, v_mul(d, dot(w, d))))


def cope_setback(node, d, recv):
    """Long-point and short-point setbacks of a tube (axis from node along unit d) coped onto
    receiving member recv (radius R). Returns (min s, max s) where the tube surface leaves recv."""
    a, b = recv[2], recv[3]
    rd = unit(v_sub(b, a))
    e1 = unit(cross(d, rd)) if norm(cross(d, rd)) > 1e-9 else unit(cross(d, [0, 0, 1]))
    e2 = cross(d, e1)
    smin, smax = 1e9, -1e9
    for k in range(0, 360, 2):
        ph = math.radians(k)
        off = v_add(v_mul(e1, R * math.cos(ph)), v_mul(e2, R * math.sin(ph)))
        f = lambda s_: dist_to_line(v_add(v_add(node, v_mul(d, s_)), off), a, rd) - R
        samples = [i * 0.1 for i in range(-50, 1200)]
        inside = [s_ for s_ in samples if f(s_) <= 1e-3]
        if not inside:
            continue
        s_cross = max(inside)
        smin, smax = min(smin, s_cross), max(smax, s_cross)
    return smin, smax


def angle_between(d1, d2):
    return math.degrees(math.acos(max(-1, min(1, abs(dot(d1, d2))))))


cut_rows = []
total_len = 0.0
for mid, name, p0, p1, e0, e1 in MEMBERS:
    L = norm(v_sub(p1, p0))
    d = unit(v_sub(p1, p0))
    cut = L
    preps = []
    for end, node, dirn in ((e0, p0, d), (e1, p1, v_mul(d, -1))):
        kind, ref = end
        if kind == "cope":
            recv = MEMBER_BY_ID[ref]
            smin, smax = cope_setback(node, dirn, recv)
            cut -= smin
            ang = angle_between(dirn, unit(v_sub(recv[3], recv[2])))
            preps.append(f"cope Ø25 onto {ref} at {ang:.0f}°, saddle depth {smax - smin:.1f}")
        elif kind == "mitre":
            other = MEMBER_BY_ID[ref]
            od = unit(v_sub(other[3], other[2]))
            # deflection between the two members' axes at the shared node
            dfl = math.degrees(math.acos(max(-1, min(1, abs(dot(dirn, od))))))
            dfl = 180 - dfl if dfl > 90 else dfl
            ext = R * math.tan(math.radians(dfl / 2))
            cut += ext
            preps.append(f"mitre {dfl / 2:.1f}° (half of {dfl:.1f}°) to {ref}")
        elif kind == "cap":
            cut += R
            preps.append(f"square cut, {ref}")
        else:
            preps.append(f"square cut, {ref}")
    total_len += cut
    cut_rows.append({"id": mid, "name": name, "tube": "25 x 2.0", "node_length": round(L, 1),
                     "cut_length_long_point": round(cut, 1), "end_A": preps[0], "end_B": preps[1]})

# ----------------------------------------------------------------------------- floor pan
pan_pts = [(200, 262.5), (560, 262.5), (630, 162.5), (900, 162.5), (900, -162.5), (630, -162.5),
           (560, -262.5), (200, -262.5)]
plate("P01 Floor pan", plane([0, 0, Z_RAIL - R], [1, 0, 0], [0, 1, 0]), pan_pts, 1.5,
      direction="negative")

# ----------------------------------------------------------------------------- rear bearing plates
for s, side in ((1, "L"), (-1, "R")):
    y_in = s * (250 + R)
    pl = plane([0, y_in, 0], [1, 0, 0], [0, 0, 1])     # normal -Y
    plate(f"P02{side} Bearing plate {side}", pl,
          [(-75, 78), (75, 78), (75, 235), (-75, 235)], 8,
          holes=[(0, ZA, 45), (-49.5, ZA, 12), (49.5, ZA, 12)], pick=(0, 100),
          direction="negative" if s > 0 else "positive")

# ----------------------------------------------------------------------------- kingpin brackets + steering knuckles
KP_Z0, KP_Z1 = 140.0, 190.0          # inner faces of the bracket ears
for s, side in ((1, "L"), (-1, "R")):
    kx, ky = WB, s * KP_Y
    yb = s * FA                      # back plate inner face (front-axle beam end)
    # back plate in the XZ plane
    plate(f"P03{side} Kingpin back plate {side}", plane([0, yb, 0], [1, 0, 0], [0, 0, 1]),
          [(kx - 20, KP_Z0 - 6), (kx + 20, KP_Z0 - 6), (kx + 20, KP_Z1 + 6), (kx - 20, KP_Z1 + 6)], 6,
          direction="negative" if s > 0 else "positive")
    # ears: from the back plate to a R20 round end around the kingpin, hole 12.2
    for zname, z0 in (("lower", KP_Z0 - 6), ("upper", KP_Z1)):
        y0 = yb + s * 6
        if s > 0:
            segs = [("L", [(kx + 20, y0), (kx + 20, ky)]), ("A", (kx, ky), (kx + 20, ky), (kx - 20, ky)),
                    ("L", [(kx - 20, ky), (kx - 20, y0), (kx + 20, y0)])]
        else:
            segs = [("L", [(kx - 20, y0), (kx - 20, ky)]), ("A", (kx, ky), (kx - 20, ky), (kx + 20, ky)),
                    ("L", [(kx + 20, ky), (kx + 20, y0), (kx - 20, y0)])]
        sketch_on(plane([0, 0, z0], [1, 0, 0], [0, 1, 0]), f"P04{side} ear {zname}")
        draw_loop(segs)
        c("sketch.circle.center", center=[kx, ky], diameter=12.2)
        c("sketch.finish")
        extrude(f"P04{side} Kingpin ear {zname} {side}", 6, "positive", pick=(kx, (y0 + ky) / 2))
    # knuckle: sleeve 22x4, spindle 20, steering arm
    sleeve = f"M01{side} Knuckle sleeve {side}"
    cylinder(sleeve, [kx, ky, KP_Z0 + 1], [0, 0, 1], 22, KP_Z1 - KP_Z0 - 2)
    cylinder(sleeve, [kx, ky, KP_Z0 + 1], [0, 0, 1], 14, KP_Z1 - KP_Z0 - 2, op="cut", targets=[sleeve])
    wy = s * TRACK_F / 2
    cylinder(f"M02{side} Spindle {side}", [kx, ky + s * 8, ZA], [0, s, 0], 20, abs(wy) + 70 - KP_Y - 8)
    # steering arm (Ackermann: arm points away from the rear-axle centre)
    ad = unit([kx, ky, 0])
    tip = [kx + 80 * ad[0], ky + 80 * ad[1]]
    nx, ny = -ad[1], ad[0]
    rx, ry = kx + 8 * ad[0], ky + 8 * ad[1]          # root: inside the sleeve wall, clear of the 14 mm bore
    segs = [("L", [(rx + 10 * nx, ry + 10 * ny), (tip[0] + 12.5 * nx, tip[1] + 12.5 * ny)]),
            ("A", tuple(tip), (tip[0] + 12.5 * nx, tip[1] + 12.5 * ny), (tip[0] - 12.5 * nx, tip[1] - 12.5 * ny)),
            ("L", [(tip[0] - 12.5 * nx, tip[1] - 12.5 * ny), (rx - 10 * nx, ry - 10 * ny),
                   (rx + 10 * nx, ry + 10 * ny)])]
    sketch_on(plane([0, 0, KP_Z0 + 2], [1, 0, 0], [0, 1, 0]), f"M03{side} arm")
    draw_loop(segs)
    c("sketch.circle.center", center=r6(tip), diameter=8.2)
    c("sketch.finish")
    extrude(f"M03{side} Steering arm {side}", 6, "positive", pick=(kx + 45 * ad[0], ky + 45 * ad[1]))
    MEMBER_BY_ID[f"ARM{side}"] = tip
    # spacer, wheel bearings, nut
    cylinder(f"M04{side} Spindle spacer {side}", [kx, ky + s * 11, ZA], [0, s, 0], 28, abs(wy) - 44.5 - KP_Y - 11)
    cylinder(f"M04{side} Spindle spacer {side}", [kx, ky + s * 11, ZA], [0, s, 0], 20.5, abs(wy) - 44.5 - KP_Y - 11,
             op="cut", targets=[f"M04{side} Spindle spacer {side}"])
    for n, a0 in ((1, -44.5), (2, 30.5)):
        bn = f"C01{side}{n} Bearing 6204-2RS {side}{n}"
        revolve(bn, [kx, wy + s * a0, ZA], [0, s, 0], [0, 0, 1], ring(0, 14, 10, 23.5))
    nut = f"C02{side} Nut M20 + washer {side}"
    cylinder(nut, [kx, wy + s * 44.5, ZA], [0, s, 0], 30, 16)
    cylinder(nut, [kx, wy + s * 44.5, ZA], [0, s, 0], 20, 16, op="cut", targets=[nut])

# kingpin bolts
for s, side in ((1, "L"), (-1, "R")):
    cylinder(f"C03{side} Kingpin bolt M12x90 {side}", [WB, s * KP_Y, KP_Z0 - 6 - 12], [0, 0, 1], 12, 90)

# ----------------------------------------------------------------------------- wheels
def wheel(tag, x, y, front):
    s = 1 if y > 0 else -1
    o = [x, y, ZA]
    ax, rd = [0, s, 0], [0, 0, 1]
    tire = [(-63.5, R_BEAD), (63.5, R_BEAD), (63.5, 140), (55, 158), (38.5, 165), (-38.5, 165),
            (-55, 158), (-63.5, 140)]
    cavity = [(-55.5, R_BEAD), (55.5, R_BEAD), (55.5, 138), (49, 150), (35, 157), (-35, 157), (-49, 150),
              (-55.5, 138)]
    sketch_on(plane(o, ax, rd), f"C04{tag} tyre")
    c("sketch.line", points=[r6(p) for p in tire], closed=True)
    c("sketch.line", points=[r6(p) for p in cavity], closed=True)
    c("sketch.finish")
    c("solid.revolve", axis="x", operation="new", body_name=f"C04{tag} Tyre 13x5.00-6 {tag}",
      profiles=[{"point": [0, 161]}])
    if front:
        rim = [(-44.5, 23.5), (44.5, 23.5), (44.5, 30), (3, 30), (3, 70), (57, 70), (57, 76), (-57, 76),
               (-57, 70), (-3, 70), (-3, 30), (-44.5, 30)]
        revolve(f"C05{tag} Rim 6x4.5 {tag}", o, ax, rd, rim)
    else:
        rim = [(-21, 30), (-21, 70), (57, 70), (57, 76), (-57, 76), (-57, 70), (-27, 70), (-27, 30)]
        revolve(f"C05{tag} Rim 6x4.5 {tag}", o, ax, rd, rim)
        # bolt-on hub 25 mm bore
        revolve(f"C06{tag} Hub 25 mm bolt-on {tag}", o, ax, rd,
                [(-75, 12.5), (-27, 12.5), (-27, 60), (-35, 60), (-35, 22.5), (-75, 22.5)])


for s, side in ((1, "L"), (-1, "R")):
    wheel(f"F{side}", WB, s * TRACK_F / 2, True)
    wheel(f"R{side}", 0.0, s * TRACK_R / 2, False)

# ----------------------------------------------------------------------------- rear axle and bearings
cylinder("M05 Rear axle 25 h9", [0, -AXLE_HALF, ZA], [0, 1, 0], AXLE_D, 2 * AXLE_HALF)
for s, side in ((1, "L"), (-1, "R")):
    y_face = s * (250 + R + 8)            # outer face of the bearing plate
    bn = f"C07{side} Flange bearing UCFL205 {side}"
    sketch_on(plane([0, y_face, 0], [1, 0, 0], [0, 0, 1]), bn)
    draw_loop([("L", [(-49.5, ZA - 17), (49.5, ZA - 17)]), ("A", (49.5, ZA), (49.5, ZA - 17), (49.5, ZA + 17)),
               ("L", [(49.5, ZA + 17), (-49.5, ZA + 17)]), ("A", (-49.5, ZA), (-49.5, ZA + 17), (-49.5, ZA - 17))])
    c("sketch.circle.center", center=[-49.5, ZA], diameter=12)
    c("sketch.circle.center", center=[49.5, ZA], diameter=12)
    c("sketch.circle.center", center=[0, ZA], diameter=AXLE_D)
    c("sketch.finish")
    extrude(bn, 13, "negative" if s > 0 else "positive", pick=(-25, ZA + 10))
    revolve(f"C07{side}b UCFL205 insert {side}", [0, y_face + s * 13, ZA], [0, s, 0], [0, 0, 1], ring(0, 18, 12.5, 32))
    revolve(f"C08{side} Shaft collar 25 {side}", [0, s * (250 + R - 14), ZA], [0, s, 0], [0, 0, 1],
            ring(0, 14, 12.5, 20))

# ----------------------------------------------------------------------------- drive: sprocket, clutch, chain
def pd(n):
    return P35 / math.sin(math.pi / n)


R1, R2 = pd(Z_SPROCKET) / 2, pd(Z_CLUTCH) / 2
xz_chain = plane([0, CHAIN_Y, 0], [1, 0, 0], [0, 0, 1])          # normal -Y
sk_name = "C09 Sprocket 72T #35"
sketch_on(xz_chain, sk_name)
c("sketch.circle.center", center=[0, ZA], diameter=round(P35 * (0.6 + 1 / math.tan(math.pi / Z_SPROCKET)), 3))
c("sketch.circle.center", center=[0, ZA], diameter=60)
c("sketch.finish")
extrude(sk_name, 2.15, "symmetric", pick=(0, ZA + 80))
revolve("C10 Sprocket hub 25 mm", [0, CHAIN_Y + 2.15, ZA], [0, 1, 0], [0, 0, 1], ring(0, 40, 12.5, 30))

# chain band (pitch line +/- 4.5)
A, B = (0.0, ZA), CLUTCH


def tangent_loop(ra, rb):
    dx, dz = B[0] - A[0], B[1] - A[1]
    Ld = math.hypot(dx, dz)
    th = math.atan2(dz, dx)
    al = math.acos((ra - rb) / Ld)
    pa = lambda r, ang: (A[0] + r * math.cos(ang), A[1] + r * math.sin(ang))
    pb = lambda r, ang: (B[0] + r * math.cos(ang), B[1] + r * math.sin(ang))
    return [("A", A, pa(ra, th + al), pa(ra, th - al)),
            ("L", [pa(ra, th - al), pb(rb, th - al)]),
            ("A", B, pb(rb, th - al), pb(rb, th + al)),
            ("L", [pb(rb, th + al), pa(ra, th + al)])], Ld, al


def draw_band(segs, n_lines):
    """Belt loop from tangent_loop(): the two straight runs first, then arcs that start and end on
    the runs' own end points, so the loop closes exactly. n_lines: lines already in the sketch."""
    arc_a, run1, arc_b, run2 = segs
    c("sketch.line", points=[r6(p) for p in run1[1]])
    c("sketch.line", points=[r6(p) for p in run2[1]])
    l1, l2 = f"l{n_lines + 1}", f"l{n_lines + 2}"
    for (_, cen, st, en), start, end in ((arc_a, f"{l2}.end", f"{l1}.start"), (arc_b, f"{l1}.end", f"{l2}.start")):
        a0 = math.atan2(st[1] - cen[1], st[0] - cen[0])
        a1 = math.atan2(en[1] - cen[1], en[0] - cen[0])
        while a1 <= a0:
            a1 += 2 * math.pi
        am, rr = (a0 + a1) / 2, math.hypot(st[0] - cen[0], st[1] - cen[1])
        c("sketch.arc.three_point", start=start, end=end,
          through=[round(cen[0] + rr * math.cos(am), 6), round(cen[1] + rr * math.sin(am), 6)])


sketch_on(xz_chain, "C11 Chain #35")
outer, Ld, al = tangent_loop(R1 + 4.5, R2 + 4.5)
inner, _, _ = tangent_loop(R1 - 4.5, R2 - 4.5)
draw_band(outer, 0)
draw_band(inner, 2)
c("sketch.finish")
extrude("C11 Chain #35", 3.75, "symmetric", pick=(0, ZA - R1))
# chain length in pitches
chain_links = 2 * Ld / P35 + (Z_SPROCKET + Z_CLUTCH) / 2 + ((Z_SPROCKET - Z_CLUTCH) / (2 * math.pi)) ** 2 * P35 / Ld

# clutch: drum + sprocket on the engine PTO shaft
ex, ez = CLUTCH
revolve("C12 Centrifugal clutch 10T #35", [ex, CHAIN_Y - 52, ez], [0, 1, 0], [0, 0, 1],
        [(0, 9.6), (56, 9.6), (56, 19.5), (48, 19.5), (48, 12), (45, 12), (45, 54), (0, 54)])

# ----------------------------------------------------------------------------- engine plate and engine (envelope)
plate("P05 Engine plate", plane([0, 0, Z_DECK + R], [1, 0, 0], [0, 1, 0]),
      [(-240, -150), (X_DF + 10, -150), (X_DF + 10, 150), (-240, 150)], 5,
      holes=[], direction="positive")
# engine mounting slots: 4 x M8 on 162 x 75.5 (GX160/GX200 pattern); slots along X give +/- 15 mm
# of fore-aft travel to tension the chain. Mark from the engine itself before cutting.
sketch_on(plane([0, 0, Z_DECK + R], [1, 0, 0], [0, 1, 0]), "Engine slots")
for sx in (-1, 1):
    for sy in (-1, 1):
        cxs, cys = ENGINE_X + sx * MOUNT_X / 2, ENGINE_Y + sy * MOUNT_Y / 2
        c("sketch.slot.center_to_center", p0=[cxs - 15, cys], p1=[cxs + 15, cys], width=8.5)
c("sketch.finish")
c("solid.extrude", distance=5, direction="positive", operation="cut", targets=["P05 Engine plate"],
  name="Engine slots")
ENG = "C13 Engine Honda GX200 QX"
ex0, ey0, z0 = ENGINE_X, ENGINE_Y, ENGINE_BASE_Z
if ARGS.engine_step:
    # base on the plate and PTO shaft end where the envelope's is; the shaft on the clutch axis when
    # --engine-pto is given, else the bounding box centred fore-aft on the engine position
    pto = [float(v) for v in ARGS.engine_pto.split(",")] if ARGS.engine_pto else None
    import_step("C13", "Engine Honda GX200 QX", ARGS.engine_step, ARGS.engine_rot,
                lambda lo, hi, p: [(ex0 - p[0]) if p else ex0 - (lo[0] + hi[0]) / 2,
                                   ey0 + PTO_FACE + SHAFT_L - hi[1], z0 - lo[2]], ref=pto)
    if pto is None:
        print("C13: no --engine-pto given; check that the shaft lines up with the clutch")
else:
    box(ENG, [ex0 - 100, ey0 - 95, z0], [ex0 + 100, ey0 + PTO_FACE, z0 + 200])                 # crankcase
    box(ENG, [ex0 - 140, ey0 - 60, z0 + 120], [ex0 - 40, ey0 + 60, z0 + 225], op="join", targets=[ENG])  # cylinder
    box(ENG, [ex0 - 110, ey0 - 100, z0 + 220], [ex0 + 110, ey0 + 100, z0 + 346], op="join",
        targets=[ENG])                                                                           # fuel tank
    box(ENG, [ex0 - ENGINE_HALF_W, ey0 - 70, z0 + 150], [ex0 - 120, ey0 + 90, z0 + 260], op="join",
        targets=[ENG])                                                                           # muffler
    box(ENG, [ex0 + 100, ey0 - 80, z0 + 170], [ex0 + ENGINE_HALF_W, ey0 + 60, z0 + 300], op="join",
        targets=[ENG])                                                                           # air cleaner
    cylinder(ENG, [ex0, ey0 - 95, ez], [0, -1, 0], 170, 45, op="join", targets=[ENG])          # recoil starter
    cylinder(ENG, [ex0, ey0 + PTO_FACE, ez], [0, 1, 0], SHAFT_D, SHAFT_L, op="join", targets=[ENG])  # PTO shaft

# chain guard (1.5 mm, outboard of the chain)
outer_g, _, _ = tangent_loop(R1 + 8, R2 + 22)
sketch_on(plane([0, CHAIN_Y + 16, 0], [1, 0, 0], [0, 0, 1]), "P06 Chain guard")
draw_band(outer_g, 0)
c("sketch.circle.center", center=[0, ZA], diameter=66)
c("sketch.finish")
extrude("P06 Chain guard", 1.5, "negative", pick=(0, ZA + 70))

# ----------------------------------------------------------------------------- brake
xz_brake = plane([0, BRAKE_Y, 0], [1, 0, 0], [0, 0, 1])
sketch_on(xz_brake, "C14 Brake disc 180x4")
c("sketch.circle.center", center=[0, ZA], diameter=180)
c("sketch.circle.center", center=[0, ZA], diameter=60)
c("sketch.finish")
extrude("C14 Brake disc 180x4", 2, "symmetric", pick=(0, ZA + 70))
revolve("C15 Brake disc hub 25 mm", [0, BRAKE_Y - 2, ZA], [0, -1, 0], [0, 0, 1], ring(0, 40, 12.5, 30))
box("C16 Mechanical disc caliper (envelope)", [-115, BRAKE_Y - 20, ZA - 25], [-60, BRAKE_Y + 22, ZA + 25])
box("C16 Mechanical disc caliper (envelope)", [-100, BRAKE_Y - 4, ZA - 26], [-59, BRAKE_Y + 4, ZA + 26],
    op="cut", targets=["C16 Mechanical disc caliper (envelope)"])
plate("P07 Caliper bracket", plane([0, BRAKE_Y - 20, 0], [1, 0, 0], [0, 0, 1]),
      [(-135, Z_RAIL + R), (-55, Z_RAIL + R), (-55, ZA + 30), (-135, ZA + 30)], 6,
      holes=[(-100, ZA - 15, 8.5), (-100, ZA + 15, 8.5)], pick=(-120, Z_RAIL + 30), direction="positive")

# ----------------------------------------------------------------------------- seat: universal bucket seat
# Modelled as a 5 mm shell: flat base on the seat tabs, back reclined SEAT_RECLINE, side bolsters.
SEAT = "C17 Seat universal HDPE bucket 450"
SEAT_Z, SEAT_T = SEAT_BASE_Z, 5.0                 # underside on the seat tabs; shell thickness
SEAT_TOP = SEAT_Z + SEAT_H
_tan = math.tan(math.radians(SEAT_RECLINE))
back_x = lambda z: SEAT_REAR - (z - SEAT_Z) * _tan          # outside of the back
if ARGS.seat_step:
    # underside on the seat tabs, front edge at SEAT_FRONT, centred on the kart
    import_step("C17", "Seat", ARGS.seat_step, ARGS.seat_rot,
                lambda lo, hi, _p: [SEAT_FRONT - hi[0], -(lo[1] + hi[1]) / 2, SEAT_Z - lo[2]])
else:
    sketch_on(plane([0, 0, 0], [1, 0, 0], [0, 0, 1]), SEAT)          # XZ, normal -Y
    c("sketch.line", closed=True, points=[r6(p) for p in (
        [[SEAT_REAR, SEAT_Z], [SEAT_FRONT, SEAT_Z], [SEAT_FRONT, SEAT_Z + 70], [SEAT_FRONT - 160, SEAT_Z + 100],
         [back_x(SEAT_Z + 230) + 70, SEAT_Z + 230], [back_x(SEAT_TOP) + 40, SEAT_TOP], [back_x(SEAT_TOP), SEAT_TOP]])])
    c("sketch.finish")
    extrude(SEAT, SEAT_W / 2, "symmetric")
    cav_z0, cav_z1 = SEAT_Z + SEAT_T, SEAT_TOP + 120
    sketch_on(plane([0, 0, 0], [1, 0, 0], [0, 0, 1]), "Seat cavity")
    c("sketch.line", closed=True, points=[r6(p) for p in (
        [[back_x(cav_z0) + SEAT_T, cav_z0], [SEAT_FRONT + 10, cav_z0], [SEAT_FRONT + 10, cav_z1],
         [back_x(cav_z1) + SEAT_T, cav_z1]])])
    c("sketch.finish")
    c("solid.extrude", distance=SEAT_W / 2 - SEAT_T, direction="symmetric", operation="cut", targets=[SEAT],
      name="Seat cavity")
# seat tabs on the seat crosses under the seat's holes: 40 x 30 x 4, hole 8.5; a tab with a height
# above the tube top stands on a welded block of that height
for i, (x, y, h) in enumerate(SEAT_TABS, 1):
    plate(f"P08{i} Seat tab {i}", plane([0, 0, Z_RAIL + R + h], [1, 0, 0], [0, 1, 0]),
          [(x - 20, y - 15), (x + 20, y - 15), (x + 20, y + 15), (x - 20, y + 15)], 4,
          holes=[(x, y, 8.5)], pick=(x - 12, y), direction="positive")
    if h > 0:
        box(f"P14{i} Seat tab block {i}", [x - 15, y - 12, Z_RAIL + R], [x + 15, y + 12, Z_RAIL + R + h])
# seat-back tabs: 4 mm plates welded to the front of the deck front cross, parallel to the seat back;
# an M8 bolt goes through tab, spacer washers and seat back
for y in (-100, 100):
    plate(f"P09 Seat back tab {'L' if y > 0 else 'R'}", plane([X_DF + R, 0, 0], [0, 1, 0], [0, 0, 1]),
          [(y - 15, Z_DECK - 17), (y + 15, Z_DECK - 17), (y + 15, Z_DECK + 17), (y - 15, Z_DECK + 17)], 4,
          holes=[(y, Z_DECK + 5, 8.5)], pick=(y, Z_DECK - 10), direction="positive")

# ----------------------------------------------------------------------------- steering column
cx, cz = WHEEL_C
dcol = unit([COL_BOTTOM[0] - cx, 0, COL_BOTTOM[1] - cz])
L_COL = norm([COL_BOTTOM[0] - cx, 0, COL_BOTTOM[1] - cz])
ucol = [-dcol[2], 0, dcol[0]]        # perpendicular "up" in XZ
if ucol[2] < 0:
    ucol = v_mul(ucol, -1)
P = lambda t: [cx + dcol[0] * t, 0.0, cz + dcol[2] * t]
tube_body("M06 Steering column 20x2.5", P(-20), P(L_COL), od=20, wall=2.5)
revolve("C18 Steering wheel hub", P(-20), dcol, [0, 1, 0], ring(0, 30, 10, 22))
# wheel rim: torus as revolved circle (polygon approx. of the Ø22 grip section)
grip = [(round(11 * math.cos(math.radians(a)), 4), round(140 + 11 * math.sin(math.radians(a)), 4))
        for a in range(0, 360, 30)]
revolve("C19 Steering wheel Ø280", P(-12), dcol, [0, 1, 0], grip)
for k, ang in enumerate((90, 210, 330)):
    a = math.radians(ang)
    dirv = v_add(v_mul(ucol, math.cos(a)), v_mul([0, 1, 0], math.sin(a)))
    p0 = v_add(P(-12), v_mul(dirv, 20))
    cylinder(f"C19{k + 1} Steering wheel spoke {k + 1}", p0, dirv, 12, 112)

# upper column bushing bracket: plate perpendicular to the column through the hoop-top axis
t_up = dot(v_sub([HOOP_T[0], 0, HOOP_T[2]], P(0)), dcol)
Pu = P(t_up)
h_up = norm(v_sub([HOOP_T[0], 0, HOOP_T[2]], Pu))
plate("P10 Column upper bracket", plane(Pu, [0, 1, 0], ucol),
      [(-25, -22), (25, -22), (25, h_up - R), (-25, h_up - R)], 6, holes=[(0, 0, 20.5)], pick=(0, -18),
      direction="symmetric")
revolve("C20 Column bushing Ø20 (nylon)", v_add(Pu, v_mul(dcol, 3)), dcol, [0, 1, 0], ring(0, 20, 10, 20))
revolve("C20 Column bushing Ø20 (nylon) b", v_sub(Pu, v_mul(dcol, 23)), dcol, [0, 1, 0], ring(0, 20, 10, 20))

# lower bracket on the front axle beam with a UCFL204 flange bearing
t_lo = dot(v_sub([WB, 0, ZA], P(0)), dcol)
Pl = P(t_lo)
h_lo = norm(v_sub([WB, 0, ZA], Pl))
plate("P11 Column lower bracket", plane(Pl, [0, 1, 0], ucol),
      [(-60, 30), (60, 30), (60, -(h_lo - R)), (-60, -(h_lo - R))], 6, holes=[(0, 0, 30), (-45, 0, 10.5), (45, 0, 10.5)],
      pick=(0, -(h_lo - R) + 10), direction="symmetric")
bl = "C21 Flange bearing UCFL204"
sketch_on(plane(v_sub(Pl, v_mul(dcol, 3)), [0, 1, 0], ucol), bl)
draw_loop([("L", [(-45, -12), (45, -12)]), ("A", (45, 0), (45, -12), (45, 12)),
           ("L", [(45, 12), (-45, 12)]), ("A", (-45, 0), (-45, 12), (-45, -12))])
c("sketch.circle.center", center=[0, 0], diameter=20)
c("sketch.circle.center", center=[-45, 0], diameter=10.5)
c("sketch.circle.center", center=[45, 0], diameter=10.5)
c("sketch.finish")
extrude(bl, 12, "negative", pick=(-20, 0))       # toward the wheel (-dcol is the sketch normal side)
# pitman arm
t_pit = L_COL - 12
Pp = P(t_pit)
plate("M07 Pitman arm", plane(Pp, [0, 1, 0], ucol), None, 6,
      holes=[(0, 0, 20.5), (-45, 0, 8.2), (45, 0, 8.2)], pick=(-20, 8), direction="symmetric",
      segs=[("L", [(-45, -12.5), (45, -12.5)]), ("A", (45, 0), (45, -12.5), (45, 12.5)),
            ("L", [(45, 12.5), (-45, 12.5)]), ("A", (-45, 0), (-45, 12.5), (-45, -12.5))])

# tie rods with rod ends
for s, side in ((1, "L"), (-1, "R")):
    tip = MEMBER_BY_ID[f"ARM{side}"]
    a_end = [tip[0], tip[1], KP_Z0 + 2 + 6 + 5]
    p_end = v_add(Pp, [0, s * 45, 0])
    p_end = v_add(p_end, v_mul(dcol, 8))
    dtr = unit(v_sub(a_end, p_end))
    Ltr = norm(v_sub(a_end, p_end))
    cylinder(f"C22{side} Rod end M8 (pitman) {side}", v_sub(p_end, v_mul(dcol, -4.5)), v_mul(dcol, -1), 22, 9)
    cylinder(f"C23{side} Rod end M8 (arm) {side}", [tip[0], tip[1], KP_Z0 + 8], [0, 0, 1], 22, 9)
    cylinder(f"M08{side} Tie rod Ø12 M8 LH/RH {side}", v_add(p_end, v_mul(dtr, 18)), dtr, 12, Ltr - 36)
    MEMBER_BY_ID[f"TIE{side}"] = Ltr

# ----------------------------------------------------------------------------- pedals
for y, side, label in ((60.0, "L", "brake"), (-60.0, "R", "throttle")):
    piv = [850.0, y, Z_RAIL + R + 15]
    for dy in (-12, 12):
        plate(f"P12{side} Pedal clevis tab {side}{'a' if dy < 0 else 'b'}",
              plane([0, y + dy, 0], [1, 0, 0], [0, 0, 1]),
              [(835, Z_RAIL + R), (865, Z_RAIL + R), (865, piv[2] + 10), (835, piv[2] + 10)], 4,
              holes=[(850, piv[2], 8.5)], pick=(840, Z_RAIL + R + 3),
              direction="symmetric")
    top = [815.0, y, 285.0]
    arm = v_sub(top, piv)
    cylinder(f"M09{side} Pedal arm ({label}) {side}", piv, arm, 16, norm(arm))
    box(f"P13{side} Pedal pad ({label}) {side}", [top[0] - 5, y - 35, top[2] - 50], [top[0] + 3, y + 35, top[2] + 10])

# ----------------------------------------------------------------------------- appearance / material
body_names = []
for cm in cmds:
    bn = cm["params"].get("body_name") or (cm["params"].get("name") if cm["command"] == "body.rename" else None)
    if bn and bn not in body_names:
        body_names.append(bn)

groups = {
    "frame": [b for b in body_names if b.startswith(("F0", "F1", "F2"))],
    "plates": [b for b in body_names if b.startswith("P") and not b.startswith(("P01", "P05", "P06"))],
    "pan": [b for b in body_names if b.startswith(("P01", "P05", "P06"))],
    "steel": [b for b in body_names if b.startswith(("M0", "C02", "C03", "C08", "C10", "C15", "C18"))],
    "tyre": [b for b in body_names if b.startswith("C04")],
    "rim": [b for b in body_names if b.startswith(("C05", "C06"))],
    "bearing": [b for b in body_names if b.startswith(("C01", "C07", "C21"))],
    "sprocket": [b for b in body_names if b.startswith(("C09", "C14"))],
    "chain": [b for b in body_names if b.startswith(("C11", "C12", "C16", "C19", "C20", "C22", "C23"))],
    "engine": [b for b in body_names if b.startswith("C13")],
    "seat": [b for b in body_names if b.startswith("C17")],
}
style = {
    "frame": ("Steel", {"color": "#d0402a"}),
    "plates": ("Steel", {"color": "#d0402a"}),
    "pan": ("Steel", "Aluminum - Satin"),
    "steel": ("Steel", "Steel - Satin"),
    "tyre": ("Default", "Rubber - Black"),
    "rim": ("Steel", "Paint - Gloss White"),
    "bearing": ("Steel", "Stainless Steel - Brushed"),
    "sprocket": ("Steel", "Steel - Satin"),
    "chain": ("Steel", "Aluminum - Anodized Black"),
    "engine": ("Nylon", {"color": "#3b3b40"}),   # envelope; density chosen so its mass ~ a real 196 cc engine
    "seat": ("Polycarbonate", "ABS - Black"),     # fibreglass shell; ~1.2 g/cm3 gives ~2.5 kg
}
for g, bodies in groups.items():
    if not bodies:
        continue
    mat, ap = style[g]
    c("material.assign", bodies=bodies, material=mat)
    if isinstance(ap, str):
        c("appearance.assign", bodies=bodies, appearance=ap)
    else:
        c("appearance.assign", bodies=bodies, **ap)

json.dump({"commands": cmds}, open(ARGS.out, "w"), indent=1)
with open("cut_list.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(cut_rows[0].keys()))
    w.writeheader()
    w.writerows(cut_rows)
# ============================================================================= bill of materials
# (part id prefix in the model or "" when not modelled, category, description, specification,
#  material / standard, qty, unit, catalogue mass each in kg or "", notes)
BUY, MAKE_T, MAKE_P, MAKE_M, FAST = "buy", "make: tube", "make: plate", "make: machined", "buy: fastener"
n_stock = math.ceil(total_len * 1.1 / 6000)
BOM = [
    ("C13", BUY, "Engine", "Honda GX200 QX (GX200UT2QX2): 196 cc OHV, 5.5 hp at 3600 rpm (governed), "
     "3/4 in x 2-7/16 in keyed shaft, 313 x 376 x 346 mm",
     "-", 1, "pc", 16.1, "Same base pattern and shaft: Predator 212 non-hemi, Loncin G200F (clones use 5/16-24 "
     "mounting bolts)"),
    ("C12", BUY, "Centrifugal clutch", "Dry centrifugal clutch, 3/4 in bore, 10T ANSI #35, engages ~2000 rpm",
     "-", 1, "pc", "", "Max-Torque / Hilliard type"),
    ("C11", BUY, "Roller chain", f"ANSI #35 roller chain, {CHAIN_LINKS} links incl. 1 connecting link",
     "ISO 606 06C-1", 1, "pc", "", f"centre distance {_centres(CHAIN_LINKS):.1f} mm, tension with engine slots"),
    ("C09", BUY, "Axle sprocket", "72T ANSI #35 bolt-on sprocket", "ISO 606 06C-1", 1, "pc", "",
     "bolt pattern to match C10"),
    ("C10", BUY, "Sprocket hub", "Sprocket hub, 25 mm bore, 8 mm keyway, set screws", "-", 1, "pc", "", ""),
    ("C07", BUY, "Rear axle bearing", "UCFL205 2-bolt flange unit, 25 mm bore, set-screw insert", "ISO 9628",
     2, "pc", 0.8, "bolt centres 99 mm"),
    ("C08", BUY, "Shaft collar", "Set-screw shaft collar, 25 mm", "-", 2, "pc", "", "inboard of the bearings"),
    ("C06", BUY, "Rear wheel hub", "Bolt-on hub, 25 mm bore, 8 mm keyway, flange to suit C05", "-", 2, "pc", "",
     "buy as a set with the rims"),
    ("C04", BUY, "Tyre", "13x5.00-6 off-road / knobby, tubeless", "-", 4, "pc", "", ""),
    ("C05", BUY, "Rim", "6 x 4.5 in steel 2-piece rim; front rims bored for 2 x 6204", "-", 4, "pc", "", ""),
    ("C01", BUY, "Front wheel bearing", "6204-2RS deep-groove ball bearing 20 x 47 x 14", "ISO 15", 4, "pc",
     0.106, ""),
    ("", BUY, "Kingpin bush", "Flanged PTFE-lined bush 12 x 14 x 12 (e.g. SKF PCMF 121412E)", "ISO 3547", 4,
     "pc", "", "press into M01 after reaming to 14 H7"),
    ("C03", FAST, "Kingpin bolt", "Hex bolt M12 x 90, 8.8, with nylock nut and 2 washers", "ISO 4014 / 10511",
     2, "set", "", ""),
    ("C02", FAST, "Stub-axle nut", "Nylock nut M20 x 1.5 + washer 20", "ISO 10512 / 7089", 2, "set", "", ""),
    ("", FAST, "Cotter pin", "Split pin 3.2 x 32", "ISO 1234", 2, "pc", "", "stub-axle nut lock"),
    ("C22", BUY, "Rod end, pitman side", "Female rod end M8 right-hand (e.g. SKF SI 8 E)", "ISO 12240-4", 2,
     "pc", "", ""),
    ("C23", BUY, "Rod end, steering-arm side", "Female rod end M8 left-hand (e.g. SKF SIL 8 E)", "ISO 12240-4",
     2, "pc", "", ""),
    ("", FAST, "Rod-end bolts", "Hex bolt M8 x 35, 8.8, nylock nut, 2 washers", "ISO 4014 / 10511", 4, "set",
     "", ""),
    ("", FAST, "Tie-rod jam nuts", "Hex nut M8 RH x 2, M8 LH x 2", "ISO 4032", 4, "pc", "", ""),
    ("C19", BUY, "Steering wheel", "Kart steering wheel 280 mm, 3-bolt", "-", 1, "pc", "", "model: rim + spokes"),
    ("C18", BUY, "Steering wheel hub", "3-bolt steering hub for 20 mm column", "-", 1, "pc", "", ""),
    ("C21", BUY, "Column lower bearing", "UCFL204 2-bolt flange unit, 20 mm bore", "ISO 9628", 1, "pc", 0.6,
     "bolt centres 90 mm"),
    ("C20", BUY, "Column upper bush", "Split nylon steering-column bush, 20 mm (2 halves)", "-", 1, "set", "",
     "model: 2 halves"),
    ("C14", BUY, "Brake disc", "Steel brake disc 180 x 4 mm", "-", 1, "pc", "", ""),
    ("C15", BUY, "Brake disc hub", "Disc hub, 25 mm bore, 8 mm keyway", "-", 1, "pc", "", ""),
    ("C16", BUY, "Brake caliper", "Mechanical (cable) disc caliper for 4 mm disc", "-", 1, "pc", "",
     "drill P07 to its bolt pattern"),
    ("", BUY, "Brake cable", "Brake cable with housing and adjuster, 1.5 m", "-", 1, "pc", "", ""),
    ("", BUY, "Throttle cable", "Throttle cable with housing, 1.5 m, to suit the engine's governor lever", "-",
     1, "pc", "", ""),
    ("C17", BUY, "Seat", "Universal high-back plastic (HDPE) go-kart bucket seat, about 450 W x 355 H x 370 D, "
     "4 mounting holes 254 x 273 (10 x 10-3/4 in)", "-", 1, "pc", "",
     "sold for karts, buggies and drift trikes; check the hole pattern on arrival; add a seat cushion"),
    ("", BUY, "Keys", "Parallel key 8 x 7 x 30", "DIN 6885 A", 4, "pc", "", "hubs, sprocket hub, disc hub"),
    ("", BUY, "Pedal return springs", "Extension spring ~50 N", "-", 2, "pc", "", ""),
    ("", BUY, "Tube end plugs", "Plastic end plug for 25 x 2 tube", "-", 6, "pc", "", "F01 x2, F15 x2, F16 x2"),
    ("", FAST, "Bearing bolts UCFL205", "Hex bolt M10 x 40, 8.8, nylock nut, 2 washers", "ISO 4017 / 10511", 4,
     "set", "", ""),
    ("", FAST, "Bearing bolts UCFL204", "Hex bolt M10 x 30, 8.8, nylock nut, 2 washers", "ISO 4017 / 10511", 2,
     "set", "", ""),
    ("", FAST, "Engine bolts", "Hex bolt M8 x 25, 8.8, spring + flat washer (into the engine's M8 base)",
     "ISO 4017", 4, "set", "", "5/16-24 UNF on most clones"),
    ("", FAST, "Seat bolts", "Hex bolt M8 x 25, 8.8, large washer 8.4 x 24, nylock nut", "ISO 4017 / DIN 9021",
     6, "set", "", "4 base + 2 back"),
    ("", FAST, "Caliper bolts", "Hex bolt M8 x 30, 8.8, nylock nut", "ISO 4017 / 10511", 2, "set", "", ""),
    ("", FAST, "Pedal pivot bolts", "Shoulder bolt 8 x 30 (M6) or M8 x 45 bolt with nylock nut", "ISO 7379", 2,
     "set", "", ""),
    ("", FAST, "Chain guard fasteners", "M6 rivet nut + M6 x 12 button screw", "ISO 7380", 3, "set", "", ""),
    ("", FAST, "Floor pan rivets", "Blind rivet 4.8 x 12 steel", "ISO 15983", 24, "pc", "",
     "or stitch-weld"),
    ("F", MAKE_T, "Frame tubes", f"Round tube 25 x 2.0, {len(cut_rows)} pieces, total {total_len / 1000:.2f} m "
     f"(see cut_list.csv); order {n_stock} x 6 m", "EN 10305-3 E235 (or 1 in x 14 ga DOM)", len(cut_rows), "pc",
     "", "copes and mitres per cut_list.csv"),
    ("M05", MAKE_M, "Rear axle", "Dia 25 h9 x 860, keyways 8 x 4 at hubs, sprocket and disc hub", "C45 bright bar",
     1, "pc", "", ""),
    ("M01", MAKE_M, "Knuckle sleeve", "Tube 22 x 4 x 48, ream 14 H7 after welding", "E355 tube", 2, "pc", "", ""),
    ("M02", MAKE_M, "Stub axle", "Dia 20 x 162, thread M20 x 1.5 x 25, 3.2 mm cotter hole", "S355 bright bar", 2,
     "pc", "", "weld to M01 in a fixture"),
    ("M03", MAKE_M, "Steering arm", "6 mm plate, hole 8.2 at 80 mm from kingpin", "S235", 2, "pc", "", ""),
    ("M04", MAKE_M, "Stub-axle spacer", "Tube 28 x 4 x 44.5, faces square", "E235 tube", 2, "pc", "", ""),
    ("M06", MAKE_M, "Steering column", "Tube 20 x 2.5 x 510", "E355 tube", 1, "pc", "", ""),
    ("M07", MAKE_M, "Pitman arm", "6 mm plate, hole 20.5 + 2 x 8.2 at +/-45", "S235", 1, "pc", "", ""),
    ("M08", MAKE_M, "Tie rod", "Dia 12 x ~165, M8 RH one end, M8 LH other, 20 deep", "S235 bright bar", 2, "pc",
     "", "set toe-in 0-2 mm"),
    ("M09", MAKE_M, "Pedal arm", "Tube 16 x 2 x 171 with 8.5 pivot boss", "E235 tube", 2, "pc", "", ""),
    ("P01", MAKE_P, "Floor pan", "1.5 mm sheet, 700 x 525 outline", "DC01 / S235", 1, "pc", "", ""),
    ("P02", MAKE_P, "Rear bearing plate", "8 mm, 150 x 157, hole 45 + 2 x 12 at 99", "S235", 2, "pc", "", ""),
    ("P03", MAKE_P, "Kingpin back plate", "6 mm, 40 x 62", "S235", 2, "pc", "", ""),
    ("P04", MAKE_P, "Kingpin ear", "6 mm, 40 x 39 with R20 end, hole 12.2", "S235", 4, "pc", "", ""),
    ("P05", MAKE_P, "Engine plate", "5 mm, 390 x 300, 4 slots 8.5 x 30 (mark from the engine)", "S235", 1, "pc",
     "", ""),
    ("P06", MAKE_P, "Chain guard", "1.5 mm sheet, follows the chain, hole 66 for the hub, 15 mm folded lip",
     "DC01", 1, "pc", "", ""),
    ("P07", MAKE_P, "Caliper bracket", "6 mm, 80 x 92.5, 2 x 8.5 (match caliper)", "S235", 1, "pc", "", ""),
    ("P08", MAKE_P, "Seat tab", "4 mm, 40 x 30, hole 8.5, under the seat's mounting holes", "S235", len(SEAT_TABS),
     "pc", "", ""),
] + [
    ("P14", MAKE_P, "Seat tab block", "30 x 24 flat bar stack / block under a raised seat tab, height " +
     ", ".join(f"{t[2]:.0f}" for t in SEAT_TABS if t[2] > 0), "S235", sum(1 for t in SEAT_TABS if t[2] > 0), "pc",
     "", "") for _ in [0] if any(t[2] > 0 for t in SEAT_TABS)
] + [
    ("P09", MAKE_P, "Seat-back tab", "4 mm, 30 x 34, hole 8.5 (bolts through the seat back)", "S235", 2, "pc",
     "", "drill the seat back on assembly"),
    ("P10", MAKE_P, "Column upper bracket", "6 mm, 50 x 55, hole 20.5", "S235", 1, "pc", "", ""),
    ("P11", MAKE_P, "Column lower bracket", "6 mm, 120 x 65, hole 30 + 2 x 10.5 at 90", "S235", 1, "pc", "", ""),
    ("P12", MAKE_P, "Pedal clevis tab", "4 mm, 30 x 25, hole 8.5", "S235", 4, "pc", "", ""),
    ("P13", MAKE_P, "Pedal pad", "8 mm, 70 x 60, knurled", "S235", 2, "pc", "", ""),
]
# every modelled part id must match the number of bodies in the model
ONE_PIECE = {"C19": 4, "C20": 2, "C07": 2}   # wheel = rim + 3 spokes; bush = 2 halves; housing + insert
ONE_PIECE.update(IMPORTED)                     # a vendor STEP may hold several bodies for one part
for pid, cat, *_rest in BOM:
    if not pid or pid == "F":
        continue
    qty = _rest[3]
    found = sum(1 for bn in body_names if bn.startswith(pid))
    expect = qty * ONE_PIECE.get(pid, 1)
    if found != expect:
        raise SystemExit(f"BOM {pid}: {found} bodies in the model, BOM says {expect}")
listed = {r[0] for r in BOM if r[0]}
for bn in body_names:
    if bn[0] != "F" and not any(bn.startswith(p) for p in listed):
        raise SystemExit(f"model body {bn!r} has no BOM row")
with open("bom.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["item", "part_id", "category", "description", "specification", "material_standard", "qty",
                "unit", "mass_each_kg", "notes"])
    for i, (pid, cat, desc, spec, mat, qty, unit, mass, note) in enumerate(BOM, 1):
        w.writerow([i, pid, cat, desc, spec, mat, qty, unit, mass, note])

print(len(cmds), "commands,", len(body_names), "bodies, tube", round(total_len), "mm, chain", round(chain_links, 2))
