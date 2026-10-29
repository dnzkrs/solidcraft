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

    def holes(self, name, origin, into, centres, diameter, depth=None, target=None):
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
        self.cmd("solid.extrude", **cut, operation="cut", targets=[target or self.body], name=name)

    def turned(self, name, pts, body=None, operation="new"):
        """A turned shape: the closed polygon `pts` of (radius, z) points in the XZ half plane,
        revolved about the Z axis. Returns its volume (Pappus)."""
        self.sketch(f"{name} section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
        self.polyline(pts)
        self.finish()
        extra = {"body_name": body or self.body} if operation == "new" else {"targets": [body or self.body]}
        self.cmd("solid.revolve", axis="Z", operation=operation, name=name, **extra)
        return revolved_volume(pts)


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


def revolved_volume(pts):
    """Volume of the closed polygon of (r, z) points revolved about the z axis: 2π ∬ r dA."""
    m = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        m += (x0 + x1) * (x0 * y1 - x1 * y0)
    return abs(2 * math.pi * m / 6)


def loop_area(start, segs):
    """Area enclosed by a Script.loop() boundary (lines and circular arcs), exactly."""
    a, p = 0.0, start
    for seg in segs:
        if seg[0] == "line":
            e = seg[1]
            a += p[0] * e[1] - e[0] * p[1]
        else:
            _, c, e, ccw = seg
            r = math.dist(c, p)
            t0, t1 = math.atan2(p[1] - c[1], p[0] - c[0]), math.atan2(e[1] - c[1], e[0] - c[0])
            sweep = (t1 - t0) % (2 * math.pi) if ccw else -((t0 - t1) % (2 * math.pi))
            a += r * r * sweep + r * (c[0] * (math.sin(t0 + sweep) - math.sin(t0))
                                      - c[1] * (math.cos(t0 + sweep) - math.cos(t0)))
        p = e
    return abs(a) / 2


def radial_hole(d, r_out, r_in=0.0, walls=1, n=4000):
    """Volume a Ø d hole along a radius removes from a tube (r_out, r_in) whose axis it crosses
    at right angles: through one wall, or both (walls=2; with r_in = 0, through the solid)."""
    h, v = d / n, 0.0
    for i in range(n):
        y = -d / 2 + (i + 0.5) * h
        width = 2 * math.sqrt(max(0.0, d * d / 4 - y * y))
        length = math.sqrt(max(0.0, r_out * r_out - y * y)) - math.sqrt(max(0.0, r_in * r_in - y * y))
        v += width * length * h
    return v * walls if r_in > 0 else v * 2 if walls == 2 else v


def hexagon(af, rot_deg=0):
    """Corners of a regular hexagon with across-flats `af`, centred on the origin."""
    r = af / math.sqrt(3)
    return [(r * math.cos(math.radians(rot_deg + 60 * i)), r * math.sin(math.radians(rot_deg + 60 * i)))
            for i in range(6)]


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


# ----------------------------------------------------------------------------- 1-14
@part("1-14", "Motor crank shaft", {"web L": "Steel", "web R": "Steel", "crank pin": "Stainless Steel",
                                     "shaft L": "Stainless Steel", "shaft R": "Stainless Steel"})
def crank_shaft(s):
    """Sheet 03, 1-14 (scale 1:2): a built-up crankshaft, five bodies: two M/S webs, an S/S
    crankpin and two S/S shafts, pressed together (PF). Axis = Z, symmetric about Z = 0 (the
    middle of the crankpin); the crankpin is on +X. The left shaft (Z < 0) has the Ø4 cross hole."""
    TW = s.param("crank_web_t", 12, "web thickness")
    G = s.param("crank_gap", 12, "gap between the webs")
    THROW = s.param("crank_throw", 22, "crank radius (stroke 44), measured on the drawing's vector lines")
    WW = s.param("crank_web_w", 14, "web width: NOT DIMENSIONED, estimated from the iso view (12-15)")
    WT = s.param("crank_web_top", 34.5, "web end beyond the main axis on the crankpin side (measured)")
    WB = s.param("crank_web_bottom", 30, "web end beyond the main axis on the other side (measured)")
    DP = s.param("crank_pin_d", 8, "crankpin, 8PF")
    DF = s.param("crank_fit_d", 10, "shaft end pressed into the web, 10PF")
    DJ = s.param("crank_journal_d", 9.5, "bearing journal (1-06 bore)")
    LJ = s.param("crank_journal_l", 10.5, "journal length")
    DS = s.param("crank_shaft_d", 8, "shaft")
    LS = s.param("crank_shaft_l", 64.5, "shaft length beyond the web")
    TAP = s.param("crank_end_tap", 10, "M5 x 10 deep in each shaft end (tap drill Ø4.2)")
    XH = s.param("crank_cross_hole", 9.5, "Ø4 cross hole in the left shaft, 9.5 from the journal")
    n = s.body.split()[0]
    z1 = G / 2 + TW                              # web outer face
    v = 0.0
    for side, sg in (("L", -1), ("R", 1)):
        z0 = G / 2 if sg > 0 else -z1           # web face with the lower Z
        s.sketch(f"Web {side}", (0, 0, z0), (1, 0, 0), (0, 1, 0))
        s.polyline([(-WB, -WW / 2), (WT, -WW / 2), (WT, WW / 2), (-WB, WW / 2)])
        s.cmd("sketch.circle.center", center=[0, 0], diameter=DF)
        s.cmd("sketch.circle.center", center=[THROW, 0], diameter=DP)
        s.finish()
        s.cmd("solid.extrude", distance=TW, profiles=[{"point": [-WB / 2 - 5, 0]}], operation="new",
              name=f"Web {side}", body_name=f"{n} web {side}")
        v += ((WT + WB) * WW - math.pi / 4 * (DF * DF + DP * DP)) * TW
        # shaft: fit Ø10 through the web, journal, shaft
        prof = [(0, G / 2), (DF / 2, G / 2), (DF / 2, z1), (DJ / 2, z1), (DJ / 2, z1 + LJ), (DS / 2, z1 + LJ),
                (DS / 2, z1 + LS), (0, z1 + LS)]
        if sg < 0:
            prof = [(r, -z) for r, z in reversed(prof)]
        v += s.turned(f"Shaft {side}", prof, body=f"{n} shaft {side}")
        zend = sg * (z1 + LS)
        s.holes(f"M5 tapped end {side}", (0, 0, zend), (0, 0, -sg), [(0, 0, zend)], 4.2, TAP,
                target=f"{n} shaft {side}")
        v -= math.pi / 4 * 4.2 ** 2 * TAP
    s.holes("Cross hole", (-DS / 2, 0, 0), (1, 0, 0), [(-DS / 2, 0, -(z1 + LJ + XH))], 4,
            target=f"{n} shaft L")
    v -= radial_hole(4, DS / 2, walls=2)
    s.sketch("Crank pin", (0, 0, -z1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[THROW, 0], diameter=DP)
    s.finish()
    s.cmd("solid.extrude", distance=2 * z1, operation="new", name="Crank pin", body_name=f"{n} crank pin")
    v += math.pi / 4 * DP * DP * 2 * z1
    return v


# ----------------------------------------------------------------------------- 1-17
@part("1-17", "Motor crank shaft cam plate", "Steel")
def cam_plate(s):
    """Sheet 03, 1-17 (scale 1:1.5, section D-D): plate on the XY plane, Z = 0..5; the bore on
    the origin, the R25 lobe on +Y. Counterbore Ø19 x 2.5 on the Z = 5 face; the bore is M16
    (modelled at its tap drill Ø14), screwed onto the 1-20 hub."""
    T = s.param("cam_t", 5, "thickness")
    R1 = s.param("cam_r_lobe", 25, "lobe radius about the bore")
    R2 = s.param("cam_r_base", 16, "base radius about the bore")
    RF = s.param("cam_r_corner", 4, "corner radius between flank and lobe")
    A = math.radians(s.param("cam_flank_angle", 37.5, "flank angle to the centre line", unit="deg"))
    DCB = s.param("cam_cbore_d", 19, "counterbore")
    HCB = s.param("cam_cbore_depth", 2.5, "counterbore depth")
    DT = s.param("cam_tap_d", 14, "M16 tapped (tap drill Ø14)")
    nL, wL = (-math.cos(A), -math.sin(A)), (-math.sin(A), math.cos(A))
    sd = math.sqrt((R1 - RF) ** 2 - (R2 - RF) ** 2)
    cL = ((R2 - RF) * nL[0] + sd * wL[0], (R2 - RF) * nL[1] + sd * wL[1])
    t1L = (R2 * nL[0] + sd * wL[0], R2 * nL[1] + sd * wL[1])
    t2L = (cL[0] * R1 / (R1 - RF), cL[1] * R1 / (R1 - RF))
    p16L = (R2 * nL[0], R2 * nL[1])
    m = lambda p: (-p[0], p[1])
    start = p16L
    segs = [("arc", (0, 0), m(p16L), True), ("line", m(t1L)), ("arc", m(cL), m(t2L), True),
            ("arc", (0, 0), t2L, True), ("arc", cL, t1L, True), ("line", p16L)]
    s.sketch("Outline", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=DT)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [0, R1 - 3]}], name="Plate", body_name=s.body)
    s.holes("Counterbore", (0, 0, T), (0, 0, -1), [(0, 0, T)], DCB, HCB)
    return loop_area(start, segs) * T - math.pi / 4 * (DT * DT * T + (DCB * DCB - DT * DT) * HCB)


