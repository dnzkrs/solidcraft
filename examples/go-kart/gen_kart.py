"""SolidCraft script generator for a youth off-road go-kart (welded 25x2 steel tube frame).

Frame: X forward (driver faces +X), Y left, Z up, ground at Z = 0, rear axle on the Y axis
at X = 0. All dimensions in millimetres.

Writes:
  go_kart.json       the SolidCraft command script (solvecraft-cli run/eval/snapshot)
  cut_list.csv       tube cut list with cope/mitre end preparation
"""
import csv
import json
import math

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
ENGINE_X, ENGINE_BASE_Z, CRANK_H = -60.0, 262.5, 95.0
CLUTCH = (ENGINE_X, ENGINE_BASE_Z + CRANK_H)      # (x, z) in the chain plane
WHEEL_C = (540.0, 460.0)                 # steering wheel centre (x, z)
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
            _, cen, st, en = s
            c("sketch.arc.center_point", center=[round(cen[0], 6), round(cen[1], 6)],
              start=[round(st[0], 6), round(st[1], 6)], end=[round(en[0], 6), round(en[1], 6)])


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


# ============================================================================= FRAME
# nodes (left side; right side mirrored in Y)
RC = (-260.0, 250.0, Z_RAIL)        # rear corner
M1 = (480.0, 250.0, Z_RAIL)         # start of front taper
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
    member(f"F14{side}", f"Deck front upright {side}", [140.0, 250.0 * s, Z_RAIL], [140.0, 250.0 * s, Z_DECK], ("cope", f"F01{side}"), ("cope", "F16"))
    member(f"F17{side}", f"Deck rail {side}", [X_RU, 140.0 * s, Z_DECK], [140.0, 140.0 * s, Z_DECK], ("cope", "F15"), ("cope", "F16"))
    member(f"F18{side}", f"Rear diagonal {side}", [X_RU, 250.0 * s, 200.0], [-160.0, 250.0 * s, Z_RAIL], ("cope", f"F13{side}"), ("cope", f"F01{side}"))
    member(f"F19{side}", f"Deck front brace {side}", [140.0, 250.0 * s, 175.0], [250.0, 250.0 * s, Z_RAIL], ("cope", f"F14{side}"), ("cope", f"F01{side}"))
    member(f"F20{side}", f"Hoop upright {side}", m(HOOP_B, s), m(HOOP_K, s), ("cope", f"F03{side}"), ("mitre", f"F21{side}"))
    member(f"F21{side}", f"Hoop shoulder {side}", m(HOOP_K, s), m(HOOP_T, s), ("mitre", f"F20{side}"), ("mitre", "F22"))
    member(f"F23{side}", f"Side rail {side}", [140.0, 250.0 * s, Z_SIDE], m(SIDE_F, s), ("cope", f"F14{side}"), ("cope", f"F20{side}"))

member("F05", "Nose cross", m(N1, 1), m(N1, -1), ("mitre", "F04L"), ("mitre", "F04R"))
member("F06", "Rear cross", m(RC, 1), m(RC, -1), ("cope", "F01L"), ("cope", "F01R"))
member("F07", "Seat cross front", [440.0, 250.0, Z_RAIL], [440.0, -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F08", "Seat cross rear", [200.0, 250.0, Z_RAIL], [200.0, -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F09", "Brake cross", [-120.0, 250.0, Z_RAIL], [-120.0, -250.0, Z_RAIL], ("cope", "F01L"), ("cope", "F01R"))
member("F10", "Pedal cross", [850.0, 150.0, Z_RAIL], [850.0, -150.0, Z_RAIL], ("cope", "F03L"), ("cope", "F03R"))
member("F12", "Front axle beam", [WB, FA, ZA], [WB, -FA, ZA], ("sq", "welds to kingpin bracket back plate"), ("sq", "welds to kingpin bracket back plate"))
member("F15", "Deck rear cross", [X_RU, 250.0, Z_DECK], [X_RU, -250.0, Z_DECK], ("cap", "runs 12.5 past F13L, end plug"), ("cap", "runs 12.5 past F13R, end plug"))
member("F16", "Deck front cross", [140.0, 250.0, Z_DECK], [140.0, -250.0, Z_DECK], ("cap", "runs 12.5 past F14L, end plug"), ("cap", "runs 12.5 past F14R, end plug"))
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
pan_pts = [(200, 262.5), (480, 262.5), (630, 162.5), (900, 162.5), (900, -162.5), (630, -162.5),
           (480, -262.5), (200, -262.5)]
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


sketch_on(xz_chain, "C11 Chain #35")
outer, Ld, al = tangent_loop(R1 + 4.5, R2 + 4.5)
inner, _, _ = tangent_loop(R1 - 4.5, R2 - 4.5)
draw_loop(outer)
draw_loop(inner)
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
      [(-240, -150), (150, -150), (150, 150), (-240, 150)], 5,
      holes=[], direction="positive")
