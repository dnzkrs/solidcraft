"""SolidCraft script generator for the parts of the Lanz mini tractor (model engine and chassis).

Drawings: "Lanz Mini Tractor", JDW Draughting Services (J.A.M. de Waal, 2014), after the original
drawings by C.P. Hendrikx (1996). Part numbers and names follow the drawings' parts list (sheet 02).

Each part is modelled on its own, in its own coordinate system (stated per part), in mm.
Every dimension used is in the part's parameter block, with the drawing it comes from.

Writes, for each part, into parts/:
  <part>.json          the SolidCraft command script (solvecraft-cli run/eval/snapshot)
and with --build also:
  <part>.solvecraft    the design, <part>.step, <part>.png (iso snapshot)
and checks each model against a hand-computed volume.

  python3 gen_parts.py               # write the scripts
  python3 gen_parts.py --build       # also build, export and check them
  python3 gen_parts.py --build 1-02  # only these parts
"""
import argparse
import json
import math
import os
import re
import shutil
import struct
import subprocess

_here = os.path.dirname(os.path.abspath(__file__))
_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument("parts", nargs="*", help="part numbers to write (default: all)")
_ap.add_argument("--build", action="store_true", help="build, export and check the parts")
_ap.add_argument("--cli", default=os.environ.get("SOLVECRAFT_CLI") or shutil.which("solvecraft-cli")
                 or os.path.join(_here, "..", "..", "target", "release", "solvecraft-cli"))
ARGS = _ap.parse_args()

OUT = os.path.join(_here, "parts")
PARTS = {}


def part(number, name, material):
    """Registers a part builder: fn(Script) fills the script, returns the hand-estimated volume (mm³)."""
    def reg(fn):
        PARTS[number] = (name, material, fn)
        return fn
    return reg


class Script:
    def __init__(self, body):
        self.body = body
        self.cmds = []

    def cmd(self, command, **params):
        self.cmds.append({"command": command, "params": params})

    def param(self, name, value, comment, unit="mm"):
        self.cmd("parameters.add", name=name, expression=f"{value:g}", unit=unit, comment=comment)
        return value

    def sketch(self, name, origin, x_dir, y_dir):
        """A sketch on the plane through `origin` spanned by `x_dir`, `y_dir` (sketch y is y_dir)."""
        self.cmd("sketch.create", plane={"origin": list(origin), "x_dir": list(x_dir), "y_dir": list(y_dir)},
                 name=name)

    def polyline(self, pts):
        self.cmd("sketch.line", points=[[round(x, 6), round(y, 6)] for x, y in pts], closed=True)

    def loop(self, start, segs):
        """A closed loop from `start`: segs are ("line", end) or ("arc", centre, end, ccw); the last
        segment must end at `start`."""
        rnd = lambda p: [round(p[0], 6), round(p[1], 6)]
        p = start
        for seg in segs:
            if seg[0] == "line":
                self.cmd("sketch.line", points=[rnd(p), rnd(seg[1])])
                p = seg[1]
            else:
                _, c, e, ccw = seg
                a, b = (p, e) if ccw else (e, p)
                self.cmd("sketch.arc.center_point", center=rnd(c), start=rnd(a), end=rnd(b))
                p = e
        assert math.dist(p, start) < 1e-9, "loop is not closed"

    def finish(self):
        self.cmd("sketch.finish")

    def holes(self, name, origin, into, centres, diameter, depth=None):
        """A hole pattern as one feature: circles in a sketch on the plane through `origin` normal
        to `into`, cut `depth` deep along `into` (through all without a depth). `centres` are world
        points on that plane. (One cut per pattern: holes added one by one with solid.hole can come
        out 3.4 mm short after a 'coincident-face separation' boolean retry.)"""
        n = _unit(into)
        x = _unit(_cross(n, (0, 0, 1)) if abs(n[2]) < 0.9 else _cross((0, 1, 0), n))
        y = _cross(n, x)                       # x × y = n: the cut goes along `into`
        self.sketch(name, origin, x, y)
        for c in centres:
            d = [c[i] - origin[i] for i in range(3)]
            assert abs(sum(d[i] * n[i] for i in range(3))) < 1e-9, f"{name}: centre off the sketch plane"
            self.cmd("sketch.circle.center", center=[round(sum(d[i] * x[i] for i in range(3)), 6),
                                                      round(sum(d[i] * y[i] for i in range(3)), 6)],
                     diameter=diameter)
        self.finish()
        cut = {"through_all": True} if depth is None else {"distance": depth}
        self.cmd("solid.extrude", **cut, operation="cut", targets=[self.body], name=name)