# ----------------------------------------------------------------------------- 1-18
@part("1-18", "Motor crank shaft cam follower lock nut", "Brass")
def lock_nut(s):
    """Sheet 03, 1-18 (scale 1:1.5): 20 hex x 5 with a Ø19 x 3 collar, M16 (tap drill Ø14).
    Axis = Z; the hex on Z = 0..5, the collar on Z = 5..8."""
    AF = s.param("nut_af", 20, "hex across flats")
    TH = s.param("nut_hex_t", 5, "hex thickness")
    DC = s.param("nut_collar_d", 19, "collar diameter")
    TC = s.param("nut_collar_t", 3, "collar length")
    DT = s.param("nut_tap_d", 14, "M16 (tap drill Ø14)")
    s.sketch("Hex", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=TH, name="Hex", body_name=s.body)
    v = math.sqrt(3) / 2 * AF * AF * TH
    v += s.turned("Collar", [(DT / 2, TH - 1), (DC / 2, TH - 1), (DC / 2, TH + TC), (DT / 2, TH + TC)],
                  operation="join") - math.pi / 4 * (DC * DC - DT * DT) * 1
    s.holes("M16 tapped", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], DT)
    return v - math.pi / 4 * DT * DT * TH


# ----------------------------------------------------------------------------- 1-19
@part("1-19", "Motor crank shaft cam follower spacer", "Brass")
def cam_spacer(s):
    """Sheet 03, 1-19: ring Ø22 x Ø16 x 3. Axis = Z from Z = 0."""
    D = s.param("spacer_od", 22, "outside diameter")
    DI = s.param("spacer_id", 16, "inside diameter")
    T = s.param("spacer_t", 3, "thickness")
    return s.turned("Ring", [(DI / 2, 0), (D / 2, 0), (D / 2, T), (DI / 2, T)])