# engine mounting slots (GX160/GX200-pattern engines: 4 x M8 on about 162 x 75.5; slots along X
# give +/- 15 mm of fore-aft travel to tension the chain)
sketch_on(plane([0, 0, Z_DECK + R], [1, 0, 0], [0, 1, 0]), "Engine slots")
for sx in (-1, 1):
    for sy in (-1, 1):
        cxs, cys = ENGINE_X + sx * 75.5 / 2, 15.0 + sy * 81.0
        c("sketch.slot.center_to_center", p0=[cxs - 15, cys], p1=[cxs + 15, cys], width=8.5)
c("sketch.finish")
c("solid.extrude", distance=5, direction="positive", operation="cut", targets=["P05 Engine plate"],
  name="Engine slots")
ENG = "C13 Engine 196-212 cc OHV (envelope)"
box(ENG, [ENGINE_X - 130, -90, ENGINE_BASE_Z], [ENGINE_X + 130, 120, ENGINE_BASE_Z + 170])
box(ENG, [ENGINE_X - 110, -110, ENGINE_BASE_Z + 170], [ENGINE_X + 110, 110, ENGINE_BASE_Z + 270],
    op="join", targets=[ENG])
cylinder(ENG, [ENGINE_X, -90, ez], [0, -1, 0], 160, 40, op="join", targets=[ENG])
cylinder(ENG, [ENGINE_X, 120, ez], [0, 1, 0], 19.05, CHAIN_Y - 52 - 120 + 56, op="join", targets=[ENG])

# chain guard (1.5 mm, outboard of the chain)
outer_g, _, _ = tangent_loop(R1 + 8, R2 + 22)
sketch_on(plane([0, CHAIN_Y + 16, 0], [1, 0, 0], [0, 0, 1]), "P06 Chain guard")
draw_loop(outer_g)
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

# ----------------------------------------------------------------------------- seat (composite kart seat, envelope)
SEAT = "C17 Kart seat size S (envelope)"
sketch_on(plane([0, 0, 0], [1, 0, 0], [0, 0, 1]), SEAT)          # XZ, normal -Y
c("sketch.line", closed=True, points=[[190, 106.5], [440, 106.5], [440, 115.5], [205, 115.5], [160, 470],
                                      [150, 470]])
c("sketch.finish")
extrude(SEAT, 150, "symmetric")
# seat tabs welded on the seat crosses: 40 x 25 x 4 flat bar standing up, hole 8.5
for i, (x, y) in enumerate([(200, -110), (200, 110), (440, -110), (440, 110)], 1):
    plate(f"P08{i} Seat tab {i}", plane([0, 0, Z_RAIL + R], [1, 0, 0], [0, 1, 0]),
          [(x - 20, y - 15), (x + 20, y - 15), (x + 20, y + 15), (x - 20, y + 15)], 4,
          holes=[(x, y, 8.5)], pick=(x - 12, y), direction="positive")
# seat back support straps from the deck front cross
for y in (-100, 100):
    plate(f"P09 Seat back tab {'L' if y > 0 else 'R'}", plane([0, y, 0], [1, 0, 0], [0, 0, 1]),
          [(140 + R, Z_DECK - 15), (171, Z_DECK - 15), (167.5, Z_DECK + 15), (140 + R, Z_DECK + 15)], 4,
          holes=[(162, Z_DECK, 8.5)], pick=(156, Z_DECK - 10), direction="symmetric")

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
    bn = cm["params"].get("body_name")
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
    "seat": ("ABS Plastic", "ABS - Black"),
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

json.dump({"commands": cmds}, open("go_kart.json", "w"), indent=1)
with open("cut_list.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(cut_rows[0].keys()))
    w.writeheader()
    w.writerows(cut_rows)
print(len(cmds), "commands,", len(body_names), "bodies, tube", round(total_len), "mm, chain", round(chain_links, 2))