def _unit(v):
    m = math.sqrt(sum(c * c for c in v))
    return tuple(c / m for c in v)


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def ring_pts(n, radius, start_deg):
    return [(radius * math.cos(math.radians(start_deg + i * 360 / n)),
             radius * math.sin(math.radians(start_deg + i * 360 / n))) for i in range(n)]


def grid_area(inside, x0, x1, y0, y1, h=0.025):
    """Area of {(x, y): inside(x, y)} in the box, by midpoint sampling on an h grid."""
    nx, ny = int(round((x1 - x0) / h)), int(round((y1 - y0) / h))
    n = 0
    for i in range(nx):
        x = x0 + (i + 0.5) * h
        for j in range(ny):
            if inside(x, y0 + (j + 0.5) * h):
                n += 1
    return n * h * h


# ----------------------------------------------------------------------------- 1-01
@part("1-01", "Motor frame", "Aluminum")
def motor_frame(s):
    """Sheet 03, 1-01 (scale 1:1.5, section A-A 1:2). X along the engine: X = 0 on the outer face
    of the cylinder upright, the crankshaft end at X = 96. Y across (symmetric), Z up from the
    underside. The cylinder axis is X at Z = 70; the crankshaft axis is Y at X = 68, Z = 70."""
    L = s.param("frame_length", 96, "overall length")
    W = s.param("frame_width", 56, "overall width (28 + 28)")
    HB = s.param("frame_base_h", 35, "base height (the U floor; 100 - 65.5 = 34.5 on the drawing)")
    TU = s.param("frame_upright_t", 12, "cylinder upright thickness")
    HU = s.param("frame_upright_h", 100, "cylinder upright height")
    RU = s.param("frame_upright_r", 10, "upright top corners, U and cheek fillets")
    ZC = s.param("frame_axis_z", 70, "cylinder and crankshaft axis height")
    DCB = s.param("frame_cyl_bore", 33, "cylinder spigot bore in the upright")
    PCD = s.param("frame_pcd", 44, "4 x Ø4.5 on PCD 44 at 45 deg (cylinder bolts)")
    XK0 = s.param("frame_cheek_x0", TU + 40, "cheek inner (cylinder-side) face, 12 + 40")
    XK1 = s.param("frame_cheek_x1", TU + 40 + 32, "cheek outer face, 12 + 40 + 32")
    HK = s.param("frame_cheek_h", 84, "cheek height")
    TK = s.param("frame_cheek_t", 9, "cheek thickness (at Y = ±19 … ±28)")
    RK = s.param("frame_cheek_r12", 12, "fillet from the cheek's outer face to the base end")
    XB = s.param("frame_crank_x", XK1 - 16, "crankshaft bore position, 16 from the cheek's outer face")
    DCK = s.param("frame_crank_bore", 19, "crankshaft bearing bore (1-06 bearings)")
    SW = s.param("frame_clamp_slot", 10, "clamp slot width")
    XS = s.param("frame_clamp_x", XK1 - 4, "clamp screw, 4 from the cheek's outer face")
    DS = s.param("frame_clamp_hole", 4, "clamp screw clearance hole above the slot")
    TD = s.param("frame_clamp_tap_depth", 14, "M4 below the slot, 14 deep")
    PX0 = s.param("frame_pit_x0", 19, "crank pit start (section A-A)")
    PL = s.param("frame_pit_length", 71.5, "crank pit length (section A-A)")
    PW = s.param("frame_pit_width", 18, "crank pit width (9 + 9)")
    PZ = s.param("frame_pit_floor", 24, "crank pit floor height (section A-A)")
    OD12 = s.param("frame_oil_d12", 12, "Ø12 x 9.5 deep in the upright's outer face at Z = 30")
    OX = s.param("frame_oil_x", 9.5, "Ø8 cross hole: 9.5 from the outer face, at Z = 30")
    OZ = 30
    yk = W / 2 - TK                              # 19: cheek inner face

    # 1 base, upright and bearing cheeks: the side profile on the XZ plane, extruded across Y
    s.sketch("Frame profile", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop((0, 0), [("line", (L, 0)), ("line", (L, HB)),
                    ("arc", (XK1 + RK, HB + RK), (XK1, HB + RK), False),
                    ("line", (XK1, HK)), ("line", (XK0 + RU, HK)),
                    ("arc", (XK0 + RU, HK - RU), (XK0, HK - RU), True),
                    ("line", (XK0, HB + RU)), ("arc", (XK0 - RU, HB + RU), (XK0 - RU, HB), False),
                    ("line", (TU + RU, HB)), ("arc", (TU + RU, HB + RU), (TU, HB + RU), False),
                    ("line", (TU, HU)), ("line", (0, HU)), ("line", (0, 0))])
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Frame", body_name=s.body)
    s.cmd("solid.fillet", edges=[[TU / 2, W / 2, HU], [TU / 2, -W / 2, HU]], radius=RU, name="Upright corners")

    # 2 the gap between the two 9 mm bearing cheeks
    s.sketch("Cheek gap", (0, 0, HB), (1, 0, 0), (0, 1, 0))
    s.polyline([(TU + 2 * RU, -yk), (L + 2, -yk), (L + 2, yk), (TU + 2 * RU, yk)])
    s.finish()
    s.cmd("solid.extrude", distance=HK - HB + 2, operation="cut", targets=[s.body], name="Cheek gap")

    # 3 cylinder upright: spigot bore and the 4 bolt holes (the 1-02 pattern)
    s.holes("Cylinder bore", (0, 0, 0), (1, 0, 0), [(0, 0, ZC)], DCB, TU + 1)
    s.holes("Cylinder bolt holes", (0, 0, 0), (1, 0, 0), [(0, y, ZC + z) for y, z in ring_pts(4, PCD / 2, 45)],
            4.5, TU + 1)

    # 4 crankshaft bearing bores, clamp slots and clamp screws
    s.holes("Crankshaft bores", (0, W / 2, 0), (0, -1, 0), [(XB, W / 2, ZC)], DCK)
    s.sketch("Clamp slot", (0, W / 2, 0), (1, 0, 0), (0, 0, 1))
    s.polyline([(XB, ZC - SW / 2), (L + 2, ZC - SW / 2), (L + 2, ZC + SW / 2), (XB, ZC + SW / 2)])
    s.finish()
    s.cmd("solid.extrude", through_all=True, operation="cut", targets=[s.body], name="Clamp slots")
    clamp = [(XS, y, 0) for y in (W / 2 - TK / 2, -(W / 2 - TK / 2))]
    s.holes("Clamp screw holes", (0, 0, HK), (0, 0, -1), [(x, y, HK) for x, y, _ in clamp], DS,
            HK - ZC - SW / 2 + 0.5)
    s.holes("Clamp screw M4 tapped", (0, 0, ZC - SW / 2), (0, 0, -1), [(x, y, ZC - SW / 2) for x, y, _ in clamp],
            3.3, TD)

    # 5 crank pit between the cheeks
    s.sketch("Crank pit", (0, 0, HB), (1, 0, 0), (0, 1, 0))
    s.polyline([(PX0, -PW / 2), (PX0 + PL, -PW / 2), (PX0 + PL, PW / 2), (PX0, PW / 2)])
    s.finish()
    s.cmd("solid.extrude", distance=HB - PZ, direction="negative", operation="cut", targets=[s.body], name="Crank pit")

    # 6 mounting holes in the underside: 4 x M6 x 25 deep, 4 x M4 x 10 deep
    m6 = [(TU, -16), (TU, 16), (TU + 72, -16), (TU + 72, 16)]
    m4 = [(34.5, 24), (34.5 + 54, 24), (34.5, -24), (34.5 + 35, -24)]
    s.holes("Mounting M6 tapped", (0, 0, 0), (0, 0, 1), [(x, y, 0) for x, y in m6], 5.0, 25)
    s.holes("Mounting M4 tapped", (0, 0, 0), (0, 0, 1), [(x, y, 0) for x, y in m4], 3.3, 10)

    # 7 oil passages: Ø12 x 9.5 deep in the outer face, crossed by a Ø8 hole through the frame
    s.holes("Oil well", (0, 0, 0), (1, 0, 0), [(0, 0, OZ)], OD12, OX)
    s.holes("Oil cross hole", (0, W / 2, 0), (0, -1, 0), [(OX, W / 2, OZ)], 8)

    # hand volume
    cyl = lambda d, h: math.pi / 4 * d * d * h
    v = (L * HB + TU * (HU - HB) + (1 - math.pi / 4) * RU * RU) * W
    v -= 2 * (1 - math.pi / 4) * RU * RU * TU

    def cheek(x, z):
        if z < HB or x < XK0 - RU or x > L or z > HK:
            return False
        if x < XK0 and math.dist((x, z), (XK0 - RU, HB + RU)) < RU:
            return False                                     # outside the root fillet
        if x < XK0 and z >= HB + RU:
            return False
        if x < XK0 + RU and z > HK - RU and math.dist((x, z), (XK0 + RU, HK - RU)) > RU:
            return False                                     # rounded top corner
        if x > XK1 and (z > HB + RK or math.dist((x, z), (XK1 + RK, HB + RK)) < RK):
            return False                                     # R12 run-out
        if math.dist((x, z), (XB, ZC)) < DCK / 2:
            return False                                     # bearing bore
        if x > XB and abs(z - ZC) < SW / 2:
            return False                                     # clamp slot
        return True
    v += 2 * TK * grid_area(cheek, XK0 - RU, L, HB, HK)
    v -= cyl(DCB, TU) + 4 * cyl(4.5, TU)
    v -= 2 * (cyl(DS, HK - ZC - SW / 2) + cyl(3.3, TD))
    v -= PL * PW * (HB - PZ)
    v -= 4 * cyl(5.0, 25) + 4 * cyl(3.3, 10)
    # Ø12 well and Ø8 cross hole, minus their common part (inside the well, x < 9.5): there the
    # Ø12 well spans 2·sqrt(36 − dz²) across Y
    v -= cyl(OD12, OX) + cyl(8, W)
    h = 0.01
    v += sum(2 * math.sqrt(max(0.0, 36 - dz * dz)) * h * h
             for dx in [-4 + (i + 0.5) * h for i in range(int(4 / h))]
             for dz in [-4 + (j + 0.5) * h for j in range(int(8 / h))] if dx * dx + dz * dz < 16)
    return v


# ----------------------------------------------------------------------------- 1-02
@part("1-02", "Motor cylinder", "Cast Iron")
def motor_cylinder(s):
    """Sheet 03, 1-02 (scale 1:2). Axis = Z; Z = 0 on the 5 mm end flange, Z = 71 on the 9 mm
    flange (the one with the radial M4 oiler hole, which lies on +X)."""
    L = s.param("cyl_length", 71, "overall length (1-02)")
    D = s.param("cyl_fin_d", 56, "fin and flange diameter")
    DR = s.param("cyl_root_d", 36, "fin root diameter")
    DB = s.param("cyl_bore_d", 32, "bore, reamed (32RM)")
    F1 = s.param("cyl_flange1", 5, "flange width at Z = 0")
    F2 = s.param("cyl_flange2", 9, "flange width at Z = L (oiler end)")
    N, P, T = 12, s.param("cyl_fin_pitch", 4.5, "fin pitch (12x4.5=54)"), s.param("cyl_fin_t", 1.5, "fin thickness")
    PCD = s.param("cyl_pcd", 44, "M4 tapped holes, 4 per end, 45 deg off the oiler hole")
    HD = s.param("cyl_hole_depth", 10, "M4 x 10 deep")
    OZ = s.param("cyl_oiler_z", L - 4.5, "radial M4 oiler hole, 4.5 from the oiler end")
    G = P - T                                  # gap 3
    assert abs(F1 + N * P + G + F2 - L) < 1e-9, "fin pack does not fit the length"

    # base feature: the half-section revolved about Z (sketch x = radius along +X, y = Z)
    r, R, RR = DB / 2, D / 2, DR / 2
    pts = [(r, 0), (R, 0), (R, F1), (RR, F1)]
    for i in range(N):
        z = F1 + i * P + G
        pts += [(RR, z), (R, z), (R, z + T), (RR, z + T)]
    z = F1 + N * P + G
    pts += [(RR, z), (R, z), (R, L), (r, L)]
    s.sketch("Half section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.polyline(pts)
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Cylinder", body_name=s.body)

    # 4 x M4 x 10 deep on PCD 44 at each end, at 45 deg to the oiler hole
    # (tapped holes are modelled at the tap drill, Ø3.3 for M4)
    for zf, dz, end in ((0, 1, "Z0"), (L, -1, "oiler end")):
        s.holes(f"M4 tapped, {end}", (0, 0, zf), (0, 0, dz), [(x, y, zf) for x, y in ring_pts(4, PCD / 2, 45)],
                3.3, HD)
    # oiler hole: M4 radially through the wall into the bore, on +X
    s.holes("Oiler hole M4 tapped", (R, 0, 0), (-1, 0, 0), [(R, 0, OZ)], 3.3, (R - r) + 1)

    # hand volume: flanges + root tube + fins − tapped holes (tap drill 3.3). The PCD holes lie
    # outside the fin root, so a 10 deep hole only removes metal where it crosses a flange or fin.
    a = lambda d1, d2: math.pi / 4 * (d1 * d1 - d2 * d2)
    v = a(D, DB) * (F1 + F2) + a(DR, DB) * (N * P + G) + a(D, DR) * N * T
    metal = [(0, F1), (L - F2, L)] + [(F1 + i * P + G, F1 + (i + 1) * P) for i in range(N)]
    in_metal = lambda z0, z1: sum(max(0, min(z1, b) - max(z0, a_)) for a_, b in metal)
    tap = math.pi / 4 * 3.3 ** 2
    # radial hole: a Ø3.3 cylinder between the bore and the outside diameter
    radial = sum(2 * math.sqrt(max(0, 1.65 ** 2 - y * y)) * (math.sqrt(R * R - y * y) - math.sqrt(r * r - y * y))
                 for y in [(-1.65 + (i + 0.5) * 3.3 / 2000) for i in range(2000)]) * 3.3 / 2000
    return v - 4 * tap * (in_metal(0, HD) + in_metal(L - HD, L)) - radial


def annulus(d1, d2):
    return math.pi / 4 * (d1 * d1 - d2 * d2)


def strip(R, x0, x1):
    """Area of the part of a circle of radius R between x = x0 and x = x1."""
    F = lambda x: x * math.sqrt(R * R - x * x) + R * R * math.asin(x / R)
    return F(x1) - F(x0)


# ----------------------------------------------------------------------------- 1-03
@part("1-03", "Motor cylinder gasket ring", "Copper")
def gasket_ring(s):
    """Sheet 03, 1-03. Axis = Z; Z = 0 on the Ø36 face, the Ø32 spigot (into the 1-02 bore) on +Z."""
    D = s.param("gasket_od", 36, "outside diameter")
    DI = s.param("gasket_id", 30, "inside diameter")
    DS = s.param("gasket_spigot_d", 32, "spigot diameter, fits the Ø32 bore of 1-02")
    T = s.param("gasket_t", 3, "overall thickness")
    TS = s.param("gasket_spigot_t", 1, "spigot length")
    s.sketch("Half section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.polyline([(DI / 2, 0), (D / 2, 0), (D / 2, T - TS), (DS / 2, T - TS), (DS / 2, T), (DI / 2, T)])
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Ring", body_name=s.body)
    return annulus(D, DI) * (T - TS) + annulus(DS, DI) * TS


# ----------------------------------------------------------------------------- 1-04
@part("1-04", "Motor inner cylinder head", "Cast Iron")
def inner_cylinder_head(s):
    """Sheet 03, 1-04 (scale 1:2 and detail). Disc on the XY plane, Z = 0 on the face with the
    valve channel (it lies along Y), Z = 3.5 on the countersunk face. The four Ø4.5 holes are on
    the 1-02 hole pattern (PCD 44, at 45 deg to the channel)."""
    D = s.param("head_d", 56, "diameter")
    T = s.param("head_t", 3.5, "thickness")
    PCD = s.param("head_pcd", 44, "4 x Ø4.5 on PCD 44, taken over from 1-02")
    DH = s.param("head_hole_d", 4.5, "clearance holes for M4")
    W = s.param("head_channel_w", 20, "valve channel width (10 + 10)")
    CD = s.param("head_channel_depth", 0.5, "valve channel depth")
    GW = s.param("head_groove_w", 0.5, "relief groove width at each channel edge")
    GD = s.param("head_groove_depth", 1, "relief groove depth")
    DP = s.param("head_port_d", 10, "central port")
    DCS = s.param("head_csink_d", 15, "countersink on the face away from the channel, 90 deg")
    R = D / 2

    s.sketch("Disc", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[0, 0], diameter=D)
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Disc", body_name=s.body)
    # valve channel across the whole face, then the relief grooves along its edges
    s.sketch("Channel", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-W / 2, -R - 2], p1=[W / 2, R + 2])
    s.finish()
    s.cmd("solid.extrude", distance=CD, operation="cut", targets=[s.body], name="Valve channel")
    s.sketch("Relief grooves", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    for x0 in (-W / 2 - GW, W / 2):
        s.cmd("sketch.rectangle.two_point", p0=[x0, -R - 2], p1=[x0 + GW, R + 2])
    s.finish()
    s.cmd("solid.extrude", distance=GD, operation="cut", targets=[s.body], name="Relief grooves")
    s.holes("Bolt holes", (0, 0, T), (0, 0, -1), [(x, y, T) for x, y in ring_pts(4, PCD / 2, 45)], DH)
    # central port with its 90 deg countersink: a revolved cut
    hcs = (DCS - DP) / 2                       # 90 deg countersink depth
    s.sketch("Port section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.polyline([(0, -1), (DP / 2, -1), (DP / 2, T - hcs), (DCS / 2, T), (DCS / 2 + 1, T + 1), (0, T + 1)])
    s.finish()
    s.cmd("solid.revolve", axis="Z", operation="cut", targets=[s.body], name="Countersunk port")
    v = math.pi / 4 * D * D * T
    v -= strip(R, -W / 2, W / 2) * CD + 2 * strip(R, W / 2, W / 2 + GW) * GD
    v -= 4 * math.pi / 4 * DH * DH * T
    v -= math.pi / 12 * hcs * (DCS ** 2 + DCS * DP + DP ** 2) + math.pi / 4 * DP * DP * (T - CD - hcs)
    return v


# ----------------------------------------------------------------------------- 1-09
@part("1-09", "Motor cylinder oiler glass", "Polycarbonate")
def oiler_glass(s):
    """Sheet 03, 1-09: plastic tubing Ø15 x Ø13, 19 long. Axis = Z, from Z = 0."""
    D = s.param("glass_od", 15, "outside diameter")
    DI = s.param("glass_id", 13, "inside diameter")
    L = s.param("glass_length", 19, "length")
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[0, 0], diameter=D)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=DI)
    s.finish()
    s.cmd("solid.extrude", distance=L, profiles=[{"point": [(D + DI) / 4, 0]}], name="Tube", body_name=s.body)
    return annulus(D, DI) * L


# ----------------------------------------------------------------------------- driver
def write(number):
    name, material, fn = PARTS[number]
    s = Script(f"{number} {name}")
    estimate = fn(s)
    s.cmd("material.assign", bodies=[s.body], material=material)
    path = os.path.join(OUT, f"{number}.json")
    with open(path, "w") as f:
        json.dump({"commands": s.cmds}, f, indent=1)
        f.write("\n")
    return path, estimate


def stl_volume(path):
    """Volume enclosed by a binary or ASCII STL (divergence theorem): an independent check of the
    kernel's measured volume (slightly low: the chords cut inside convex curved faces)."""
    with open(path, "rb") as f:
        data = f.read()
    tris = []
    if data[:5] == b"solid" and b"facet" in data[:400]:
        vs = [tuple(map(float, m)) for m in re.findall(rb"vertex\s+(\S+)\s+(\S+)\s+(\S+)", data)]
        tris = [vs[i:i + 3] for i in range(0, len(vs) - 2, 3)]
    else:
        n = struct.unpack_from("<I", data, 80)[0]
        for i in range(n):
            f = struct.unpack_from("<12f", data, 84 + 50 * i)
            tris.append((f[3:6], f[6:9], f[9:12]))
    v6 = 0.0
    half_edges = set()
    for a, b, c in tris:
        v6 += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
               + a[2] * (b[0] * c[1] - b[1] * c[0]))
        q = [tuple(round(x, 4) for x in p) for p in (a, b, c)]
        for i in range(3):
            e = (q[i], q[(i + 1) % 3])
            half_edges.discard(e[::-1]) if e[::-1] in half_edges else half_edges.add(e)
    return v6 / 6, len(half_edges)


def build(number, path, estimate):
    base = os.path.join(OUT, number)
    stl = os.path.join(OUT, f".{number}.check.stl")
    subprocess.run([ARGS.cli, "run", path, "--save", base + ".solvecraft", "--out", base + ".step", "--out", stl,
                    "--quiet"], check=True)
    mesh_vol, open_edges = stl_volume(stl)
    os.remove(stl)
    res = json.loads(subprocess.run([ARGS.cli, "eval", base + ".solvecraft"], check=True,
                                    capture_output=True, text=True).stdout)
    errors = [t for t in res["timeline"] if t.get("error")]
    # a 'coincident-face separation' retry can leave the result displaced: treat it as an error
    errors += [t for t in res["timeline"] if "separation" in (t.get("warning") or "")]
    notes = [t for t in res["timeline"] if t.get("warning") and t not in errors
             and not t["warning"].startswith("Boolean retry")]
    bodies = res["bodies"]
    vol = bodies[0]["volume_mm3"] if len(bodies) == 1 else float("nan")
    bb = bodies[0]["bbox"] if bodies else None
    dv, dm = (vol - estimate) / estimate, (mesh_vol - estimate) / estimate
    # the kernel's measure must agree with the hand volume; the exported mesh is a second check
    # when it is closed (an open STL gives no volume)
    ok = len(bodies) == 1 and not errors and abs(dv) < 0.001 and (open_edges or abs(dm) < 0.005)
    mesh = f"{mesh_vol:.1f} ({dm * 100:+.2f} %)" if not open_edges else f"not closed ({open_edges} open edges)"
    print(f"{number}: {'OK  ' if ok else 'FAIL'} hand volume {estimate:.1f} mm³, STL mesh {mesh}, "
          f"SolidCraft {vol:.1f} ({dv * 100:+.2f} %), mass {bodies[0]['mass_g'] if bodies else 0:.1f} g, "
          f"bbox {bb['min'] if bb else '-'} .. {bb['max'] if bb else '-'}, faces {bodies[0]['face_types'] if bodies else '-'}")
    for t in errors + notes:
        print(f"   {t['name']}: {t.get('error') or t.get('warning')}")
    subprocess.run([ARGS.cli, "snapshot", base + ".solvecraft", "--out", base + ".png", "--view", "iso"],
                   check=True, capture_output=True)
    return ok


def main():
    os.makedirs(OUT, exist_ok=True)
    numbers = ARGS.parts or sorted(PARTS)
    ok = True
    for n in numbers:
        if n not in PARTS:
            raise SystemExit(f"unknown part {n}; known: {', '.join(sorted(PARTS))}")
        path, est = write(n)
        if ARGS.build:
            ok &= build(n, path, est)
    if not ok:
        raise SystemExit(1)


main()