# ----------------------------------------------------------------------------- 1-20
@part("1-20", "Motor flywheel hub", "Brass")
def flywheel_hub(s):
    """Sheet 03, 1-20 (scale 1:2). Axis = Z; Z = 0 at the threaded end (M16, modelled at Ø16),
    the Ø22 collar on Z = 19.5..34.5. Bore Ø8 for the crankshaft. Radial grub screw holes on +X:
    M4 9.5 from the threaded end, M6 8 from the collar end (tap drills Ø3.3, Ø5)."""
    DT = s.param("hub_thread_d", 16, "M16 thread, modelled at its major diameter")
    LT = s.param("hub_thread_l", 19.5, "threaded part (thread 14 long)")
    DC = s.param("hub_collar_d", 22, "collar")
    LC = s.param("hub_collar_l", 15, "collar length")
    DB = s.param("hub_bore", 8, "bore on the Ø8 crankshaft")
    Z4 = s.param("hub_m4_z", LT - 10, "M4 grub screw, 10 from the collar")
    Z6 = s.param("hub_m6_z", LT + LC - 8, "M6 grub screw, 8 from the collar end")
    v = s.turned("Hub", [(DB / 2, 0), (DT / 2, 0), (DT / 2, LT), (DC / 2, LT), (DC / 2, LT + LC), (DB / 2, LT + LC)])
    s.holes("M4 grub tapped", (DT / 2, 0, 0), (-1, 0, 0), [(DT / 2, 0, Z4)], 3.3, (DT - DB) / 2 + 1)
    s.holes("M6 grub tapped", (DC / 2, 0, 0), (-1, 0, 0), [(DC / 2, 0, Z6)], 5.0, (DC - DB) / 2 + 1)
    return v - radial_hole(3.3, DT / 2, DB / 2) - radial_hole(5.0, DC / 2, DB / 2)


# ----------------------------------------------------------------------------- 1-21
@part("1-21", "Motor flywheel", "Brass")
def flywheel(s):
    """Sheet 03, 1-21 (scale 1:2.5, section E-E): Ø110 x 19 rim, 6 thick web in its middle plane
    with 5 equally spaced spokes 10 wide, Ø16 bore. Axis = Z, the rim on Z = 0..19; a spoke on +Y."""
    D = s.param("fly_d", 110, "outside diameter")
    DR = s.param("fly_rim_id", 90, "rim inside diameter")
    W = s.param("fly_w", 19, "rim width")
    TW = s.param("fly_web_t", 6, "web thickness (19 - 2 x 6.5), in the middle")
    DO = s.param("fly_window_d", 86, "spoke windows: outer diameter")
    SW = s.param("fly_spoke_w", 10, "spoke width")
    RW = s.param("fly_window_r", 6.5, "spoke window inner radius (centres on PCD 39)")
    DB = s.param("fly_bore", 16, "bore")
    N = 5
    z0 = (W - TW) / 2
    v = s.turned("Wheel", [(DB / 2, z0), (DR / 2, z0), (DR / 2, 0), (D / 2, 0), (D / 2, W), (DR / 2, W),
                           (DR / 2, z0 + TW), (DB / 2, z0 + TW)])
    s.sketch("Spoke windows", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    half = math.pi / N
    dc = (SW / 2 + RW) / math.sin(half)          # 19.56: PCD 39
    area = 0.0
    for k in range(N):
        b = math.pi / 2 + half + k * 2 * half    # window bisector; spokes at 90 deg + k 72 deg
        s1, s2 = (math.cos(b - half), math.sin(b - half)), (math.cos(b + half), math.sin(b + half))
        n1, n2 = (-s1[1], s1[0]), (s2[1], -s2[0])
        c = (dc * math.cos(b), dc * math.sin(b))
        t1 = (c[0] - RW * n1[0], c[1] - RW * n1[1])
        t2 = (c[0] - RW * n2[0], c[1] - RW * n2[1])
        L = math.sqrt((DO / 2) ** 2 - (SW / 2) ** 2)
        o1 = (SW / 2 * n1[0] + L * s1[0], SW / 2 * n1[1] + L * s1[1])
        o2 = (SW / 2 * n2[0] + L * s2[0], SW / 2 * n2[1] + L * s2[1])
        segs = [("line", o1), ("arc", (0, 0), o2, True), ("line", t2), ("arc", c, t1, True)]
        s.loop(t1, segs)
        area += loop_area(t1, segs)
    s.finish()
    s.cmd("solid.extrude", through_all=True, operation="cut", targets=[s.body], name="Spoke windows")
    return v - area * TW


# ----------------------------------------------------------------------------- 1-22
@part("1-22", "Motor piston", "Cast Iron")
def piston(s):
    """Sheet 03, 1-22 (scale 1:2): Ø32 x 30 cup, Ø28 bore 28 deep, 2 thick crown with a Ø5 hole
    for the piston rod. Axis = Z; the crown on Z = 0..2."""
    D = s.param("piston_d", 32, "diameter (fits the Ø32 bore of 1-02)")
    L = s.param("piston_l", 30, "length")
    DI = s.param("piston_id", 28, "inside diameter")
    TC = s.param("piston_crown", 2, "crown thickness (30 - 28)")
    DH = s.param("piston_rod_hole", 5, "piston rod hole")
    return s.turned("Piston", [(DH / 2, 0), (D / 2, 0), (D / 2, L), (DI / 2, L), (DI / 2, TC), (DH / 2, TC)])


# ----------------------------------------------------------------------------- 1-26
@part("1-26", "Motor valve rocking shaft bearing", "Brass")
def rocking_bearing(s):
    """Sheet 03, 1-26: flanged bush, flange Ø10 x 1.5, body Ø8 x 12, bore Ø6. Axis = Z, the flange
    on Z = 0..1.5."""
    DF = s.param("rb_flange_d", 10, "flange")
    TF = s.param("rb_flange_t", 1.5, "flange thickness")
    D = s.param("rb_d", 8, "body")
    L = s.param("rb_l", 12, "body length")
    DI = s.param("rb_bore", 6, "bore (1-27 shaft)")
    return s.turned("Bush", [(DI / 2, 0), (DF / 2, 0), (DF / 2, TF), (D / 2, TF), (D / 2, TF + L), (DI / 2, TF + L)])


# ----------------------------------------------------------------------------- 1-27
@part("1-27", "Motor valve rocking shaft", "Stainless Steel")
def rocking_shaft(s):
    """Sheet 03, 1-27 (scale 1:2): Ø6 x 60 with M4 x 10 ends (modelled at Ø4) and an M4 tapped
    cross hole in the middle (tap drill Ø3.3, along X). Axis = Z from Z = 0."""
    D = s.param("rs_d", 6, "shaft")
    L = s.param("rs_l", 60, "Ø6 length (30 + 30)")
    DE = s.param("rs_end_d", 4, "M4 ends, at the major diameter")
    LE = s.param("rs_end_l", 10, "end length")
    v = s.turned("Shaft", [(0, 0), (DE / 2, 0), (DE / 2, LE), (D / 2, LE), (D / 2, LE + L), (DE / 2, LE + L),
                           (DE / 2, 2 * LE + L), (0, 2 * LE + L)])
    s.holes("M4 tapped cross hole", (D / 2, 0, 0), (-1, 0, 0), [(D / 2, 0, LE + L / 2)], 3.3)
    return v - radial_hole(3.3, D / 2, walls=2)


# ----------------------------------------------------------------------------- 1-28
@part("1-28", "Motor valve rod", "Steel")
def valve_rod(s):
    """Sheet 03, 1-28 (scale 1:2): Ø4 x 94 rod, M4 at both ends (16 and 7 long; threads not
    modelled). Axis = Z from Z = 0, the 16 long thread at Z = 0."""
    D = s.param("vr_d", 4, "rod, M4 ends")
    L = s.param("vr_l", 94, "length")
    return s.turned("Rod", [(0, 0), (D / 2, 0), (D / 2, L), (0, L)])


# ----------------------------------------------------------------------------- 1-31
@part("1-31", "Motor valve rocking arm", "Steel")
def rocking_arm(s):
    """Sheet 03, 1-31 (scale 1:2): 2.5 thick arm, centres 57 apart, R6 end with a Ø4 hole (on the
    origin) and R5 end with an M4 tapped hole (tap drill Ø3.3) on +X. On the XY plane, Z = 0..2.5."""
    T = s.param("arm_t", 2.5, "thickness")
    C = s.param("arm_centres", 57, "hole centres")
    R1 = s.param("arm_r1", 6, "end radius at the Ø4 hole")
    R2 = s.param("arm_r2", 5, "end radius at the M4 hole")
    sp = (R1 - R2) / C
    cp = math.sqrt(1 - sp * sp)
    p1l, p2l = (R1 * sp, -R1 * cp), (C + R2 * sp, -R2 * cp)
    p1u, p2u = (R1 * sp, R1 * cp), (C + R2 * sp, R2 * cp)
    segs = [("line", p2l), ("arc", (C, 0), p2u, True), ("line", p1u), ("arc", (0, 0), p1l, True)]
    s.sketch("Arm", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(p1l, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=4)
    s.cmd("sketch.circle.center", center=[C, 0], diameter=3.3)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [C / 2, 0]}], name="Arm", body_name=s.body)
    return (loop_area(p1l, segs) - math.pi / 4 * (16 + 3.3 ** 2)) * T


# ----------------------------------------------------------------------------- driver
def write(number):
    name, material, fn = PARTS[number]
    s = Script(f"{number} {name}")
    estimate = fn(s)
    # material: one name for a single-body part, or {body suffix: material} for an assembly of
    # bodies named "<number> <suffix>"
    materials = {s.body: material} if isinstance(material, str) else \
        {f"{number} {b}": m for b, m in material.items()}
    for body, m in materials.items():
        s.cmd("material.assign", bodies=[body], material=m)
    path = os.path.join(OUT, f"{number}.json")
    with open(path, "w") as f:
        json.dump({"commands": s.cmds}, f, indent=1)
        f.write("\n")
    return path, estimate, len(materials)


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


def build(number, path, estimate, n_bodies):
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
    vol = sum(b["volume_mm3"] for b in bodies)
    mass = sum(b["mass_g"] for b in bodies)
    lo = [min(b["bbox"]["min"][i] for b in bodies) for i in range(3)] if bodies else [0] * 3
    hi = [max(b["bbox"]["max"][i] for b in bodies) for i in range(3)] if bodies else [0] * 3
    dv, dm = (vol - estimate) / estimate, (mesh_vol - estimate) / estimate
    # the kernel's measure must agree with the hand volume; the exported mesh is a second check
    # when it is closed (an open STL gives no volume)
    ok = len(bodies) == n_bodies and not errors and abs(dv) < 0.001 and (open_edges or abs(dm) < 0.015)
    mesh = f"{mesh_vol:.1f} ({dm * 100:+.2f} %)" if not open_edges else f"not closed ({open_edges} open edges)"
    print(f"{number}: {'OK  ' if ok else 'FAIL'} {len(bodies)}/{n_bodies} bodies, hand volume {estimate:.1f} mm³, "
          f"STL mesh {mesh}, SolidCraft {vol:.1f} ({dv * 100:+.2f} %), mass {mass:.1f} g, "
          f"box {' x '.join(f'{hi[i] - lo[i]:.2f}' for i in range(3))} from ({', '.join(f'{v:.2f}' for v in lo)})")
    for t in errors + notes:
        print(f"   {t['name']}: {t.get('error') or t.get('warning')}")
    subprocess.run([ARGS.cli, "snapshot", base + ".solvecraft", "--out", base + ".png", "--view", "iso"],
                   check=True, capture_output=True)
    if ok:
        name, material, _ = PARTS[number]
        mats = material if isinstance(material, str) else ", ".join(sorted(set(material.values())))
        SUMMARY[number] = {"name": name, "material": mats, "bodies": len(bodies),
                           "volume_mm3": round(vol, 1), "mass_g": round(mass, 1)}
    return ok


SUMMARY_PATH = os.path.join(OUT, "summary.json")
SUMMARY = {}


def write_summary():
    """parts/summary.json and the parts table in README.md, from the parts built so far."""
    with open(SUMMARY_PATH, "w") as f:
        json.dump(dict(sorted(SUMMARY.items())), f, indent=1)
        f.write("\n")
    rows = ["| Part | Name | Material | Bodies | Volume mm³ | Mass g |", "|---|---|---|---:|---:|---:|"]
    rows += [f"| {n} | {r['name']} | {r['material']} | {r['bodies']} | {r['volume_mm3']:,.1f} | {r['mass_g']:,.1f} |"
             for n, r in sorted(SUMMARY.items())]
    readme = os.path.join(_here, "README.md")
    with open(readme) as f:
        text = f.read()
    a, b = text.index("<!-- parts -->") + len("<!-- parts -->"), text.index("<!-- /parts -->")
    with open(readme, "w") as f:
        f.write(text[:a] + "\n" + "\n".join(rows) + "\n" + text[b:])
    attribute(SUMMARY)


def attribute(parts):
    """Rows in the repository's ATTRIBUTION.md for each part's PNG and STEP file (`cargo xtask
    assets` requires one per asset file)."""
    path = os.path.join(_here, "..", "..", "ATTRIBUTION.md")
    with open(path) as f:
        lines = f.read().split("\n")
    have = {l.split("|")[1].strip() for l in lines if l.startswith("| examples/lanz-tractor/")}
    last = max((i for i, l in enumerate(lines) if l.startswith("| examples/")), default=len(lines) - 1)
    new = []
    for n, r in sorted(parts.items()):
        for ext, what in (("png", "SolidCraft snapshot"), ("step", "SolidCraft STEP export")):
            f = f"examples/lanz-tractor/parts/{n}.{ext}"
            if f not in have:
                new.append(f"| {f} | repository owner | {what} of an original SolidCraft model of Lanz mini tractor "
                           f"part {n} ({r['name'].lower()}), modelled in examples/lanz-tractor/gen_parts.py from "
                           f"the LANZ-A3 drawings by J.A.M. de Waal (2014) after C.P. Hendrikx (1996) | private use; "
                           f"dimensions from copyrighted drawings, see examples/lanz-tractor/README.md |")
    if new:
        lines[last + 1:last + 1] = new
        with open(path, "w") as f:
            f.write("\n".join(lines))


def main():
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(SUMMARY_PATH):
        with open(SUMMARY_PATH) as f:
            SUMMARY.update(json.load(f))
    numbers = ARGS.parts or sorted(PARTS)
    ok = True
    for n in numbers:
        if n not in PARTS:
            raise SystemExit(f"unknown part {n}; known: {', '.join(sorted(PARTS))}")
        path, est, n_bodies = write(n)
        if ARGS.build:
            ok &= build(n, path, est, n_bodies)
    if ARGS.build:
        write_summary()
    if not ok:
        raise SystemExit(1)


main()
