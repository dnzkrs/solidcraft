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


TOLERANCE = {}


def part(number, name, material, tol=0.001):
    """Registers a part builder: fn(Script) fills the script, returns the hand-estimated volume (mm³).
    `tol`: how far SolidCraft's measured volume may be from it (relative)."""
    def reg(fn):
        PARTS[number] = (name, material, fn)
        TOLERANCE[number] = tol
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
        local = self.plane(name, origin, into)
        for c in centres:
            self.cmd("sketch.circle.center", center=[round(v, 6) for v in local(c)], diameter=diameter)
        self.finish()
        cut = {"through_all": True} if depth is None else {"distance": depth}
        self.cmd("solid.extrude", **cut, operation="cut", targets=[target or self.body], name=name)

    def plane(self, name, origin, into):
        """Starts a sketch on the plane through `origin` normal to `into` (a positive extrude goes
        along `into`); returns the world-point → sketch-point mapping for it."""
        n = _unit(into)
        x = _unit(_cross(n, (0, 0, 1)) if abs(n[2]) < 0.9 else _cross((0, 1, 0), n))
        y = _cross(n, x)                       # x × y = n
        self.sketch(name, origin, x, y)

        def local(p):
            d = [p[i] - origin[i] for i in range(3)]
            assert abs(sum(d[i] * n[i] for i in range(3))) < 1e-9, f"{name}: point off the sketch plane"
            return (sum(d[i] * x[i] for i in range(3)), sum(d[i] * y[i] for i in range(3)))
        return local

    def cut_poly(self, name, origin, into, pts, depth=None, target=None):
        """Cuts the closed polygon of world points `pts` (on the plane through `origin` normal to
        `into`) along `into`, `depth` deep or through all."""
        local = self.plane(name, origin, into)
        self.polyline([local(p) for p in pts])
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


def integrate2(f, x0, x1, y0, y1, n=600):
    """∬ f(x, y) over a box, midpoint rule on an n x n grid."""
    hx, hy = (x1 - x0) / n, (y1 - y0) / n
    return sum(f(x0 + (i + 0.5) * hx, y0 + (j + 0.5) * hy) for i in range(n) for j in range(n)) * hx * hy


# ----------------------------------------------------------------------------- 1-07
@part("1-07", "Motor cylinder oiler base", "Brass")
def oiler_base(s):
    """Sheet 03, 1-07 (scale 1:2): M4 x 6 stud (modelled at Ø4), Ø8 x 5 collar, 8 hex x 4.5,
    M6 tapped 8 deep from the hex end (Ø5), Ø2 oil hole through. Axis = Z, the stud at Z = 0."""
    LS = s.param("ob_stud_l", 6, "M4 stud length (into the 1-02 oiler hole)")
    DC = s.param("ob_collar_d", 8, "collar")
    LC = s.param("ob_collar_l", 5, "collar length")
    AF = s.param("ob_hex_af", 8, "hex across flats")
    LH = s.param("ob_hex_l", 4.5, "hex length")
    TD = s.param("ob_m6_depth", 8, "M6 tapped depth from the top (tap drill Ø5)")
    DO = s.param("ob_oil_hole", 2, "oil hole")
    top = LS + LC + LH
    # made like the part: 8 hex bar, the collar turned to Ø8, the stud, then the bores
    s.sketch("Hex", (0, 0, LS), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=LC + LH, name="Hex bar", body_name=s.body)
    s.turned("Collar", [(DC / 2, LS - 1), (AF, LS - 1), (AF, LS + LC), (DC / 2, LS + LC)], operation="cut")
    s.turned("Stud", [(0, 0), (2, 0), (2, LS + 1), (0, LS + 1)], operation="join")
    s.holes("M6 tapped", (0, 0, top), (0, 0, -1), [(0, 0, top)], 5.0, TD)
    s.holes("Oil hole", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], DO)
    v = math.sqrt(3) / 2 * AF * AF * LH + math.pi / 4 * (DC * DC * LC + 16 * LS)
    return v - math.pi / 4 * (25 * TD + DO * DO * (top - TD))


# ----------------------------------------------------------------------------- 1-15
@part("1-15", "Motor crank shaft drive pulley", "Brass")
def drive_pulley(s):
    """Sheet 03, 1-15 (scale 1:1; groove from the drawing's vector lines): Ø24 x 6.5 boss, then a
    6 wide pulley: two 1 thick Ø26 flanges and a V groove 4 wide at the top, 2.5 at its Ø20 flat
    bottom. M16 bore (tap drill Ø14), M4 grub screw 4 from the boss end (Ø3.3, on +X).
    Axis = Z, the boss end at Z = 0."""
    DB = s.param("pul_boss_d", 24, "boss")
    LB = s.param("pul_boss_l", 6.5, "boss length")
    DF = s.param("pul_d", 26, "flange diameter")
    TF = s.param("pul_flange_t", 1, "flange thickness")
    WT = s.param("pul_groove_top", 4, "groove width between the flanges")
    WB = s.param("pul_groove_bottom", 2.5, "groove bottom width")
    DG = s.param("pul_groove_d", 20, "groove bottom diameter")
    DT = s.param("pul_tap_d", 14, "M16 (tap drill Ø14)")
    ZG = s.param("pul_grub_z", 4, "M4 grub screw position")
    z0 = LB + TF
    c = (WT - WB) / 2
    pts = [(DT / 2, 0), (DB / 2, 0), (DB / 2, LB), (DF / 2, LB), (DF / 2, z0), (DG / 2, z0 + c),
           (DG / 2, z0 + c + WB), (DF / 2, z0 + WT), (DF / 2, z0 + WT + TF), (DT / 2, z0 + WT + TF)]
    v = s.turned("Pulley", pts)
    s.holes("M4 grub tapped", (DB / 2, 0, 0), (-1, 0, 0), [(DB / 2, 0, ZG)], 3.3, (DB - DT) / 2 + 1)
    return v - radial_hole(3.3, DB / 2, DT / 2)


# ----------------------------------------------------------------------------- 1-23
@part("1-23", "Motor piston cross head", "Brass")
def cross_head(s):
    """Sheet 03, 1-23 (scale 1:2): Ø10 x 18, M5 tapped 9 deep from Z = 0 (Ø4.2) for the piston
    rod, 5 wide fork slot 9 deep from Z = 18 (the slot across X), Ø3.5 pin hole along X 13.5 from
    Z = 0. Axis = Z."""
    D = s.param("ch_d", 10, "diameter")
    L = s.param("ch_l", 18, "length")
    TD = s.param("ch_tap_depth", 9, "M5 tapped depth (meets the slot)")
    SW = s.param("ch_slot_w", 5, "fork slot width")
    SD = s.param("ch_slot_depth", 9, "fork slot depth")
    ZP = s.param("ch_pin_z", 13.5, "pin hole position")
    DP = s.param("ch_pin_d", 3.5, "pin hole")
    R = D / 2
    v = s.turned("Body", [(0, 0), (R, 0), (R, L), (0, L)])
    s.holes("M5 tapped", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], 4.2, TD)
    s.cut_poly("Fork slot", (0, -R - 1, 0), (0, 1, 0),
               [(-SW / 2, -R - 1, L - SD), (SW / 2, -R - 1, L - SD), (SW / 2, -R - 1, L + 1), (-SW / 2, -R - 1, L + 1)])
    s.holes("Pin hole", (R, 0, 0), (-1, 0, 0), [(R, 0, ZP)], DP)
    v -= math.pi / 4 * 4.2 ** 2 * TD + strip(R, -SW / 2, SW / 2) * SD
    # pin hole: through the two fork cheeks (|x| > 2.5) of the Ø10 section
    v -= integrate2(lambda y, z: 2 * max(0.0, math.sqrt(max(0.0, R * R - y * y)) - SW / 2)
                    if y * y + z * z < DP * DP / 4 else 0.0, -DP / 2, DP / 2, -DP / 2, DP / 2)
    return v


# ----------------------------------------------------------------------------- 1-24A
@part("1-24A", "Motor piston rod", {"rod": "Steel", "pin": "Stainless Steel"})
def piston_rod(s):
    """Sheet 03, 1-24A (scale 1:1.5): M/S rod, Ø4.9 x 10 (through the 1-22 piston crown) then
    Ø6 x 79, with a Ø3.5 x 27 S/S cross pin pressed in 4 from the Ø4.9 end (along Y) and a Ø4
    cross hole 5 from the other end (along X, for the 1-24B pin). Axis = Z from the Ø4.9 end."""
    D1 = s.param("pr_d1", 4.9, "end through the piston")
    L1 = s.param("pr_l1", 10, "its length")
    D2 = s.param("pr_d2", 6, "rod")
    L2 = s.param("pr_l2", 79, "rod length")
    DP = s.param("pr_pin_d", 3.5, "cross pin, 3.5PF")
    LP = s.param("pr_pin_l", 27, "cross pin length (from the drawing's vector lines)")
    ZP = s.param("pr_pin_z", 4, "cross pin position")
    DH = s.param("pr_hole_d", 4, "cross hole at the other end")
    ZH = s.param("pr_hole_z", L1 + L2 - 5, "5 from the end")
    n = s.body.split()[0]
    rod, pin = f"{n} rod", f"{n} pin"
    v = s.turned("Rod", [(0, 0), (D1 / 2, 0), (D1 / 2, L1), (D2 / 2, L1), (D2 / 2, L1 + L2), (0, L1 + L2)], body=rod)
    s.holes("Pin hole", (0, D1 / 2, 0), (0, -1, 0), [(0, D1 / 2, ZP)], DP, target=rod)
    s.holes("Cross hole", (D2 / 2, 0, 0), (-1, 0, 0), [(D2 / 2, 0, ZH)], DH, target=rod)
    v -= radial_hole(DP, D1 / 2, walls=2) + radial_hole(DH, D2 / 2, walls=2)
    s.sketch("Cross pin", (0, -LP / 2, 0), (1, 0, 0), (0, 0, -1))
    s.cmd("sketch.circle.center", center=[0, -ZP], diameter=DP)
    s.finish()
    s.cmd("solid.extrude", distance=LP, operation="new", name="Cross pin", body_name=pin)
    return v + math.pi / 4 * DP * DP * LP


# ----------------------------------------------------------------------------- 1-24B
@part("1-24B", "Motor piston rod big end part-1", "Brass")
def big_end_1(s):
    """Sheet 03, 1-24B (scale 1:2): Ø10 x 12 socket for the 1-24A rod (Ø6 bore 11 deep, Ø4 pin
    hole 6 from the end, along X) and a 10 x 10 x 11 block ending in half of the Ø8 crankpin bearing
    (axis Y). M4 tapped through the block along X, 3.5 from the socket, for the 1-24C screws.
    Axis = Z from the socket end."""
    D = s.param("be_d", 10, "socket diameter; block 10 x 10")
    LS = s.param("be_socket_l", 12, "socket length")
    LB = s.param("be_block_l", 11, "block length")
    DB = s.param("be_bore", 6, "rod bore")
    BD = s.param("be_bore_depth", 11, "rod bore depth")
    ZP = s.param("be_pin_z", 6, "pin hole position (1-24A hole is 5 from its end)")
    DP = s.param("be_pin_d", 4, "pin hole")
    DC = s.param("be_crank_d", 8, "crankpin bearing")
    ZS = s.param("be_screw_z", LS + 3.5, "M4 tapped, 3.5 into the block")
    R = D / 2
    # the block, then the socket overlapping 0.5 into it (a socket butted against the block, or
    # turned down from square bar, fails: its Ø10 is tangent to the block's faces)
    s.sketch("Block", (0, 0, LS), (1, 0, 0), (0, 1, 0))
    s.polyline([(-R, -R), (R, -R), (R, R), (-R, R)])
    s.finish()
    s.cmd("solid.extrude", distance=LB, name="Block", body_name=s.body)
    s.turned("Socket", [(0, 0), (R, 0), (R, LS + 0.5), (0, LS + 0.5)], operation="join")
    s.holes("Rod bore", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], DB, BD)
    v = math.pi / 4 * D * D * LS + D * D * LB - math.pi / 4 * DB * DB * BD
    s.holes("Bearing half", (0, -R, 0), (0, 1, 0), [(0, -R, LS + LB)], DC)
    s.holes("M4 tapped", (R, 0, 0), (-1, 0, 0), [(R, 0, ZS)], 3.3)
    s.holes("Pin hole", (R, 0, 0), (-1, 0, 0), [(R, 0, ZP)], DP)
    v -= math.pi / 8 * DC * DC * D + math.pi / 4 * 3.3 ** 2 * D + radial_hole(DP, R, DB / 2, walls=2)
    return v


# ----------------------------------------------------------------------------- 1-24C
@part("1-24C", "Motor piston rod big end part-2", "Brass")
def big_end_2(s):
    """Sheet 03, 1-24C (scale 1:2): U-shaped cap over the 1-24B block: two 8 thick arms 11 long
    with a 10 opening, an 8 long bridge holding the other half of the Ø8 crankpin bearing, 10
    wide. Ø4.3 holes (M4 clearance, sheet 02 note 3) through both arms, a Ø2 oil hole from the
    top into the bearing. X along the rod (the arms' open end at X = 0), Z up, Y across."""
    LA = s.param("cap_arm_l", 11, "arm length")
    LB = s.param("cap_bridge_l", 8, "bridge length")
    TA = s.param("cap_arm_t", 8, "arm thickness")
    OP = s.param("cap_opening", 10, "opening (5 + 5) for the 1-24B block")
    W = s.param("cap_w", 10, "width")
    DC = s.param("cap_crank_d", 8, "crankpin bearing, centred on the bridge face")
    XS = s.param("cap_screw_x", 3.5, "screw holes")
    DS = s.param("cap_screw_d", 4.3, "M4 clearance")
    XO = s.param("cap_oil_x", 15, "oil hole (3.5 + 11.5)")
    H = OP / 2 + TA
    s.sketch("Side profile", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.polyline([(0, -H), (LA + LB, -H), (LA + LB, H), (0, H), (0, OP / 2), (LA, OP / 2), (LA, -OP / 2), (0, -OP / 2)])
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Cap", body_name=s.body)
    s.holes("Bearing half", (0, -W / 2, 0), (0, 1, 0), [(LA, -W / 2, 0)], DC)
    s.holes("Screw holes", (0, 0, H), (0, 0, -1), [(XS, 0, H)], DS)
    s.holes("Oil hole", (0, 0, H), (0, 0, -1), [(XO, 0, H)], 2, H)
    v = ((LA + LB) * 2 * H - LA * OP - math.pi / 8 * DC * DC) * W
    v -= math.pi / 4 * DS * DS * 2 * TA
    rc = DC / 2
    v -= integrate2(lambda x, y: (H - (math.sqrt(max(0.0, rc * rc - (x - LA) ** 2)) if x - LA < rc else 0.0))
                    if (x - XO) ** 2 + y * y < 1 else 0.0, XO - 1, XO + 1, -1, 1)
    return v


# ----------------------------------------------------------------------------- 1-25A
@part("1-25A", "Motor cylinder slide valve-1", "Stainless Steel")
def slide_valve_1(s):
    """Sheet 03, 1-25A (scale 1:2): flat plate 19.8 x 50 x 0.1 (S/S or spring steel), R4 corners,
    Ø5 hole on the centre line 6 from one end. On the XY plane, the hole end at Y = 0."""
    W = s.param("sv_w", 19.8, "width (9.9 + 9.9)")
    L = s.param("sv_l", 50, "length")
    T = s.param("sv_t", 0.1, "thickness")
    RC = s.param("sv_r", 4, "corner radius")
    YH = s.param("sv_hole_y", 6, "hole position")
    DH = s.param("sv_hole_d", 5, "hole")
    x0, x1 = -W / 2, W / 2
    segs = [("line", (x1 - RC, 0)), ("arc", (x1 - RC, RC), (x1, RC), True), ("line", (x1, L - RC)),
            ("arc", (x1 - RC, L - RC), (x1 - RC, L), True), ("line", (x0 + RC, L)),
            ("arc", (x0 + RC, L - RC), (x0, L - RC), True), ("line", (x0, RC)), ("arc", (x0 + RC, RC), (x0 + RC, 0), True)]
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop((x0 + RC, 0), segs)
    s.cmd("sketch.circle.center", center=[0, YH], diameter=DH)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [0, L / 2]}], name="Plate", body_name=s.body)
    return (loop_area((x0 + RC, 0), segs) - math.pi / 4 * DH * DH) * T


# ----------------------------------------------------------------------------- 1-25B
@part("1-25B", "Motor cylinder slide valve-2", "Stainless Steel")
def slide_valve_2(s):
    """Sheet 03, 1-25B (scale 1:2): 0.1 spring sheet 19.8 x 50, flat for 10 (with the Ø5 hole 6
    from the end) and 4 at the other end, bowed R162 in between (bow 1.0: 1.1 over the sheet).
    The side profile is on the XZ plane (Z along the sheet, the bow toward +X), extruded across Y."""
    W = s.param("sv2_w", 19.8, "width")
    L = s.param("sv2_l", 50, "length")
    T = s.param("sv2_t", 0.1, "thickness")
    F1 = s.param("sv2_flat1", 10, "flat end with the hole")
    F2 = s.param("sv2_flat2", 4, "flat end at the other side")
    RB = s.param("sv2_bow_r", 162, "bow radius")
    DH = s.param("sv2_hole_d", 5, "hole")
    ZH = s.param("sv2_hole_z", 6, "hole position")
    zm = (F1 + L - F2) / 2
    half = (L - F2 - F1) / 2
    sag = RB - math.sqrt(RB * RB - half * half)
    c = (T / 2 + sag - RB, zm)                   # centre of the bow's mid surface
    dz = lambda r, x: math.sqrt(r * r - (x - c[0]) ** 2)
    zo, zi = dz(RB + T / 2, T), dz(RB - T / 2, 0)
    segs = [("line", (T, 0)), ("line", (T, zm - zo)), ("arc", c, (T, zm + zo), True), ("line", (T, L)),
            ("line", (0, L)), ("line", (0, zm + zi)), ("arc", c, (0, zm - zi), False), ("line", (0, 0))]
    s.sketch("Side profile", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop((0, 0), segs)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Sheet", body_name=s.body)
    s.holes("Hole", (-1, 0, 0), (1, 0, 0), [(-1, 0, ZH)], DH)
    return loop_area((0, 0), segs) * W - math.pi / 4 * DH * DH * T


# ----------------------------------------------------------------------------- 1-29
@part("1-29", "Motor valve rod lock nut", "Brass")
def valve_rod_lock_nut(s):
    """Sheet 03, 1-29: Ø6 x 9 with an 8 hex x 4 at one end; M4 tapped 3 deep from the Ø6 end
    (Ø3.3), Ø4.5 through the rest (clearance for the Ø4 1-28 rod). Axis = Z from the Ø6 end."""
    D = s.param("vh_d", 6, "body")
    L = s.param("vh_l", 13, "overall length (3 + 10)")
    LH = s.param("vh_hex_l", 4, "hex length")
    AF = s.param("vh_hex_af", 8, "hex across flats")
    LT = s.param("vh_tap_l", 3, "M4 tapped length")
    DC = s.param("vh_clear_d", 4.5, "clearance bore")
    s.sketch("Hex", (0, 0, L - LH), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=LH, name="Hex", body_name=s.body)
    s.turned("Body", [(0, 0), (D / 2, 0), (D / 2, L - LH + 1), (0, L - LH + 1)], operation="join")
    s.holes("Clearance bore", (0, 0, L), (0, 0, -1), [(0, 0, L)], DC, L - LT)
    s.holes("M4 tapped", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], 3.3, LT + 1)
    v = math.sqrt(3) / 2 * AF * AF * LH + math.pi / 4 * D * D * (L - LH)
    return v - math.pi / 4 * (DC * DC * (L - LT) + 3.3 ** 2 * LT)


# ----------------------------------------------------------------------------- 1-30
@part("1-30", "Motor valve rod valve holder", "Brass")
def valve_holder(s):
    """Sheet 03, 1-30: flange Ø10 x 3, spigot Ø5 x 6, M4 tapped through (Ø3.3). Axis = Z, the
    flange at Z = 0. The Ø5 spigot carries the slide valves (1-25A/B, Ø5 holes)."""
    DF = s.param("vb_flange_d", 10, "flange")
    TF = s.param("vb_flange_t", 3, "flange thickness")
    D = s.param("vb_d", 5, "spigot")
    L = s.param("vb_l", 6, "spigot length")
    return s.turned("Bush", [(1.65, 0), (DF / 2, 0), (DF / 2, TF), (D / 2, TF), (D / 2, TF + L), (1.65, TF + L)])


# ----------------------------------------------------------------------------- 1-33
@part("1-33", "Motor rocking arm cam follower axle", "Steel")
def follower_axle(s):
    """Sheet 03, 1-33: M4 x 4 (modelled at Ø4), Ø6 x 6, head Ø10 x 2 (its small notch is not
    modelled). Axis = Z from the M4 end."""
    LT = s.param("fa_thread_l", 4, "M4 length")
    D = s.param("fa_d", 6, "axle")
    L = s.param("fa_l", 6, "axle length")
    DH = s.param("fa_head_d", 10, "head")
    TH = s.param("fa_head_t", 2, "head thickness")
    return s.turned("Axle", [(0, 0), (2, 0), (2, LT), (D / 2, LT), (D / 2, LT + L), (DH / 2, LT + L),
                             (DH / 2, LT + L + TH), (0, LT + L + TH)])


def clip_above(poly, z0):
    """The part of the polygon of (y, z) points with z >= z0 (Sutherland-Hodgman)."""
    out = []
    for a, b in zip(poly, poly[1:] + poly[:1]):
        ina, inb = a[1] >= z0, b[1] >= z0
        if ina:
            out.append(a)
        if ina != inb:
            t = (z0 - a[1]) / (b[1] - a[1])
            out.append((a[0] + t * (b[0] - a[0]), z0))
    return out


def polygon_area(poly):
    return abs(sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(poly, poly[1:] + poly[:1]))) / 2


def offset_polyline(pts, d):
    """The open polyline of (y, z) points offset by d to its left (miter corners)."""
    lines = []
    for a, b in zip(pts, pts[1:]):
        t = _unit((b[0] - a[0], b[1] - a[1], 0))
        lines.append(((a[0] - d * t[1], a[1] + d * t[0]), (t[0], t[1])))
    out = [lines[0][0]]
    for (p, u), (q, w) in zip(lines, lines[1:]):
        k = ((q[0] - p[0]) * w[1] - (q[1] - p[1]) * w[0]) / (u[0] * w[1] - u[1] * w[0])
        out.append((p[0] + k * u[0], p[1] + k * u[1]))
    (p, u), end = lines[-1], pts[-1]
    out.append((end[0] - d * u[1], end[1] + d * u[0]))
    return out


# ----------------------------------------------------------------------------- 1-05
@part("1-05", "Motor outer cylinder head", "Cast Iron")
def outer_cylinder_head(s):
    """Sheet 03, 1-05 ("refer to 1-04 for all dimension details", scale 1:2): the 1-04 disc
    without the valve channel: Ø56 x 3.5 (thickness taken from 1-04), 4 x Ø4.5 on PCD 44 at 45 deg,
    Ø10 port countersunk 90 deg to Ø15 on the Z = 0 face (dashed on the drawing: the hidden side)."""
    D = s.param("oh_d", 56, "diameter")
    T = s.param("oh_t", 3.5, "thickness: not given, taken from 1-04")
    PCD = s.param("oh_pcd", 44, "bolt holes PCD")
    DH = s.param("oh_hole_d", 4.5, "M4 clearance")
    DP = s.param("oh_port_d", 10, "central port")
    DCS = s.param("oh_csink_d", 15, "countersink, 90 deg")
    s.sketch("Disc", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[0, 0], diameter=D)
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Disc", body_name=s.body)
    s.holes("Bolt holes", (0, 0, T), (0, 0, -1), [(x, y, T) for x, y in ring_pts(4, PCD / 2, 45)], DH)
    hcs = (DCS - DP) / 2
    s.sketch("Port section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.polyline([(0, -1), (DCS / 2 + 1, -1), (DCS / 2, 0), (DP / 2, hcs), (DP / 2, T + 1), (0, T + 1)])
    s.finish()
    s.cmd("solid.revolve", axis="Z", operation="cut", targets=[s.body], name="Countersunk port")
    v = math.pi / 4 * (D * D - 4 * DH * DH) * T
    return v - math.pi / 12 * hcs * (DCS ** 2 + DCS * DP + DP ** 2) - math.pi / 4 * DP * DP * (T - hcs)


# ----------------------------------------------------------------------------- 1-06
@part("1-06", "Motor crank shaft ball bearing", "Steel")
def crank_bearing(s):
    """Sheet 03, 1-06: bought ball bearing Ø19 x Ø9.5 x 9 (drawn as PPI). Modelled as its
    envelope with the race faces 0.5 recessed, for fitting checks only. Axis = Z from Z = 0."""
    D = s.param("brg_od", 19, "outside diameter")
    DI = s.param("brg_id", 9.5, "bore (the 1-14 journal)")
    W = s.param("brg_w", 9, "width")
    pts = [(DI / 2, 0), (DI / 2 + 1.5, 0), (DI / 2 + 1.5, 0.5), (D / 2 - 1.5, 0.5), (D / 2 - 1.5, 0), (D / 2, 0),
           (D / 2, W), (D / 2 - 1.5, W), (D / 2 - 1.5, W - 0.5), (DI / 2 + 1.5, W - 0.5), (DI / 2 + 1.5, W),
           (DI / 2, W)]
    return s.turned("Bearing envelope", pts)


# ----------------------------------------------------------------------------- 1-32
@part("1-32", "Motor rocking arm cam follower", "Steel")
def cam_follower(s):
    """Sheet 03, 1-32 (scale 1:1.5): roller Ø16 x 8, Ø6 bore (the 1-33 axle), Ø11 recess 2.5 deep
    on one face, Ø10 x 0.5 thrust face on the other. Axis = Z, the thrust face at Z = 0."""
    D = s.param("cf_d", 16, "roller diameter")
    W = s.param("cf_w", 8, "roller width")
    DB = s.param("cf_bore", 6, "bore")
    DR = s.param("cf_recess_d", 11, "recess")
    HR = s.param("cf_recess_depth", 2.5, "recess depth")
    DT = s.param("cf_boss_d", 10, "thrust boss")
    HT = s.param("cf_boss_h", 0.5, "thrust boss height")
    return s.turned("Roller", [(DB / 2, 0), (DT / 2, 0), (DT / 2, HT), (D / 2, HT), (D / 2, HT + W),
                               (DR / 2, HT + W), (DR / 2, HT + W - HR), (DB / 2, HT + W - HR)])


# ----------------------------------------------------------------------------- 1-35
@part("1-35", "Exhaust pipe holding bracket", "Brass")
def exhaust_pipe_bracket(s):
    """Sheet 03, 1-35 (scale 1:2): 3 thick brass strip, 10 wide, bent: an 8.5 tab with a Ø3 hole
    (4.5 from the top), a 14.5 high joggle offsetting it 10.5, then a fork R26 / R18 about a centre
    2 above its feet, with 2 x Ø4.5 on R22 at 45 deg. Z up from the feet (the top at Z = 54.5),
    X across, the fork plate on Y = 10.5..13.5, the tab on Y = 0..3. Bends are sharp."""
    T = s.param("epb_t", 3, "thickness")
    W = s.param("epb_w", 10, "strip width (5 + 5)")
    H1 = s.param("epb_tab", 8.5, "tab height")
    H2 = s.param("epb_joggle_h", 14.5, "joggle height")
    H3 = s.param("epb_fork_h", 31.5, "fork part height")
    OFF = s.param("epb_offset", 10.5, "joggle offset")
    RO = s.param("epb_r_out", 26, "fork outside radius")
    RI = s.param("epb_r_in", 18, "fork inside radius (the pipe)")
    LEG = s.param("epb_legs", 2, "fork feet below the centre")
    PCR = s.param("epb_pcd_r", 22, "holes on R22 at 45 deg")
    DH = s.param("epb_hole_d", 4.5, "fork holes")
    DT = s.param("epb_tab_hole", 3, "tab hole")
    ZT = s.param("epb_tab_hole_z", 4.5, "tab hole from the top")
    top = H1 + H2 + H3
    zc = LEG
    zj = H3                                     # bottom of the joggle
    # side profile (y, z): the −Y face of the strip as a polyline, offset by T toward +Y
    inner = [(0, top), (0, top - H1), (OFF, zj), (OFF, zj - 7)]
    side = inner + offset_polyline(inner, T)[::-1]
    s.sketch("Side profile", (0, 0, 0), (0, 1, 0), (0, 0, 1))
    s.polyline(side)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Tab and joggle", body_name=s.body)
    # the fork plate: front outline in (x, z), sketched on Y = OFF + T and extruded T toward −Y
    ao = math.sqrt(RO * RO - (W / 2) ** 2)
    start = (-W / 2, zj)
    segs = [("line", (-W / 2, zc + ao)), ("arc", (0, zc), (-RO, zc), True), ("line", (-RO, zc - LEG)),
            ("line", (-RI, zc - LEG)), ("line", (-RI, zc)), ("arc", (0, zc), (RI, zc), False),
            ("line", (RI, zc - LEG)), ("line", (RO, zc - LEG)), ("line", (RO, zc)),
            ("arc", (0, zc), (W / 2, zc + ao), True), ("line", (W / 2, zj)), ("line", start)]
    s.sketch("Fork", (0, OFF + T, 0), (1, 0, 0), (0, 0, 1))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Fork")
    s.holes("Tab hole", (0, -1, 0), (0, 1, 0), [(0, -1, top - ZT)], DT)
    hx = PCR * math.sin(math.pi / 4)
    s.holes("Fork holes", (0, -1, 0), (0, 1, 0), [(-hx, -1, zc + hx), (hx, -1, zc + hx)], DH)
    v = W * polygon_area(clip_above(side, zj)) + T * loop_area(start, segs)
    return v - math.pi / 4 * (DT * DT + 2 * DH * DH) * T


def removed_by_cylinder(inside, p0, d, dia, length, n=120):
    """Volume of material (inside(x, y, z) is True) within the cylinder of diameter `dia` from p0
    along the unit vector d for `length`: midpoint sampling."""
    u = _unit(_cross(d, (0, 0, 1)) if abs(d[2]) < 0.9 else _cross(d, (1, 0, 0)))
    w = _cross(d, u)
    r, v, h = dia / 2, 0, dia / n
    nl = max(1, int(length / h))
    hl = length / nl
    for i in range(n):
        a = -r + (i + 0.5) * h
        for j in range(n):
            b = -r + (j + 0.5) * h
            if a * a + b * b > r * r:
                continue
            for k in range(nl):
                t = (k + 0.5) * hl
                q = [p0[m] + a * u[m] + b * w[m] + t * d[m] for m in range(3)]
                if inside(*q):
                    v += 1
    return v * h * h * hl


def in_revolved(pts, x, y, z):
    """Is (x, y, z) inside the closed (r, z) polygon `pts` revolved about the Z axis?"""
    r, inside = math.hypot(x, y), False
    for (r0, z0), (r1, z1) in zip(pts, pts[1:] + pts[:1]):
        if (z0 > z) != (z1 > z) and r < r0 + (z - z0) * (r1 - r0) / (z1 - z0):
            inside = not inside
    return inside


# ----------------------------------------------------------------------------- 1-08
@part("1-08", "Motor cylinder oiler glass base", "Brass")
def oiler_glass_base(s):
    """Sheet 03, 1-08 (scale 1:1, read off the drawing's vector lines): Ø4 x 4 nozzle (its small
    30 deg tip chamfer not modelled), M6 x 5 (at Ø6) into 1-07, Ø17 x 2 flange with a Ø15 x 1
    recess for the 1-09 glass, Ø5 x 4 boss tapped M3 3 deep (Ø2.5) for the 1-10 screw, Ø3 bore
    from below, and a Ø2 drain hole rising at 15 deg from the bore into the recess (on +X).
    Axis = Z, the nozzle tip at Z = 0."""
    LN = s.param("gb_nozzle_l", 4, "nozzle length")
    LT = s.param("gb_thread_l", 5, "M6 length")
    DF = s.param("gb_flange_d", 17, "flange")
    TF = s.param("gb_flange_t", 2, "flange thickness")
    DR = s.param("gb_recess_d", 15, "recess for the glass (Ø15)")
    HR = s.param("gb_recess_h", 1, "recess depth")
    DB = s.param("gb_boss_d", 5, "boss")
    HB = s.param("gb_boss_h", 4, "boss height above the flange")
    ZB = s.param("gb_bore_top", 9.88, "top of the Ø3 bore (measured)")
    TD = s.param("gb_m3_depth", 3, "M3 tapped depth (measured 3.1)")
    zf = LN + LT
    top = zf + TF + HB
    pts = [(1.5, 0), (2, 0), (2, LN), (3, LN), (3, zf), (DF / 2, zf), (DF / 2, zf + TF), (DR / 2, zf + TF),
           (DR / 2, zf + TF - HR), (DB / 2, zf + TF - HR), (DB / 2, top), (0, top), (0, ZB), (1.5, ZB)]
    v = s.turned("Body", pts)
    s.holes("M3 tapped", (0, 0, top), (0, 0, -1), [(0, 0, top)], 2.5, TD)
    a = math.radians(15)
    d = (math.cos(a), 0, math.sin(a))
    p0 = (-1, 0, 10.53 - math.tan(a))           # the hole axis crosses the bore axis at Z = 10.53
    s.holes("Drain hole", p0, d, [p0], 2, 6)
    v -= math.pi / 4 * 2.5 ** 2 * TD
    v -= removed_by_cylinder(lambda x, y, z: in_revolved(pts, x, y, z) and not (z > top - TD and x * x + y * y < 1.5625),
                             p0, d, 2, 6)
    return v


# ----------------------------------------------------------------------------- 1-10
@part("1-10", "Motor cylinder oiler glass top", "Brass")
def oiler_glass_top(s):
    """Sheet 03, 1-10: funnel: Ø17 x 2 base with a Ø15 x 1 recess underneath (over the 1-09 glass),
    1 thick wall at 60 deg up to Ø17 at a height of 6; Ø3 hole in the middle (the M3 screw into 1-08)
    and two Ø2 feed holes 3 either side (on X). Axis = Z, the base at Z = 0."""
    D = s.param("gt_d", 17, "base and rim diameter")
    DR = s.param("gt_recess_d", 15, "recess underneath")
    HR = s.param("gt_recess_h", 1, "recess depth")
    TB = s.param("gt_base_t", 2, "base thickness")
    H = s.param("gt_h", 6, "height")
    A = math.radians(s.param("gt_angle", 60, "wall angle to the base", unit="deg"))
    T = s.param("gt_wall", 1, "wall thickness")
    DC = s.param("gt_hole_d", 3, "central hole")
    XF = s.param("gt_feed_x", 3, "feed holes, Ø2")
    R = D / 2
    run = (H - TB) / math.tan(A)
    dt = T / math.sin(A)
    pts = [(DC / 2, HR), (DR / 2, HR), (DR / 2, 0), (R, 0), (R, TB), (R - run, TB), (R, H), (R - dt, H),
           (R - dt - run, TB), (DC / 2, TB)]
    v = s.turned("Funnel", pts)
    s.holes("Feed holes", (0, 0, -1), (0, 0, 1), [(-XF, 0, -1), (XF, 0, -1)], 2, TB + 2)
    return v - 2 * math.pi * (TB - HR)


# ----------------------------------------------------------------------------- 1-11
@part("1-11", "Motor block oil channel", "Steel")
def oil_channel(s):
    """Sheet 03, 1-11 (scale 1:2): 1.5 thick M/S strip, 20 long, bent into a channel: two 28 flats
    (to the centre) and a semicircular trough of inside Ø15.5 between them, hanging below the flats'
    top face. Side profile on the XZ plane (top face at Z = 0), extruded 20 along Y."""
    T = s.param("oc_t", 1.5, "thickness")
    L = s.param("oc_half", 28, "end to centre")
    DI = s.param("oc_trough_d", 15.5, "trough inside diameter")
    W = s.param("oc_w", 20, "length (20mm LONG)")
    ri, ro = DI / 2, DI / 2 + T
    xo = math.sqrt(ro * ro - T * T)
    start = (-L, 0)
    segs = [("line", (-ri, 0)), ("arc", (0, 0), (ri, 0), True), ("line", (L, 0)), ("line", (L, -T)),
            ("line", (xo, -T)), ("arc", (0, 0), (-xo, -T), False), ("line", (-L, -T)), ("line", start)]
    s.sketch("Side profile", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Channel", body_name=s.body)
    return loop_area(start, segs) * W


# ----------------------------------------------------------------------------- 1-12
@part("1-12", "Motor block oil valve part-1", "Brass")
def oil_valve_1(s):
    """Sheet 03, 1-12: M6 x 6 stud (at Ø6), 8 hex x 22 body tapped M6 8 deep from the far end (Ø5),
    Ø2 through. Axis = Z from the stud end."""
    LS = s.param("ov1_stud_l", 6, "M6 stud")
    LH = s.param("ov1_hex_l", 22, "hex body")
    AF = s.param("ov1_af", 8, "hex across flats")
    TD = s.param("ov1_tap_depth", 8, "M6 tapped depth (for 1-13)")
    top = LS + LH
    s.sketch("Hex", (0, 0, LS), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=LH, name="Hex bar", body_name=s.body)
    s.turned("Stud", [(0, 0), (3, 0), (3, LS + 1), (0, LS + 1)], operation="join")
    s.holes("M6 tapped", (0, 0, top), (0, 0, -1), [(0, 0, top)], 5.0, TD)
    s.holes("Oil hole", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], 2)
    v = math.sqrt(3) / 2 * AF * AF * LH + math.pi / 4 * 36 * LS
    return v - math.pi / 4 * (25 * TD + 4 * (top - TD))


# ----------------------------------------------------------------------------- 1-13
@part("1-13", "Motor block oil valve part-2", "Brass")
def oil_valve_2(s):
    """Sheet 03, 1-13: valve screwed into 1-12: Ø4 x 5.5 tip with a 45 deg point chamfer (to Ø1.5)
    and a Ø2 cross hole 3.5 from the tip (along X), M6 x 6 (at Ø6), 8 hex x 3.5, Ø3.5 x 5 spigot;
    Ø2 bore from the spigot end to the cross hole. Axis = Z from the tip."""
    LT = s.param("ov2_tip_l", 5.5, "tip length")
    DT = s.param("ov2_tip_d", 4, "tip diameter (measured)")
    LM = s.param("ov2_thread_l", 6, "M6 length")
    LH = s.param("ov2_hex_l", 3.5, "hex length")
    AF = s.param("ov2_af", 8, "hex across flats")
    LS = s.param("ov2_spigot_l", 5, "spigot length")
    DS = s.param("ov2_spigot_d", 3.5, "spigot diameter")
    ZX = s.param("ov2_cross_z", 3.5, "cross hole position")
    z1, z2 = LT, LT + LM
    z3 = z2 + LH
    top = z3 + LS
    ch = (DT - 1.5) / 2
    s.sketch("Hex", (0, 0, z1), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=LM + LH, name="Hex bar", body_name=s.body)
    s.turned("Thread", [(3, z1 - 1), (AF, z1 - 1), (AF, z2), (3, z2)], operation="cut")
    tip = [(0, 0), (0.75, 0), (DT / 2, ch), (DT / 2, z1 + 1), (0, z1 + 1)]
    spig = [(0, z3 - 1), (DS / 2, z3 - 1), (DS / 2, top), (0, top)]
    s.turned("Tip", tip, operation="join")
    s.turned("Spigot", spig, operation="join")
    s.holes("Bore", (0, 0, top), (0, 0, -1), [(0, 0, top)], 2, top - ZX)
    s.holes("Cross hole", (DT / 2, 0, 0), (-1, 0, 0), [(DT / 2, 0, ZX)], 2)
    v = revolved_volume([(0, 0), (0.75, 0), (DT / 2, ch), (DT / 2, z1), (0, z1)])
    v += math.pi / 4 * 36 * LM + math.sqrt(3) / 2 * AF * AF * LH + math.pi / 4 * DS * DS * LS
    v -= math.pi / 4 * 4 * (top - ZX)
    # the cross hole, less what the bore already took out where they meet
    v -= removed_by_cylinder(lambda x, y, z: x * x + y * y < DT * DT / 4 and not (x * x + y * y < 1 and z > ZX),
                             (DT / 2, 0, ZX), (-1, 0, 0), 2, DT)
    return v


# ----------------------------------------------------------------------------- 1-36
@part("1-36", "Exhaust lower circular bracket", "Aluminum")
def exhaust_lower_bracket(s):
    """Sheet 04, 1-36 (scale 1:2, read with the drawing's vector lines): Ø31 x 14 base, a cone
    from Ø31 up to Ø38.5 over 17, and a Ø33 x 7 band on top; the bore tapers from Ø27 at 6.5 up to
    Ø24 at the top, Ø27 below. 4 x M3 (Ø2.5) radially through the band 3.5 from the top, on X and
    Y, for the 1-37 ring. Axis = Z from the base."""
    DB = s.param("elb_base_d", 31, "base diameter")
    HB = s.param("elb_base_h", 14, "base height")
    DC = s.param("elb_cone_d", 38.5, "cone top diameter")
    HC = s.param("elb_cone_h", 17, "cone height")
    DT = s.param("elb_band_d", 33, "top band diameter (1-37 sits on it)")
    HT = s.param("elb_band_h", 7, "band height")
    DI1 = s.param("elb_bore_bottom", 27, "bore at the bottom")
    HI = s.param("elb_bore_step", 6.5, "Ø27 bore height, then the taper")
    DI2 = s.param("elb_bore_top", 24, "bore at the top")
    ZS = s.param("elb_screw_z", 3.5, "M3 holes below the top")
    top = HB + HC + HT
    pts = [(DI1 / 2, 0), (DB / 2, 0), (DB / 2, HB), (DC / 2, HB + HC), (DT / 2, HB + HC), (DT / 2, top),
           (DI2 / 2, top), (DI1 / 2, HI)]
    v = s.turned("Bracket", pts)
    z = top - ZS
    ri = DI2 / 2 + (DI1 - DI2) / 2 * (top - z) / (top - HI)
    s.holes("M3 tapped X", (DT / 2, 0, 0), (-1, 0, 0), [(DT / 2, 0, z)], 2.5)
    s.holes("M3 tapped Y", (0, DT / 2, 0), (0, -1, 0), [(0, DT / 2, z)], 2.5)
    return v - 2 * radial_hole(2.5, DT / 2, ri, walls=2)


# ----------------------------------------------------------------------------- 1-37
@part("1-37", "Exhaust base ring", "Brass")
def exhaust_base_ring(s):
    """Sheet 04, 1-37 (scale 1:2, vector lines): Ø40 x 10 with a 6 high cone to Ø33 on top; Ø27
    bore, counterbored Ø33 x 7 from below over the 1-36 band; 4 x Ø3 radial holes 3.5 from the
    bottom, on X and Y (the 1-36 M3 screws). Axis = Z from the bottom."""
    D = s.param("ebr_d", 40, "diameter")
    H1 = s.param("ebr_h1", 10, "cylindrical height")
    H2 = s.param("ebr_h2", 6, "cone height")
    DTP = s.param("ebr_top_d", 33, "cone top diameter")
    DI = s.param("ebr_bore", 27, "bore")
    DCB = s.param("ebr_cbore_d", 33, "counterbore from below")
    HCB = s.param("ebr_cbore_h", 7, "counterbore depth")
    ZH = s.param("ebr_hole_z", 3.5, "Ø3 holes from the bottom")
    v = s.turned("Ring", [(DCB / 2, 0), (D / 2, 0), (D / 2, H1), (DTP / 2, H1 + H2), (DI / 2, H1 + H2),
                          (DI / 2, HCB), (DCB / 2, HCB)])
    s.holes("Holes X", (D / 2, 0, 0), (-1, 0, 0), [(D / 2, 0, ZH)], 3)
    s.holes("Holes Y", (0, D / 2, 0), (0, -1, 0), [(0, D / 2, ZH)], 3)
    return v - 2 * radial_hole(3, D / 2, DCB / 2, walls=2)


# ----------------------------------------------------------------------------- 1-38
@part("1-38", "Exhaust stack", "Brass")
def exhaust_stack(s):
    """Sheet 04, 1-38 (scale 1:2, vector lines): 100 high: Ø33 x 2 flange, Ø27 x 19, a cone from
    Ø27 to Ø21 over 75 and a Ø19 x 4 top band; the bore tapers straight from Ø24 at the bottom to
    Ø17 at the top. Axis = Z from the flange."""
    DF = s.param("es_flange_d", 33, "flange")
    TF = s.param("es_flange_t", 2, "flange thickness")
    D1 = s.param("es_d1", 27, "lower diameter")
    H1 = s.param("es_h1", 19, "lower cylinder height")
    D2 = s.param("es_d2", 21, "cone top diameter")
    H2 = s.param("es_h2", 75, "cone height")
    DT = s.param("es_top_d", 19, "top band")
    HT = s.param("es_top_h", 4, "top band height")
    DB1 = s.param("es_bore_bottom", 24, "bore at the bottom")
    DB2 = s.param("es_bore_top", 17, "bore at the top")
    top = TF + H1 + H2 + HT
    return s.turned("Stack", [(DB1 / 2, 0), (DF / 2, 0), (DF / 2, TF), (D1 / 2, TF), (D1 / 2, TF + H1),
                              (D2 / 2, TF + H1 + H2), (DT / 2, TF + H1 + H2), (DT / 2, top), (DB2 / 2, top)])


# ----------------------------------------------------------------------------- 1-39
@part("1-39", "Exhaust stack top ring", "Brass")
def exhaust_top_ring(s):
    """Sheet 04, 1-39 (scale 1:1.5, vector lines): a Ø26.5 bead, 4 thick with a full R2 round edge,
    on a Ø22 x 2 spigot; Ø14.5 bore 2 deep from the top, Ø19 below it (over the 1-38 top band).
    Axis = Z from the bottom of the spigot."""
    D = s.param("etr_d", 26.5, "bead diameter")
    T = s.param("etr_t", 4, "bead thickness, full round R2")
    DS = s.param("etr_spigot_d", 22, "spigot")
    HS = s.param("etr_spigot_h", 2, "spigot height")
    DI1 = s.param("etr_bore_top", 14.5, "bore at the top")
    HI1 = s.param("etr_bore_top_h", 2, "its depth")
    DI2 = s.param("etr_bore", 19, "bore below (over 1-38)")
    rb = D / 2 - T / 2                          # bead edge centre radius
    z0, z1 = HS, HS + T
    start = (DI2 / 2, 0)
    segs = [("line", (DS / 2, 0)), ("line", (DS / 2, z0)), ("line", (rb, z0)),
            ("arc", (rb, z0 + T / 2), (rb, z1), True), ("line", (DI1 / 2, z1)), ("line", (DI1 / 2, z1 - HI1)),
            ("line", (DI2 / 2, z1 - HI1)), ("line", start)]
    s.sketch("Ring section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Ring", body_name=s.body)
    # Pappus on the polygon, plus the half-disc of the bead edge (area π/8 T², centroid 2T/3π out)
    poly = [start, (DS / 2, 0), (DS / 2, z0), (rb, z0), (rb, z1), (DI1 / 2, z1), (DI1 / 2, z1 - HI1), (DI2 / 2, z1 - HI1)]
    half = math.pi / 8 * T * T
    return revolved_volume(poly) + 2 * math.pi * (rb + 2 * T / (3 * math.pi)) * half


def link(s, centres, r1, r2, d1, d2, t, body=None, name="Link", z0=0):
    """A flat link on the XY plane, Z = 0..t: ends of radius r1 at the origin and r2 at (centres, 0),
    joined by their outer tangents, holes d1 and d2 at the ends. Returns its volume."""
    sp = (r1 - r2) / centres
    cp = math.sqrt(1 - sp * sp)
    p1l, p2l = (r1 * sp, -r1 * cp), (centres + r2 * sp, -r2 * cp)
    p1u, p2u = (r1 * sp, r1 * cp), (centres + r2 * sp, r2 * cp)
    segs = [("line", p2l), ("arc", (centres, 0), p2u, True), ("line", p1u), ("arc", (0, 0), p1l, True)]
    s.sketch(name, (0, 0, z0), (1, 0, 0), (0, 1, 0))
    s.loop(p1l, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=d1)
    s.cmd("sketch.circle.center", center=[centres, 0], diameter=d2)
    s.finish()
    s.cmd("solid.extrude", distance=t, profiles=[{"point": [centres / 2, 0]}], operation="new", name=name,
          body_name=body or s.body)
    return (loop_area(p1l, segs) - math.pi / 4 * (d1 * d1 + d2 * d2)) * t


# ----------------------------------------------------------------------------- 1-43
@part("1-43", "Top steering shaft bracket", "Aluminum")
def steering_shaft_bracket(s):
    """Sheet 04, 1-43 (scale 1:1.5): 1.5 thick aluminium, made with SolidCraft's sheet-metal tools
    from the drawn flat pattern: an R7.5 end round a Ø4 hole, 15 wide, a tab with a second Ø4
    hole (21.6 along, 8.5 up), a 45 deg corner, and a fold of 46 deg (134 deg between the legs)
    at the tab. Flat pattern on the XY plane, the first hole on the origin; the tab folds down (-Z).
    The fold line sits 0.43 past the drawn one (at the tab's step): SolidCraft needs the bend
    zone clear of the step's corner."""
    T = s.param("ssb_t", 1.5, "thickness")
    R = s.param("ssb_end_r", 7.5, "end radius (15 wide)")
    XF = s.param("ssb_fold_x", 15.2, "fold line (drawn)")
    XT = s.param("ssb_tab_w", 11.4, "tab width")
    YT = s.param("ssb_tab_top", 13, "tab top (8.5 + 4.5)")
    XC = s.param("ssb_corner_x", 17.5, "45 deg corner starts")
    H2 = s.param("ssb_hole2", 21.6, "second hole, along")
    Y2 = s.param("ssb_hole2_y", 8.5, "second hole, up")
    DH = s.param("ssb_hole_d", 4, "holes")
    A = s.param("ssb_fold_angle", 46, "fold angle (180 - 134)", unit="deg")
    RB = s.param("ssb_bend_r", 0.2, "bend radius (sharp on the drawing)")
    xe = XF + XT
    s.cmd("sheet.manage_rules", name="Lanz 1.5", thickness=f"{T} mm", k_factor="0.5", bend_radius=f"{RB} mm",
          active=True)
    s.sketch("Flat pattern", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    pts = [(0, -R), (XC, -R), (xe, -R + (xe - XC)), (xe, YT), (XF, YT), (XF, R), (0, R)]
    s.cmd("sketch.line", points=[list(p) for p in pts])
    s.cmd("sketch.arc.center_point", center=[0, 0], start=[0, R], end=[0, -R])
    s.finish()
    s.cmd("sheet.flange", base="Flat pattern", body_name=s.body)
    s.holes("Holes", (0, 0, T), (0, 0, -1), [(0, 0, T), (H2, Y2, T)], DH)
    zone = (RB + 0.5 * T) * math.radians(A)
    xf = XF + zone / 2 + 0.05
    s.cmd("sheet.fold", points=[[xf, -R - 2, T], [xf, YT + 2, T]], angle=A, position="centerline",
          flip=True)
    s.cmd("browser.visibility", visible=False, items=["Flat pattern"])
    return (polygon_area(pts) + math.pi / 2 * R * R - 2 * math.pi / 4 * DH * DH) * T


# ----------------------------------------------------------------------------- 1-44
@part("1-44", "Accelerator bridge bracket", "Steel")
def accelerator_bridge_bracket(s):
    """Sheet 04, 1-44 (scale 1:1.5, vector lines): 2 thick M/S, sharp bends: a 60 x 14 top strip,
    an ear turned up at each end (12 wide, 12.5 high, R6 top, Ø4 hole and an M2 hole, Ø1.6) and a
    plate hanging from the strip's front edge, narrowing to two R4.5 lobes round Ø4 holes on R22 at
    45 deg, joined by an R17.5 arc. Strip top at Z = 0, X across (ears at X = ±28..30), the plate
    on Y = -2..0, the ears on Y = 0..12."""
    T = s.param("abb_t", 2, "thickness")
    HW = s.param("abb_half_w", 28, "centre to the ears' inside")
    D = s.param("abb_strip_d", 14, "strip depth (12 + 2)")
    EW = s.param("abb_ear_w", 12, "ear width")
    EH = s.param("abb_ear_h", 12.5, "ear height above the strip")
    ZA = s.param("abb_arc_z", 32.2, "R17.5 / R22 centre below the strip top (measured)")
    RA = s.param("abb_arc_r", 17.5, "concave arc")
    PCR = s.param("abb_pcr", 22, "holes on R22 at 45 deg")
    RL = s.param("abb_lobe_r", 4.5, "lobe radius")
    DH = s.param("abb_hole_d", 4, "holes")
    ZM = s.param("abb_m2_z", 1.93, "M2 hole above the strip top (measured)")
    W = HW + T
    # strip
    s.sketch("Strip", (0, 0, -T), (1, 0, 0), (0, 1, 0))
    s.polyline([(-W, -T), (W, -T), (W, D - T), (-W, D - T)])
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Strip", body_name=s.body)
    # ears: profile in (y, z), from inside the strip up to the R6 top
    re = EW / 2
    ear_start = (0, -1)
    ear = [("line", (EW, -1)), ("line", (EW, EH - re)), ("arc", (re, EH - re), (0, EH - re), True), ("line", ear_start)]
    for x0, name in ((HW, "Ear R"), (-W, "Ear L")):
        s.sketch(name, (x0, 0, 0), (0, 1, 0), (0, 0, 1))      # normal +X
        s.loop(ear_start, ear)
        s.finish()
        s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name=name)
    # plate: outline in (x, z), from inside the strip down to the lobes
    zc = -ZA
    hx = PCR * math.sin(math.pi / 4)
    cl, cr = (-hx, zc + hx), (hx, zc + hx)
    a = (-HW, -T)
    dx, dz = cl[0] - a[0], cl[1] - a[1]
    dd = math.hypot(dx, dz)
    ang = math.atan2(dz, dx) - math.asin(RL / dd)        # the outer tangent from the corner
    tl = (a[0] + math.sqrt(dd * dd - RL * RL) * math.cos(ang), a[1] + math.sqrt(dd * dd - RL * RL) * math.sin(ang))
    m = lambda p: (-p[0], p[1])
    pl = (RA * math.cos(math.radians(135)), zc + RA * math.sin(math.radians(135)))
    start = (-HW, -T / 2)
    segs = [("line", a), ("line", tl), ("arc", cl, pl, True), ("arc", (0, zc), m(pl), False),
            ("arc", cr, m(tl), True), ("line", m(a)), ("line", m(start)), ("line", start)]
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Plate")   # toward -Y
    s.holes("Ear holes", (W, 0, 0), (-1, 0, 0), [(W, re, EH - re)], DH)
    s.holes("Ear M2 holes", (W, 0, 0), (-1, 0, 0), [(W, re, ZM)], 1.6)
    s.holes("Plate holes", (0, 1, 0), (0, -1, 0), [(cl[0], 1, cl[1]), (cr[0], 1, cr[1])], DH)
    ear_area = EW * (EH - re) + math.pi / 2 * re * re - math.pi / 4 * (DH * DH + 1.6 ** 2)
    plate = loop_area(start, segs) - 2 * HW * T / 2 - 2 * math.pi / 4 * DH * DH
    return 2 * W * D * T + 2 * ear_area * T + plate * T


# ----------------------------------------------------------------------------- 1-45
@part("1-45", "Accelerator lever-1 guide plate", "Steel")
def guide_plate(s):
    """Sheet 04, 1-45 (scale 1:1.5): 2 thick M/S sector: R22 top arc about the Ø4 pivot (origin),
    flanks at 30 deg to the centre line tangent to an R7 round about a Ø2 countersunk hole 4.5 below
    the pivot (countersink not modelled), R3 corners; a 4 wide slot on R18 over ±30 deg (R2 ends).
    On the XY plane, the arc toward +Y, Z = 0..2."""
    T = s.param("gp_t", 2, "thickness")
    R1 = s.param("gp_r_top", 22, "top arc radius")
    RB = s.param("gp_r_bottom", 7, "bottom round radius")
    YB = s.param("gp_bottom_y", 4.5, "bottom round centre below the pivot")
    RF = s.param("gp_r_corner", 3, "corner radius")
    A = math.radians(s.param("gp_flank", 30, "flank angle to the centre line", unit="deg"))
    RS = s.param("gp_slot_r", 18, "slot centre radius")
    WS = s.param("gp_slot_w", 4, "slot width")
    AS = math.radians(s.param("gp_slot_a", 30, "slot half angle", unit="deg"))
    c2 = (0, -YB)
    nL, wL = (-math.cos(A), -math.sin(A)), (-math.sin(A), math.cos(A))
    base = (c2[0] + (RB - RF) * nL[0], c2[1] + (RB - RF) * nL[1])
    bw = base[0] * wL[0] + base[1] * wL[1]
    sd = -bw + math.sqrt(bw * bw - (base[0] ** 2 + base[1] ** 2 - (R1 - RF) ** 2))
    cL = (base[0] + sd * wL[0], base[1] + sd * wL[1])
    t1L = (cL[0] + RF * nL[0], cL[1] + RF * nL[1])
    t2L = (cL[0] * R1 / (R1 - RF), cL[1] * R1 / (R1 - RF))
    pL = (c2[0] + RB * nL[0], c2[1] + RB * nL[1])
    m = lambda p: (-p[0], p[1])
    segs = [("arc", c2, m(pL), True), ("line", m(t1L)), ("arc", m(cL), m(t2L), True),
            ("arc", (0, 0), t2L, True), ("arc", cL, t1L, True), ("line", pL)]
    pol = lambda r, a: (r * math.sin(a), r * math.cos(a))      # angle from +Y, positive toward +X
    ro, ri = RS + WS / 2, RS - WS / 2
    sseg = [("arc", (0, 0), pol(ri, AS), False), ("arc", pol(RS, AS), pol(ro, AS), True),
            ("arc", (0, 0), pol(ro, -AS), True), ("arc", pol(RS, -AS), pol(ri, -AS), True)]
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(pL, segs)
    s.loop(pol(ri, -AS), sseg)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=4)
    s.cmd("sketch.circle.center", center=list(c2), diameter=2)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [0, 10]}], name="Plate", body_name=s.body)
    return (loop_area(pL, segs) - loop_area(pol(ri, -AS), sseg) - math.pi / 4 * (16 + 4)) * T


# ----------------------------------------------------------------------------- 1-46
@part("1-46", "Accelerator bridge shaft", "Steel")
def bridge_shaft(s):
    """Sheet 04, 1-46 (scale 1:2): Ø4 x 65.5, M3 tapped 10 deep at both ends (Ø2.5). Axis = Z."""
    D = s.param("bs_d", 4, "diameter")
    L = s.param("bs_l", 65.5, "length")
    TD = s.param("bs_tap_depth", 10, "M3 depth")
    v = s.turned("Shaft", [(0, 0), (D / 2, 0), (D / 2, L), (0, L)])
    s.holes("M3 tapped end 1", (0, 0, 0), (0, 0, 1), [(0, 0, 0)], 2.5, TD)
    s.holes("M3 tapped end 2", (0, 0, L), (0, 0, -1), [(0, 0, L)], 2.5, TD)
    return v - 2 * math.pi / 4 * 2.5 ** 2 * TD


# ----------------------------------------------------------------------------- 1-47, 1-48
@part("1-47", "Accelerator lever-1", "Steel")
def lever_1(s):
    """Sheet 04, 1-47: 2 thick M/S link, R4 ends 25 apart, M3 tapped (Ø2.5) at the origin end and
    Ø3 at the other, on X."""
    C = s.param("l1_centres", 25, "hole centres")
    return link(s, C, 4, 4, 2.5, 3, 2)


@part("1-48", "Accelerator lever-2", "Steel")
def lever_2(s):
    """Sheet 04, 1-48 ("refer to part 1-47 for all other dimension details"): as 1-47 with the
    holes 18 apart."""
    C = s.param("l2_centres", 18, "hole centres")
    return link(s, C, 4, 4, 2.5, 3, 2)


# ----------------------------------------------------------------------------- 1-49
@part("1-49", "Accelerator lever-3", {"lever": "Steel", "hub": "Brass"})
def lever_3(s):
    """Sheet 04, 1-49: a 2 thick M/S lever (R6 end round the Ø8 hole at the origin, R4 end with
    an M3 hole (Ø2.5) 18 along X) with a brass hub pressed into the Ø8 hole: Ø8 spigot through the
    lever, Ø12 x 6 collar on Z = 2..8, Ø4 bore (the 1-46 shaft) and an M3 grub screw hole 3 above
    the lever, on -X."""
    C = s.param("l3_centres", 18, "hole centres")
    DC = s.param("l3_hub_d", 12, "hub collar")
    LC = s.param("l3_hub_l", 6, "hub collar length")
    DS = s.param("l3_spigot_d", 8, "hub spigot, 8PF")
    DB = s.param("l3_bore", 4, "hub bore")
    ZG = s.param("l3_grub_z", 3, "M3 grub screw above the lever")
    n = s.body.split()[0]
    v = link(s, C, 6, 4, DS, 2.5, 2, body=f"{n} lever", name="Lever")
    v += s.turned("Hub", [(DB / 2, 0), (DS / 2, 0), (DS / 2, 2), (DC / 2, 2), (DC / 2, 2 + LC), (DB / 2, 2 + LC)],
                  body=f"{n} hub")
    s.holes("M3 grub tapped", (-DC / 2, 0, 0), (1, 0, 0), [(-DC / 2, 0, 2 + ZG)], 2.5, (DC - DB) / 2 + 1,
            target=f"{n} hub")
    return v - radial_hole(2.5, DC / 2, DB / 2)


# ----------------------------------------------------------------------------- 1-50, 1-52
@part("1-50", "Accelerator lever-1 spring bolt", "Steel")
def spring_bolt(s):
    """Sheet 04, 1-50: M3 x 4 (at Ø3), Ø4 x 6 shank, Ø6 x 1.5 head (its screwdriver slot not
    modelled). Axis = Z from the thread end."""
    return s.turned("Bolt", [(0, 0), (1.5, 0), (1.5, 4), (2, 4), (2, 10), (3, 10), (3, 11.5), (0, 11.5)])


@part("1-52", "Accelerator levers bolt", "Steel")
def levers_bolt(s):
    """Sheet 04, 1-52 (scale 1:1, vector lines): M3 x 2.5 (at Ø3), Ø4 x 2.1 shoulder, Ø8 x 1.5 head
    (its screwdriver slot not modelled). Axis = Z from the thread end."""
    return s.turned("Bolt", [(0, 0), (1.5, 0), (1.5, 2.5), (2, 2.5), (2, 4.6), (4, 4.6), (4, 6.1), (0, 6.1)])


# ----------------------------------------------------------------------------- 1-53
@part("1-53", "Accelerator crank", "Steel")
def accelerator_crank(s):
    """Sheet 04, 1-53 (scale 1:1.5; the part is not in the parts list on sheet 02, the name is
    ours): Ø5 M/S rod, 27.5 from its end to the centre of the drop, bent down R3.5 inside (R6 on
    the centre line), a 30 drop between centre lines (35 overall), bent R3.5 on the centre line
    into a Ø12 x 3 collar and a Ø5 x 6 stub (12.5 from the drop's centre line). In the XZ plane:
    the top leg on Z = 0 from X = -27.5, the drop on X = 0."""
    D = s.param("ac_d", 5, "rod")
    L1 = s.param("ac_top", 27.5, "end to the drop's centre line")
    H = s.param("ac_drop", 30, "drop between centre lines (35 - 5)")
    R1 = s.param("ac_r1", 6, "top bend, centre line (R3.5 inside)")
    R2 = s.param("ac_r2", 3.5, "bottom bend, centre line (to the collar)")
    DC = s.param("ac_collar_d", 12, "collar")
    TC = s.param("ac_collar_t", 3, "collar thickness")
    LS = s.param("ac_stub", 6, "stub length")
    s.sketch("Path", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.line", points=[[-L1, 0], [-R1, 0]])                                    # l1
    s.cmd("sketch.arc.center_point", center=[-R1, -R1], start=[0, -R1], end=[-R1, 0])       # a1
    s.cmd("sketch.line", points=[[0, -R1], [0, -H + R2]])                                   # l2
    s.cmd("sketch.arc.center_point", center=[R2, -H + R2], start=[0, -H + R2], end=[R2, -H])  # a2
    s.cmd("sketch.line", points=[[R2, -H], [R2 + TC + LS, -H]])                             # l3
    s.finish()
    # the rod runs on through the collar to the end of the stub; the collar is pressed on
    s.cmd("solid.pipe", path_sketch="Path", path=["l1", "a1", "l2", "a2", "l3"], diameter=D, name="Rod",
          body_name=s.body)
    s.cmd("solid.cylinder", diameter=DC, height=TC, base=[R2, 0, -H], axis=[1, 0, 0], operation="join",
          targets=[s.body], name="Collar")
    length = (L1 - R1) + math.pi / 2 * R1 + (H - R1 - R2) + math.pi / 2 * R2 + TC + LS
    return math.pi / 4 * (D * D * length + (DC * DC - D * D) * TC)


# ----------------------------------------------------------------------------- 1-51
# a 0.5 wire: its measured volume (from a tessellation) is good to about 0.5 %
@part("1-51", "Accelerator lever-1 spring", "Steel", tol=0.01)
def lever_spring(s):
    """Sheet 04, 1-51: compression spring (spring steel), Ø5 outside, Ø4 inside (0.5 wire),
    7 long uncompressed (3 installed); 5 turns (counted on the drawing). Modelled uncompressed,
    plain ends. Axis = Z from Z = 0."""
    DO = s.param("sp_od", 5, "outside diameter")
    DW = s.param("sp_wire", 0.5, "wire diameter ((5 - 4) / 2)")
    L = s.param("sp_free_l", 7, "free length")
    N = s.param("sp_turns", 5, "turns", unit="")
    dm = DO - DW
    s.cmd("solid.coil", diameter=dm, turns=N, height=L - DW, section_size=DW, section="circular",
          section_position="center", base=[0, 0, DW / 2], name="Spring", body_name=s.body)
    return math.pi / 4 * DW * DW * N * math.hypot(math.pi * dm, (L - DW) / N)


def flame_protector(s, mirror):
    """1-40 and its mirror image 1-41 (sheet 04, flat pattern at 1:1.5, read with the vector lines):
    1.5 thick brass, perforated with 26 x Ø3.5 at 6 pitch, folded sharp so that the legs make 78 deg.
    Flat-pattern coordinates (X, Y) about the centre of the R28 end; the fold line is X = 9.8
    (13.5 + 10 + 6.6 from the left edge). The perforated leg lies on Z = 0..1.5; the R28 leg (2 x Ø4
    on R22 at 45 deg) turns up about the fold line on the top face. 1-41 is mirrored in Y."""
    T = s.param("fp_t", 1.5, "thickness")
    XF = s.param("fp_fold_x", 9.8, "fold line")
    ANG = s.param("fp_angle", 78, "angle between the legs", unit="deg")
    R = s.param("fp_r", 28, "end radius (about the R22 hole circle's centre)")
    DH = s.param("fp_perf_d", 3.5, "perforations")
    P = s.param("fp_pitch", 6, "perforation pitch")
    DB = s.param("fp_hole_d", 4, "holes on R22 at 45 deg")
    sy = -1 if mirror else 1
    phi = math.radians(180 - ANG)
    d = (math.cos(phi), 0, math.sin(phi))                  # the folded leg runs this way from the fold
    nout = (math.sin(phi), 0, -math.cos(phi))              # and is T thick this way
    # the bent strip's cross-section (flat leg, sharp mitred corner, folded leg) extruded across
    # the part's width, then each leg trimmed to its outline (joining separate legs fails in
    # SolidCraft where their faces meet)
    L = R - XF                                             # folded leg length to the end of the R28
    po = (XF + T * nout[0], T + T * nout[2])               # outer edge of the folded leg at the fold
    k = -po[1] / d[2]
    q = (po[0] + k * d[0], 0)                              # the sharp outer corner
    sect = [(-20.3, 0), q, (po[0] + L * d[0], po[1] + L * d[2]), (XF + L * d[0], T + L * d[2]), (XF, T), (-20.3, T)]
    y0, y1 = (-26, 24) if not mirror else (-24, 26)
    s.sketch("Bent section", (0, y1, 0), (1, 0, 0), (0, 0, 1))      # normal -Y
    s.polyline(sect)
    s.finish()
    s.cmd("solid.extrude", distance=y1 - y0, name="Bent strip", body_name=s.body)
    # perforations in the flat leg (before the trims: after them SolidCraft fails to mesh a face)
    # rows of 5, 5, 5, 5, 4 and 2 (the last ones right-aligned), the first column 4 from the edge
    cols = [-16.3 + P * i for i in range(5)]
    grid = [(cols[i], 7 - P * j) for j, n in enumerate((5, 5, 5, 5, 4, 2)) for i in range(5 - n, 5)]
    s.holes("Perforations", (0, 0, T), (0, 0, -1), [(x, sy * y, T) for x, y in grid], DH)
    # flat leg outline (cut down from its top face)
    for name, poly in (("Trim top left", [(-21, 8.5), (-20.3, 8.5), (-6.8, 11), (-6.8, 25), (-21, 25)]),
                       ("Trim notch", [(3.2, 11), (XF, 11), (XF, 25), (3.2, 25)]),
                       ("Trim bottom left", [(-21, -15.4), (-20.3, -15.4), (3.7, -26), (3.7, -27), (-21, -27)])):
        s.cut_poly(name, (0, 0, T), (0, 0, -1), [(x, sy * y, T) for x, y in poly], T)
    # beside the tab (Y 11..24) neither the flat leg nor the corner exists: cut both away, up to
    # the folded leg's end face
    ycut = [(XF, T), po, (po[0] - 3 * d[0], po[1] - 3 * d[2]), (XF - 1, po[1] - 3 * d[2]), (XF - 1, T)]
    yc0, yc1 = (11, 25) if not mirror else (-25, -11)
    s.sketch("Trim beside the tab", (0, yc1, 0), (1, 0, 0), (0, 0, 1))
    s.polyline(ycut)
    s.finish()
    s.cmd("solid.extrude", distance=yc1 - yc0, operation="cut", targets=[s.body], name="Trim beside the tab")
    # folded leg outline: the R28 end (cut along the leg's thickness from its inner face)
    x0, x1 = math.sqrt(R * R - 26 * 26), math.sqrt(R * R - 24 * 24)
    s.sketch("Trim R28", (XF, 0, T), d, (0, 1, 0))                    # normal = -nout
    # (a rectangle less the whole R28 circle: its edge crosses the strip's ends at an angle;
    # outlines that met the ends exactly left a face behind or cut wrongly)
    s.polyline([(0.3, -30), (L + 1, -30), (L + 1, 30), (0.3, 30)])
    s.cmd("sketch.circle.center", center=[-XF, 0], diameter=2 * R)
    s.finish()
    s.cmd("solid.extrude", distance=T + 1, direction="negative", operation="cut", targets=[s.body],
          profiles=[{"point": [L + 0.5, 29]}], name="Trim R28")
    A = [(-20.3, -15.4), (3.7, -26), (XF, -26), (XF, 11), (3.2, 11), (3.2, 24), (-6.8, 24), (-6.8, 11), (-20.3, 8.5)]
    bstart = (0, -26)
    bsegs = [("line", (x0 - XF, -26)), ("arc", (-XF, 0), (x1 - XF, 24), True), ("line", (0, 24)), ("line", bstart)]
    ylo, yhi = -26, 11
    h = 22 * math.sin(math.pi / 4)
    pts = [(XF + (h - XF) * d[0], yy, T + (h - XF) * d[2]) for yy in (h, -h)]
    s.holes("Holes", (XF, 0, T), nout, pts, DB)
    wedge_exact = polygon_area([(XF, T), (XF, 0), q, po])
    return (polygon_area(A) + loop_area(bstart, bsegs) - (len(grid) * DH * DH + 2 * DB * DB) * math.pi / 4) * T \
        + wedge_exact * (yhi - ylo)


@part("1-40", "LH-flame protector", "Brass")
def flame_protector_lh(s):
    """Sheet 04, 1-40: see flame_protector()."""
    return flame_protector(s, False)


@part("1-41", "RH-flame protector", "Brass")
def flame_protector_rh(s):
    """Sheet 04, 1-41: the mirror image of 1-40; see flame_protector()."""
    return flame_protector(s, True)


# ----------------------------------------------------------------------------- 1-42
@part("1-42", "Front flame guard", {"guard": "Brass", "rod": "Steel"})
def front_flame_guard(s):
    """Sheet 04, 1-42 (scale 1:1, vector lines): 0.5 thick brass, 28 wide, perforated with 2 x 2
    square holes at 3 pitch (9 across, 1 from the edges), folded so that its 26 and 10 legs make
    105 deg; an M/S rod Ø1.5 x 34 along the end of the short leg. Made with SolidCraft's sheet-
    metal tools: flat pattern on the XY plane (X across, the long leg from Y = 0), fold at Y = 26
    (bend radius 0.2, K-factor 0.5). The long leg has 8 rows of holes (2 clear of the fold, as
    drawn); the short leg's holes are not dimensioned: 2 rows assumed."""
    T = s.param("ffg_t", 0.5, "thickness")
    W = s.param("ffg_w", 28, "width")
    L1 = s.param("ffg_long", 26, "long leg")
    L2 = s.param("ffg_short", 10, "short leg")
    A = s.param("ffg_angle", 105, "angle between the legs", unit="deg")
    SQ = s.param("ffg_sq", 2, "square holes")
    P = s.param("ffg_pitch", 3, "hole pitch")
    DR = s.param("ffg_rod_d", 1.5, "rod")
    LR = s.param("ffg_rod_l", 34, "rod length")
    n = s.body.split()[0]
    guard = f"{n} guard"
    s.cmd("sheet.manage_rules", name="Lanz 0.5", thickness=f"{T} mm", k_factor="0.5", bend_radius="0.2 mm",
          active=True)
    s.sketch("Flat pattern", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline([(-W / 2, 0), (W / 2, 0), (W / 2, L1 + L2), (-W / 2, L1 + L2)])
    s.finish()
    s.cmd("sheet.flange", base="Flat pattern", body_name=guard)
    rows = [1 + P * j for j in range(8)] + [L1 + 2 + P * j for j in range(2)]
    cols = [-W / 2 + 1 + P * i for i in range(9)]
    s.sketch("Perforations", (0, 0, T), (1, 0, 0), (0, 1, 0))
    for y in rows:
        for x in cols:
            s.cmd("sketch.rectangle.two_point", p0=[x, y], p1=[x + SQ, y + SQ])
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", operation="cut", targets=[guard], name="Perforations")
    s.cmd("sheet.fold", points=[[-W / 2 - 2, L1, T], [W / 2 + 2, L1, T]], angle=180 - A, position="centerline",
          body=guard)
    s.cmd("browser.visibility", visible=False, items=["Flat pattern"])
    # the rod along the end of the short leg (the leg turns up toward +Z about Y = 26)
    a = math.radians(180 - A)
    end = (L1 + L2 * math.cos(a), L2 * math.sin(a))      # the leg's end, near enough for the rod
    c = (end[0] + DR / 2 * math.cos(a), end[1] + DR / 2 * math.sin(a))
    s.cmd("solid.cylinder", diameter=DR, height=LR, base=[-LR / 2, round(c[0], 4), round(c[1], 4)], axis="X",
          operation="new", name="Rod", body_name=f"{n} rod")
    return (W * (L1 + L2) - len(rows) * len(cols) * SQ * SQ) * T + math.pi / 4 * DR * DR * LR


# ----------------------------------------------------------------------------- 1-34
# a Ø1 wire: its measured volume (from a tessellation) is good to about 0.5 %
@part("1-34", "Motor rocking arm valve spring", "Steel", tol=0.01)
def valve_spring(s):
    """Sheet 03, 1-34 (scale 1:2): Ø1 spring-steel wire bent to R150 from an eye (Ø4 inside) to a
    free end 86 along and 30.5 down, flat at the free end. The eye is modelled as 300 deg of a
    Ø5 (centre line) loop, tangent to the R150 bend. In the XZ plane, the R150 bend starting at
    the origin."""
    DW = s.param("vs_wire", 1, "wire diameter")
    R = s.param("vs_r", 150, "bend radius")
    DX = s.param("vs_dx", 86, "eye to free end, along")
    DZ = s.param("vs_dz", 30.5, "eye to free end, down")
    DE = s.param("vs_eye_d", 4, "eye, inside")
    re = (DE + DW) / 2
    ch = math.hypot(DX, DZ)
    u = (DX / ch, -DZ / ch)
    nrm = (-u[1], u[0])
    h = math.sqrt(R * R - ch * ch / 4)
    c = (DX / 2 + h * nrm[0], -DZ / 2 + h * nrm[1])         # the bend's centre (above the wire)
    r0 = (-c[0] / R, -c[1] / R)                            # radius direction at the start
    t0 = (-r0[1], r0[0])                                   # the wire's direction at the start
    ce = (re * -t0[1], re * t0[0])                         # the eye's centre, beside the start
    ts = math.atan2(-ce[1], -ce[0])
    p0 = (ce[0] + re * math.cos(ts - math.radians(300)), ce[1] + re * math.sin(ts - math.radians(300)))
    rnd = lambda p: [round(p[0], 6), round(p[1], 6)]
    s.sketch("Wire path", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.arc.center_point", center=rnd(ce), start=rnd(p0), end=[0, 0])     # a1: the eye
    s.cmd("sketch.arc.center_point", center=rnd(c), start=[0, 0], end=[DX, -DZ])    # a2: the R150 bend
    s.finish()
    # two pipes: one solid.pipe along both arcs comes out inside out (negative volume)
    s.cmd("solid.pipe", path_sketch="Wire path", path=["a2"], diameter=DW, name="Wire", body_name=s.body)
    s.cmd("solid.pipe", path_sketch="Wire path", path=["a1"], diameter=DW, operation="join", targets=[s.body],
          name="Eye")
    length = R * 2 * math.asin(ch / (2 * R)) + re * math.radians(300)
    return math.pi / 4 * DW * DW * length


def slot_loop(c1, c2, r):
    """A closed slot (two R ends joined by tangents) between centres c1 and c2, as Script.loop()
    arguments."""
    dx, dy = c2[0] - c1[0], c2[1] - c1[1]
    L = math.hypot(dx, dy)
    n = (-dy / L * r, dx / L * r)
    a1, b1 = (c1[0] - n[0], c1[1] - n[1]), (c2[0] - n[0], c2[1] - n[1])
    b2, a2 = (c2[0] + n[0], c2[1] + n[1]), (c1[0] + n[0], c1[1] + n[1])
    return a1, [("line", b1), ("arc", c2, b2, True), ("line", a2), ("arc", c1, a1, True)]


def countersink(s, name, x, y, z0, d, dcs, up, through):
    """A Ø d hole with a 90 deg countersink to Ø dcs at the face Z = z0, drilled up (+Z) or down,
    `through` deep: a revolve cut about the hole's axis."""
    h = (dcs - d) / 2
    sg = 1 if up else -1
    s.sketch(name, (x, y, z0), (1, 0, 0), (0, 0, sg))
    s.polyline([(0, -1), (dcs / 2 + 1, -1), (dcs / 2, 0), (d / 2, h), (d / 2, through + 1), (0, through + 1)])
    s.finish()
    s.cmd("solid.revolve", axis="y", operation="cut", targets=[s.body], name=name)
    return math.pi / 12 * h * (dcs * dcs + dcs * d + d * d) + math.pi / 4 * d * d * (through - h)


# ----------------------------------------------------------------------------- 2-01
@part("2-01", "Chassis front end", "Aluminum")
def chassis_front_end(s):
    """Sheet 04, 2-01 (scale 1:1.5, vector lines; detail "A" is drawn from below): 6 thick plate,
    254 x 88 with a pointed front end, a 102 x 46 window with R4 corners, two slots, Ø4 holes (A),
    M4 tapped holes (B, Ø3.3), 4 x Ø6 countersunk Ø12 from underneath (C) and an 8 wide slot
    recess 3 deep in the underside (detail A). X from the point backward, Y across, Z = 0..6.
    Material not given on the drawing: aluminium assumed (its 3D view is shaded like the other
    aluminium parts)."""
    T = s.param("cfe_t", 6, "thickness")
    L = s.param("cfe_l", 254, "length")
    H = s.param("cfe_half_w", 44, "half width (88)")
    XN = s.param("cfe_nose", 34.5, "length of the pointed end")
    W0, W1, WH = 34.5, 136.5, 23                 # window X from, to; half height
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline([(0, 0), (XN, -H), (L, -H), (L, H), (XN, H)])
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Plate", body_name=s.body)
    v = (L - XN) * 2 * H * T + XN * H * T
    # window, through
    rw = 4
    start = (W0 + rw, -WH)
    segs = [("line", (W1 - rw, -WH)), ("arc", (W1 - rw, -WH + rw), (W1, -WH + rw), True), ("line", (W1, WH - rw)),
            ("arc", (W1 - rw, WH - rw), (W1 - rw, WH), True), ("line", (W0 + rw, WH)),
            ("arc", (W0 + rw, WH - rw), (W0, WH - rw), True), ("line", (W0, -WH + rw)),
            ("arc", (W0 + rw, -WH + rw), start, True)]
    s.sketch("Window", (0, 0, T), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", operation="cut", targets=[s.body], name="Window")
    v -= loop_area(start, segs) * T
    # slots, through
    s.sketch("Slots", (0, 0, T), (1, 0, 0), (0, 1, 0))
    sl = [slot_loop((108, -32), (120, -32), 2.5), slot_loop((197.5, -32), (233.5, -32), 4)]
    for a, sg in sl:
        s.loop(a, sg)
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", operation="cut", targets=[s.body], name="Slots")
    v -= sum(loop_area(a, sg) for a, sg in sl) * T
    A = [(61, 32), (61, -32), (131, 32), (131, -32), (142, 0), (144.5, -32), (186.5, 24), (186.5, -24),
         (221.5, 24), (240.5, -24)]
    B = [(34.5, 32), (34.5, -32), (13.5, 0)]
    s.holes("Holes A (Ø4)", (0, 0, T), (0, 0, -1), [(x, y, T) for x, y in A], 4)
    s.holes("Holes B (M4 tapped)", (0, 0, T), (0, 0, -1), [(x, y, T) for x, y in B], 3.3)
    v -= math.pi / 4 * (16 * len(A) + 3.3 ** 2 * len(B)) * T
    # detail A: the slot recess in the underside, then the four countersunk holes from below
    ra, rs = slot_loop((222, -8), (243, -8), 4)
    s.sketch("Recess", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(ra, rs)
    s.finish()
    s.cmd("solid.extrude", distance=3, operation="cut", targets=[s.body], name="Recess (detail A)")
    v -= loop_area(ra, rs) * 3
    C = [(164, 16), (164, -16), (236, 16), (236, -16)]
    for i, (x, y) in enumerate(C):
        v -= countersink(s, f"Hole C{i + 1} (Ø6, c'sunk below)", x, y, 0, 6, 12, True, T)
    # the recess and the countersink at (236, -16) overlap: add back their common part
    in_slot = lambda x, y: abs(y + 8) <= 4 and (222 <= x <= 243 or min(math.dist((x, y), (222, -8)),
                                                                        math.dist((x, y), (243, -8))) <= 4)
    v += integrate2(lambda x, y: min(3.0, max(0.0, 6 - math.dist((x, y), (236, -16))))
                    if in_slot(x, y) else 0.0, 230, 242, -22, -10, 600)
    return v


def angle_bracket(s, mirror):
    """2-03 and its mirror image 2-04 (sheet 04, scale 1:1.5/1:2, vector lines): 3.5 thick
    aluminium angle, 80 long: a 19.5 wide top flange (2 x M4 tapped, an R4.5 slot 22 between
    centres, all 10 from the leg's outer face) and a 33 deep leg narrowing with R4 corners to an
    R6 nose round a Ø6 hole (55 along, 27 down), with 2 x Ø2.5 holes 13 down. X along, the leg's
    outer face on Y = 0 (the flange toward +Y; 2-04: toward -Y), the flange top on Z = 0."""
    T = s.param("ab_t", 3.5, "thickness")
    L = s.param("ab_l", 80, "length (5 + 35 + 22 + 13 + 5)")
    F = s.param("ab_flange", 19.5, "flange width over the leg")
    XC, ZC, RN = 55, -27, 6                      # nose: Ø6 hole centre and radius
    RC = 4
    sy = -1 if mirror else 1
    # leg outline in (x, z): flanks tangent to the nose at the measured angles, R4 corners
    def flank(theta, side):
        u = (math.cos(theta), math.sin(theta))
        n = (u[1], -u[0])                                       # outward normal (below the line)
        t = (XC + RN * n[0], ZC + RN * n[1])                    # tangent point on the nose
        return u, n, t
    out = []
    for theta, x_edge, side in ((math.radians(-9.38), 0, -1), (math.radians(20.76), L, 1)):
        u, n, t = flank(theta, side)
        # corner centre: RC in from the edge X = x_edge, RC inside the flank line
        cx = x_edge + (RC if x_edge == 0 else -RC)
        # inside the flank: (C - t) . n = -RC  ->  solve for cz
        cz = t[1] + (-RC - (cx - t[0]) * n[0]) / n[1]
        out.append(((cx, cz), (cx + RC * n[0], cz + RC * n[1]), t))
    (cl, tl, nl), (cr, tr, nr) = out
    start = (0, 0)
    segs = [("line", (0, cl[1])), ("arc", cl, tl, True), ("line", nl), ("arc", (XC, ZC), nr, True),
            ("line", tr), ("arc", cr, (L, cr[1]), True), ("line", (L, 0)), ("line", start)]
    s.sketch("Leg", (0, 0, 0), (1, 0, 0), (0, 0, 1))                  # normal -Y
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative" if not mirror else "positive", name="Leg",
          body_name=s.body)
    s.sketch("Flange", (0, 0, -T), (1, 0, 0), (0, 1, 0))
    s.polyline([(0, sy * 1), (L, sy * 1), (L, sy * F), (0, sy * F)])
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Flange")
    v = (loop_area(start, segs) + (F - T) * L) * T
    s.holes("Flange M4 tapped", (0, 0, 0), (0, 0, -1), [(5, sy * 10, 0), (75, sy * 10, 0)], 3.3)
    a, sg = slot_loop((40, sy * 10), (62, sy * 10), 4.5)
    s.sketch("Flange slot", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(a, sg)
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", operation="cut", targets=[s.body], name="Flange slot")
    y0 = -1 if not mirror else 1
    s.holes("Leg holes", (0, y0, 0), (0, -y0, 0), [(7, y0, -13), (71, y0, -13)], 2.5)
    s.holes("Leg Ø6 hole", (0, y0, 0), (0, -y0, 0), [(XC, y0, ZC)], 6)
    v -= (2 * math.pi / 4 * 3.3 ** 2 + loop_area(a, sg)) * T + math.pi / 4 * (2 * 2.5 ** 2 + 36) * T
    return v


@part("2-03", "LH-steering and fuel tank bracket", "Aluminum")
def steering_bracket_lh(s):
    """Sheet 04, 2-03: see angle_bracket()."""
    return angle_bracket(s, False)


@part("2-04", "RH-steering and fuel tank bracket", "Aluminum")
def steering_bracket_rh(s):
    """Sheet 04, 2-04: the mirror image of 2-03; see angle_bracket()."""
    return angle_bracket(s, True)


# ----------------------------------------------------------------------------- 2-05
@part("2-05", "Steering floor bracket", "Aluminum")
def steering_floor_bracket(s):
    """Sheet 04, 2-05: 1.5 thick aluminium, made with the sheet-metal tools from its flat pattern:
    15 wide, an R7.5 end round a Ø4 hole (the origin), a second Ø4 hole 22 along, the square end 5
    beyond it (R1 corners, read from the drawing), folds 11.5 and 18 from the square end. The side
    view shows a Z: 90 deg at the first fold, about 45 deg (not dimensioned) at the second.
    Bend radius 0.2, K-factor 0.5."""
    T = s.param("sfb_t", 1.5, "thickness")
    R = s.param("sfb_end_r", 7.5, "end radius (15 wide)")
    X2 = s.param("sfb_hole2", 22, "second hole")
    XE = s.param("sfb_end", 27, "square end (22 + 5)")
    F1 = s.param("sfb_fold1", 27 - 11.5, "first fold, 11.5 from the square end")
    F2 = s.param("sfb_fold2", 27 - 11.5 - 6.5, "second fold, 6.5 further")
    A2 = s.param("sfb_angle2", 45, "second bend (drawn, not dimensioned)", unit="deg")
    rc = 1
    s.cmd("sheet.manage_rules", name="Lanz 1.5", thickness=f"{T} mm", k_factor="0.5", bend_radius="0.2 mm",
          active=True)
    start = (0, -R)
    segs = [("line", (XE - rc, -R)), ("arc", (XE - rc, -R + rc), (XE, -R + rc), True), ("line", (XE, R - rc)),
            ("arc", (XE - rc, R - rc), (XE - rc, R), True), ("line", (0, R)), ("arc", (0, 0), start, True)]
    s.sketch("Flat pattern", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("sheet.flange", base="Flat pattern", body_name=s.body)
    s.holes("Holes", (0, 0, T), (0, 0, -1), [(0, 0, T), (X2, 0, T)], 4)
    s.cmd("sheet.fold", points=[[F2, -R - 2, T], [F2, R + 2, T]], angle=A2, position="centerline")
    s.cmd("sheet.fold", points=[[F1, -R - 2, T], [F1, R + 2, T]], angle=90, position="centerline", flip=True)
    s.cmd("browser.visibility", visible=False, items=["Flat pattern"])
    return (loop_area(start, segs) - 2 * math.pi / 4 * 16) * T


def rounded_rect(w, h, r):
    """Script.loop() arguments for a w x h rectangle centred on the origin with corner radius r."""
    a, b = w / 2, h / 2
    start = (-a + r, -b)
    return start, [("line", (a - r, -b)), ("arc", (a - r, -b + r), (a, -b + r), True), ("line", (a, b - r)),
                   ("arc", (a - r, b - r), (a - r, b), True), ("line", (-a + r, b)),
                   ("arc", (-a + r, b - r), (-a, b - r), True), ("line", (-a, -b + r)),
                   ("arc", (-a + r, -b + r), start, True)]


def in_rounded_rect(y, z, w, h, r):
    a, b = w / 2 - r, h / 2 - r
    dy, dz = max(abs(y) - a, 0), max(abs(z) - b, 0)
    return (abs(y) <= w / 2 and abs(z) <= h / 2) and dy * dy + dz * dz <= r * r


# ----------------------------------------------------------------------------- 2-06
@part("2-06", "Fuel tank", "Brass")
def fuel_tank(s):
    """Sheet 04, 2-06 (scale 1:2, section F-F): soldered brass box: a 90 long tube, 40 x 30 outside
    with R2 corners and a 1 wall, closed by end plates made separately and soldered in 2 from each
    end (modelled 1 thick, flush with the tube's inside). In the top: a Ø11 hole for the 1-07 spout
    19 from one end, 2 x M3 (Ø2.5) 20 apart and 6 from the side for the 2-10 bracket; a Ø10 hole
    drilled at 45 deg through the top edge 58 from that end (the gear wheel of 2-12 runs in it).
    X along, Y across, Z up from the bottom; the drilled edge is on -Y."""
    L = s.param("ft_l", 90, "length")
    W = s.param("ft_w", 40, "width (20 + 20)")
    H = s.param("ft_h", 30, "height")
    T = s.param("ft_wall", 1, "wall")
    R = s.param("ft_r", 2, "outside corner radius (read from section F-F)")
    XE = s.param("ft_end_inset", 2, "end plates' inner faces from the tube ends")
    zc = H / 2
    so, go = rounded_rect(W, H, R)
    si, gi = rounded_rect(W - 2 * T, H - 2 * T, R - T)
    s.sketch("Tube section", (0, 0, zc), (0, 1, 0), (0, 0, 1))      # normal +X
    s.loop(so, go)
    s.loop(si, gi)
    s.finish()
    s.cmd("solid.extrude", distance=L, profiles=[{"point": [W / 2 - T / 2, 0]}], name="Tube", body_name=s.body)
    ai = loop_area(si, gi)
    v = (loop_area(so, go) - ai) * L
    # end plates: overlapping 0.3 into the wall so that they join (their faces would only touch)
    sp, gp = rounded_rect(W - 2 * T + 0.6, H - 2 * T + 0.6, R - T + 0.3)
    for x0, name in ((XE - 1, "End plate 1"), (L - XE, "End plate 2")):
        s.sketch(name, (x0, 0, zc), (0, 1, 0), (0, 0, 1))
        s.loop(sp, gp)
        s.finish()
        s.cmd("solid.extrude", distance=1, operation="join", targets=[s.body], name=name)
        v += ai * 1
    s.holes("Spout hole", (0, 0, H), (0, 0, -1), [(19, 0, H)], 11, 2 * T)
    s.holes("M3 tapped", (0, 0, H), (0, 0, -1), [(38, W / 2 - 6, H), (58, W / 2 - 6, H)], 2.5, 2 * T)
    v -= math.pi / 4 * (121 + 2 * 2.5 ** 2) * T
    # the Ø10 hole at 45 deg through the edge (top and -Y side meet at the sharp corner (y, z) = (-20, 30))
    d = (0, 1 / math.sqrt(2), -1 / math.sqrt(2))
    p0 = (58, -W / 2 - 3 * d[1], H - 3 * d[2])
    s.cmd("solid.cylinder", diameter=10, height=9, base=[p0[0], round(p0[1], 6), round(p0[2], 6)],
          axis=[0, round(d[1], 9), round(d[2], 9)], operation="cut", targets=[s.body], name="Edge hole")
    wall = lambda x, y, z: 0 <= x <= L and in_rounded_rect(y, z - zc, W, H, R) and not \
        in_rounded_rect(y, z - zc, W - 2 * T, H - 2 * T, R - T)
    return v - removed_by_cylinder(wall, p0, d, 10, 9, n=160)


# ----------------------------------------------------------------------------- 2-07
@part("2-07", "Fuel tank spout", "Brass")
def fuel_tank_spout(s):
    """Sheet 04, 2-07 (scale 1:1.5): a Ø10 x 31 tube with a Ø8 bore soldered into a Ø12 x 10 collar
    tapped M10 (Ø8.5) 6.5 deep (34.5 from the bottom) for the 2-08 cover. Axis = Z from the
    bottom of the tube."""
    D1 = s.param("fs_tube_d", 10, "tube (in the tank's Ø11 hole)")
    L1 = s.param("fs_tube_l", 31, "tube length")
    DB = s.param("fs_bore", 8, "bore")
    D2 = s.param("fs_collar_d", 12, "collar")
    L2 = s.param("fs_collar_l", 10, "collar length")
    ZT = s.param("fs_thread_from", 34.5, "M10 from here to the top (tap drill Ø8.5)")
    return s.turned("Spout", [(DB / 2, 0), (D1 / 2, 0), (D1 / 2, L1), (D2 / 2, L1), (D2 / 2, L1 + L2),
                              (4.25, L1 + L2), (4.25, ZT), (DB / 2, ZT)])


# ----------------------------------------------------------------------------- 2-08, 2-09
@part("2-08", "Fuel tank spout cover", "Brass")
def spout_cover(s):
    """Sheet 04, 2-08: M10 x 7 (at Ø10), Ø12 x 2 collar, Ø10 x 2 neck, 12 hex x 3, Ø4 vent through.
    Axis = Z from the thread end."""
    AF = s.param("sc_hex_af", 12, "hex across flats")
    TH = s.param("sc_hex_t", 3, "hex thickness")
    LT = s.param("sc_thread_l", 7, "M10 length")
    s.turned("Body", [(0, 0), (5, 0), (5, LT), (6, LT), (6, LT + 2), (5, LT + 2), (5, LT + 4.5), (0, LT + 4.5)])
    s.sketch("Hex", (0, 0, LT + 4), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=TH, operation="join", targets=[s.body], name="Hex")
    s.holes("Vent", (0, 0, LT + 4 + TH), (0, 0, -1), [(0, 0, LT + 4 + TH)], 4)
    v = math.pi / 4 * (100 * LT + 144 * 2 + 100 * 2) + math.sqrt(3) / 2 * AF * AF * TH
    return v - math.pi / 4 * 16 * (LT + 4 + TH)


@part("2-09", "Fuel tank inner wick holding pipe", "Brass")
def wick_pipe(s):
    """Sheet 04, 2-09 (scale 1:2): Ø12 x 26 tube on a Ø11 x 4 spigot (into the tank's Ø11 hole),
    Ø9 bore through. Axis = Z from the spigot end."""
    return s.turned("Pipe", [(4.5, 0), (5.5, 0), (5.5, 4), (6, 4), (6, 30), (4.5, 30)])


# ----------------------------------------------------------------------------- 2-10
@part("2-10", "Fuel tank gear wheel axle bracket", "Brass")
def gear_axle_bracket(s):
    """Sheet 04, 2-10 (scale 1:1.5): a 1 thick brass U, 42 long and 10 wide, walls 18 high inside
    ending in R5 ears with Ø4 holes (the 2-12 shaft), soldered on a 34 x 10 x 7 block (5 from one
    end) with 2 x Ø3 holes 20 apart (12 from the other end) for the M3 screws into the tank.
    X along, Y across, Z up; the U's base on Z = 0..1, the block under it."""
    T = s.param("gab_t", 1, "sheet thickness")
    L = s.param("gab_l", 42, "length outside")
    W = s.param("gab_w", 10, "width")
    HW = s.param("gab_wall", 18, "wall height above the base")
    RE = s.param("gab_ear_r", 5, "ear radius (Ø4 holes at its centre)")
    s.sketch("U section", (0, 0, 0), (1, 0, 0), (0, 0, 1))                 # normal -Y
    s.polyline([(0, 0), (L, 0), (L, T + HW), (L - T, T + HW), (L - T, T), (T, T), (T, T + HW), (0, T + HW)])
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="U", body_name=s.body)
    v = (L * T + 2 * T * HW) * W
    # round the walls' tops: cut the corners above the ear centres outside R5 (both walls at once)
    zc = T + HW - RE
    s.sketch("Ear rounding", (-1, 0, 0), (0, 1, 0), (0, 0, 1))         # normal +X; sketch (y, z)
    for sy in (1, -1):
        p0, p1 = (sy * RE, zc), (0, zc + RE)
        s.loop(p0, [("arc", (0, zc), p1, sy > 0), ("line", (0, zc + RE + 1)), ("line", (sy * (RE + 1), zc + RE + 1)),
                    ("line", (sy * (RE + 1), zc)), ("line", p0)])
    s.finish()
    s.cmd("solid.extrude", through_all=True, operation="cut", targets=[s.body], name="Ear rounding")
    v -= 2 * T * 2 * (RE * RE - math.pi / 4 * RE * RE)
    s.holes("Ear holes", (-1, 0, 0), (1, 0, 0), [(-1, 0, zc)], 4)
    v -= 2 * math.pi / 4 * 16 * T
    s.sketch("Block", (0, 0, -7), (1, 0, 0), (0, 1, 0))
    s.polyline([(5, -W / 2), (39, -W / 2), (39, W / 2), (5, W / 2)])
    s.finish()
    s.cmd("solid.extrude", distance=7.5, operation="join", targets=[s.body], name="Block")
    s.holes("Screw holes", (0, 0, -7), (0, 0, 1), [(10, 0, -7), (30, 0, -7)], 3, 7 + T + 0.5)
    return v + 34 * W * 7 - 2 * math.pi / 4 * 9 * (7 + T)


# ----------------------------------------------------------------------------- 2-12
@part("2-12", "Fuel tank gearwheel and shaft", {"gear": "Brass", "shaft": "Steel"})
def tank_gear_shaft(s):
    """Sheet 04, 2-12: a brass gear (12 teeth, Ø13 over the tips, Ø11 at the roots, teeth 2 wide at
    the root and 1.5 at the tip, 8 wide) pressed on the end of a Ø4 x 77 M/S shaft. The tooth count
    is read off the drawing; the tooth form is simplified to straight flanks. Axis = Z, the gear on
    Z = 0..8."""
    N = s.param("tg_teeth", 12, "teeth (counted)", unit="")
    DT = s.param("tg_tip_d", 13, "tip diameter")
    DR = s.param("tg_root_d", 11, "root diameter")
    WT = s.param("tg_tip_w", 1.5, "tooth width at the tip")
    WR = s.param("tg_root_w", 2, "tooth width at the root")
    B = s.param("tg_w", 8, "gear width")
    DS = s.param("tg_shaft_d", 4, "shaft")
    LS = s.param("tg_shaft_l", 77, "shaft length")
    n = s.body.split()[0]
    pts = []
    for k in range(int(N)):
        t = 2 * math.pi * k / N
        ar, at = math.asin(WR / DR), math.asin(WT / DT)
        for r, a in ((DR / 2, t - ar), (DT / 2, t - at), (DT / 2, t + at), (DR / 2, t + ar)):
            pts.append((r * math.cos(a), r * math.sin(a)))
    s.sketch("Gear", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(pts)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=DS)
    s.finish()
    s.cmd("solid.extrude", distance=B, profiles=[{"point": [DR / 2 - 1, 0]}], operation="new", name="Gear",
          body_name=f"{n} gear")
    v = (polygon_area(pts) - math.pi / 4 * DS * DS) * B
    v += s.turned("Shaft", [(0, 0), (DS / 2, 0), (DS / 2, LS), (0, LS)], body=f"{n} shaft")
    return v


# ----------------------------------------------------------------------------- 2-14, 2-15
@part("2-14", "Fuel tank wick holder", "Brass")
def wick_holder(s):
    """Sheet 04, 2-14 (scale 1:1.5): 36 high: a Ø14.5 body with 7 cooling fins Ø18 x 1 at 3.5 pitch
    from the bottom, then a cone to Ø12.5 at the top; Ø12 bore 26 deep from below (over the 2-09
    pipe), Ø8 above it. Axis = Z from the bottom."""
    H = s.param("wh_h", 36, "height")
    D = s.param("wh_d", 14.5, "body")
    DT = s.param("wh_top_d", 12.5, "top of the cone")
    HC = s.param("wh_cone_from", 26, "cone starts (= the Ø12 bore's depth)")
    DF = s.param("wh_fin_d", 18, "fins")
    P = s.param("wh_pitch", 3.5, "fin pitch (6 x 3.5 = 21)")
    pts = [(6, 0)]
    for i in range(7):
        z = i * P
        pts += [(DF / 2, z), (DF / 2, z + 1), (D / 2, z + 1)] if i else [(DF / 2, 0), (DF / 2, 1), (D / 2, 1)]
        if i < 6:
            pts += [(D / 2, (i + 1) * P)]
    pts = [(6, 0)] + [p for p in pts[1:]]
    pts += [(D / 2, HC), (DT / 2, H), (4, H), (4, HC), (6, HC)]
    # drop repeated points
    clean = [pts[0]]
    for p in pts[1:]:
        if math.dist(p, clean[-1]) > 1e-9:
            clean.append(p)
    return s.turned("Holder", clean)


@part("2-15", "Fuel tank wick", "Default")
def wick(s):
    """Sheet 04, 2-15 (scale 1:2): wick material, Ø8 x 85 with a pointed end (cone about 6.7 long,
    measured). The library has no wick material: SolidCraft's default density is used."""
    D = s.param("wk_d", 8, "diameter")
    L = s.param("wk_l", 85, "length")
    LT = s.param("wk_tip", 6.7, "pointed end (measured)")
    return s.turned("Wick", [(0, 0), (D / 2, 0), (D / 2, L - LT), (0, L)])


# ----------------------------------------------------------------------------- 2-16
@part("2-16", "Axle body support bracket", "Aluminum")
def axle_support_bracket(s):
    """Sheet 04, 2-16 (scale 1:1.5): 3.5 thick aluminium L: a flange 88 wide and 18 deep (corners
    cut 11 x 8), a notch 46 wide and 8.5 deep with R4 corners in its front edge and 2 x M4 (Ø3.3)
    at ±32, 8.5 from it; under its back edge a web 66 wide narrowing to an R8 nose round a Ø6
    hole 23 below the flange top. X across, Y back from the front edge, Z up; flange top Z = 0."""
    T = s.param("asb_t", 3.5, "thickness")
    W = s.param("asb_w", 88, "flange width (44 + 44)")
    D = s.param("asb_d", 18, "flange depth")
    WN = s.param("asb_notch_w", 46, "notch width (23 + 23)")
    DN = s.param("asb_notch_d", 8.5, "notch depth")
    WW = s.param("asb_web_w", 66, "web width at the top (33 + 33)")
    ZH = s.param("asb_hole_z", 23, "Ø6 hole below the flange top")
    RN = s.param("asb_nose_r", 8, "nose radius")
    # flange (top view outline), the notch with R4 corners
    a, rn = W / 2, 4
    start = (-a, 0)
    segs = [("line", (-WN / 2, 0)), ("line", (-WN / 2, DN - rn)), ("arc", (-WN / 2 + rn, DN - rn), (-WN / 2 + rn, DN), False),
            ("line", (WN / 2 - rn, DN)), ("arc", (WN / 2 - rn, DN - rn), (WN / 2, DN - rn), False),
            ("line", (WN / 2, 0)), ("line", (a, 0)), ("line", (a, 10)), ("line", (WW / 2, D)), ("line", (-WW / 2, D)),
            ("line", (-a, 10)), ("line", start)]
    s.sketch("Flange", (0, 0, -T), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Flange", body_name=s.body)
    v = loop_area(start, segs) * T
    # web: in the plane Y = D - T .. D, from inside the flange down to the nose
    c = (0, -ZH)
    A = (-WW / 2, -T)
    dx, dz = c[0] - A[0], c[1] - A[1]
    dd = math.hypot(dx, dz)
    ang = math.atan2(dz, dx) - math.asin(RN / dd)
    tl = (A[0] + math.sqrt(dd * dd - RN * RN) * math.cos(ang), A[1] + math.sqrt(dd * dd - RN * RN) * math.sin(ang))
    m = lambda p: (-p[0], p[1])
    wstart = (-WW / 2, -T + 1)
    wsegs = [("line", A), ("line", tl), ("arc", c, m(tl), True), ("line", m(A)), ("line", m(wstart)), ("line", wstart)]
    s.sketch("Web", (0, D, 0), (1, 0, 0), (0, 0, 1))                   # normal -Y
    s.loop(wstart, wsegs)
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Web")
    v += (loop_area(wstart, wsegs) - WW * 1) * T
    s.holes("M4 tapped", (0, 0, 0), (0, 0, -1), [(-32, DN, 0), (32, DN, 0)], 3.3)
    s.holes("Ø6 hole", (0, D, 0), (0, -1, 0), [(0, D, -ZH)], 6)
    return v - math.pi / 4 * (2 * 3.3 ** 2 + 36) * T


# ----------------------------------------------------------------------------- 2-17
@part("2-17", "Front axle yoke support bracket", "Aluminum")
def yoke_support_bracket(s):
    """Sheet 04, 2-17: 3.5 thick aluminium angle, 16 wide: a flange 17 deep with an M4 hole (Ø3.3)
    8 from its free edge, and a leg 31 high (from the flange top) with an M6 hole (Ø5) 8 above its
    end, both on the centre line. X across, the leg's outer face on Y = 0, flange toward +Y, flange
    top Z = 0."""
    T = s.param("ysb_t", 3.5, "thickness")
    W = s.param("ysb_w", 16, "width (8 + 8)")
    D = s.param("ysb_d", 17, "flange depth (9 + 8)")
    H = s.param("ysb_h", 31, "leg height")
    s.sketch("Section", (0, 0, 0), (0, 1, 0), (0, 0, 1))                 # normal +X
    s.polyline([(0, 0), (D, 0), (D, -T), (T, -T), (T, -H), (0, -H)])
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Angle", body_name=s.body)
    s.holes("M4 tapped", (0, 0, 0), (0, 0, -1), [(0, D - 8, 0)], 3.3)
    s.holes("M6 tapped", (0, 0, 0), (0, 1, 0), [(0, 0, -H + 8)], 5.0)
    return ((D + H - T) * T) * W - math.pi / 4 * (3.3 ** 2 + 25) * T


# ----------------------------------------------------------------------------- tangent helpers
def tangent_from(p, c, r, left=True):
    """The point where a line from p touches the circle (c, r): on the left of the direction p→c
    when `left`, else on the right."""
    dx, dy = c[0] - p[0], c[1] - p[1]
    d = math.hypot(dx, dy)
    a = math.atan2(dy, dx) + (1 if left else -1) * math.asin(r / d)
    t = math.sqrt(d * d - r * r)
    return (p[0] + t * math.cos(a), p[1] + t * math.sin(a))


def outer_tangent(c1, r1, c2, r2):
    """The outer tangent of two circles on the left of the direction c1→c2: its two touch points."""
    a = math.atan2(c2[1] - c1[1], c2[0] - c1[0])
    phi = a + math.acos((r1 - r2) / math.dist(c1, c2))
    n = (math.cos(phi), math.sin(phi))
    return (c1[0] + r1 * n[0], c1[1] + r1 * n[1]), (c2[0] + r2 * n[0], c2[1] + r2 * n[1])


def valley_fillet(left, v, r):
    """A concave round of radius r in the symmetric valley left → v → mirror(left), the valley
    pointing up (v above the line's other end): (left touch point, centre)."""
    u = _unit((v[0] - left[0], v[1] - left[1], 0))
    half = math.atan2(u[1], u[0])                      # each flank's slope = half the deflection
    t = r * math.tan(half)
    return (v[0] - u[0] * t, v[1] - u[1] * t), (v[0], v[1] - r / math.cos(half))


def cross_hole(R, a, rb=0.0, n=4000):
    """Volume a Ø2a hole removes going right through a Ø2R round bar (with a Ø2rb bore), the axes
    crossing at right angles: ∫ hole width x chord through the material."""
    h, v = 2 * a / n, 0.0
    for i in range(n):
        y = -a + (i + 0.5) * h
        chord = 2 * math.sqrt(R * R - y * y) - (2 * math.sqrt(rb * rb - y * y) if abs(y) < rb else 0)
        v += 2 * math.sqrt(a * a - y * y) * chord * h
    return v


# ----------------------------------------------------------------------------- 2-18
@part("2-18", "Rear axle yoke arm", "Aluminum")
def rear_yoke_arm(s):
    """Sheet 04, 2-18 (scale 1:2): a 4 thick aluminium arm. A Ø12 hole in an R9.5 boss at the
    origin; Ø3 holes in R4.5 ends at (±47, -10). The top edges run tangent from the ends to the
    boss (their virtual sharp is 10 above the Ø12 centre); the bottom edges run from the ends to a
    point 8.5 below the Ø12 centre, rounded R20 there. XY plane, Z = 0..4."""
    T = s.param("rya_t", 4, "thickness")
    X = s.param("rya_x", 47, "end holes either side")
    YE = s.param("rya_ends", 10, "end holes below the Ø12 centre")
    RB = s.param("rya_boss_r", 9.5, "boss radius")
    RE = s.param("rya_end_r", 4.5, "end radius")
    YV = s.param("rya_valley", 8.5, "bottom point below the Ø12 centre")
    RV = s.param("rya_valley_r", 20, "round at the bottom point")
    m = lambda p: (-p[0], p[1])
    cl, c0 = (-X, -YE), (0, 0)
    tl_end, tl_boss = outer_tangent(cl, RE, c0, RB)        # left top edge, on the left of cl→c0
    v = (0, -YV)
    # the bottom flank from the end circle's underside to v
    bl = tangent_from(v, cl, RE, left=True)
    fl, fc = valley_fillet(bl, v, RV)
    start = bl
    segs = [("line", fl), ("arc", fc, m(fl), False), ("line", m(bl)), ("arc", m(cl), m(tl_end), True),
            ("line", m(tl_boss)), ("arc", c0, tl_boss, True), ("line", tl_end), ("arc", cl, bl, True)]
    s.sketch("Arm", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=12)
    for x in (-X, X):
        s.cmd("sketch.circle.center", center=[x, -YE], diameter=3)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [0, -YV + 1]}], name="Arm", body_name=s.body)
    return (loop_area(start, segs) - math.pi / 4 * (144 + 2 * 9)) * T


# ----------------------------------------------------------------------------- 2-19
@part("2-19", "Front axle yoke tie rod", "Steel")
def yoke_tie_rod(s):
    """Sheet 04, 2-19: a Ø5 x 118.5 rod with M3 x 7 ends (threads at the Ø3 major diameter).
    Axis = Z."""
    D = s.param("ytr_d", 5, "rod")
    L = s.param("ytr_l", 118.5, "rod length")
    LT = s.param("ytr_thread", 7, "M3 ends")
    return s.turned("Rod", [(0, 0), (1.5, 0), (1.5, LT), (D / 2, LT), (D / 2, LT + L), (1.5, LT + L),
                            (1.5, 2 * LT + L), (0, 2 * LT + L)])


# ----------------------------------------------------------------------------- 2-20
@part("2-20", "Front axle yoke arm", "Aluminum")
def front_yoke_arm(s):
    """Sheet 04, 2-20 (scale 1:2.5): a 4 thick aluminium arm 165 long, the ends 16 high about the
    hole line (Y = 0). A Ø12 hole 10 above the hole line at the centre, in an R11 round; the top
    edges run tangent to it from the ends of the straight end portions (±56.5, 8). The bottom edges
    run from (±56.5, -8) up to the hole line at the centre, rounded R50 there. Ø3 / Ø4 / Ø3 holes at
    47 / 64.5 / 78.5 either side. XY plane, Z = 0..4."""
    T = s.param("fya_t", 4, "thickness")
    L = s.param("fya_l", 165, "length (82.5 + 82.5)")
    H = s.param("fya_end_h", 16, "end height (8 + 8)")
    XS = s.param("fya_straight", 56.5, "straight end portions start")
    YC = s.param("fya_hole_y", 10, "Ø12 above the hole line")
    RC = s.param("fya_top_r", 11, "round over the Ø12")
    RV = s.param("fya_valley_r", 50, "round at the bottom centre")
    m = lambda p: (-p[0], p[1])
    a, h = L / 2, H / 2
    c = (0, YC)
    tl = tangent_from((-XS, h), c, RC, left=True)
    fl, fc = valley_fillet((-XS, -h), (0, 0), RV)
    start = (-a, -h)
    segs = [("line", (-XS, -h)), ("line", fl), ("arc", fc, m(fl), False), ("line", (XS, -h)), ("line", (a, -h)),
            ("line", (a, h)), ("line", (XS, h)), ("line", m(tl)), ("arc", c, tl, True), ("line", (-XS, h)),
            ("line", (-a, h)), ("line", start)]
    holes = [(x, 3) for x in (-78.5, -47, 47, 78.5)] + [(x, 4) for x in (-64.5, 64.5)]
    s.sketch("Arm", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, YC], diameter=12)
    for x, d in holes:
        s.cmd("sketch.circle.center", center=[x, 0], diameter=d)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [-a + 1, -h + 1]}], name="Arm", body_name=s.body)
    return (loop_area(start, segs) - math.pi / 4 * (144 + sum(d * d for _, d in holes))) * T


# ----------------------------------------------------------------------------- 2-21
@part("2-21", "Front axle yoke bearing", {"bush": "Brass", "pin": "Steel"})
def yoke_bearing(s):
    """Sheet 04, 2-21 (scale 1:1.5, measured from the section's lines): a brass flanged bush, Ø16 x 4
    flange and a Ø12 x 4.1 spigot (pressed into the arm's Ø12 hole: 12PF), reamed Ø8; on a steel
    pin: a Ø12 x 3 head with an R1 round, a Ø8 x 8.1 shank in the bush and an M6 x 10 end (at the
    Ø6 major diameter), drilled Ø2 right through. Axis = Z, the head's end face on Z = 0."""
    HD = s.param("ybr_head", 3, "pin head length")
    LB = s.param("ybr_bush", 8.1, "bush length")
    LF = s.param("ybr_flange", 4, "flange width")
    LT = s.param("ybr_thread", 10, "M6 end")
    n = s.body.split()[0]
    z1, z2 = HD, HD + LB
    v = s.turned("Pin", [(1, 0), (6, 0), (6, z1), (4, z1), (4, z2), (3, z2), (3, z2 + LT), (1, z2 + LT)],
                 body=f"{n} pin")
    s.cmd("solid.fillet", edges=[[6, 0, 0]], radius=1, name="Head round")
    k = (10 - 3 * math.pi) / (12 - 3 * math.pi)                # spandrel centroid from the corner, x r
    v -= 2 * math.pi * (6 - k) * (1 - math.pi / 4)
    v += s.turned("Bush", [(4, z1), (8, z1), (8, z1 + LF), (6, z1 + LF), (6, z2), (4, z2)], body=f"{n} bush")
    return v


# ----------------------------------------------------------------------------- 2-22
@part("2-22", "Front axle yoke wheel hinge bracket", "Brass")
def wheel_hinge_bracket(s):
    """Sheet 04, 2-22 (scale 1:2): a brass block 16 wide: a bar 25 long and 6 thick, then an eye
    10 high (4 deeper than the bar), its end an R5 round 32 from the bar's end, bored Ø6 across.
    M4 (Ø3.3) and M3 (Ø2.5) holes down through the bar at 7 and 21 from its end. X along, Y across,
    Z = 0 the top face."""
    W = s.param("whb_w", 16, "width (8 + 8)")
    LB = s.param("whb_bar", 25, "bar length")
    T = s.param("whb_t", 6, "bar thickness")
    XE = s.param("whb_eye", 32, "eye centre from the bar's end (25 + 7)")
    R = s.param("whb_eye_r", 5, "eye radius")
    start = (0, 0)
    segs = [("line", (XE, 0)), ("arc", (XE, -R), (XE, -2 * R), False), ("line", (LB, -2 * R)),
            ("line", (LB, -T)), ("line", (0, -T)), ("line", start)]
    s.sketch("Side", (0, -W / 2, 0), (1, 0, 0), (0, 0, 1))              # normal -Y
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=W, direction="negative", name="Block", body_name=s.body)
    v = loop_area(start, segs) * W
    s.holes("Ø6 eye", (0, -W / 2, 0), (0, 1, 0), [(XE, -W / 2, -R)], 6)
    s.holes("M4 tapped", (0, 0, 0), (0, 0, -1), [(7, 0, 0)], 3.3)
    s.holes("M3 tapped", (0, 0, 0), (0, 0, -1), [(21, 0, 0)], 2.5)
    return v - math.pi / 4 * (36 * W + (3.3 ** 2 + 2.5 ** 2) * T)


# ----------------------------------------------------------------------------- 2-23
@part("2-23", "Wheel pivot axle", {"axle": "Steel", "pin": "Brass"})
def wheel_pivot_axle(s):
    """Sheet 04, 2-23 (scale 1:1.5): a steel block Ø18 x 16 with two flats 13 apart (6.5 + 6.5),
    bored Ø5 through the flats 8 up; on it a Ø6 x 16 axle with a Ø4 x 3 top, cross-drilled Ø1.5 at
    1.5 below the top for a Ø1.5 x 9 brass pin. Axis = Z, flats normal to Y, block bottom Z = 0."""
    D = s.param("wpa_d", 18, "block")
    F = s.param("wpa_flats", 13, "across the flats")
    HB = s.param("wpa_block_h", 16, "block height (8 + 8)")
    DA = s.param("wpa_axle_d", 6, "axle")
    HA = s.param("wpa_axle_h", 16, "axle length")
    HT = s.param("wpa_top_h", 3, "Ø4 top")
    LP = s.param("wpa_pin", 9, "pin length")
    n = s.body.split()[0]
    r, h = D / 2, F / 2
    x = math.sqrt(r * r - h * h)
    start = (x, -h)
    segs = [("arc", (0, 0), (x, h), True), ("line", (-x, h)), ("arc", (0, 0), (-x, -h), True), ("line", start)]
    s.sketch("Block", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=HB, name="Block", body_name=f"{n} axle")
    v = loop_area(start, segs) * HB
    # the axle starts 1 inside the block so the two overlap instead of touching
    z2 = HB + HA
    v += s.turned("Axle", [(0, HB - 1), (DA / 2, HB - 1), (DA / 2, z2), (2, z2), (2, z2 + HT), (0, z2 + HT)],
                  body=f"{n} axle", operation="join") - math.pi * (DA / 2) ** 2 * 1
    s.holes("Ø5 cross hole", (0, -D, 0), (0, 1, 0), [(0, -D, HB / 2)], 5, target=f"{n} axle")
    zp = z2 + HT - 1.5
    s.holes("Pin hole", (0, -D, 0), (0, 1, 0), [(0, -D, zp)], 1.5, target=f"{n} axle")
    v -= math.pi / 4 * 25 * F + cross_hole(2, 0.75)
    s.sketch("Pin", (0, -LP / 2, 0), (1, 0, 0), (0, 0, 1))               # normal -Y
    s.cmd("sketch.circle.center", center=[0, zp], diameter=1.5)
    s.finish()
    s.cmd("solid.extrude", distance=LP, direction="negative", operation="new", name="Pin", body_name=f"{n} pin")
    return v + math.pi / 4 * 1.5 ** 2 * LP


# ----------------------------------------------------------------------------- 2-24
@part("2-24", "Wheel pivot axle connector bracket", "Steel")
def axle_connector_bracket(s):
    """Sheet 04, 2-24 (scale 1:1.5): a 2 thick steel plate 12 x 13 with a Ø5 hole at the origin; a
    neck 8 wide leaves it and twists through 90° into a tab 8 high and 2 thick, its end an R4
    round with an M3 (Ø2.5) hole 27 from the Ø5. The twist (drawn from X = 6 to about 22) is a
    loft from the plate's 8 x 2 section to the tab's 2 x 8 section. Plate on Z = -1..1."""
    T = s.param("acb_t", 2, "thickness")
    W = s.param("acb_w", 12, "plate along X (6 + 6)")
    D = s.param("acb_d", 13, "plate across (6.5 + 6.5)")
    B = s.param("acb_neck", 8, "neck and tab width")
    X1 = s.param("acb_twist_end", 22, "twist ends (measured)")
    XH = s.param("acb_hole_x", 27, "M3 from the Ø5")
    R = B / 2
    s.sketch("Plate", (0, 0, -T / 2), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-W / 2, -D / 2], p1=[W / 2, D / 2])
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Plate", body_name=s.body)
    v = W * D * T
    # the twist: a loft whose faces are all planar. It starts 1 mm inside the plate, its section
    # there extrapolated so the faces are the same planes: the two solids cross instead of
    # touching (touching faces need a separation retry)
    e = -1 / (X1 - W / 2)
    s.sketch("Neck start", (W / 2 - 1, 0, 0), (0, 1, 0), (0, 0, 1))      # normal +X
    s.cmd("sketch.rectangle.two_point", p0=[-(B - (B - T) * e) / 2, -(T + (B - T) * e) / 2],
          p1=[(B - (B - T) * e) / 2, (T + (B - T) * e) / 2])
    s.finish()
    s.sketch("Neck end", (X1, 0, 0), (0, 1, 0), (0, 0, 1))
    s.cmd("sketch.rectangle.two_point", p0=[-T / 2, -B / 2], p1=[T / 2, B / 2])
    s.finish()
    s.cmd("solid.loft", sections=[{"sketch": "Neck start"}, {"sketch": "Neck end"}], operation="join",
          targets=[s.body], name="Twist")
    # ruled loft between corresponding corners: a (B - (B-T)t) x (T + (B-T)t) section
    v += (X1 - W / 2) * (B * T + (B - T) ** 2 / 6)
    # tab: square-ended in the plane Y = -T/2 .. T/2, then its end rounded R4 by a cut
    s.sketch("Tab", (0, T / 2, 0), (1, 0, 0), (0, 0, 1))                 # normal -Y
    s.cmd("sketch.rectangle.two_point", p0=[X1, -R], p1=[XH + R, R])
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Tab")
    s.sketch("Tab end", (0, T, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.rectangle.two_point", p0=[XH, -R - 1], p1=[XH + R + 1, R + 1])
    s.cmd("sketch.circle.center", center=[XH, 0], diameter=B)
    s.finish()
    s.cmd("solid.extrude", distance=2 * T, operation="cut", targets=[s.body],
          profiles=[{"point": [XH + R + 0.5, 0]}], name="Tab end round")
    v += ((XH - X1) * B + math.pi / 2 * R * R) * T
    s.holes("Ø5", (0, 0, T / 2), (0, 0, -1), [(0, 0, T / 2)], 5)
    s.holes("M3 tapped", (0, T / 2, 0), (0, -1, 0), [(XH, T / 2, 0)], 2.5)
    return v - math.pi / 4 * (25 + 2.5 ** 2) * T


# ----------------------------------------------------------------------------- 2-13
@part("2-13", "Fuel tank gear wheel shaft handle collar", {"collar": "Brass", "lever": "Steel"})
def handle_collar(s):
    """Sheet 04, 2-13 (scale 1:1.5): a brass collar on the Ø4 gear shaft (2-12): Ø11.5 x 14 with a
    Ø8 x 4 spigot on one side and a Ø6 x 4 spigot on the other, bored Ø4, cross-drilled Ø4 9 from
    the Ø6 side. A 2 thick steel lever pressed on the Ø6 spigot: R5 round the Ø6 hole, R4 round an M3
    (Ø2.5) hole 19 away. Axis = Z, the collar's Ø6-side face on Z = 0, the lever on Z = 0..2 along X."""
    D = s.param("hc_d", 11.5, "collar")
    L = s.param("hc_l", 14, "collar length")
    C = s.param("hc_centres", 19, "lever hole centres")
    n = s.body.split()[0]
    v = link(s, C, 5, 4, 6, 2.5, 2, body=f"{n} lever", name="Lever")
    v += s.turned("Collar", [(2, -L - 4), (4, -L - 4), (4, -L), (D / 2, -L), (D / 2, 0), (3, 0), (3, 4), (2, 4)],
                  body=f"{n} collar")
    s.holes("Ø4 cross hole", (-D, 0, 0), (1, 0, 0), [(-D, 0, -9)], 4, target=f"{n} collar")
    return v - cross_hole(D / 2, 2, 2)


# ----------------------------------------------------------------------------- 2-25
@part("2-25", "Wheel pivot axle steering arm", "Steel")
def steering_arm(s):
    """Sheet 05, 2-25 (scale 1:1.5, bend read from the vector lines): a 2 thick steel upright 14
    wide, 17 high with an R7 top round a Ø5 hole 10 up, and a flat arm 2 thick, 7 wide, leaving its
    foot with R3.5 roots. 16 from the upright's back the arm bends 26° on R16.5 (inside edge), then
    runs on to two M4 (Ø3.3) holes 8 apart, the end one in an R4 end. X along the arm from the
    upright's back face, Y across, Z up from the arm's underside."""
    T = s.param("sa_t", 2, "thickness")
    W = s.param("sa_w", 7, "arm width")
    RR = s.param("sa_root_r", 3.5, "root rounds")
    XB = s.param("sa_bend_x", 16, "bend starts (measured)")
    RB = s.param("sa_bend_r", 16.5, "bend radius, inside edge")
    A = math.radians(s.param("sa_bend_a", 26, "bend angle", unit="deg"))
    D1 = s.param("sa_hole1", 13.38, "first hole along the bent leg's centre line (measured)")
    P = s.param("sa_pitch", 8, "hole pitch")
    RE = s.param("sa_end_r", 4, "end radius")
    HU = s.param("sa_up_h", 17, "upright height (2 + 8 + 7)")
    h = W / 2
    c = (XB, h + RB)                                       # bend centre (the bend turns toward +Y)
    ro, ri = RB + W, RB
    u = (math.cos(A), math.sin(A))
    n = (math.sin(A), -math.cos(A))                       # the bent leg's right-hand side
    e0 = (XB + (RB + h) * math.sin(A), h + RB - (RB + h) * math.cos(A))   # bent leg's centre-line start
    ce = (e0[0] + (D1 + P) * u[0], e0[1] + (D1 + P) * u[1])                # end hole
    c1 = (e0[0] + D1 * u[0], e0[1] + D1 * u[1])
    back = math.sqrt(RE * RE - h * h)
    pr = (ce[0] - back * u[0] + h * n[0], ce[1] - back * u[1] + h * n[1])
    pl = (ce[0] - back * u[0] - h * n[0], ce[1] - back * u[1] - h * n[1])
    oe = (c[0] + ro * math.sin(A), c[1] - ro * math.cos(A))
    ie = (c[0] + ri * math.sin(A), c[1] - ri * math.cos(A))
    start = (0, -7)
    segs = [("line", (T, -7)), ("arc", (T + RR, -7), (T + RR, -h), False), ("line", (XB, -h)),
            ("arc", c, oe, True), ("line", pr), ("arc", ce, pl, True), ("line", ie), ("arc", c, (XB, h), False),
            ("line", (T + RR, h)), ("arc", (T + RR, 7), (T, 7), False), ("line", (0, 7)), ("line", start)]
    s.sketch("Arm", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    for p in (c1, ce):
        s.cmd("sketch.circle.center", center=[round(p[0], 6), round(p[1], 6)], diameter=3.3)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [1, 0]}], name="Arm", body_name=s.body)
    v = (loop_area(start, segs) - 2 * math.pi / 4 * 3.3 ** 2) * T
    s.sketch("Upright", (0, 0, 0), (0, 1, 0), (0, 0, 1))                 # normal +X
    ru, zc = 7, HU - 7
    s.loop((-ru, 0), [("line", (ru, 0)), ("line", (ru, zc)), ("arc", (0, zc), (-ru, zc), True), ("line", (-ru, 0))])
    s.cmd("sketch.circle.center", center=[0, zc], diameter=5)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [0, 1]}], operation="join", targets=[s.body],
          name="Upright")
    return v + (2 * ru * zc + math.pi / 2 * ru * ru - math.pi / 4 * 25 - 2 * ru * T) * T


# ----------------------------------------------------------------------------- 2-26
@part("2-26", "Wheel pivot axle connecting rod", "Steel")
def connecting_rod(s):
    """Sheet 05, 2-26: a 2 thick, 8 wide steel strip with R4 ends and Ø4 holes 164 apart (172
    overall), cranked down 10 between 28 and 64 from one end (outer faces of the two legs). The bends
    are drawn round but not dimensioned: R1 inside, R3 outside. X along, Z = 0 the top face."""
    T = s.param("cr_t", 2, "thickness")
    W = s.param("cr_w", 8, "width")
    L = s.param("cr_l", 172, "overall (164 + 4 + 4)")
    X1 = s.param("cr_crank_from", 28, "crank's first leg, outer face")
    X2 = s.param("cr_crank_to", 64, "crank's second leg, outer face (28 + 36)")
    DZ = s.param("cr_drop", 10, "drop")
    ri, ro = 1, 1 + T
    zb = -T - DZ                                            # underside of the lowered part
    start = (0, -T)
    segs = [("line", (X1 - ri, -T)), ("arc", (X1 - ri, -T - ri), (X1, -T - ri), False),
            ("line", (X1, zb + ro)), ("arc", (X1 + ro, zb + ro), (X1 + ro, zb), True),
            ("line", (X2 - ro, zb)), ("arc", (X2 - ro, zb + ro), (X2, zb + ro), True),
            ("line", (X2, -T - ri)), ("arc", (X2 + ri, -T - ri), (X2 + ri, -T), False),
            ("line", (L, -T)), ("line", (L, 0)), ("line", (X2 + ri, 0)),
            ("arc", (X2 + ri, -T - ri), (X2 - T, -T - ri), True), ("line", (X2 - T, zb + ro)),
            ("arc", (X2 - ro, zb + ro), (X2 - ro, zb + T), False), ("line", (X1 + ro, zb + T)),
            ("arc", (X1 + ro, zb + ro), (X1 + T, zb + ro), False), ("line", (X1 + T, -T - ri)),
            ("arc", (X1 - ri, -T - ri), (X1 - ri, 0), True), ("line", (0, 0)), ("line", start)]
    s.sketch("Side", (0, 0, 0), (1, 0, 0), (0, 0, 1))                    # normal -Y
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Rod", body_name=s.body)
    v = loop_area(start, segs) * W
    r = W / 2
    s.sketch("End rounds", (0, 0, 1), (1, 0, 0), (0, -1, 0))       # normal -Z
    for xc, x0, x1 in ((r, -1, r), (L - r, L - r, L + 1)):
        s.cmd("sketch.rectangle.two_point", p0=[x0, -r - 1], p1=[x1, r + 1])
        s.cmd("sketch.circle.center", center=[xc, 0], diameter=W)
    s.finish()
    s.cmd("solid.extrude", distance=4, operation="cut", targets=[s.body],
          profiles=[{"point": [-0.5, 0]}, {"point": [L + 0.5, 0]}], name="End rounds")
    s.holes("Ø4 holes", (0, 0, 1), (0, 0, -1), [(r, 0, 1), (L - r, 0, 1)], 4, depth=4)
    return v - 2 * (2 * r * r - math.pi / 2 * r * r) * T - 2 * math.pi * 4 * T


# ----------------------------------------------------------------------------- 2-27A, 2-27B
@part("2-27A", "Wheel pivot spacer ring-1", "Steel")
def spacer_ring_1(s):
    """Sheet 05, 2-27A: a Ø8 / Ø5 x 1 steel washer. Axis = Z."""
    return s.turned("Ring", [(2.5, 0), (4, 0), (4, 1), (2.5, 1)])


@part("2-27B", "Wheel pivot spacer ring-2", "Steel")
def spacer_ring_2(s):
    """Sheet 05, 2-27B: a Ø12 / Ø5 x 2 steel washer. Axis = Z."""
    return s.turned("Ring", [(2.5, 0), (6, 0), (6, 2), (2.5, 2)])


# ----------------------------------------------------------------------------- 2-28
@part("2-28", "Wheel axle", "Steel")
def wheel_axle(s):
    """Sheet 05, 2-28: a Ø8 x 2 head with a 2 wide, 1 deep screwdriver slot, Ø6 x 8, Ø5 x 18 and an
    M4 x 4 end (at the Ø4 major diameter). Axis = Z, the head's end on Z = 0."""
    v = s.turned("Axle", [(0, 0), (4, 0), (4, 2), (3, 2), (3, 10), (2.5, 10), (2.5, 28), (2, 28), (2, 32), (0, 32)])
    s.sketch("Slot", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-5, -1], p1=[5, 1])
    s.finish()
    s.cmd("solid.extrude", distance=1, operation="cut", targets=[s.body], name="Slot")
    band = 2 * (math.sqrt(15) + 16 * math.asin(0.25))       # the |y| < 1 band of the Ø8 head
    return v - band * 1


# ----------------------------------------------------------------------------- 2-29
@part("2-29", "Wheel axle ball bearing", "Steel")
def wheel_bearing(s):
    """Sheet 05, 2-29: a bought-in ball bearing, Ø16 / Ø6, 8 thick as noted on the drawing, modelled
    as its envelope (a plain ring). Axis = Z."""
    return s.turned("Bearing", [(3, 0), (8, 0), (8, 8), (3, 8)])


# ----------------------------------------------------------------------------- 2-30
@part("2-30", "Connecting rod screw", "Steel")
def connecting_rod_screw(s):
    """Sheet 05, 2-30: a Ø8 x 2 head, a Ø4 x 2.1 shoulder and an M3 x 4 end (at the Ø3 major
    diameter); the head's slot is not dimensioned and not modelled. Axis = Z."""
    return s.turned("Screw", [(0, 0), (4, 0), (4, 2), (2, 2), (2, 4.1), (1.5, 4.1), (1.5, 8.1), (0, 8.1)])


# ----------------------------------------------------------------------------- 2-31, 2-32
@part("2-31", "Front wheel rim", "Aluminum")
def front_rim(s):
    """Sheet 05, 2-31 (section A-A, 1:1.5, radii and steps read from the vector lines): Ø72 rim
    21.6 wide with a 45° tyre groove (Ø62 floor, 10 wide), Ø66.5 chamfers to a Ø58 bore 4.3 deep on
    each side; on one side a cone from Ø50 down to a Ø32 hub face 1 proud of the rim; web 10 thick
    from the hub face, Ø16 counterbore 9 deep, Ø14 through; 4 x M3 (Ø2.5) on a Ø24 PCD, counterbored
    Ø6 x 4 from the other side. Axis = Z, the hub face on Z = 0."""
    z1, z2 = 1, 22.6
    pts = [(8, 0), (16, 0), (16, z1), (25, z1 + 4.3), (29, z1 + 4.3), (33.25, z1), (36, z1), (36, z1 + 0.8),
           (31, z1 + 5.8), (31, z1 + 15.8), (36, z2 - 0.8), (36, z2), (33.25, z2), (29, z2 - 4.3), (29, 10),
           (7, 10), (7, 9), (8, 9)]
    v = s.turned("Rim", pts)
    # off the revolve's seam (in the XZ plane): a counterbore across it needed a separation retry
    ctr = [(12 * math.cos(a), 12 * math.sin(a), 0) for a in (math.pi / 4 + k * math.pi / 2 for k in range(4))]
    # both cuts start 1 clear of the faces (a cut sketched on the web face needed a separation retry)
    s.holes("Ø6 counterbores", (0, 0, 11), (0, 0, -1), [(x, y, 11) for x, y, _ in ctr], 6, depth=5)
    s.holes("M3 tapped", (0, 0, -1), (0, 0, 1), [(x, y, -1) for x, y, _ in ctr], 2.5, depth=8)
    return v - 4 * math.pi / 4 * (2.5 ** 2 * 6 + 36 * 4)


@part("2-32", "Front wheel tyre", "Default")
def front_tyre(s):
    """Sheet 05, 2-32: a rubber ring Ø110.3 over a Ø24 section (a torus). SolidCraft has no rubber
    material: the default density (1.29, close to rubber's) with the black rubber appearance."""
    D = s.param("ft_d", 110.3, "outside diameter")
    DS = s.param("ft_section", 24, "section")
    rc = (D - DS) / 2
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.circle.center", center=[rc, 0], diameter=DS)
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Tyre", body_name=s.body)
    s.cmd("appearance.assign", bodies=[s.body], appearance="Rubber - Black")
    return 2 * math.pi ** 2 * rc * (DS / 2) ** 2


# ----------------------------------------------------------------------------- 2-33
@part("2-33", "Front wheel hub cap", "Brass")
def hub_cap(s):
    """Sheet 05, 2-33 (section B-B, read from the vector lines): a Ø32 x 2.5 flange with 4 x Ø3 on
    a Ø24 PCD; a Ø16 hub standing 1 proud on one side, recessed Ø14 x 2.5, and 1.5 on the other,
    then a Ø12.5 / Ø10 lip 1 high; Ø3 through the middle. Axis = Z, the recessed face on Z = 0."""
    v = s.turned("Cap", [(1.5, 2.5), (7, 2.5), (7, 0), (8, 0), (8, 1), (16, 1), (16, 3.5), (8, 3.5), (8, 5),
                         (6.25, 5), (6.25, 6), (5, 6), (5, 5), (1.5, 5)])
    ctr = [(12 * math.cos(a), 12 * math.sin(a), 4) for a in (0, math.pi / 2, math.pi, 1.5 * math.pi)]
    s.holes("Ø3 holes", (0, 0, 4), (0, 0, -1), ctr, 3, depth=4)
    return v - 4 * math.pi / 4 * 9 * 2.5


# ----------------------------------------------------------------------------- 2-34, 2-37
@part("2-34", "Steering lay shaft", "Steel")
def lay_shaft(s):
    """Sheet 05, 2-34 (scale 1:1.5): a Ø6 x 86 shaft, cross-drilled Ø3 13.5 from one end; 18 from the
    other a Ø3 x 18 pin pressed across it. Axis = Z."""
    v = s.turned("Shaft", [(0, 0), (3, 0), (3, 86), (0, 86)])
    s.holes("Ø3 cross hole", (-5, 0, 0), (1, 0, 0), [(-5, 0, 13.5)], 3)
    s.sketch("Pin", (0, -9, 0), (1, 0, 0), (0, 0, 1))                    # normal -Y
    s.cmd("sketch.circle.center", center=[0, 86 - 18], diameter=3)
    s.finish()
    s.cmd("solid.extrude", distance=18, direction="negative", operation="join", targets=[s.body], name="Pin")
    return v - cross_hole(3, 1.5) + math.pi / 4 * 9 * 18 - cross_hole(3, 1.5)


@part("2-37", "Steering tie rod", "Steel")
def steering_tie_rod(s):
    """Sheet 05, 2-37 (scale 1:1.5): a Ø5 x 47 rod with M4 x 10 ends (at the Ø4 major diameter).
    Axis = Z."""
    return s.turned("Rod", [(0, 0), (2, 0), (2, 10), (2.5, 10), (2.5, 57), (2, 57), (2, 67), (0, 67)])


# ----------------------------------------------------------------------------- 2-35
@part("2-35", "Steering lay shaft crank", {"collar": "Brass", "lever": "Steel"})
def lay_shaft_crank(s):
    """Sheet 05, 2-35 (scale 1:1.5): a brass collar Ø18 x 8 with a Ø10 spigot through the lever and
    3 beyond, bored Ø6 for the lay shaft, an M3 (Ø2.5) set-screw hole 4 from its end; a 2 thick steel
    lever, R7.5 round the spigot and R5.5 round an M4 (Ø3.3) hole 26 away. Axis = Z, the lever on
    Z = 0..2 along X."""
    n = s.body.split()[0]
    v = link(s, 26, 7.5, 5.5, 10, 3.3, 2, body=f"{n} lever", name="Lever")
    v += s.turned("Collar", [(3, -3), (5, -3), (5, 2), (9, 2), (9, 10), (3, 10)], body=f"{n} collar")
    s.holes("M3 tapped", (10, 0, 0), (-1, 0, 0), [(10, 0, 6)], 2.5, depth=10, target=f"{n} collar")
    return v - cross_hole(9, 1.25, 3) / 2


# ----------------------------------------------------------------------------- 2-36
@part("2-36", "Steering lay shaft gear wheel", "Brass")
def lay_shaft_gear(s):
    """Sheet 05, 2-36 (scale 1:1.5): a brass gear, 30 teeth, Ø32 over the tips and Ø28 at the roots,
    the gaps 1.7 wide at the tip and 1.1 at the root, 6 wide (measured); a Ø18 x 8 hub with an M3
    (Ø2.5) set-screw hole 4 from its end, a Ø12 x 3.5 boss on the other side, bored Ø6. The teeth's
    R5 throat (for the worm) is not modelled. Axis = Z, the hub's end on Z = 0."""
    N = s.param("lg_teeth", 30, "teeth", unit="")
    RT = s.param("lg_tip_d", 32, "tip diameter") / 2
    RR = s.param("lg_root_d", 28, "root diameter") / 2
    GT = s.param("lg_gap_tip", 1.7, "gap at the tip")
    GR = s.param("lg_gap_root", 1.1, "gap at the root")
    B = s.param("lg_w", 6, "tooth width (measured)")
    v = s.turned("Gear blank", [(3, 0), (9, 0), (9, 8), (RT, 8), (RT, 8 + B), (6, 8 + B), (6, 11.5 + B),
                                (3, 11.5 + B)])
    at, ar = math.asin(GT / 2 / RT), math.asin(GR / 2 / RR)
    s.sketch("Tooth gaps", (0, 0, 7), (1, 0, 0), (0, 1, 0))
    for k in range(int(N)):
        t = 2 * math.pi * (k + 0.5) / N
        pts = [(RR, t - ar), (RT, t - at), (RT + 1.5, t - at), (RT + 1.5, t + at), (RT, t + at), (RR, t + ar)]
        s.polyline([(r * math.cos(a), r * math.sin(a)) for r, a in pts])
    s.finish()
    s.cmd("solid.extrude", distance=B + 2, operation="cut", targets=[s.body], name="Tooth gaps")
    quad = polygon_area([(r * math.cos(a), r * math.sin(a)) for r, a in
                         ((RR, -ar), (RT, -at), (RT, at), (RR, ar))])
    gap = quad + RT * RT / 2 * (2 * at - math.sin(2 * at))
    v -= N * gap * B
    s.holes("M3 tapped", (10, 0, 0), (-1, 0, 0), [(10, 0, 4)], 2.5, depth=10)
    return v - cross_hole(9, 1.25, 3) / 2


# ----------------------------------------------------------------------------- 2-38, 2-39, 2-40
@part("2-38", "Steering tie rod end", "Steel")
def tie_rod_end(s):
    """Sheet 05, 2-38 (section C-C, scale 1.5:1, read from the vector lines): a 7 AF hex 15 long and
    a Ø6 x 10 neck; from the hex end a Ø6 bore 7 deep, a Ø5 ball seat on to 12, coned to Ø4 at
    13.5, then tapped M4 (Ø3.3) through the neck; a slot 4 wide from the underside flat into the
    bore over the first 13.5 (the ball's neck goes through it). The cone from the hex to the neck
    is not modelled. Axis = Z, the hex's end on Z = 0, the slot toward -Y."""
    AF = s.param("tre_af", 7, "hex across the flats")
    LH = s.param("tre_hex", 15, "hex length")
    LN = s.param("tre_neck", 10, "Ø6 neck length")
    WS = s.param("tre_slot_w", 4, "slot width")
    LS = s.param("tre_slot_l", 13.5, "slot length")
    RT = 3.3 / 2
    s.sketch("Hex", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=LH, name="Hex", body_name=s.body)
    s.turned("Neck", [(0, LH - 1), (3, LH - 1), (3, LH + LN), (0, LH + LN)], operation="join")
    s.turned("Bore", [(0, -1), (3, -1), (3, 7), (2.5, 7), (2.5, 12), (2, LS), (RT, LS), (RT, LH + LN + 1),
                      (0, LH + LN + 1)], operation="cut")
    s.sketch("Slot", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-WS / 2, -AF / 2 - 0.5], p1=[WS / 2, -1.5])
    s.finish()
    s.cmd("solid.extrude", distance=LS + 1, operation="cut", targets=[s.body], name="Slot")

    def slot_out(r, n=4000):                 # the slot's area below the bore (the slot's top at -1.5)
        h, a = WS / n, 0.0
        for i in range(n):
            x = -WS / 2 + (i + 0.5) * h
            top = min(-1.5, -math.sqrt(r * r - x * x)) if abs(x) < r else -1.5
            a += (top + AF / 2) * h
        return a
    hexa = math.sqrt(3) / 2 * AF * AF
    v = (hexa - math.pi * 9 - slot_out(3)) * 7 + (hexa - math.pi * 6.25 - slot_out(2.5)) * 5
    m = 60                                                   # the cone: Simpson in z
    f = lambda z: hexa - math.pi * (2.5 - (z - 12) / 3) ** 2 - slot_out(2.5 - (z - 12) / 3, 800)
    hz = (LS - 12) / m
    v += hz / 3 * sum((1 if i in (0, m) else 4 if i % 2 else 2) * f(12 + i * hz) for i in range(m + 1))
    v += (hexa - math.pi * RT * RT) * (LH - LS) + math.pi * (9 - RT * RT) * LN
    return v


@part("2-39", "Steering tie rod end plug", "Steel")
def tie_rod_end_plug(s):
    """Sheet 05, 2-39: an M6 x 6 plug (at the Ø6 major diameter) with a Ø5 nose 3 long, its end
    chamfered 1.5 x 45°. The R2.5 seat for the ball (about 0.2 deep) and the screwdriver slot are
    not dimensioned and not modelled. Axis = Z."""
    return s.turned("Plug", [(0, 0), (3, 0), (3, 6), (2.5, 6), (2.5, 7.5), (1, 9), (0, 9)])


@part("2-40", "Steering tie rod end balljoint", "Steel")
def tie_rod_balljoint(s):
    """Sheet 05, 2-40: a 7 AF x 2.5 hex with an M4 x 5 stem below (at the Ø4 major diameter) and a
    Ø3 neck up to an SR2.5 ball whose centre is 8 above the hex's underside. The hex's 10° chamfer is
    not modelled. Axis = Z, the hex's underside on Z = 0."""
    AF = s.param("bj_af", 7, "hex across the flats")
    TH = s.param("bj_hex_t", 2.5, "hex thickness")
    ZB = s.param("bj_ball_z", 8, "ball centre above the hex's underside")
    RB = s.param("bj_ball_r", 2.5, "ball radius")
    # the round part as one revolve, then the (planar) hex joined over it. The ball's arc is split
    # at its equator: one arc across the equator revolves into an inside-out solid
    zn = ZB - math.sqrt(RB * RB - 1.5 ** 2)                  # where the Ø3 neck meets the ball
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop((0, -5), [("line", (2, -5)), ("line", (2, 1)), ("line", (1.5, 1)), ("line", (1.5, zn)),
                     ("arc", (0, ZB), (RB, ZB), True), ("arc", (0, ZB), (0, ZB + RB), True), ("line", (0, -5))])
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Stem, neck and ball", body_name=s.body)
    h = RB - (ZB - zn)                                        # the ball's cap below the neck's end
    v = math.pi * 4 * 6 + math.pi * 2.25 * (zn - 1) + 4 / 3 * math.pi * RB ** 3 - math.pi * h * h * (3 * RB - h) / 3
    s.sketch("Hex", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(AF))
    s.finish()
    s.cmd("solid.extrude", distance=TH, operation="join", targets=[s.body], name="Hex")
    return v + math.sqrt(3) / 2 * AF * AF * TH - math.pi * 4 * 1 - math.pi * 2.25 * (TH - 1)


# ----------------------------------------------------------------------------- 2-43
# a Ø2 wire: its measured volume is good to a few tenths of a per cent
@part("2-43", "Accelerator link", "Steel", tol=0.01)
def accelerator_link(s):
    """Sheet 05, 2-43 (scale 1:2): a Ø2 steel wire, eyes of Ø4.5 (taken as the wire's centre line)
    at both ends, at right angles to each other. From the lower eye's centre 69 straight, then a
    20 leg to the upper eye's centre, 5.3 to one side. The kink is drawn sharp; it is bent R3 here.
    The lower eye in the YZ plane centred on the origin, the rest in the XZ plane."""
    D = s.param("al_d", 2, "wire")
    RE = s.param("al_eye", 4.5, "eye diameter, centre line") / 2
    L1 = s.param("al_l1", 69, "lower eye to the kink")
    L2 = s.param("al_l2", 20, "kink to the upper eye")
    DX = s.param("al_dx", 5.3, "upper eye to one side")
    RB = s.param("al_bend", 3, "kink bend radius (assumed)")
    th = math.asin(DX / L2)
    d = (-math.sin(th), 0, math.cos(th))
    U = (-DX, 0, L1 + L2 * math.cos(th))
    t = RB * math.tan(th / 2)
    # the legs stop 0.3 outside the eyes' centre lines: ended on them, a Ø2 leg's sides touch the
    # Ø2 eye's tube tangentially and the join fails
    g0 = RE + 0.3
    e = (U[0] - g0 * d[0], U[2] - g0 * d[2])                  # where the leg meets the upper eye
    a_end = (-RB + RB * math.cos(th), L1 - t + RB * math.sin(th))
    s.sketch("Path", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.line", points=[[0, g0], [0, round(L1 - t, 6)]])                                   # l1
    s.cmd("sketch.arc.center_point", center=[-RB, round(L1 - t, 6)], start=[0, round(L1 - t, 6)],
          end=[round(a_end[0], 6), round(a_end[1], 6)])                                            # a1
    s.cmd("sketch.line", points=[[round(a_end[0], 6), round(a_end[1], 6)], [round(e[0], 6), round(e[1], 6)]])  # l2
    s.finish()
    s.cmd("solid.pipe", path_sketch="Path", path=["l1", "a1", "l2"], diameter=D, name="Wire", body_name=s.body)
    v = math.pi / 4 * D * D * ((L1 - t - g0) + RB * th + (L2 - t - g0))
    s.sketch("Lower eye", (0, 0, 0), (0, 1, 0), (1, 0, 0))
    s.cmd("sketch.circle.center", center=[RE, 0], diameter=D)
    s.finish()
    s.cmd("solid.revolve", axis="y", operation="join", targets=[s.body], name="Lower eye")
    s.sketch("Upper eye", U, (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[RE, 0], diameter=D)
    s.finish()
    s.cmd("solid.revolve", axis="y", operation="join", targets=[s.body], name="Upper eye")
    r = D / 2
    v += 2 * (2 * math.pi ** 2 * RE * r * r)
    in_lower = lambda x, y, z: (math.hypot(y, z) - RE) ** 2 + x * x <= r * r
    in_upper = lambda x, y, z: (math.hypot(x - U[0], z - U[2]) - RE) ** 2 + y * y <= r * r
    v -= removed_by_cylinder(in_lower, (0, 0, g0), (0, 0, 1), D, 1.5)
    v -= removed_by_cylinder(in_upper, (e[0], 0, e[1]), (-d[0], 0, -d[2]), D, 1.5)
    return v


# ----------------------------------------------------------------------------- 2-46
@part("2-46", "Pulling hook", "Steel")
def pulling_hook(s):
    """Sheet 05, 2-46: an SR5 domed head 5 high (a Ø10 half ball), a Ø5 x 15 shank, a Ø8 x 3 collar
    and an M4 x 8 end (at the Ø4 major diameter); the small edge rounds are not modelled. Axis = Z,
    the threaded end on Z = 0."""
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    start = (0, 0)
    segs = [("line", (2, 0)), ("line", (2, 8)), ("line", (4, 8)), ("line", (4, 11)), ("line", (2.5, 11)),
            ("line", (2.5, 26)), ("line", (5, 26)), ("arc", (0, 26), (0, 31), True), ("line", start)]
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Hook", body_name=s.body)
    return math.pi * (4 * 8 + 16 * 3 + 6.25 * 15) + 2 / 3 * math.pi * 125


# ----------------------------------------------------------------------------- 2-41
@part("2-41", "Steering column and worm gear", {"shaft": "Steel", "worm": "Brass", "collar 1": "Brass",
                                                "collar 2": "Brass"})
def steering_column(s):
    """Sheet 05, 2-41 (scale 1:1.5): a Ø4 steel column 254 long (the last 10 measured) with a brass
    worm pressed on one end and two brass collars Ø10 x 7, 50.5 and 175.5 from that end, each pinned
    by a Ø2 x 11 steel pin; a Ø2 x 14 pin crosses the column 244 from the worm's end. The worm is
    Ø14 over a Ø10 root, 15.5 long; its thread is a square-section helix (2.2 x 2.2, a 6° lead angle
    on Ø12: lead 3.96, 3 turns), the drawn trapezoid form and end chamfers simplified. Axis = Z, the
    worm's end on Z = 0; the pins along X."""
    n = s.body.split()[0]
    L = s.param("sc_l", 254, "column length (244 to the end pin + 10, measured)")
    ZC = [s.param("sc_collar1", 50.5, "first collar's centre"), s.param("sc_collar2", 175.5, "second collar's centre (50.5 + 125)")]
    ZP = s.param("sc_end_pin", 244, "end pin (175.5 + 68.5)")
    LW = s.param("sc_worm_l", 15.5, "worm length")
    lead = math.pi * 12 * math.tan(math.radians(6))
    turns, a, d0 = 3, 2.2, 9.6
    v = s.turned("Column", [(0, 0), (2, 0), (2, L), (0, L)], body=f"{n} shaft")
    for z, lp in ((ZC[0], 11), (ZC[1], 11), (ZP, 14)):
        s.cmd("solid.cylinder", diameter=2, height=lp, base=[-lp / 2, 0, z], axis="X", operation="join",
              targets=[f"{n} shaft"], name="Pin")
        v += math.pi * lp - cross_hole(2, 1)
    s.cmd("solid.cylinder", diameter=10, height=LW, base=[0, 0, 0], axis="Z", name="Worm core", body_name=f"{n} worm")
    v += math.pi * 25 * LW
    # the thread's square section reaches 0.2 into the core (r 4.8 .. 7) so the two cross. It is
    # joined as two 1.5-turn coils, end to end: a join of more than about 2 turns exceeds the
    # kernel's limit on contact work ("lumps: contact work exceeds the limit")
    for k in range(2):
        s.cmd("solid.coil", diameter=d0, turns=turns / 2, pitch=round(lead, 6), section_size=a, section="square",
              section_position="outside", base=[0, 0, round(1.8 + k * turns / 2 * lead, 6)], axis="Z",
              start_angle=180 * k * (turns % 2), operation="join", targets=[f"{n} worm"], name="Worm thread")
    # bored last: with the bore already in the core the second coil's join exceeds the limit too
    s.cmd("solid.cylinder", diameter=4, height=LW + 2, base=[0, 0, -1], axis="Z", operation="cut",
          targets=[f"{n} worm"], name="Worm bore")
    v -= math.pi * 4 * LW
    v += a * a * 2 * math.pi * (d0 / 2 + a / 2) * turns - 0.2 * a * 2 * math.pi * 4.9 * turns
    for k, z in enumerate(ZC):
        body = f"{n} collar {k + 1}"
        v += s.turned(f"Collar {k + 1}", [(2, z - 3.5), (5, z - 3.5), (5, z + 3.5), (2, z + 3.5)], body=body)
        s.holes(f"Collar {k + 1} pin hole", (-6, 0, 0), (1, 0, 0), [(-6, 0, z)], 2, target=body)
        v -= cross_hole(5, 1, 2)
    return v


# ----------------------------------------------------------------------------- 2-42
@part("2-42", "Steering wheel", "Aluminum")
def steering_wheel(s):
    """Sheet 05, 2-42 (scale 1:2.5): an aluminium wheel, rim Ø64 / Ø54 x 6, four Ø3 spokes in the
    rim's mid plane to a Ø13.5 x 15 hub bored Ø4, cross-drilled Ø2 5 from the hub's end. The rim is
    modelled square-edged. Axis = Z, the rim and the hub's inner end on Z = 0."""
    RO, RI = s.param("sw_rim_od", 64, "rim") / 2, s.param("sw_rim_id", 54, "rim inside") / 2
    T = s.param("sw_rim_t", 6, "rim thickness")
    RH = s.param("sw_hub_d", 13.5, "hub") / 2
    LH = s.param("sw_hub_l", 15, "hub length")
    DS = s.param("sw_spoke_d", 3, "spokes")
    v = s.turned("Hub", [(2, 0), (RH, 0), (RH, LH), (2, LH)])
    rs = DS / 2
    for k in range(4):
        a = k * math.pi / 2
        u = (math.cos(a), math.sin(a), 0)
        s.cmd("solid.cylinder", diameter=DS, height=RI + 1 - (RH - 0.75), base=[round((RH - 0.75) * u[0], 6),
              round((RH - 0.75) * u[1], 6), T / 2], axis=[round(c, 6) for c in u], operation="join",
              targets=[s.body], name="Spoke")
    v += s.turned("Rim", [(RI, 0), (RO, 0), (RO, T), (RI, T)], operation="join")
    h, sp = 2 * rs / 2000, 0.0
    for i in range(2000):
        y = -rs + (i + 0.5) * h
        sp += 2 * math.sqrt(rs * rs - y * y) * (math.sqrt(RI * RI - y * y) - math.sqrt(RH * RH - y * y)) * h
    s.holes("Ø2 cross hole", (0, -10, 0), (0, 1, 0), [(0, -10, LH - 5)], 2)
    return v + 4 * sp - cross_hole(RH, 1, 2)


# ----------------------------------------------------------------------------- 2-44
@part("2-44", "Front lighting main beam", "Brass")
def lighting_beam(s):
    """Sheet 05, 2-44 (scale 1:1.5, read with the vector lines): a 9 x 5 x 0.5 brass tube 87 long,
    its corners on one side cut back at 37° from 6.3 across the end. Top wall: Ø4 at 4.5 and 11.5
    from each end, two 7 wide slots from 19 to 34 and 53 to 68, a Ø8 at the middle; bottom wall:
    Ø7 under the end holes and Ø4 at 11.5. X along, Y across from the straight side, Z up."""
    L = s.param("lb_l", 87, "length")
    W = s.param("lb_w", 9, "width")
    H = s.param("lb_h", 5, "height")
    T = s.param("lb_t", 0.5, "wall")
    YC = s.param("lb_corner", 6.3, "corner cut starts across the end")
    A = math.radians(s.param("lb_corner_a", 37, "corner cut angle", unit="deg"))
    s.sketch("Section", (0, 0, 0), (0, 1, 0), (0, 0, 1))                 # normal +X
    s.cmd("sketch.rectangle.two_point", p0=[0, 0], p1=[W, H])
    s.cmd("sketch.rectangle.two_point", p0=[T, T], p1=[W - T, H - T])
    s.finish()
    s.cmd("solid.extrude", distance=L, profiles=[{"point": [T / 2, H / 2]}], name="Tube", body_name=s.body)
    v = (W * H - (W - 2 * T) * (H - 2 * T)) * L
    run = (W - YC) / math.tan(A)
    k = run / (W - YC)
    s.sketch("Corner cuts", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    for m in (lambda x: x, lambda x: L - x):
        s.polyline([(m(-1), YC - 1 / k), (m((W + 1 - YC) * k), W + 1), (m(-1), W + 1)])
    s.finish()
    s.cmd("solid.extrude", distance=H + 2, operation="cut", targets=[s.body], name="Corner cuts")
    tri = (W - YC) * run / 2
    side = k * ((W - YC) ** 2 - (W - T - YC) ** 2) / 2      # the cut's part of the side wall's band
    v -= 2 * (tri * 2 * T + side * (H - 2 * T))
    yc = W / 2
    bottom = [(4.5, 7), (L - 4.5, 7)]
    s.sketch("Bottom holes", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    for x, d in bottom:
        s.cmd("sketch.circle.center", center=[x, yc], diameter=d)
    s.finish()
    s.cmd("solid.extrude", distance=2, operation="cut", targets=[s.body], name="Bottom holes")
    # the Ø4 holes at 11.5 are in both walls: one cut through
    s.sketch("Through holes", (0, 0, H + 1), (1, 0, 0), (0, -1, 0))       # normal -Z
    for x in (11.5, L - 11.5):
        s.cmd("sketch.circle.center", center=[x, -yc], diameter=4)
    s.finish()
    s.cmd("solid.extrude", distance=H + 2, operation="cut", targets=[s.body], name="Through holes")
    # the Ø8 just fills the tube's 8 inside: drawn exactly, it is tangent to the inner faces of the
    # side walls and the cut fails, so it is 0.02 smaller
    top = [(4.5, 4), (L - 4.5, 4), (L / 2, 7.98)]
    s.sketch("Top holes", (0, 0, H + 1), (1, 0, 0), (0, -1, 0))           # normal -Z
    for x, d in top:
        s.cmd("sketch.circle.center", center=[x, -yc], diameter=d)
    for x0, x1 in ((19, 34), (L - 34, L - 19)):
        st, sg = slot_loop((x0, -yc), (x1, -yc), 3.5)
        s.loop(st, sg)
    s.finish()
    s.cmd("solid.extrude", distance=2, operation="cut", targets=[s.body], name="Top holes")
    holes = sum(math.pi / 4 * d * d for _, d in top + bottom) + 2 * (math.pi * 3.5 ** 2 + 7 * 15) + 4 * math.pi * 4
    return v - holes * T


# ----------------------------------------------------------------------------- 2-45
@part("2-45", "Front lighting lampstand", {"housing": "Brass", "reflector": "Stainless Steel",
                                          "stem": "Brass", "washer": "Brass"})
def lampstand(s):
    """Sheet 05, 2-45 (scale 1:1, half section, read from the drawing at 1:1): a brass lamp housing
    19 long: a Ø9 x 7 cup with a 1.5 back wall and Ø7 inside, a Ø13.5 step, a cone out to Ø22 and a
    Ø22 / Ø20 mouth 6 long; a stainless reflector cone 0.5 thick inside it from a Ø6 / Ø7 sleeve to
    Ø20; a Ø4 / Ø3 brass stem tube 30 long entering the cup 4 from its back through a Ø4 hole, and a
    Ø7 / Ø4 x 1 brass washer 2 above the stem's end. The housing's cone wall and the reflector are
    read off the half section (not all dimensioned). Lamp axis = Z, back face on Z = 0; stem along
    -X."""
    n = s.body.split()[0]
    hp = [(0, 0), (4.5, 0), (4.5, 7), (6.75, 7), (11, 12.85), (11, 19), (10, 19), (10, 12.85), (5.8, 8.5),
          (3.5, 8.5), (3.5, 1.5), (0, 1.5)]
    v = s.turned("Housing", hp, body=f"{n} housing")
    s.holes("Stem hole", (-6, 0, 0), (1, 0, 0), [(-6, 0, 4)], 4, depth=4, target=f"{n} housing")
    v -= cross_hole(4.5, 2, 3.5) / 2
    v += s.turned("Reflector", [(3, 6.9), (3.5, 6.9), (3.5, 8.4), (10, 12.85), (10, 13.1), (9.6, 13.1), (3, 8.75)],
                  body=f"{n} reflector")
    s.cmd("solid.cylinder", diameter=4, height=30, base=[-32.5, 0, 4], axis="X", name="Stem", body_name=f"{n} stem")
    s.cmd("solid.cylinder", diameter=3, height=32, base=[-33.5, 0, 4], axis="X", operation="cut",
          targets=[f"{n} stem"], name="Stem bore")
    s.cmd("solid.cylinder", diameter=7, height=1, base=[-30.5, 0, 4], axis="X", name="Washer",
          body_name=f"{n} washer")
    s.cmd("solid.cylinder", diameter=4, height=3, base=[-31.5, 0, 4], axis="X", operation="cut",
          targets=[f"{n} washer"], name="Washer bore")
    return v + math.pi / 4 * (16 - 9) * 30 + math.pi / 4 * (49 - 16) * 1


# ----------------------------------------------------------------------------- rounded polygons
def fillet_polygon(pts, r):
    """A convex counter-clockwise polygon with every corner rounded to radius r, as Script.loop()
    arguments, plus the corner data [(corner, touch1, centre, touch2)]."""
    corners = []
    for i, p in enumerate(pts):
        a, b = pts[i - 1], pts[(i + 1) % len(pts)]
        u1 = _unit((a[0] - p[0], a[1] - p[1], 0))
        u2 = _unit((b[0] - p[0], b[1] - p[1], 0))
        half = math.acos(max(-1.0, min(1.0, u1[0] * u2[0] + u1[1] * u2[1]))) / 2
        t, d = r / math.tan(half), r / math.sin(half)
        bis = _unit((u1[0] + u2[0], u1[1] + u2[1], 0))
        corners.append((p, (p[0] + u1[0] * t, p[1] + u1[1] * t), (p[0] + bis[0] * d, p[1] + bis[1] * d),
                        (p[0] + u2[0] * t, p[1] + u2[1] * t)))
    segs = []
    for p, t1, c, t2 in corners:
        segs += [("line", t1), ("arc", c, t2, True)]
    return corners[-1][3], segs, corners


def in_fillet_polygon(corners, pts, x, y):
    """Is (x, y) inside the rounded polygon (fillet_polygon's corners of the polygon pts)?"""
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        if (b[0] - a[0]) * (y - a[1]) - (b[1] - a[1]) * (x - a[0]) < 0:
            return False
    for p, t1, c, t2 in corners:
        quad = [p, t2, c, t1]                                   # the corner's cut-off zone
        inside = all((q[0] - o[0]) * (y - o[1]) - (q[1] - o[1]) * (x - o[0]) >= 0
                     for o, q in zip(quad, quad[1:] + quad[:1]))
        if inside and math.hypot(x - c[0], y - c[1]) > math.dist(c, t1):
            return False
    return True


# ----------------------------------------------------------------------------- 2-47
@part("2-47", "Motor side cover", {"cover": "Brass", "tab": "Brass"})
def motor_side_cover(s):
    """Sheet 05, 2-47 (flat pattern, scale 1:2; end view 1:3): 0.5 brass, a 302.2 x 99 blank with a
    59.5 x 5 tab under the middle, bent down 90° on R11.5 (inside) at the two bend lines 53.1 apart
    into a U. Each side: a top corner cut 30° from 13 down, an R5 notch at the edge 31 up over a
    4 wide step to the bottom, a trapezoid window (57 top, 41 bottom, 42 high, 19 below the top,
    34 from the bend line, R6 corners). Left side: an 8 wide slot 48 up to its R4 centre, 22.5 + 4
    from the end; right side: an 11 wide slot 27 up to its R5.5 centre, an arch 20 wide and 22 high
    (R8 corners) and an 11 x 2.5 notch. Unfolded with a K-factor of 0.5 (inside 57.6; the end view
    says 58). The tab (one piece with the cover) is a second solid: neither trimming it out of the
    sheet nor joining it on gives a correct result in SolidCraft (see the README). Flat X across, Y up
    from the bottom edge; the middle panel's top face on Z = 0.5, the sides bent down (-Z)."""
    n = s.body.split()[0]
    T = s.param("msc_t", 0.5, "thickness")
    W = s.param("msc_half", 151.1, "half the blank's width")
    H = s.param("msc_h", 99, "height")
    BL = s.param("msc_bends", 53.1, "between the bend lines")
    RB = s.param("msc_r", 11.5, "bend radius, inside")
    TW, TH = s.param("msc_tab_w", 59.5, "tab width"), s.param("msc_tab_h", 5, "tab depth")
    ba = math.pi / 2 * (RB + T / 2)
    fc, fs = BL / 2 - ba / 2, BL / 2 + ba / 2                   # middle panel's half width; sides start
    side = W - fs
    ri, ro = RB, RB + T
    x0 = fc + ri                                                # inside face of the sides
    zb = -RB - side
    m = lambda p: (-p[0], p[1])
    # sheet metal: the flat blank (every edge feature in its outline), the windows cut in the flat,
    # then the two folds. Cutting the edge features out of a bent-up solid U goes wrong in
    # SolidCraft (the cuts come out up to 1.75 too deep on the 0.5 sheet, see the README).
    s.cmd("sheet.manage_rules", name="Lanz 0.5", thickness=f"{T} mm", k_factor="0.5", bend_radius=f"{RB} mm",
          active=True)
    t30 = math.tan(math.radians(30))
    k = 13 * t30
    start = (-(W - 4), 0)
    segs = [("line", (-124.6, 0)), ("line", (-124.6, 48)), ("arc", (-120.6, 48), (-116.6, 48), False),
            ("line", (-116.6, 0)), ("line", (82.25, 0)), ("line", (82.25, 27)), ("arc", (87.75, 27), (93.25, 27), False),
            ("line", (93.25, 0)), ("line", (109.25, 0)), ("line", (109.25, 14)),
            ("arc", (117.25, 14), (117.25, 22), False), ("line", (121.25, 22)), ("arc", (121.25, 14), (129.25, 14), False),
            ("line", (129.25, 2.5)), ("line", (140.25, 2.5)), ("line", (140.25, 0)), ("line", (W - 4, 0)),
            ("line", (W - 4, 31 - 3)), ("arc", (W, 31), (W, 36), False), ("line", (W, H - 13)), ("line", (W - k, H)),
            ("line", (-(W - k), H)), ("line", (-W, H - 13)), ("line", (-W, 36)), ("arc", (-W, 31), (-(W - 4), 28), False),
            ("line", start)]
    s.sketch("Flat pattern", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("sheet.flange", base="Flat pattern", body_name=f"{n} cover")
    win = [(60.55, 38), (101.55, 38), (117.55, 80), (60.55, 80)]
    wstart, wsegs, _ = fillet_polygon(win, 6)
    s.sketch("Windows", (0, 0, T), (1, 0, 0), (0, 1, 0))
    for mm in (1, -1):
        s.loop((mm * wstart[0], wstart[1]), [(sg_[0], (mm * sg_[1][0], sg_[1][1])) if sg_[0] == "line" else
                                             (sg_[0], (mm * sg_[1][0], sg_[1][1]), (mm * sg_[2][0], sg_[2][1]),
                                              sg_[3] if mm > 0 else not sg_[3]) for sg_ in wsegs])
    s.finish()
    s.cmd("solid.extrude", through_all=True, direction="negative", operation="cut", targets=[f"{n} cover"],
          name="Windows")
    for x in (BL / 2, -BL / 2):
        s.cmd("sheet.fold", points=[[x, -2, T], [x, H + 2, T]], angle=90, position="centerline", flip=True,
              fixed=[0, H / 2, T], body=f"{n} cover")
    s.cmd("browser.visibility", visible=False, items=["Flat pattern", "Windows"])
    # the tab: the middle panel and the bends' first phi below the bottom edge
    phi = (TW / 2 - fc) / (RB + T / 2)
    c = (fc, -RB)
    po = (c[0] + ro * math.sin(phi), c[1] + ro * math.cos(phi))
    pi_ = (c[0] + ri * math.sin(phi), c[1] + ri * math.cos(phi))
    s.sketch("Tab", (0, -TH, 0), (1, 0, 0), (0, 0, 1))
    tst = (-fc, T)
    tsg = [("line", (fc, T)), ("arc", c, po, False), ("line", pi_), ("arc", c, (fc, 0), True), ("line", (-fc, 0)),
           ("arc", m(c), m(pi_), True), ("line", m(po)), ("arc", m(c), tst, False)]
    s.loop(tst, tsg)
    s.finish()
    s.cmd("solid.extrude", distance=TH, direction="negative", name="Tab", body_name=f"{n} tab")
    s.cmd("browser.visibility", visible=False, items=["Tab"])
    return (loop_area(start, segs) - 2 * loop_area(wstart, wsegs)) * T + loop_area(tst, tsg) * TH


# ----------------------------------------------------------------------------- 2-48
@part("2-48", "Motor top cover", "Brass")
def motor_top_cover(s):
    """Sheet 05, 2-48 (scale 1:2): a 0.5 brass tray, 123.5 x 59 with R12.5 corners at one end and a
    skirt 14 deep (from the top) round both sides and that end; a Ø34 hole 23 from the round end
    and a 4.5 x 45 slot across, 53 from it. The other end is open. (A line 4 short of the open end
    in the plan, 119.5, is not explained by the views; the skirts are taken to the full length.)
    X along from the round end, Z = 0 the top."""
    L = s.param("mtc_l", 123.5, "length")
    W = s.param("mtc_w", 59, "width (29.5 + 29.5)")
    R = s.param("mtc_r", 12.5, "end corners")
    D = s.param("mtc_skirt", 14, "skirt depth")
    T = s.param("mtc_t", 0.5, "thickness")
    h = W / 2

    def outline(x0, x1, hh, r):
        return (x1, -hh), [("line", (x1, hh)), ("line", (x0 + r, hh)), ("arc", (x0 + r, hh - r), (x0, hh - r), True),
                           ("line", (x0, -hh + r)), ("arc", (x0 + r, -hh + r), (x0 + r, -hh), True), ("line", (x1, -hh))]
    s.sketch("Outline", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    st, sg = outline(0, L, h, R)
    s.loop(st, sg)
    s.finish()
    s.cmd("solid.extrude", distance=D, direction="negative", name="Tray", body_name=s.body)
    v = loop_area(st, sg) * D
    # hollowed with a shell (open underneath and at the square end): cutting the inside out with
    # an extrude took the 0.5 top away as well
    s.cmd("solid.shell", faces=[[L / 2, 0, -D], [L, 0, -D / 2]], thickness=T, direction="inside", name="Shell")
    st2, sg2 = outline(T, L + 1, h - T, R - T)
    v -= (loop_area(st2, sg2) - (h - T) * 2 * 1) * (D - T)
    s.sketch("Holes", (0, 0, 1), (1, 0, 0), (0, -1, 0))                  # normal -Z
    s.cmd("sketch.circle.center", center=[23, 0], diameter=34)
    s.cmd("sketch.rectangle.two_point", p0=[53, -22.5], p1=[57.5, 22.5])
    s.finish()
    s.cmd("solid.extrude", distance=2, operation="cut", targets=[s.body], name="Holes")
    return v - (math.pi * 17 ** 2 + 4.5 * 45) * T


# ----------------------------------------------------------------------------- 2-49
@part("2-49", "Motor side cover air cover", "Steel")
def air_cover(s):
    """Sheet 05, 2-49 (scale 1:2): a steel gauze, 0.5 thick, 69.5 wide at the top, 49.5 at the
    bottom, 52 high, one side square and the other slanted, R11 corners. The gauze (0.5 wire, 2.0
    openings at 2.5, measured) is modelled as a 0.5 sheet with 2 x 2 square holes at a 2.5 pitch;
    the openings cut by the edge are left closed. X across from the square side, Y up."""
    T = s.param("ac_t", 0.5, "thickness")
    WT = s.param("ac_top", 69.5, "top width")
    WB = s.param("ac_bottom", 49.5, "bottom width")
    H = s.param("ac_h", 52, "height")
    P, O = 2.5, 2.0
    pts = [(0, 0), (WB, 0), (WT, H), (0, H)]
    st, sg, corners = fillet_polygon(pts, 11)
    s.sketch("Gauze", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(st, sg)
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Gauze", body_name=s.body)
    holes = []
    for i in range(int(WT / P) + 1):
        for j in range(int(H / P) + 1):
            x0, y1 = 0.5 + i * P, H - 0.5 - j * P
            sq = [(x0, y1 - O), (x0 + O, y1 - O), (x0 + O, y1), (x0, y1)]
            if all(in_fillet_polygon(corners, pts, x, y) for x, y in sq):
                holes.append(sq)
    s.sketch("Openings", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    for sq in holes:
        s.polyline(sq)
    s.finish()
    s.cmd("solid.extrude", distance=T + 2, operation="cut", targets=[s.body], name="Openings")
    return (loop_area(st, sg) - len(holes) * O * O) * T


# ----------------------------------------------------------------------------- 3-01
@part("3-01", "Chassis rear end", "Aluminum")
def chassis_rear_end(s):
    """Sheet 05, 3-01 (scale 1:2, read with the vector lines): a 6 thick aluminium plate 118 long:
    28 at 56 wide, then 90 at 128 wide, an 8 wide relief with an R4 end cut 4 into the wide part at
    each step. Holes: A = Ø4 at (12, ±24), (66, ±24), (34, ±59), (62, ±59); B = M4 (Ø3.3) at
    (78, ±54), (108, ±54), (79, -5); C = M6 (Ø5) at (108, 0), (104, -32); D = Ø8 at (70.5, -5); an
    8 wide slot from (40, -5) to (50, -5). Under the narrow end a flange 6 thick, 56 wide, 31.5 deep
    (measured), with Ø6 holes 6 (at ±16) and 24 (at 0) from its edge. X along from the narrow end,
    Z = 0 the plate's underside."""
    T = s.param("cre_t", 6, "plate thickness")
    LN, WN = s.param("cre_narrow_l", 28, "narrow end length"), s.param("cre_narrow_w", 56, "narrow end width")
    L, W = s.param("cre_l", 118, "length (28 + 90)"), s.param("cre_w", 128, "width (64 + 64)")
    DF = s.param("cre_flange_d", 31.5, "flange depth below the plate (measured)")
    a, b = WN / 2, W / 2
    start = (0, -a)
    segs = [("line", (LN + 4, -a)), ("arc", (LN + 4, -a - 4), (LN + 4, -a - 8), False), ("line", (LN, -a - 8)),
            ("line", (LN, -b)), ("line", (L, -b)), ("line", (L, b)), ("line", (LN, b)), ("line", (LN, a + 8)),
            ("line", (LN + 4, a + 8)), ("arc", (LN + 4, a + 4), (LN + 4, a), False), ("line", (0, a)), ("line", start)]
    holes = ([((x, y), 4) for x in (12, 66) for y in (24, -24)] + [((x, y), 4) for x in (34, 62) for y in (59, -59)]
             + [((x, y), 3.3) for x in (78, 108) for y in (54, -54)] + [((79, -5), 3.3), ((108, 0), 5), ((104, -32), 5),
                                                                        ((70.5, -5), 8)])
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    for (x, y), d in holes:
        s.cmd("sketch.circle.center", center=[x, y], diameter=d)
    st, sg = slot_loop((40, -5), (50, -5), 4)
    s.loop(st, sg)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [1, 0]}], name="Plate", body_name=s.body)
    v = (loop_area(start, segs) - sum(math.pi / 4 * d * d for _, d in holes) - loop_area(st, sg)) * T
    # the flange reaches 1 into the plate so the two overlap
    s.sketch("Flange", (0, 0, -DF), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[0, -a], p1=[6, a])
    s.finish()
    s.cmd("solid.extrude", distance=DF + 1, operation="join", targets=[s.body], name="Flange")
    v += 6 * WN * DF
    s.holes("Flange holes", (-1, 0, 0), (1, 0, 0), [(-1, 16, -DF + 6), (-1, -16, -DF + 6), (-1, 0, -DF + 24)], 6, depth=8)
    return v - 3 * math.pi * 9 * 6


# ----------------------------------------------------------------------------- 3-02
@part("3-02", "Rear axle support bracket", "Aluminum")
def rear_axle_support_bracket(s):
    """Sheet 05, 3-02 (scale 1:2, read with the vector lines): an aluminium block 40 wide, 60 high
    and 10 thick, bored Ø24 18 above its foot and split by a 4 wide slot from the bore to one side;
    the clamp screw 16 from the centre: Ø5 up from the foot to the slot, M4 (Ø3.3) 18 deep above it;
    two M4 (Ø3.3) x 20 in the top at ±14. X across, Y up from the foot, Z through the thickness."""
    W, H, T = s.param("ras_w", 40, "width (20 + 20)"), s.param("ras_h", 60, "height"), s.param("ras_t", 10, "thickness")
    YB = s.param("ras_bore_y", 18, "bore above the foot")
    D = s.param("ras_bore_d", 24, "bore")
    S = s.param("ras_slot", 4, "slot width")
    XS = s.param("ras_screw_x", 16, "clamp screw from the centre (20 - 4)")
    R = D / 2
    s.sketch("Block", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-W / 2, 0], p1=[W / 2, H])
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Block", body_name=s.body)
    xe = math.sqrt(R * R - (S / 2) ** 2)
    start = (xe, YB + S / 2)
    segs = [("line", (W / 2 + 1, YB + S / 2)), ("line", (W / 2 + 1, YB - S / 2)), ("line", (xe, YB - S / 2)),
            ("arc", (0, YB), start, False)]
    s.sketch("Bore and slot", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T + 2, operation="cut", targets=[s.body], name="Bore and slot")
    open_ = loop_area(start, segs) - 1 * S                     # less the part outside the block
    s.holes("Clamp screw clearance", (0, -1, 0), (0, 1, 0), [(XS, -1, T / 2)], 5, depth=YB - S / 2 + 2)
    s.holes("Clamp screw thread", (0, YB, 0), (0, 1, 0), [(XS, YB, T / 2)], 3.3, depth=S / 2 + 18)
    s.holes("M4 tapped", (0, H + 1, 0), (0, -1, 0), [(14, H + 1, T / 2), (-14, H + 1, T / 2)], 3.3, depth=21)
    v = (W * H - open_) * T
    return v - math.pi * 6.25 * (YB - S / 2) - math.pi / 4 * 3.3 ** 2 * (18 + 2 * 20)


# ----------------------------------------------------------------------------- 3-03 to 3-06
def pcd_holes(s, name, z0, depth, d, n=8, pcd=52, start_deg=22.5, target=None):
    """n holes of diameter d on a PCD round the Z axis, drilled up from Z = z0; turned off the
    revolve's seam (a cut across the seam needs a separation retry)."""
    ctr = [(pcd / 2 * math.cos(math.radians(start_deg + i * 360 / n)),
            pcd / 2 * math.sin(math.radians(start_deg + i * 360 / n)), z0) for i in range(n)]
    s.holes(name, (0, 0, z0), (0, 0, 1), ctr, d, depth=depth, target=target)
    return n * math.pi / 4 * d * d


@part("3-03", "Differential housing part-1", "Steel")
def diff_housing_1(s):
    """Sheet 05, 3-03 (scale 1:1.5, read from the section's lines): a Ø13 x 12 tube, a Ø20 x 8 hub, a
    Ø60 x 2 flange with 8 x Ø4 on a Ø52 PCD and a Ø42 x 2 spigot; bored Ø9 through the tube, Ø8 for
    4 and Ø14 8 deep from the spigot's face. Axis = Z, the tube's end on Z = 0. The holes are drawn
    at 0° and 45°; here they are turned 22.5° (a round part does not notice)."""
    v = s.turned("Housing", [(4.5, 0), (6.5, 0), (6.5, 12), (10, 12), (10, 20), (30, 20), (30, 22), (21, 22), (21, 24),
                             (7, 24), (7, 16), (4, 16), (4, 12), (4.5, 12)])
    return v - pcd_holes(s, "Ø4 holes", 19, 4, 4) * 2           # through the 2 flange


@part("3-04", "Differential housing part-2", "Steel")
def diff_housing_2(s):
    """Sheet 05, 3-04 (scale 1:2, read from the section's lines): a Ø13 x 12 tube and a Ø20 x 8 hub
    like 3-03, then a Ø46 body 28 long with a Ø42 bore 28 deep (4 wall) and a Ø60 x 4 flange with
    8 x M4 (Ø3.3) on the Ø52 PCD matching 3-03; bored Ø9, Ø8 and Ø14 like 3-03; a Ø6 radial hole 15
    from the flange face. Axis = Z, the tube's end on Z = 0; the holes turned 22.5° as on 3-03 and the
    radial hole at 45°."""
    v = s.turned("Housing", [(4.5, 0), (6.5, 0), (6.5, 12), (10, 12), (10, 20), (23, 20), (23, 48), (30, 48), (30, 52),
                             (21, 52), (21, 24), (7, 24), (7, 16), (4, 16), (4, 12), (4.5, 12)])
    v -= pcd_holes(s, "M4 tapped", 47, 6, 3.3) * 4             # through the 4 flange
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("Ø6 radial", (25 * u[0], 25 * u[1], 0), (-u[0], -u[1], 0), [(25 * u[0], 25 * u[1], 37)], 6, depth=5)
    return v - cross_hole(23, 3, 21) / 2


@part("3-05", "Rear axle main bearing housing part-1", "Aluminum")
def bearing_housing_1(s):
    """Sheet 05, 3-05 (scale 1:2, steps read from the lines): a Ø24 x 13.5 tube and a Ø38 x 12 flange;
    bored Ø20 7 deep, Ø18, and Ø32 10 deep from the flange face. Axis = Z."""
    return s.turned("Housing", [(10, 0), (12, 0), (12, 13.5), (19, 13.5), (19, 25.5), (16, 25.5), (16, 15.5), (9, 15.5),
                                (9, 7), (10, 7)])


@part("3-06", "Rear axle main bearing housing part-2", "Aluminum")
def bearing_housing_2(s):
    """Sheet 05, 3-06 (scale 1:2, steps read from the lines): as 3-05 with a 40.5 long tube: Ø24 x 40.5
    and Ø38 x 12; bored Ø20 7 deep, Ø18, and Ø32 10 deep. Axis = Z."""
    return s.turned("Housing", [(10, 0), (12, 0), (12, 40.5), (19, 40.5), (19, 52.5), (16, 52.5), (16, 42.5), (9, 42.5),
                                (9, 7), (10, 7)])


# ----------------------------------------------------------------------------- 3-07 to 3-17
def revolved_loop(s, name, start, segs, body=None, operation="new"):
    """Revolve a (r, z) loop with arcs about Z (Script.loop arguments in the XZ half plane)."""
    s.sketch(f"{name} section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.loop(start, segs)
    s.finish()
    extra = {"body_name": body or s.body} if operation == "new" else {"targets": [body or s.body]}
    s.cmd("solid.revolve", axis="Z", operation=operation, name=name, **extra)


def spandrel_ring(r_corner, rad, inward=True):
    """Volume of the ring a radius `rad` round removes from (or adds to) a circular corner edge at
    radius r_corner: the spandrel (1 - pi/4) rad² about its centroid."""
    k = (10 - 3 * math.pi) / (12 - 3 * math.pi) * rad
    return 2 * math.pi * (r_corner - k if inward else r_corner + k) * (1 - math.pi / 4) * rad * rad


@part("3-07", "Rear axle main housing ball bearing-1", "Steel")
def ball_bearing_1(s):
    """Sheet 06, 3-07: a bought-in ball bearing Ø32 / Ø13, 10 thick (as drawn), modelled as its
    envelope. Axis = Z."""
    return s.turned("Bearing", [(6.5, 0), (16, 0), (16, 10), (6.5, 10)])


@part("3-08", "Rear axle main housing ball bearing-2", "Steel")
def ball_bearing_2(s):
    """Sheet 06, 3-08: a bought-in ball bearing Ø20 / Ø8, 8 thick, modelled as its envelope. Axis = Z."""
    return s.turned("Bearing", [(4, 0), (10, 0), (10, 8), (4, 8)])


def rear_axle(s, L):
    D, DE, LE = 8, 6, 13
    v = s.turned("Axle", [(0, 0), (D / 2, 0), (D / 2, L), (DE / 2, L), (DE / 2, L + LE), (0, L + LE)])
    s.cmd("solid.cylinder", diameter=4.5, height=21, base=[-10.5, 0, 12.5], axis="X", operation="join",
          targets=[s.body], name="Cross pin")
    return v + math.pi / 4 * 4.5 ** 2 * 21 - cross_hole(D / 2, 2.25)


@part("3-09A", "Rear axle-1", "Steel")
def rear_axle_1(s):
    """Sheet 06, 3-09A (scale 1:2): a Ø8 x 67 steel axle with a Ø6 x 13 end and a Ø4.5 x 21 cross pin
    (pressed in) 12.5 from the other end. Axis = Z, the pin along X."""
    return rear_axle(s, s.param("ra_l", 67, "Ø8 length"))


@part("3-09B", "Rear axle-2", "Steel")
def rear_axle_2(s):
    """Sheet 06, 3-09B (scale 1:2): as 3-09A with the Ø8 part 94 long. Axis = Z."""
    return rear_axle(s, s.param("ra_l", 94, "Ø8 length"))


@part("3-10", "Differential gear wheel", "Brass")
def diff_gear(s):
    """Sheet 06, 3-10 (scale 1:1, from the lines): a brass bevel gear on a 90° pitch cone: the back
    face to Ø15.1, a 45° back cone to the Ø21.1 tips 3 out, the face cone at 45° down to the Ø13 hub
    4 further, the hub 7.5 long with an R2 end; reamed Ø6. Modelled as the gear blank: the teeth
    (about 20, not dimensioned) are not cut. Axis = Z, the back face on Z = 0."""
    zt, zh, zl = 2.96, 6.98, 14.49
    start = (3, 0)
    segs = [("line", (7.56, 0)), ("line", (10.52, zt)), ("line", (6.5, zh)), ("line", (6.5, zl - 2)),
            ("arc", (4.5, zl - 2), (4.5, zl), True), ("line", (3, zl)), ("line", start)]
    revolved_loop(s, "Blank", start, segs)
    pts = [(3, 0), (7.56, 0), (10.52, zt), (6.5, zh), (6.5, zl), (3, zl)]
    return revolved_volume(pts) - spandrel_ring(6.5, 2)


@part("3-11", "Differential gear wheel shaft", "Stainless Steel")
def diff_gear_shaft(s):
    """Sheet 06, 3-11 (scale 1:1.5): a Ø6 x 45.5 stainless shaft, tapped M4 (Ø3.3) 10 deep at both
    ends. Axis = Z."""
    L = s.param("dgs_l", 45.5, "length")
    return s.turned("Shaft", [(1.65, 0), (3, 0), (3, L), (1.65, L), (1.65, L - 10), (0, L - 10), (0, 10), (1.65, 10)])


@part("3-13", "Rear wheel spacer", "Brass")
def rear_wheel_spacer(s):
    """Sheet 06, 3-13 (scale 1:1.5): a brass spool: Ø19 x 2 flanges 15 apart on a Ø12 body with R2
    roots, bored Ø8. Axis = Z."""
    start = (4, 0)
    segs = [("line", (9.5, 0)), ("line", (9.5, 2)), ("line", (8, 2)), ("arc", (8, 4), (6, 4), False),
            ("line", (6, 15)), ("arc", (8, 15), (8, 17), False), ("line", (9.5, 17)), ("line", (9.5, 19)),
            ("line", (4, 19)), ("line", start)]
    revolved_loop(s, "Spool", start, segs)
    pts = [(4, 0), (9.5, 0), (9.5, 2), (6, 2), (6, 17), (9.5, 17), (9.5, 19), (4, 19)]
    return revolved_volume(pts) + 2 * spandrel_ring(6, 2, inward=False)


@part("3-14", "Rear wheel mounting plate", "Steel")
def rear_wheel_mounting_plate(s):
    """Sheet 06, 3-14 (scale 1:1.5, section A-A): a Ø42 x 5 steel flange between a Ø20 x 6 and a
    Ø20 x 13 hub, bored Ø8; 5 x M4 (Ø3.3) on a Ø32 PCD (72° apart, one at the top); a Ø4.5 cross
    hole through the long hub 8 from the flange. Axis = Z; the cross hole at 45° (off the seam)."""
    v = s.turned("Plate", [(4, 0), (10, 0), (10, 6), (21, 6), (21, 11), (10, 11), (10, 24), (4, 24)])
    v -= pcd_holes(s, "M4 tapped", 5, 7, 3.3, n=5, pcd=32, start_deg=90) * 5
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("Ø4.5 cross hole", (12 * u[0], 12 * u[1], 0), (-u[0], -u[1], 0), [(12 * u[0], 12 * u[1], 19)], 4.5)
    return v - cross_hole(10, 2.25, 4)


@part("3-17", "Rear wheel hub cap", "Brass")
def rear_hub_cap(s):
    """Sheet 06, 3-17 (scale 1:1, from a 1000 dpi render): a Ø20 x 2 brass cap with a Ø14 recess 1
    deep in its face; on the back a split spigot Ø7 x 5, bored Ø5.5 (measured), with a barb to Ø8
    over its last 2 and a 1 wide cross slot along its length. Axis = Z, the face on Z = 0; the slot
    turned 45° (off the seam)."""
    start = (0, 1)
    pts = [(0, 1), (7, 1), (7, 0), (10, 0), (10, 2), (3.5, 2), (3.5, 5), (3.95, 5), (3.5, 7), (2.75, 7), (2.75, 2), (0, 2)]
    v = s.turned("Cap", pts)
    c, w, a = math.cos(math.radians(45)), 0.5, 5
    cross = []
    for k in range(4):                                       # a plus sign, arms 5 long, turned 45°
        ang = math.radians(45 + 90 * k)
        ux, uy, nx, ny = math.cos(ang), math.sin(ang), -math.sin(ang), math.cos(ang)
        cross += [(w * ux - w * nx, w * uy - w * ny), (a * ux - w * nx, a * uy - w * ny), (a * ux + w * nx, a * uy + w * ny)]
    s.sketch("Cross slot", (0, 0, 7.5), (1, 0, 0), (0, -1, 0))             # normal -Z
    s.polyline([(x, -y) for x, y in cross])
    s.finish()
    s.cmd("solid.extrude", distance=5.5, operation="cut", targets=[s.body], name="Cross slot")
    # the slots take a 1 wide strip of the spigot's wall on each of the four sides
    n, cut = 400, 0.0
    for i in range(n):
        z = 2 + (i + 0.5) * 5 / n
        R = 3.5 if z < 5 else 3.95 - 0.225 * (z - 5)
        h, strip = 1.0 / 200, 0.0
        for j in range(200):
            y = -0.5 + (j + 0.5) * h
            strip += (math.sqrt(R * R - y * y) - math.sqrt(2.75 ** 2 - y * y)) * h
        cut += 4 * strip * 5 / n
    return v - cut


# ----------------------------------------------------------------------------- 3-15 to 3-25
def revolved_loop_volume(start, segs, n=720):
    """Volume of a Script.loop() (r, z) boundary revolved about Z, its arcs split finely."""
    pts, p = [start], start
    for seg in segs:
        if seg[0] == "line":
            p = seg[1]
            pts.append(p)
        else:
            _, c, e, ccw = seg
            r = math.dist(c, p)
            t0, t1 = math.atan2(p[1] - c[1], p[0] - c[0]), math.atan2(e[1] - c[1], e[0] - c[0])
            sweep = (t1 - t0) % (2 * math.pi) if ccw else -((t0 - t1) % (2 * math.pi))
            for i in range(1, n + 1):
                t = t0 + sweep * i / n
                pts.append((c[0] + r * math.cos(t), c[1] + r * math.sin(t)))
            p = e
    return revolved_volume(pts[:-1])


def tray_outline(w, h, rt, rb, d=0.0):
    """A w x h outline (X centred, Y from 0 up) with top corners rt and bottom corners rb, offset
    inward by d, as Script.loop() arguments."""
    a, y0, y1, t, b = w / 2 - d, d, h - d, rt - d, rb - d
    start = (-a + b, y0)
    return start, [("line", (a - b, y0)), ("arc", (a - b, y0 + b), (a, y0 + b), True), ("line", (a, y1 - t)),
                   ("arc", (a - t, y1 - t), (a - t, y1), True), ("line", (-a + t, y1)),
                   ("arc", (-a + t, y1 - t), (-a, y1 - t), True), ("line", (-a, y0 + b)),
                   ("arc", (-a + b, y0 + b), start, True)]


@part("3-15", "Rear wheel rim", "Aluminum")
def rear_rim(s):
    """Sheet 06, 3-15 (section B-B, scale 1:2, read from the lines): a pressed aluminium rim about
    2 thick: Ø142 lips 1 wide, 45° sides to a Ø132 floor 14 wide, Ø136 inside the lips, Ø128 inside
    the floor; a 3 thick web offset by a 45° step from Ø112 / Ø109.5 to Ø100 / Ø97.5, bored Ø20 with
    5 x Ø4 on a Ø32 PCD (as 3-14). Axis = Z, one lip's face on Z = 0."""
    pts = [(68, 0), (71, 0), (71, 1), (66, 6), (66, 20), (71, 25), (71, 26), (68, 26), (68, 25), (64, 21), (64, 13),
           (54.75, 13), (48.75, 7), (10, 7), (10, 4), (50, 4), (56, 10), (64, 10), (64, 5), (68, 1)]
    v = s.turned("Rim", pts)
    return v - pcd_holes(s, "Ø4 holes", 3, 5, 4, n=5, pcd=32, start_deg=90) * 3


@part("3-16", "Rear wheel tyre", "Default")
def rear_tyre(s):
    """Sheet 06, 3-16: a rubber ring, Ø33.8 section on a 132 inside diameter (the rim's floor): a
    torus. Default density (1.29) with the black rubber appearance, as 2-32."""
    DS = s.param("rt_section", 33.8, "section")
    DI = s.param("rt_inside", 132, "inside diameter")
    rc = DI / 2 + DS / 2
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    s.cmd("sketch.circle.center", center=[rc, 0], diameter=DS)
    s.finish()
    s.cmd("solid.revolve", axis="Z", name="Tyre", body_name=s.body)
    s.cmd("appearance.assign", bodies=[s.body], appearance="Rubber - Black")
    return 2 * math.pi ** 2 * rc * (DS / 2) ** 2


@part("3-18", "Rear wheel drive gear wheel", "Brass")
def rear_drive_gear(s):
    """Sheet 06, 3-18 (scale 1:1.5): a 2.5 thick brass gear, 57 teeth, Ø78.8 over the tips, Ø73.5 at
    the roots, the teeth 1 wide at the tip and 2.5 at the root (their R5 flanks straightened); bored
    Ø20 with 8 x Ø4 on a Ø52 PCD (as 3-03). XY plane, Z = 0..2.5."""
    N = s.param("rdg_teeth", 57, "teeth", unit="")
    RT, RR = s.param("rdg_tip_d", 78.8, "tip diameter") / 2, s.param("rdg_root_d", 73.5, "root diameter") / 2
    T = s.param("rdg_t", 2.5, "thickness")
    at, ar = math.asin(0.5 / RT), math.asin(1.25 / RR)
    pts = []
    for k in range(int(N)):
        t = 2 * math.pi * k / N
        for r, a in ((RR, t - ar), (RT, t - at), (RT, t + at), (RR, t + ar)):
            pts.append((r * math.cos(a), r * math.sin(a)))
    holes = [(0, 0, 20)] + [(26 * math.cos(i * math.pi / 4), 26 * math.sin(i * math.pi / 4), 4) for i in range(8)]
    s.sketch("Gear", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(pts)
    for x, y, d in holes:
        s.cmd("sketch.circle.center", center=[round(x, 6), round(y, 6)], diameter=d)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [33, 0]}], name="Gear", body_name=s.body)
    return (polygon_area(pts) - sum(math.pi / 4 * d * d for _, _, d in holes)) * T


@part("3-19", "Drivers console side frame", "Aluminum")
def console_side_frame(s):
    """Sheet 06, 3-19 (scale 1:1.5): an 8 thick aluminium frame: a foot 72 long, its end 8 high with
    a 45° corner up to 16, and an upright 39 wide, 81.5 high (R4 into the foot); in its back edge a
    notch 17.5 deep from 8 to 39 up (R3 corners), a slope 6 in over the 10 above it. A Ø10 hole at
    (21.5, 61), a Ø4 at (58, 10); M4 (Ø3.3): 10 deep in the top at 6 and at 32 tilted 15°, two 10
    deep in the front edge at 61 (into the Ø10) and 45 up (measured), one through the foot at 12 and one 9 deep at 66 in the
    underside. X along from the back edge, Y up, Z = 0..8."""
    T = s.param("csf_t", 8, "thickness")
    start = (0, 0)
    segs = [("line", (72, 0)), ("line", (72, 8)), ("line", (64, 16)), ("line", (43, 16)), ("arc", (43, 20), (39, 20), False),
            ("line", (39, 81.5)), ("line", (0, 81.5)), ("line", (0, 49)), ("line", (6, 39)), ("line", (14.5, 39)),
            ("arc", (14.5, 36), (17.5, 36), False), ("line", (17.5, 11)), ("arc", (14.5, 11), (14.5, 8), False),
            ("line", (0, 8)), ("line", start)]
    s.sketch("Frame", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[21.5, 61], diameter=10)
    s.cmd("sketch.circle.center", center=[58, 10], diameter=4)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [30, 5]}], name="Frame", body_name=s.body)
    v = (loop_area(start, segs) - math.pi * 25 - math.pi * 4) * T
    zc = T / 2
    s.holes("M4 top", (0, 82.5, 0), (0, -1, 0), [(6, 82.5, zc)], 3.3, depth=11)
    u = (math.sin(math.radians(15)), -math.cos(math.radians(15)), 0)
    p0 = (32 - 2 * u[0], 81.5 - 2 * u[1], 0)
    s.holes("M4 top, 15°", p0, u, [(p0[0], p0[1], zc)], 3.3, depth=12)
    s.holes("M4 front", (40, 0, 0), (-1, 0, 0), [(40, 45, zc)], 3.3, depth=11)
    s.holes("M4 front, into the Ø10", (40, 0, 0), (-1, 0, 0), [(40, 61, zc)], 3.3, depth=15)
    # the one at 12 goes through the foot into the notch: drilled on past the notch's floor
    s.holes("M4 underside", (0, -1, 0), (0, 1, 0), [(12, -1, zc)], 3.3, depth=10.5)
    # 9 deep (not 8: a hole ending in the plane of the notch's floor, Y = 8, needs a separation
    # retry that leaves it 2.5 deeper, although the two faces are far apart)
    s.holes("M4 underside, end", (0, -1, 0), (0, 1, 0), [(66, -1, zc)], 3.3, depth=10)
    a = math.pi / 4 * 3.3 ** 2
    h, into_bore = 3.3 / 400, 0.0                     # the front M4 at 61 runs from X = 39 into the Ø10
    for i in range(400):
        y = -1.65 + (i + 0.5) * h
        into_bore += 2 * math.sqrt(1.65 ** 2 - y * y) * (39 - 21.5 - math.sqrt(25 - y * y)) * h
    return v - a * (10 + 10 + 10 + 8 + 9) - into_bore


@part("3-21", "Accelerator control lever", {"lever": "Steel", "collar": "Brass"})
def accelerator_control_lever(s):
    """Sheet 06, 3-21 (scale 1:1.5): a 2 thick steel lever: an R6 end round a Ø8 hole, tapering to
    6 wide 36 up, then a 4 wide tip 14 long; an M3 (Ø2.5) 18 up. A brass collar Ø12 x 6 with a Ø8
    spigot pressed into the lever (8PF), bored Ø4, an M3 (Ø2.5) set screw 3 from the lever. Lever in
    the XY plane on Z = 0..2, the collar on Z = 2..8."""
    n = s.body.split()[0]
    tr = tangent_from((3, 36), (0, 0), 6, left=True)
    tl = (-tr[0], tr[1])
    start = (2, 50)
    segs = [("line", (-2, 50)), ("line", (-2, 36)), ("line", (-3, 36)), ("line", tl), ("arc", (0, 0), tr, True),
            ("line", (3, 36)), ("line", (2, 36)), ("line", start)]
    s.sketch("Lever", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=8)
    s.cmd("sketch.circle.center", center=[0, 18], diameter=2.5)
    s.finish()
    s.cmd("solid.extrude", distance=2, profiles=[{"point": [0, 30]}], name="Lever", body_name=f"{n} lever")
    v = (loop_area(start, segs) - math.pi * 16 - math.pi / 4 * 6.25) * 2
    v += s.turned("Collar", [(2, 0), (4, 0), (4, 2), (6, 2), (6, 8), (2, 8)], body=f"{n} collar")
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("M3 set screw", (7 * u[0], 7 * u[1], 0), (-u[0], -u[1], 0), [(7 * u[0], 7 * u[1], 5)], 2.5, depth=5,
            target=f"{n} collar")
    return v - cross_hole(6, 1.25, 2) / 2


@part("3-22", "Accelerator control lever handle", "Brass")
def accelerator_lever_handle(s):
    """Sheet 06, 3-22: a brass knob 18.5 high: tapering from Ø6 at the foot to about Ø8.4 at 14
    (measured), an R2 shoulder into an R4.5 dome; a 4 x 2 slot 14 deep in the foot for the lever's
    tip. Axis = Z, the foot on Z = 0."""
    p0, p1, S, R, RF = (3, 0), (4.2, 14), (0, 14), 4.5, 2
    L = math.dist(p0, p1)
    u = ((p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L)
    nn = (-u[1], u[0])                                         # toward the axis
    # fillet centre C = p0 + t u + RF nn with |C - S| = R - RF
    q = (p0[0] + RF * nn[0] - S[0], p0[1] + RF * nn[1] - S[1])
    bq = q[0] * u[0] + q[1] * u[1]
    t = -bq + math.sqrt(bq * bq - (q[0] ** 2 + q[1] ** 2 - (R - RF) ** 2))
    C = (p0[0] + t * u[0] + RF * nn[0], p0[1] + t * u[1] + RF * nn[1])
    T1 = (p0[0] + t * u[0], p0[1] + t * u[1])
    d = math.dist(C, S)
    T2 = (S[0] + R * (C[0] - S[0]) / d, S[1] + R * (C[1] - S[1]) / d)
    start = (0, 0)
    segs = [("line", p0), ("line", T1), ("arc", C, T2, True), ("arc", S, (0, S[1] + R), True), ("line", start)]
    revolved_loop(s, "Knob", start, segs)
    s.sketch("Slot", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-2, -1], p1=[2, 1])
    s.finish()
    s.cmd("solid.extrude", distance=15, operation="cut", targets=[s.body], name="Slot")
    return revolved_loop_volume(start, segs) - 4 * 2 * 14


@part("3-25A", "Drivers seat base", "Brass")
def seat_base(s):
    """Sheet 06, 3-25A (scale 1:2): a brass tray 62 x 51 (R19 corners at the back, R10 at the front)
    and 6 high: a 1 plate and a 6 x 5 x 1 angle round its edge (inside R18 / R9). Ø2.5 pilot holes:
    four 32 from the front at ±4 and ±18.5, two in the back wall at ±4, 3.5 below its top; a Ø3 for
    the leg 12.3 from the front. X across, Y from the front edge, Z up."""
    W, H, RT, RB, Ht = 62, 51, 19, 10, 6
    st0, sg0 = tray_outline(W, H, RT, RB)
    s.sketch("Outline", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(st0, sg0)
    s.finish()
    s.cmd("solid.extrude", distance=Ht, name="Tray", body_name=s.body)
    # drilled before the tray is hollowed, 0.5 past the wall (drilled into the hollow tray the cut
    # fails); the holes' lower edge (Z 1.25 .. 2) nicks the angle's flat leg over that 0.5
    s.holes("Back wall holes", (0, H + 1, 0), (0, -1, 0), [(-4, H + 1, Ht - 3.5), (4, H + 1, Ht - 3.5)], 2.5, depth=2.5)
    st6, sg6 = tray_outline(W, H, RT, RB, 6)
    st1, sg1 = tray_outline(W, H, RT, RB, 1)
    s.sketch("Inside the angle", (0, 0, Ht + 1), (1, 0, 0), (0, -1, 0))   # normal -Z
    s.loop((st6[0], -st6[1]), [(g[0], (g[1][0], -g[1][1])) if g[0] == "line" else
                               (g[0], (g[1][0], -g[1][1]), (g[2][0], -g[2][1]), not g[3]) for g in sg6])
    s.finish()
    s.cmd("solid.extrude", distance=Ht, operation="cut", targets=[s.body], name="Inside the angle")
    s.sketch("Inside the wall", (0, 0, Ht + 1), (1, 0, 0), (0, -1, 0))
    s.loop((st1[0], -st1[1]), [(g[0], (g[1][0], -g[1][1])) if g[0] == "line" else
                               (g[0], (g[1][0], -g[1][1]), (g[2][0], -g[2][1]), not g[3]) for g in sg1])
    s.finish()
    s.cmd("solid.extrude", distance=5, operation="cut", targets=[s.body], name="Inside the wall")
    a0, a1, a6 = loop_area(st0, sg0), loop_area(st1, sg1), loop_area(st6, sg6)
    v = a0 * Ht - a6 * (Ht - 1) - (a1 - a6) * (Ht - 2)
    pl = [(-18.5, 32), (-4, 32), (4, 32), (18.5, 32)]
    s.sketch("Plate holes", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    for x, y in pl:
        s.cmd("sketch.circle.center", center=[x, y], diameter=2.5)
    s.cmd("sketch.circle.center", center=[0, 12.3], diameter=3)
    s.finish()
    s.cmd("solid.extrude", distance=2.5, operation="cut", targets=[s.body], name="Plate holes")
    r, dd = 1.25, 0.5
    nick = (r * r * math.acos(dd / r) - dd * math.sqrt(r * r - dd * dd)) * 0.5
    return v - (4 * math.pi / 4 * 6.25 + math.pi / 4 * 9) * 1 - 2 * (math.pi / 4 * 6.25 * 1 + nick)


@part("3-25B", "Drivers seat", "Oak")
def seat(s):
    """Sheet 06, 3-25B (scale 1:2): a wooden seat: a 60 x 49 x 4 slab (R18 / R9) that fits inside
    3-25A's wall, under a 62 x 51 x 6 top (R19 / R10) with its upper edges rounded R6 (modelled R5:
    SolidCraft refuses rounds of 5.5 and more on the 6 high top). Oak density. X across, Y from the front, Z = 0 the
    slab's underside."""
    W, H, RT, RB = 62, 51, 19, 10
    st1, sg1 = tray_outline(W, H, RT, RB, 1)
    st0, sg0 = tray_outline(W, H, RT, RB)
    s.sketch("Slab", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(st1, sg1)
    s.finish()
    s.cmd("solid.extrude", distance=4.5, name="Slab", body_name=s.body)    # 0.5 into the top
    s.sketch("Top", (0, 0, 4), (1, 0, 0), (0, 1, 0))
    s.loop(st0, sg0)
    s.finish()
    s.cmd("solid.extrude", distance=6, operation="join", targets=[s.body], name="Top")
    RF = 5
    edges = [[0, 0, 10], [0, H, 10], [W / 2, H / 2, 10], [-W / 2, H / 2, 10]]
    for cx, cy, r, ang in ((W / 2 - RB, RB, RB, -45), (W / 2 - RT, H - RT, RT, 45), (-W / 2 + RT, H - RT, RT, 135),
                           (-W / 2 + RB, RB, RB, -135)):
        edges.append([round(cx + r * math.cos(math.radians(ang)), 6), round(cy + r * math.sin(math.radians(ang)), 6), 10])
    s.cmd("solid.fillet", edges=edges, radius=RF, name="Top round")
    a1, a0 = loop_area(st1, sg1), loop_area(st0, sg0)
    k = (10 - 3 * math.pi) / (12 - 3 * math.pi) * RF
    spandrel = (1 - math.pi / 4) * RF * RF
    path = (W - 2 * RT) + (W - 2 * RB) + 2 * (H - RT - RB) + math.pi * (RT - k) + math.pi * (RB - k)
    return a1 * 4 + a0 * 6 - spandrel * path


# ----------------------------------------------------------------------------- 3-26A
def line_meet(p, d, y):
    """Where the line through p along d reaches height y."""
    t = (y - p[1]) / d[1]
    return (p[0] + t * d[0], y)


@part("3-26A", "Bumper-towbar mounting bracket", "Steel")
def towbar_bracket(s):
    """Sheet 06, 3-26A (scale 1:2): a 2 x 8 steel strip with R4 ends: a top leg 43 long, a slanted leg
    dropping to 37 overall over 22.5, a bottom leg 11 long; Ø4 holes 5 and 35 from the top leg's end
    and 5 from the bottom leg's end. The bends are modelled sharp (drawn with small, undimensioned
    rounds). Side profile in the XZ plane, X along, Z up from the bottom leg's underside; 8 wide in Y."""
    T, W = s.param("tb_t", 2, "thickness"), s.param("tb_w", 8, "width")
    L1, DX, L3, H = 43, 22.5, 11, 37
    a, b = (L1, H), (L1 + DX, T)                                  # the slant's upper face
    d = (b[0] - a[0], b[1] - a[1])
    ln = math.hypot(*d)
    nrm = (d[1] / ln * T, -d[0] / ln * T)                        # toward the lower left
    nrm = (-abs(nrm[0]), -abs(nrm[1]))
    q = (a[0] + nrm[0], a[1] + nrm[1])
    p1, p2 = line_meet(q, d, H - T), line_meet(q, d, 0)
    pts = [(0, H - T), p1, p2, (L1 + DX + L3, 0), (L1 + DX + L3, T), b, a, (0, H)]
    s.sketch("Side", (0, 0, 0), (1, 0, 0), (0, 0, 1))                     # normal -Y
    s.polyline(pts)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", name="Strip", body_name=s.body)
    v = polygon_area(pts) * W
    xe = L1 + DX + L3
    r = W / 2
    s.sketch("End rounds", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    for xc, x0, x1 in ((r, -1, r), (xe - r, xe - r, xe + 1)):
        s.cmd("sketch.rectangle.two_point", p0=[x0, -r - 1], p1=[x1, r + 1])
        s.cmd("sketch.circle.center", center=[xc, 0], diameter=W)
    s.finish()
    s.cmd("solid.extrude", distance=H + 2, operation="cut", targets=[s.body],
          profiles=[{"point": [-0.5, 0]}, {"point": [xe + 0.5, 0]}], name="End rounds")
    s.holes("Ø4 holes", (0, 0, -1), (0, 0, 1), [(5, 0, -1), (35, 0, -1), (xe - 5, 0, -1)], 4, depth=H + 2)
    return v - 2 * (2 * r * r - math.pi / 2 * r * r) * T - 3 * math.pi * 4 * T


# ----------------------------------------------------------------------------- 3-26B to 3-37 (sheet 07)
@part("3-26B", "Bumper-towbar", "Steel")
def bumper_towbar(s):
    """Sheet 07, 3-26B (scale 1:2): a 2 thick steel bar 144 x 10 with R3 corners and Ø4 holes 18 from
    each end. XY plane."""
    L, W, T = 144, 10, 2
    start = (3, -5)
    segs = [("line", (L - 3, -5)), ("arc", (L - 3, -2), (L, -2), True), ("line", (L, 2)), ("arc", (L - 3, 2), (L - 3, 5), True),
            ("line", (3, 5)), ("arc", (3, 2), (0, 2), True), ("line", (0, -2)), ("arc", (3, -2), start, True)]
    s.sketch("Bar", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    for x in (18, L - 18):
        s.cmd("sketch.circle.center", center=[x, 0], diameter=4)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [10, 0]}], name="Bar", body_name=s.body)
    return (loop_area(start, segs) - 2 * math.pi * 4) * T


@part("3-27A", "Hand brake shaft", "Steel")
def hand_brake_shaft(s):
    """Sheet 07, 3-27A: a Ø4 x 58 steel shaft. Axis = Z."""
    return s.turned("Shaft", [(0, 0), (2, 0), (2, 58), (0, 58)])


@part("3-27C", "Hand brake pivot", "Brass")
def hand_brake_pivot(s):
    """Sheet 07, 3-27C (scale 1:1.5): a brass collar Ø12 x 6 with a Ø8 x 2 spigot (8PF), bored Ø4, a
    Ø3 cross hole 3 from its plain face. Axis = Z; the cross hole at 45° (off the seam)."""
    v = s.turned("Pivot", [(2, 0), (6, 0), (6, 6), (4, 6), (4, 8), (2, 8)])
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("Ø3 cross hole", (-8 * u[0], -8 * u[1], 0), u, [(-8 * u[0], -8 * u[1], 3)], 3)
    return v - cross_hole(6, 1.5, 2)


@part("3-27D", "Hand brake teethed bracket plate", "Brass")
def hand_brake_toothed_plate(s):
    """Sheet 07, 3-27D (scale 1:1.5): a 1 thick brass plate 30 wide with an R15 top round a Ø4 hole
    9.5 up (measured), toothed over 63° either side of the top (1 deep, 1.5 pitch: 21 teeth); along
    its foot two 1 wide slits make three tabs, bent over 4.5: the outer ones to one side, the middle
    one to the other. The bends are sharp. Plate in the XZ plane on Y = 0..1, Z up from the foot."""
    T, R, H = 1, 15, 9.5
    n = 21
    a0, a1 = math.radians(90 - 63), math.radians(90 + 63)
    pts = []
    for i in range(2 * n + 1):
        a = a0 + (a1 - a0) * i / (2 * n)
        r = R if i % 2 == 0 else R - 1
        pts.append((r * math.cos(a), H + r * math.sin(a)))
    start = (-R, 0)
    segs = [("line", (R, 0)), ("line", (R, H)), ("arc", (0, H), pts[0], True)] + [("line", p) for p in pts[1:]] + \
           [("arc", (0, H), (-R, H), True), ("line", start)]
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 0, 1))                    # normal -Y
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, H], diameter=4)
    for x0 in (-8, 7):
        s.cmd("sketch.rectangle.two_point", p0=[x0, 0], p1=[x0 + 1, 1])
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", profiles=[{"point": [0, 3]}], name="Plate", body_name=s.body)
    v = (loop_area(start, segs) - math.pi * 4 - 2 * 1) * T
    s.sketch("Feet", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-15, 0], p1=[-8, 4.5])
    s.cmd("sketch.rectangle.two_point", p0=[8, 0], p1=[15, 4.5])
    s.cmd("sketch.rectangle.two_point", p0=[-7, -3.5], p1=[7, 1])
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], name="Feet")
    return v + (2 * 7 * 3.5 + 14 * 3.5) * T


@part("3-27F", "Hand brake release handle spring", {"coil": "Steel", "leg 1": "Steel", "leg 2": "Steel"}, tol=0.01)
def release_spring(s):
    """Sheet 07, 3-27F: a torsion spring of Ø0.5 spring steel wire, Ø4.5 over the coil, 2.5 turns
    (1.75 long at most), legs 14 long leaving the coil tangentially. The legs are separate solids
    touching the coil's ends. Coil axis = Z."""
    n = s.body.split()[0]
    d, D, turns = 0.5, 4.5, 2.5
    rm = (D - d) / 2
    pitch = 0.505
    s.cmd("solid.coil", diameter=D - d, turns=turns, pitch=pitch, section_size=d, section="circular", section_position="center",
          base=[0, 0, 0], axis="Z", name="Coil", body_name=f"{n} coil")
    v = math.pi / 4 * d * d * 2 * math.pi * rm * turns
    ends = [(0.0, 0.0, -1), (turns * 2 * math.pi, turns * pitch, 1)]
    for k, (a, z, sgn) in enumerate(ends):
        p = (rm * math.cos(a), rm * math.sin(a), z)
        t = (-math.sin(a) * sgn, math.cos(a) * sgn, 0)
        s.cmd("solid.cylinder", diameter=d, height=14, base=[round(c, 6) for c in p], axis=[round(c, 6) for c in t],
              name=f"Leg {k + 1}", body_name=f"{n} leg {k + 1}")
        v += math.pi / 4 * d * d * 14
    return v


@part("3-27G", "Hand brake release crank", "Steel")
def release_crank(s):
    """Sheet 07, 3-27G: a steel crank plate, R6 round a Ø8 hole and R3.25 round an M3 (Ø2.5) hole 10
    away; 1.5 thick (not dimensioned: taken from the 3D view). XY plane."""
    return link(s, 10, 6, 3.25, 8, 2.5, 1.5)


@part("3-27H", "Hand brake release crank break band holder", "Brass")
def band_holder(s):
    """Sheet 07, 3-27H (scale 1.5:1): a brass Ø5 x 8 holder slotted 1 wide 7 deep from its end, a 6 AF
    x 2 hex and an M3 x 4 stud (at Ø3). Axis = Z, the slotted end on Z = 0."""
    v = s.turned("Holder", [(0, 0), (2.5, 0), (2.5, 8), (1.5, 8), (1.5, 14), (0, 14)])
    s.sketch("Hex", (0, 0, 8), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(6))
    s.finish()
    s.cmd("solid.extrude", distance=2, operation="join", targets=[s.body], name="Hex")
    v += (math.sqrt(3) / 2 * 36 - math.pi * 2.25) * 2
    s.sketch("Slot", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-0.5, -4], p1=[0.5, 4])
    s.finish()
    s.cmd("solid.extrude", distance=8, operation="cut", targets=[s.body], name="Slot")
    h, strip = 1.0 / 400, 0.0
    for i in range(400):
        x = -0.5 + (i + 0.5) * h
        strip += 2 * math.sqrt(6.25 - x * x) * h
    return v - strip * 7


@part("3-27J", "Hand brake bandend strap", "Brass")
def bandend_strap(s):
    """Sheet 07, 3-27J (scale 1:1.5): a 1 thick brass strap: a tab 8 wide with an R4 end round a Ø4
    hole 9 from the bend, and a tongue 6 wide bent down 10 with an R3 end. The bend (R2 drawn) is
    sharp here. Built as one L section 8 wide, then trimmed (joining the round-ended tongue to the
    tab needs a separation retry). Tab on Z = 0..1 along X, the tongue on X = 0..1."""
    T = 1
    pts = [(0, -9), (T, -9), (T, 0), (13, 0), (13, T), (0, T)]
    s.sketch("Section", (0, 0, 0), (1, 0, 0), (0, 0, 1))                  # normal -Y
    s.polyline(pts)
    s.finish()
    s.cmd("solid.extrude", distance=4, direction="symmetric", name="Strap", body_name=s.body)
    v = polygon_area(pts) * 8
    # tab: R4 end and Ø4 hole (cut down through Z); tongue: 6 wide with an R3 end (cut along X)
    # the end round and the hole as two cuts: picked as two regions of one sketch, the cut took
    # 13.15 instead of 19.44
    s.sketch("Tab end", (0, 0, -1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[9, -5], p1=[14, 5])
    s.cmd("sketch.circle.center", center=[9, 0], diameter=8)
    s.finish()
    s.cmd("solid.extrude", distance=3, operation="cut", targets=[s.body], profiles=[{"point": [13.5, 0]}],
          name="Tab end")
    s.holes("Ø4 hole", (0, 0, -1), (0, 0, 1), [(9, 0, -1)], 4, depth=3)
    v -= ((4 * 8 - math.pi * 16 / 2) + math.pi * 4) * T
    s.sketch("Tongue", (-1, 0, 0), (0, 1, 0), (0, 0, 1))                 # normal +X
    s.cmd("sketch.rectangle.two_point", p0=[3, -10], p1=[5, -0.5])
    s.cmd("sketch.rectangle.two_point", p0=[-5, -10], p1=[-3, -0.5])
    s.cmd("sketch.rectangle.two_point", p0=[-3, -10], p1=[3, -6])
    s.cmd("sketch.circle.center", center=[0, -6], diameter=6)
    s.finish()
    s.cmd("solid.extrude", distance=3, operation="cut", targets=[s.body],
          profiles=[{"point": [4, -3]}, {"point": [-4, -3]}, {"point": [2.9, -9.5]}], name="Tongue width and end")
    v -= (2 * 1 * (9 - 0.5) + (6 * 3 - math.pi * 9 / 2)) * T      # the sides from Z = -0.5 down, the R3 end
    return v


@part("3-27K", "Hand brake spring screw", "Steel")
def spring_screw(s):
    """Sheet 07, 3-27K: a Ø7 x 2 head, a Ø5 x 3.3 shoulder and an M4 x 5 end (at Ø4); the head's slot
    is not dimensioned and not modelled. Axis = Z."""
    return s.turned("Screw", [(0, 0), (3.5, 0), (3.5, 2), (2.5, 2), (2.5, 5.3), (2, 5.3), (2, 10.3), (0, 10.3)])


@part("3-28", "Reversing operating handle", "Brass")
def reversing_handle(s):
    """Sheet 07, 3-28: a brass knob 20.5 high, tapering from Ø8 at the foot to Ø10 (measured) under an
    SR5 dome; tapped M4 (Ø3.3) 10 deep in the foot. Axis = Z."""
    start = (1.65, 0)
    segs = [("line", (4, 0)), ("line", (5, 15.5)), ("arc", (0, 15.5), (0, 20.5), True), ("line", (0, 10)),
            ("line", (1.65, 10)), ("line", start)]
    revolved_loop(s, "Knob", start, segs)
    return revolved_loop_volume(start, segs)


@part("3-29", "Rev operating handle crank and spindle", {"lever": "Steel", "hub": "Brass", "spindle": "Steel"})
def rev_crank_spindle(s):
    """Sheet 07, 3-29 (scale 1:1.5, partly measured): a Ø4 x 111 steel spindle; at its top a 2 thick
    steel crank (R6 and R4 ends 20 apart, Ø4 at the end) pressed on a brass hub Ø12.5 x 6.5 with a
    Ø8 x 2 spigot (8PF), pinned to the spindle by a Ø2 x 12.5 pin 5.5 below the top; a second Ø2 x
    12.5 pin 14 below the top. Axis = Z, the spindle from Z = 0 up to the crank's top at 111."""
    n = s.body.split()[0]
    top = 111
    v = link(s, 20, 6, 4, 8, 4, 2, body=f"{n} lever", name="Crank", z0=top - 2)
    v += s.turned("Hub", [(2, top - 8.5), (6.25, top - 8.5), (6.25, top - 2), (4, top - 2), (4, top), (2, top)],
                  body=f"{n} hub")
    v += s.turned("Spindle", [(0, 0), (2, 0), (2, top), (0, top)], body=f"{n} spindle")
    for k, z in enumerate((top - 5.5, top - 14)):
        a = math.radians(45)
        s.cmd("solid.cylinder", diameter=2, height=12.5, base=[round(-6.25 * math.cos(a), 6), round(-6.25 * math.sin(a), 6), z],
              axis=[round(math.cos(a), 6), round(math.sin(a), 6), 0], operation="join", targets=[f"{n} spindle"],
              name=f"Pin {k + 1}")
        v += math.pi * 12.5 - cross_hole(2, 1)
    s.holes("Hub pin hole", (-8 * math.cos(math.radians(45)), -8 * math.sin(math.radians(45)), 0),
            (math.cos(math.radians(45)), math.sin(math.radians(45)), 0),
            [(-8 * math.cos(math.radians(45)), -8 * math.sin(math.radians(45)), top - 5.5)], 2, target=f"{n} hub")
    return v - cross_hole(6.25, 1, 2)


@part("3-30", "Rev spindle locking collar", "Brass")
def locking_collar(s):
    """Sheet 07, 3-30: a brass collar Ø12 x 8 bored Ø4, a Ø2 cross hole at the middle. Axis = Z; the
    cross hole at 45° (off the seam)."""
    v = s.turned("Collar", [(2, 0), (6, 0), (6, 8), (2, 8)])
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("Ø2 cross hole", (-8 * u[0], -8 * u[1], 0), u, [(-8 * u[0], -8 * u[1], 4)], 2)
    return v - cross_hole(6, 1, 2)


@part("3-31", "Coupling operating handle", {"lever": "Steel", "collar": "Brass", "knob": "Brass"})
def coupling_handle(s):
    """Sheet 07, 3-31 (scale 1:1.5): a 2 thick steel lever as 3-21 (R6 round a Ø8 hole, tapering to 6
    wide 36 up, a 4 wide tip 14 long) in a brass knob (Ø6 at its foot tapering to the Ø9 of an SR4.5
    dome, 18.5 high, a 4 x 2 slot 14 deep for the tip); a brass collar Ø12 x 6 with a Ø8 x 2 spigot
    in the lever (8PF), bored Ø4, cross-drilled Ø2.5 3 from the lever. Lever in the XZ plane on
    Y = -1..1, its axis Z; the collar along Y."""
    n = s.body.split()[0]
    tr = tangent_from((3, 36), (0, 0), 6, left=True)
    tl = (-tr[0], tr[1])
    start = (2, 50)
    segs = [("line", (-2, 50)), ("line", (-2, 36)), ("line", (-3, 36)), ("line", tl), ("arc", (0, 0), tr, True),
            ("line", (3, 36)), ("line", (2, 36)), ("line", start)]
    s.sketch("Lever", (0, 0, 0), (1, 0, 0), (0, 0, 1))                    # normal -Y
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=8)
    s.finish()
    s.cmd("solid.extrude", distance=1, direction="symmetric", profiles=[{"point": [0, 30]}], name="Lever",
          body_name=f"{n} lever")
    v = (loop_area(start, segs) - math.pi * 16) * 2
    kst = (0, 36)
    ksg = [("line", (3, 36)), ("line", (4.5, 50)), ("arc", (0, 50), (0, 54.5), True), ("line", kst)]
    revolved_loop(s, "Knob", kst, ksg, body=f"{n} knob")
    s.sketch("Knob slot", (0, 0, 35), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-2, -1], p1=[2, 1])
    s.finish()
    s.cmd("solid.extrude", distance=15, operation="cut", targets=[f"{n} knob"], name="Knob slot")
    v += revolved_loop_volume(kst, ksg) - 4 * 2 * 14
    # the spigot reaches 0.5 into the Ø12 so the two overlap
    s.cmd("solid.cylinder", diameter=8, height=2.5, base=[0, -1, 0], axis="Y", name="Collar spigot", body_name=f"{n} collar")
    s.cmd("solid.cylinder", diameter=12, height=6, base=[0, 1, 0], axis="Y", operation="join", targets=[f"{n} collar"],
          name="Collar")
    s.cmd("solid.cylinder", diameter=4, height=10, base=[0, -2, 0], axis="Y", operation="cut", targets=[f"{n} collar"],
          name="Collar bore")
    u = (math.cos(math.radians(45)), 0, math.sin(math.radians(45)))
    s.holes("Ø2.5 cross hole", (-8 * u[0], 4, -8 * u[2]), u, [(-8 * u[0], 4, -8 * u[2])], 2.5, target=f"{n} collar")
    v += math.pi * 16 * 2 + math.pi * 36 * 6 - math.pi * 4 * 8 - cross_hole(6, 1.25, 2)
    return v


@part("3-32", "Coupling operating pulley and shaft", {"pulley": "Brass", "shaft": "Steel"})
def coupling_pulley(s):
    """Sheet 07, 3-32 (scale 1:1.5): a brass pulley Ø35.5 x 6 with a groove 4 wide down to Ø32, bored
    Ø4 with an M3 (Ø2.5) set screw through the rim; a Ø4 x 62.5 steel shaft from its face with a
    Ø2.5 x 13 pin 25.6 along (measured). Axis = Z."""
    n = s.body.split()[0]
    v = s.turned("Pulley", [(2, 0), (17.75, 0), (17.75, 1), (16, 1), (16, 5), (17.75, 5), (17.75, 6), (2, 6)],
                 body=f"{n} pulley")
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("M3 set screw", (18 * u[0], 18 * u[1], 0), (-u[0], -u[1], 0), [(18 * u[0], 18 * u[1], 3)], 2.5, depth=17,
            target=f"{n} pulley")
    v -= cross_hole(16, 1.25, 2) / 2
    v += s.turned("Shaft", [(0, 0), (2, 0), (2, 62.5), (0, 62.5)], body=f"{n} shaft")
    s.cmd("solid.cylinder", diameter=2.5, height=13, base=[-6.5 * u[0], -6.5 * u[1], 25.6], axis=[round(c, 6) for c in u],
          operation="join", targets=[f"{n} shaft"], name="Pin")
    return v + math.pi / 4 * 6.25 * 13 - cross_hole(2, 1.25)


@part("3-33", "Shaft adjuster", "Brass")
def shaft_adjuster(s):
    """Sheet 07, 3-33: a brass 12 AF x 5 hex on a Ø10 x 8 body, bored Ø4 2 off centre right through
    (an eccentric). Axis = Z."""
    s.sketch("Hex", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.polyline(hexagon(12))
    s.finish()
    s.cmd("solid.extrude", distance=5, name="Hex", body_name=s.body)
    v = math.sqrt(3) / 2 * 144 * 5
    v += s.turned("Body", [(0, 4.5), (5, 4.5), (5, 13), (0, 13)], operation="join") - math.pi * 25 * 0.5
    s.holes("Eccentric bore", (0, 0, -1), (0, 0, 1), [(0, 2, -1)], 4, depth=15)
    return v - math.pi * 4 * 13


@part("3-34", "Shaft spacer", "Brass")
def shaft_spacer(s):
    """Sheet 07, 3-34: a brass Ø9 x 13 spacer bored Ø4. Axis = Z."""
    return s.turned("Spacer", [(2, 0), (4.5, 0), (4.5, 13), (2, 13)])


@part("3-35", "Accelerator levers bolt", "Steel")
def accelerator_levers_bolt(s):
    """Sheet 07, 3-35: a Ø8 x 1.5 head (slot not modelled), a Ø4 x 2.1 shoulder and an M3 x 2.5 end
    (at Ø3). Axis = Z, the threaded end on Z = 0."""
    return s.turned("Bolt", [(0, 0), (1.5, 0), (1.5, 2.5), (2, 2.5), (2, 4.6), (4, 4.6), (4, 6.1), (0, 6.1)])


@part("3-36", "Accelerator connector lever", "Steel")
def accelerator_connector(s):
    """Sheet 07, 3-36 (scale 1:2): a steel link, Ø4 holes 112 apart in R4 eyes joined by a 4 wide bar;
    1.5 thick (measured from the side view, which also shows a slight crank, not modelled). XY plane."""
    T, L = 1.5, 112
    xe = math.sqrt(16 - 4)
    start = (xe, 2)
    segs = [("line", (L - xe, 2)), ("arc", (L, 0), (L - xe, -2), False), ("line", (xe, -2)), ("arc", (0, 0), start, False)]
    s.sketch("Link", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    for x in (0, L):
        s.cmd("sketch.circle.center", center=[x, 0], diameter=4)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [L / 2, 0]}], name="Link", body_name=s.body)
    return (loop_area(start, segs) - 2 * math.pi * 4) * T


@part("3-37", "Rear stop lights", {"housing": "Brass", "lens": "Polycarbonate"})
def stop_light(s):
    """Sheet 07, 3-37: a brass housing: a 24 x 10 x 3 base with Ø3 holes at ±8 and an R4.5 boss whose
    centre is 7.5 up, bored Ø6.5 9 deep from the front with a Ø7.5 x 1 recess for a red plastic lens
    (Ø7.5 x 1, modelled in polycarbonate, red). Front view in the XZ plane, depth along +Y."""
    n = s.body.split()[0]
    start = (-12, 0)
    segs = [("line", (12, 0)), ("line", (12, 3)), ("line", (4.5, 3)), ("line", (4.5, 7.5)), ("arc", (0, 7.5), (-4.5, 7.5), True),
            ("line", (-4.5, 3)), ("line", (-12, 3)), ("line", start)]
    s.sketch("Housing", (0, 0, 0), (1, 0, 0), (0, 0, 1))                  # normal -Y
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=10, direction="negative", name="Housing", body_name=f"{n} housing")
    v = loop_area(start, segs) * 10
    s.holes("Lens recess", (0, -1, 0), (0, 1, 0), [(0, -1, 7.5)], 7.5, depth=2, target=f"{n} housing")
    s.holes("Bore", (0, 0.5, 0), (0, 1, 0), [(0, 0.5, 7.5)], 6.5, depth=8.5, target=f"{n} housing")
    s.holes("Fixing holes", (0, 0, -1), (0, 0, 1), [(-8, 5, -1), (8, 5, -1)], 3, depth=5, target=f"{n} housing")
    v -= math.pi / 4 * 7.5 ** 2 * 1 + math.pi / 4 * 6.5 ** 2 * 8 + 2 * math.pi / 4 * 9 * 3
    s.cmd("solid.cylinder", diameter=7.5, height=1, base=[0, 0, 7.5], axis="Y", name="Lens", body_name=f"{n} lens")
    s.cmd("appearance.assign", bodies=[f"{n} lens"], color="#d01818")
    return v + math.pi / 4 * 7.5 ** 2 * 1


# ----------------------------------------------------------------------------- 3-27I
@part("3-27I", "Hand brake band", "Stainless Steel")
def hand_brake_band(s):
    """Sheet 07, 3-27I (scale 1:2): a stainless band (stretched length about 175) bent into a loop:
    an R23 bottom, one leg straight up 48.5 then bent R2 into a 12 tab, the other leg running from
    the loop's side to a tip 64.2 above the loop's centre, 1.6 to the side. Taken 0.5 thick and 6
    wide (the width is not dimensioned: the strap 3-27J's tongue); the copper lining is not
    modelled. The band's centre line in the XZ plane, the loop's centre on the origin."""
    T, W, R = 0.5, 6, 23
    tip = (1.6, 64.2)
    p = tangent_from(tip, (0, 0), R, left=False)                # on the loop's far side
    s.sketch("Path", (0, 0, 0), (1, 0, 0), (0, 0, 1))
    rnd = lambda q: [round(q[0], 6), round(q[1], 6)]
    s.cmd("sketch.line", points=[rnd(tip), rnd(p)])                                       # l1
    s.cmd("sketch.arc.center_point", center=[0, 0], start=rnd(p), end=[R, 0])              # a1
    s.cmd("sketch.line", points=[[R, 0], [R, 46.5]])                                       # l2
    s.cmd("sketch.arc.center_point", center=[R + 2, 46.5], start=[R + 2, 48.5], end=[R, 46.5])  # a2 (CCW from start)
    s.cmd("sketch.line", points=[[R + 2, 48.5], [R + 12, 48.5]])                           # l3
    s.finish()
    d = (p[0] - tip[0], p[1] - tip[1])
    L1 = math.hypot(*d)
    u = (d[0] / L1, d[1] / L1)
    nrm = (-u[1], u[0])
    # the band's section at the tip, normal to the first line
    s.sketch("Section", (tip[0], 0, tip[1]), (0, 1, 0), (round(nrm[0], 9), 0, round(nrm[1], 9)))
    s.cmd("sketch.rectangle.two_point", p0=[-W / 2, -T / 2], p1=[W / 2, T / 2])
    s.finish()
    s.cmd("solid.sweep", sketch="Section", path_sketch="Path", path=["l1", "a1", "l2", "a2", "l3"], name="Band",
          body_name=s.body)
    a0 = math.atan2(p[1], p[0]) % (2 * math.pi)
    sweep = (2 * math.pi - a0)                                 # round the bottom to (R, 0)
    length = L1 + R * sweep + 46.5 + math.pi / 2 * 2 + 10
    return W * T * length


# ----------------------------------------------------------------------------- 4-01 to 4-12 (sheet 07)
def gearbox_plate(s, slots, holes):
    """A 2 thick brass angle: a 90 x 13 flange (R5 free corners) on Y = 0..2 with 4 wide slots 9 up,
    and a plate 77 x 51 (from the flange's outer face; R5 far corners) on Z = 0..2 from X = 13."""
    T = 2
    st, sg = (0, 0), [("line", (90, 0)), ("line", (90, 8)), ("arc", (85, 8), (85, 13), True), ("line", (5, 13)),
                      ("arc", (5, 8), (0, 8), True), ("line", (0, 0))]
    s.sketch("Flange", (0, 0, 0), (1, 0, 0), (0, 0, 1))                   # normal -Y
    s.loop(st, sg)
    sl = []
    for a, b in slots:
        lst, lsg = slot_loop((a, 9), (b, 9), 2)
        s.loop(lst, lsg)
        sl.append(loop_area(lst, lsg))
    s.finish()
    s.cmd("solid.extrude", distance=T, direction="negative", profiles=[{"point": [1, 1]}], name="Flange", body_name=s.body)
    v = (loop_area(st, sg) - sum(sl)) * T
    # the plate from Y = 1 so it overlaps the flange instead of sharing its outer face
    pst, psg = (13, 1), [("line", (90, 1)), ("line", (90, 46)), ("arc", (85, 46), (85, 51), True), ("line", (18, 51)),
                         ("arc", (18, 46), (13, 46), True), ("line", (13, 1))]
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(pst, psg)
    for (x, y), d in holes:
        s.cmd("sketch.circle.center", center=[round(x, 6), y], diameter=d)
    s.finish()
    s.cmd("solid.extrude", distance=T, operation="join", targets=[s.body], profiles=[{"point": [14, 48]}], name="Plate")
    return v + (loop_area(pst, psg) - sum(math.pi / 4 * d * d for _, d in holes)) * T - 77 * 1 * T


X1, X2, XD = 36.5, 36.5 + 2 * 20 * math.cos(math.radians(30)), 36.5 + 20 * math.cos(math.radians(30))


@part("4-01", "GB RH-side plate", "Brass")
def gearbox_plate_1(s):
    """Sheet 07, 4-01 (scale 1:1.5): a 2 thick brass angle, the flange 90 x 13 with slots 4 wide from
    5.5 to 11 and 40.5 to 46 (centres, 9 up), the plate 77 x 51 from X = 13. Holes: A = Ø3 at
    (17.5, 6), (17.5, 44), (86, 6), (86, 44); B = M3 (Ø2.5) at (36.5, 13), (36.5, 38), (71.1, 13),
    (71.1, 38); C = M4 (Ø3.3) at (75, 5); D = Ø4 at (36.5, 25.5) and 20 from it at ±30° (53.8,
    15.5 / 35.5); Ø6 at (71.1, 25.5). Y from the flange's outer face. The bend is sharp."""
    holes = ([((x, y), 3) for x in (17.5, 86) for y in (6, 44)] + [((x, y), 2.5) for x in (X1, X2) for y in (13, 38)]
             + [((75, 5), 3.3), ((X1, 25.5), 4), ((XD, 15.5), 4), ((XD, 35.5), 4), ((X2, 25.5), 6)])
    return gearbox_plate(s, [(5.5, 11), (40.5, 46)], holes)


@part("4-02", "GB LH-side plate", "Brass")
def gearbox_plate_2(s):
    """Sheet 07, 4-02 (scale 1:1.5): as 4-01 ("for all other dimension details refer to 4-01"), with
    slots from 5.5 to 11 and 59.5 to 65, a Ø20 at (36.5, 25.5) in place of the Ø4, M3 (Ø2.5) at
    (36.5, 6) and (36.5, 44), Ø4 at (53.8, 15.5 / 35.5), Ø6 at (71.1, 25.5), the A holes as 4-01 and
    no M4."""
    holes = ([((x, y), 3) for x in (17.5, 86) for y in (6, 44)] + [((X1, 6), 2.5), ((X1, 44), 2.5), ((X1, 25.5), 20),
                                                                   ((XD, 15.5), 4), ((XD, 35.5), 4), ((X2, 25.5), 6)])
    return gearbox_plate(s, [(5.5, 11), (59.5, 65)], holes)


@part("4-03", "GB side plate spacer", "Steel")
def gearbox_shaft(s):
    """Sheet 07, 4-03: a Ø6 x 30 steel spacer with M3 x 6 ends (at Ø3). Axis = Z."""
    return s.turned("Shaft", [(0, 0), (1.5, 0), (1.5, 6), (3, 6), (3, 36), (1.5, 36), (1.5, 42), (0, 42)])


@part("4-04", "Coupling unit outer bearing plate", "Brass")
def bearing_flange(s):
    """Sheet 07, 4-04 (scale 1:1.5, section F-F): a brass Ø20 x 2 spigot, a Ø44 x 3 flange cut flat
    13 from the centre on one side with Ø3 holes at ±19, and a Ø24 x 8 hub; bored Ø16, Ø19 6.5 deep
    from the hub's end. Axis = Z; the flat toward -X (off the revolve's seam)."""
    v = s.turned("Flange", [(8, 0), (10, 0), (10, 2), (22, 2), (22, 5), (12, 5), (12, 13), (9.5, 13), (9.5, 6.5), (8, 6.5)])
    s.sketch("Flat", (0, 0, 1), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.rectangle.two_point", p0=[-25, -25], p1=[-13, 25])
    s.finish()
    s.cmd("solid.extrude", distance=5, operation="cut", targets=[s.body], name="Flat")
    R, d = 22, 13
    v -= (R * R * math.acos(d / R) - d * math.sqrt(R * R - d * d)) * 3
    s.holes("Ø3 holes", (0, 0, 1), (0, 0, 1), [(0, 19, 1), (0, -19, 1)], 3, depth=5)
    return v - 2 * math.pi / 4 * 9 * 3


@part("4-05", "Coupling unit outer plate ball bearing", "Steel")
def gearbox_bearing(s):
    """Sheet 07, 4-05: a bought-in ball bearing Ø19 / Ø8.5 (as labelled), 6.5 thick, modelled as its
    envelope. Axis = Z."""
    return s.turned("Bearing", [(4.25, 0), (9.5, 0), (9.5, 6.5), (4.25, 6.5)])


@part("4-06", "Coupling drive pulley", "Steel")
def coupling_cup_pulley(s):
    """Sheet 07, 4-06 (scale 1:1.5, from a 900 dpi render of the section): a steel cup pulley 8 wide:
    Ø34 flanges 2 wide each side of a 20° V groove to a Ø28 floor 2.5 wide, a Ø24 cup 5 deep, a 3
    thick web, a Ø8.5 hub to 14.9 (measured) with a step to Ø12 at the web; bored Ø6 and Ø8 1 deep at
    the hub's end. Axis = Z, the cup's rim on Z = 0."""
    pts = [(12, 0), (17, 0), (17, 2.03), (14, 2.75), (14, 5.29), (17, 5.97), (17, 8), (6, 8), (6, 8.38), (4.25, 8.38),
           (4.25, 14.94), (4, 14.94), (4, 13.89), (3, 13.89), (3, 5), (12, 5)]
    return s.turned("Pulley", pts)


@part("4-08", "Coupling spacer", "Steel")
def coupling_washer(s):
    """Sheet 07, 4-08: a Ø12 / Ø8 x 1 steel spacer washer. Axis = Z."""
    return s.turned("Washer", [(4, 0), (6, 0), (6, 1), (4, 1)])


@part("4-09", "Coupling spring", "Steel", tol=0.01)
def coupling_spring(s):
    """Sheet 07, 4-09: a compression spring of Ø0.5 spring steel wire, Ø5.5 / Ø4.5, 18.5 free; 13
    turns (counted). Axis = Z."""
    turns, d, L = 13, 0.5, 18.5
    s.cmd("solid.coil", diameter=5.0, turns=turns, pitch=round((L - d) / turns, 6), section_size=d, section="circular",
          section_position="center", base=[0, 0, d / 2], axis="Z", name="Spring", body_name=s.body)
    return math.pi / 4 * d * d * 2 * math.pi * 2.5 * turns


@part("4-11", "Coupling spring retainer ball bearing", "Steel")
def coupling_bearing(s):
    """Sheet 07, 4-11: a bought-in ball bearing Ø12.5 / Ø6.5, 5 thick (as labelled), modelled as its
    envelope. Axis = Z."""
    return s.turned("Bearing", [(3.25, 0), (6.25, 0), (6.25, 5), (3.25, 5)])


@part("4-12", "Coupling ball bearing retainer", "Steel")
def bearing_retainer(s):
    """Sheet 07, 4-12 (scale 1:1.5): a steel bush Ø6.5 x 5 and Ø8 x 4, bored Ø4. Axis = Z."""
    return s.turned("Retainer", [(2, 0), (3.25, 0), (3.25, 5), (4, 5), (4, 9), (2, 9)])


# ----------------------------------------------------------------------------- 4-07 to 4-31 (sheet 07)
def gear_points(N, tip_d, root_d, tip_w, root_w, phase=0.0):
    """A straight-flanked gear outline: N teeth, tip_w wide at the tip circle, root_w at the root."""
    RT, RR = tip_d / 2, root_d / 2
    at, ar = math.asin(tip_w / 2 / RT), math.asin(root_w / 2 / RR)
    pts = []
    for k in range(int(N)):
        t = phase + 2 * math.pi * k / N
        for r, a in ((RR, t - ar), (RT, t - at), (RT, t + at), (RR, t + ar)):
            pts.append((r * math.cos(a), r * math.sin(a)))
    return pts


def gear_prism(s, name, pts, z0, width, bore, body, operation="join"):
    """Extrude a gear outline with a centre bore from Z = z0; returns its volume."""
    s.sketch(name, (0, 0, z0), (1, 0, 0), (0, 1, 0))
    s.polyline(pts)
    if bore:
        s.cmd("sketch.circle.center", center=[0, 0], diameter=bore)
    s.finish()
    rr = min(math.hypot(*p) for p in pts)
    extra = {"targets": [body]} if operation == "join" else {"body_name": body}
    pick = round((bore / 2 + rr) / 2, 6) if bore else 0
    s.cmd("solid.extrude", distance=width, operation=operation, profiles=[{"point": [pick, 0]}], name=name, **extra)
    return (polygon_area(pts) - (math.pi / 4 * bore * bore if bore else 0)) * width


Z10 = dict(N=10, tip_d=12, root_d=8, tip_w=0.75, root_w=1.5)        # 4-13's pinion profile
Z30 = dict(N=30, tip_d=32, root_d=28, tip_w=0.5, root_w=1.5)


@part("4-07", "Coupling plate", "Brass")
def coupling_plate(s):
    """Sheet 07, 4-07 (scale 1:1.5): a brass Ø18 x 8 hub with a Ø4 cross hole 4 from its end and a
    Ø26 x 4 disc whose face tapers 20° (a friction cone); bored Ø4. Axis = Z; the cross hole at 45°."""
    v = s.turned("Plate", [(2, 0), (9, 0), (9, 8), (13, 8), (13 - 4 * math.tan(math.radians(20)), 12), (2, 12)])
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    s.holes("Ø4 cross hole", (-10 * u[0], -10 * u[1], 0), u, [(-10 * u[0], -10 * u[1], 4)], 4)
    return v - cross_hole(9, 2, 2)


@part("4-10", "Coupling spring retainer", "Steel")
def spring_retainer(s):
    """Sheet 07, 4-10 (scale 1:1, from a 700 dpi render): a steel Ø7.5 x 7 spigot (measured) and a
    Ø15 x 7 cup; bored Ø6 5 deep, Ø4.5 on, and Ø12.5 5 deep from the cup's face. Axis = Z."""
    return s.turned("Retainer", [(3, 0), (3.75, 0), (3.75, 7), (7.5, 7), (7.5, 14), (6.25, 14), (6.25, 9), (2.25, 9),
                                 (2.25, 5), (3, 5)])


@part("4-13", "Coupling shaft and gearwheel-1", {"gear": "Steel", "shaft": "Stainless Steel"})
def coupling_shaft_gear(s):
    """Sheet 07, 4-13: a steel pinion, 10 teeth, Ø12 over the tips, Ø8 at the roots, the teeth 0.75
    wide at the tip and 1.5 at the root, 4 wide; pressed on a Ø4 x 76 stainless shaft 7 from its end.
    Axis = Z."""
    n = s.body.split()[0]
    v = gear_prism(s, "Pinion", gear_points(**Z10), 7, 4, 4, f"{n} gear", operation="new")
    return v + s.turned("Shaft", [(0, 0), (2, 0), (2, 76), (0, 76)], body=f"{n} shaft")


@part("4-14", "Coupling RH-pulley plate", "Steel")
def rh_pulley_plate(s):
    """Sheet 07, 4-14 (scale 1:1.5): a steel Ø32 x 3 plate with a Ø10 x 12 hub, tapped M8 (Ø6.8)
    through the plate and bored Ø8 6 deep from the hub's end; two Ø3 holes 12.5 either side (taken as
    3-sided from 4-25). Axis = Z."""
    v = s.turned("Plate", [(3.4, 0), (16, 0), (16, 3), (5, 3), (5, 15), (4, 15), (4, 9), (3.4, 9)])
    s.holes("Ø3 holes", (0, 0, -1), (0, 0, 1), [(0, 12.5, -1), (0, -12.5, -1)], 3, depth=5)
    return v - 2 * math.pi / 4 * 9 * 3


@part("4-15", "Coupling RH-pulley shaft", "Steel")
def rh_pulley_shaft(s):
    """Sheet 07, 4-15 (scale 1:1, from a 700 dpi render): a steel Ø12 x 2 collar, Ø10 x 3, Ø7 x 8.5
    and an external thread x 5.5 at Ø8; tapped M3 (Ø2.5) 10 deep from the collar end, bored Ø5.5 9
    deep from the threaded end. Axis = Z."""
    return s.turned("Shaft", [(1.25, 0), (6, 0), (6, 2), (5, 2), (5, 5), (3.5, 5), (3.5, 13.5), (4, 13.5), (4, 19),
                              (2.75, 19), (2.75, 10), (1.25, 10)])


@part("4-16", "Coupling RH-pulley", "Brass")
def rh_pulley(s):
    """Sheet 07, 4-16 (scale 1:1.5): a brass pulley: a Ø14 x 5.5 hub, Ø18 x 2 flanges each side of a
    groove 4 wide to Ø12, a Ø14 x 1.5 spigot; bored Ø10. Axis = Z."""
    return s.turned("Pulley", [(5, 0), (7, 0), (7, 5.5), (9, 5.5), (9, 7.5), (6, 7.5), (6, 11.5), (9, 11.5), (9, 13.5),
                               (7, 13.5), (7, 15), (5, 15)])


def cluster_gear(s, n, hub, gear_z, pin_z, pin_l, collar=None):
    """A steel cluster: a 30 tooth gear 4 wide from gear_z and a 10 tooth pinion pin_l long from
    pin_z (planar prisms, joined first), a Ø16 hub (z0, z1) and an optional collar (z0, z1) reaching
    0.5 into them (round bodies may not touch the prisms' faces: the join fails), bored Ø4. The
    collar is Ø7.9 (drawn Ø8, the pinion's root) so it stays inside the pinion's roots."""
    body = f"{n} gear"
    v = gear_prism(s, "Gear", gear_points(**Z30), gear_z, 4, None, body, operation="new")
    v += gear_prism(s, "Pinion", gear_points(**Z10), pin_z, pin_l, None, body)
    v += s.turned("Hub", [(0, hub[0]), (8, hub[0]), (8, hub[1] + 0.5), (0, hub[1] + 0.5)], body=body,
                  operation="join") - math.pi * 64 * 0.5
    z_end = pin_z + pin_l
    if collar:
        v += s.turned("Collar", [(0, collar[0] - 0.5), (3.95, collar[0] - 0.5), (3.95, collar[1]), (0, collar[1])],
                      body=body, operation="join") - math.pi * 3.95 ** 2 * 0.5
        z_end = collar[1]
    s.holes("Bore", (0, 0, hub[0] - 1), (0, 0, 1), [(0, 0, hub[0] - 1)], 4, depth=z_end - hub[0] + 2, target=body)
    return v - math.pi * 4 * (z_end - hub[0])


@part("4-17", "GB-gearwheel type-A", {"gear": "Steel", "shaft": "Stainless Steel"})
def gearwheel_a(s):
    """Sheet 07, 4-17 (scale 1:1.5): a steel cluster on a Ø4 x 37 stainless shaft: from 4 along, a
    Ø16 x 2 hub, a 30 tooth gear (Ø32 / Ø28, teeth 0.5 at the tip, 1.5 at the root), 4 wide, a 10
    tooth pinion 5 long (as 4-13) and a Ø8 x 3 collar. Axis = Z."""
    n = s.body.split()[0]
    v = cluster_gear(s, n, (4, 6), 6, 10, 5, collar=(15, 18))
    return v + s.turned("Shaft", [(0, 0), (2, 0), (2, 37), (0, 37)], body=f"{n} shaft")


@part("4-18", "GB-gearwheel type-B", "Steel")
def gearwheel_b(s):
    """Sheet 07, 4-18 (scale 1:1.5): a steel 10 tooth pinion 5 long (as 4-13) with a Ø8 x 6 hub
    (modelled Ø7.9, inside the pinion's roots, as on 4-17), bored Ø4 (the flat in the bore shown in
    the 3D view is not dimensioned and not modelled). Axis = Z."""
    v = gear_prism(s, "Pinion", gear_points(**Z10), 0, 5, None, s.body, operation="new")
    v += s.turned("Hub", [(0, 4.5), (3.95, 4.5), (3.95, 11), (0, 11)], operation="join") - math.pi * 3.95 ** 2 * 0.5
    s.holes("Bore", (0, 0, -1), (0, 0, 1), [(0, 0, -1)], 4, depth=13)
    return v - math.pi * 4 * 11


@part("4-19", "GB-gearwheel type-C", {"gear": "Steel", "shaft": "Stainless Steel"})
def gearwheel_c(s):
    """Sheet 07, 4-19: as 4-17 ("for all other dimension details refer to 4-17") with the hub 5 long
    from 3 along, the gear 4 wide and the pinion 6 long, no collar; on a Ø4 x 37 stainless shaft.
    Axis = Z."""
    n = s.body.split()[0]
    v = cluster_gear(s, n, (3, 8), 8, 12, 6)
    return v + s.turned("Shaft", [(0, 0), (2, 0), (2, 37), (0, 37)], body=f"{n} shaft")


@part("4-20", "GB-driver shaft spacer", "Brass")
def driver_spacer(s):
    """Sheet 07, 4-20: a Ø6 / Ø4 x 2 brass spacer. Axis = Z."""
    return s.turned("Spacer", [(2, 0), (3, 0), (3, 2), (2, 2)])


@part("4-21", "GB-idler shaft-1 spacer", "Brass")
def idler_spacer_1(s):
    """Sheet 07, 4-21: a Ø6 / Ø4 x 5 brass spacer. Axis = Z."""
    return s.turned("Spacer", [(2, 0), (3, 0), (3, 5), (2, 5)])


@part("4-22", "GB-idler shaft-2 spacer", "Brass")
def idler_spacer_2(s):
    """Sheet 07, 4-22: a Ø6 / Ø4 x 15 brass spacer. Axis = Z."""
    return s.turned("Spacer", [(2, 0), (3, 0), (3, 15), (2, 15)])


@part("4-23", "GB-output shaft reversing gearwheel", {"shaft": "Stainless Steel", "gear": "Steel",
                                                      "sleeve 1": "Brass", "sleeve 2": "Brass", "pin": "Steel"})
def output_shaft_gear(s):
    """Sheet 07, 4-23 (scale 1:1.5): a Ø6 x 87.5 stainless shaft; 34 along a brass Ø8 sleeve 7.5
    long, a steel 30 tooth gear 4 wide (as 4-17, pressed on) and a brass Ø8 sleeve 11 long; a Ø3 x 19
    steel pin 17.5 from the far end in a hole through the shaft. Axis = Z; the pin along X."""
    n = s.body.split()[0]
    v = s.turned("Shaft", [(0, 0), (3, 0), (3, 87.5), (0, 87.5)], body=f"{n} shaft")
    s.holes("Pin hole", (-4, 0, 0), (1, 0, 0), [(-4, 0, 70)], 3, target=f"{n} shaft")
    v -= cross_hole(3, 1.5)
    v += gear_prism(s, "Gear", gear_points(**Z30), 41.5, 4, 6, f"{n} gear", operation="new")
    v += s.turned("Sleeve 1", [(3, 34), (4, 34), (4, 41.5), (3, 41.5)], body=f"{n} sleeve 1")
    v += s.turned("Sleeve 2", [(3, 45.5), (4, 45.5), (4, 56.5), (3, 56.5)], body=f"{n} sleeve 2")
    s.cmd("solid.cylinder", diameter=3, height=19, base=[-9.5, 0, 70], axis="X", name="Pin", body_name=f"{n} pin")
    return v + math.pi / 4 * 9 * 19


@part("4-24", "GB-external output shaft gearwheel", {"gear": "Steel", "bush": "Brass"})
def external_output_gear(s):
    """Sheet 07, 4-24 (scale 1:1.5, section G-G): a steel gear, 19 teeth of 3-18's profile (Ø28.5 /
    Ø23, 1 wide at the tip, 2.5 at the root), 12 wide, with a Ø19 x 5.5 hub; an annular groove Ø12 /
    Ø18 8 deep in its face; a brass bush Ø10 / Ø6 x 17.5 pressed through it; a Ø3 cross hole 3.5 from
    the hub's end through both. Axis = Z, the grooved face on Z = 0."""
    n = s.body.split()[0]
    pts = gear_points(19, 28.5, 23, 1, 2.5)
    v = gear_prism(s, "Gear", pts, 0, 12, None, f"{n} gear", operation="new")
    v += s.turned("Hub", [(0, 11.5), (9.5, 11.5), (9.5, 17.5), (0, 17.5)], body=f"{n} gear", operation="join") \
        - math.pi * 9.5 ** 2 * 0.5
    s.turned("Groove", [(6, -1), (9, -1), (9, 8), (6, 8)], body=f"{n} gear", operation="cut")
    v -= math.pi * (81 - 36) * 8
    s.holes("Bore", (0, 0, -1), (0, 0, 1), [(0, 0, -1)], 10, depth=20, target=f"{n} gear")
    v -= math.pi * 25 * 17.5
    v += s.turned("Bush", [(3, 0), (5, 0), (5, 17.5), (3, 17.5)], body=f"{n} bush")
    u = (math.cos(math.radians(45)), math.sin(math.radians(45)), 0)
    for b, R, r in ((f"{n} gear", 9.5, 5), (f"{n} bush", 5, 3)):
        s.holes(f"Ø3 cross hole ({b.split()[-1]})", (-11 * u[0], -11 * u[1], 0), u, [(-11 * u[0], -11 * u[1], 14)], 3,
                target=b)
        v -= cross_hole(R, 1.5, r)
    return v


@part("4-25", "Reversing shaft bearing plate", "Steel")
def reversing_bearing_plate(s):
    """Sheet 07, 4-25 (scale 1:2): a steel Ø32 x 3 plate with a Ø10 x 17 hub, reamed Ø6 through; Ø3
    holes 12.5 either side. Axis = Z."""
    v = s.turned("Plate", [(3, 0), (16, 0), (16, 3), (5, 3), (5, 20), (3, 20)])
    s.holes("Ø3 holes", (0, 0, -1), (0, 0, 1), [(0, 12.5, -1), (0, -12.5, -1)], 3, depth=5)
    return v - 2 * math.pi / 4 * 9 * 3


@part("4-28", "Reversing shaft rack cover plate", "Brass")
def rack_cover_plate(s):
    """Sheet 07, 4-28 (scale 1:2): a 1 thick brass disc Ø29 with a Ø4 centre hole and Ø2.5 holes 10
    either side. XY plane."""
    s.sketch("Plate", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.circle.center", center=[0, 0], diameter=29)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=4)
    for x in (-10, 10):
        s.cmd("sketch.circle.center", center=[x, 0], diameter=2.5)
    s.finish()
    s.cmd("solid.extrude", distance=1, profiles=[{"point": [0, 8]}], name="Plate", body_name=s.body)
    return math.pi / 4 * (29 ** 2 - 16 - 2 * 6.25)


@part("4-31", "Coupling guide pillar", "Brass")
def guide_pillar(s):
    """Sheet 07, 4-31: a brass pillar: an M4 x 5.5 stud (at Ø4), a Ø6 x 12 body, a Ø4 x 5 neck and an
    M3 x 3 end (at Ø3). Axis = Z."""
    return s.turned("Pillar", [(0, 0), (2, 0), (2, 5.5), (3, 5.5), (3, 17.5), (2, 17.5), (2, 22.5), (1.5, 22.5),
                               (1.5, 25.5), (0, 25.5)])


# ----------------------------------------------------------------------------- 4-27, 4-29, 4-30, 5-01
@part("4-27", "Reversing shaft rack", "Brass")
def reversing_rack(s):
    """Sheet 08, 4-27 (scale 1:1): a brass Ø31 x 2 flange with two M2.5 (Ø2.05) holes 10 either side,
    and a Ø17 body 23.2 long (3.7 + 19.5) with three V grooves 2.5 wide at the top and 1 at the
    bottom (to Ø13) at a 3.5 pitch, starting 3.7 from the flange; bored Ø10. The Ø29 step drawn on
    the flange's back is not modelled. Axis = Z, the flange's face on Z = 0."""
    pts = [(5, 0), (15.5, 0), (15.5, 2), (8.5, 2)]
    z = 2 + 3.7
    for k in range(3):
        z0 = z + 3.5 * k + 0.5
        pts += [(8.5, z0), (6.5, z0 + 0.75), (6.5, z0 + 1.75), (8.5, z0 + 2.5)]
    pts += [(8.5, 2 + 3.7 + 19.5), (5, 2 + 3.7 + 19.5)]
    v = s.turned("Rack", pts)
    s.holes("M2.5 tapped", (0, 0, -1), (0, 0, 1), [(0, 10, -1), (0, -10, -1)], 2.05, depth=4)
    return v - 2 * math.pi / 4 * 2.05 ** 2 * 2


@part("4-29", "Reversing shaft pinion", {"pinion": "Brass", "shaft": "Steel", "sleeve": "Brass"})
def reversing_pinion(s):
    """Sheet 08, 4-29 (the shaft drawn broken): a brass pinion, 9 teeth, Ø11 over the tips and Ø7 at
    the roots (1 wide at the tip, 1.5 at the root), 6 wide, 5 from the end of a Ø4 steel shaft; a
    brass sleeve Ø5.5 x 20 with Ø2 cross holes 4 from each end. The shaft's length is taken as 68
    (60 drawn to the sleeve, the sleeve at its far end). Axis = Z."""
    n = s.body.split()[0]
    v = gear_prism(s, "Pinion", gear_points(9, 11, 7, 1, 1.5), 5, 6, 4, f"{n} pinion", operation="new")
    v += s.turned("Shaft", [(0, 0), (2, 0), (2, 68), (0, 68)], body=f"{n} shaft")
    v += s.turned("Sleeve", [(2, 48), (2.75, 48), (2.75, 68), (2, 68)], body=f"{n} sleeve")
    s.holes("Sleeve cross holes", (-4, 0, 0), (1, 0, 0), [(-4, 0, 52), (-4, 0, 64)], 2, target=f"{n} sleeve")
    return v - 2 * cross_hole(2.75, 1, 2)


def belt_trapezoid_centroid(a, b, h):
    """Distance of a trapezoid's centroid from its side a (sides a, b parallel, height h)."""
    return h * (a + 2 * b) / (3 * (a + b))


@part("4-30", "V-belt", "Default")
def v_belt(s):
    """Sheet 08, 4-30 (section A-A): a rubber V-belt, 4 wide outside, 2.5 inside, 3 deep, running over
    ends of R10 and R14 (outside) 101.6 apart. Swept along its inside edge. Default density with the
    black rubber appearance. The loop in the XY plane, the R10 end on the origin."""
    D, R1, R2, H, A, B = 101.6, 10, 14, 3, 2.5, 4
    r1, r2 = R1 - H, R2 - H                                    # the inside edge
    c1, c2 = (0, 0), (0, -D)
    phi = math.asin((r2 - r1) / D)
    # the tangent points on the right (+X) and left sides
    p1r = (r1 * math.cos(phi), r1 * math.sin(phi))
    p2r = (r2 * math.cos(phi), -D + r2 * math.sin(phi))
    p1l, p2l = (-p1r[0], p1r[1]), (-p2r[0], p2r[1])
    rnd = lambda q: [round(q[0], 6), round(q[1], 6)]
    s.sketch("Path", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.cmd("sketch.line", points=[rnd(p2r), rnd(p1r)])                               # l1
    s.cmd("sketch.arc.center_point", center=[0, 0], start=rnd(p1r), end=rnd(p1l))   # a1
    s.cmd("sketch.line", points=[rnd(p1l), rnd(p2l)])                               # l2
    s.cmd("sketch.arc.center_point", center=[0, -D], start=rnd(p2l), end=rnd(p2r))  # a2
    s.finish()
    d = (p1r[0] - p2r[0], p1r[1] - p2r[1])
    L = math.hypot(*d)
    u = (d[0] / L, d[1] / L)
    out = (u[1], -u[0])                                        # outward (+X side)
    # the section at the start of l1: inside edge on the path, the wide side outward
    s.sketch("Section", (p2r[0], p2r[1], 0), (round(out[0], 9), round(out[1], 9), 0), (0, 0, 1))
    s.polyline([(0, -A / 2), (H, -B / 2), (H, B / 2), (0, A / 2)])
    s.finish()
    s.cmd("solid.sweep", sketch="Section", path_sketch="Path", path=["l1", "a1", "l2", "a2"], name="Belt",
          body_name=s.body)
    s.cmd("appearance.assign", bodies=[s.body], appearance="Rubber - Black")
    area = (A + B) / 2 * H
    k = belt_trapezoid_centroid(A, B, H)
    return area * (2 * L + (r1 + k) * (math.pi - 2 * phi) + (r2 + k) * (math.pi + 2 * phi))


@part("5-01", "Belt", {"upper loop": "Nylon", "lower loop": "Nylon"})
def nylon_belt(s):
    """Sheet 11, 5-01: a nylon band 3 wide and 0.5 thick in a figure of two loops: an R16 loop whose
    legs meet 107.5 below its centre and 16.3 to the side, and an R6 loop 38.5 further across and
    20.5 below that point. Each loop is one sweep (line, arc, line) from the meeting point; the drawn
    R2 there is sharp, and the two loops are separate solids that meet there. XY plane."""
    n = s.body.split()[0]
    W, T = 3, 0.5
    V = (16.3, -107.5)
    v = 0.0
    for name, c, r, left_first in (("upper loop", (0, 0), 16, False), ("lower loop", (16.3 + 38.5, -107.5 - 20.5), 6, True)):
        t1 = tangent_from(V, c, r, left=left_first)
        t2 = tangent_from(V, c, r, left=not left_first)
        rnd = lambda q: [round(q[0], 6), round(q[1], 6)]
        a1 = math.atan2(t1[1] - c[1], t1[0] - c[0])
        a2 = math.atan2(t2[1] - c[1], t2[0] - c[0])
        sk = f"Path {name}"
        s.sketch(sk, (0, 0, 0), (1, 0, 0), (0, 1, 0))
        s.cmd("sketch.line", points=[rnd(V), rnd(t1)])                                          # l1
        # the arc runs the long way round, from t1 to t2: counter-clockwise when the first tangent
        # is on the right of V→centre
        ccw = not left_first
        start, end = (t1, t2) if ccw else (t2, t1)
        s.cmd("sketch.arc.center_point", center=rnd(c), start=rnd(start), end=rnd(end))         # a1
        s.cmd("sketch.line", points=[rnd(t2), rnd(V)])                                          # l2
        s.finish()
        sweep = (a2 - a1) % (2 * math.pi) if ccw else (a1 - a2) % (2 * math.pi)
        d = (t1[0] - V[0], t1[1] - V[1])
        L = math.hypot(*d)
        u = (d[0] / L, d[1] / L)
        nrm = (-u[1], u[0])
        sec = f"Section {name}"
        s.sketch(sec, (V[0], V[1], 0), (round(nrm[0], 9), round(nrm[1], 9), 0), (0, 0, 1))
        s.cmd("sketch.rectangle.two_point", p0=[-T / 2, -W / 2], p1=[T / 2, W / 2])
        s.finish()
        s.cmd("solid.sweep", sketch=sec, path_sketch=sk, path=["l1", "a1", "l2"], name=name.capitalize(),
              body_name=f"{n} {name}")
        v += W * T * (2 * L + r * sweep)
    return v


# ----------------------------------------------------------------------------- 3-27B, 3-27E, 3-25D
@part("3-27B", "Hand break handle", "Steel")
def hand_brake_handle(s):
    """Sheet 07, 3-27B (scale 1:1.5): a 2 thick steel lever: an R6 end round a Ø8 hole (3-27C's
    spigot), tapering to 7 wide 52 along; an M4 (Ø3.3) at 21 and a Ø2 at 32, 2.5 off the centre line;
    then a tip 4 wide and 20 long with a round end. XY plane, Z = 0..2."""
    T = 2
    tr = tangent_from((52, 3.5), (0, 0), 6, left=False)
    tl = (tr[0], -tr[1])
    start = (52, -2)
    segs = [("line", (70, -2)), ("arc", (70, 0), (70, 2), True), ("line", (52, 2)), ("line", (52, 3.5)), ("line", tr),
            ("arc", (0, 0), tl, True), ("line", (52, -3.5)), ("line", start)]
    s.sketch("Lever", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[0, 0], diameter=8)
    s.cmd("sketch.circle.center", center=[21, 0], diameter=3.3)
    s.cmd("sketch.circle.center", center=[32, -2.5], diameter=2)
    s.finish()
    s.cmd("solid.extrude", distance=T, profiles=[{"point": [45, 0]}], name="Lever", body_name=s.body)
    return (loop_area(start, segs) - math.pi / 4 * (64 + 3.3 ** 2 + 4)) * T


@part("3-27E", "Hand break release handle", "Brass")
def release_handle(s):
    """Sheet 07, 3-27E (from the side and top views): a brass blade 6.5 wide: in side view the top
    edge runs straight for 50, then rises 16° for 16 to a tip 1.5 thick; the lower edge falls from the
    tip to an R4 round about a Ø5 hole 18 along and 6.5 below the top (10.5 deep there), then rises
    to the top at the left end. A fork slot from the left end: 3 wide for 10.5, then 2 wide to 25
    (taken right through the blade's height). Side profile in the XZ plane, the top at Z = 0; the
    6.5 width along Y."""
    W = 6.5
    c, r = (18, -6.5), 4
    a = math.radians(16)
    tip_top = (50 + 16 * math.cos(a), 16 * math.sin(a))
    tip_low = (tip_top[0] + 1.5 * math.sin(a), tip_top[1] - 1.5 * math.cos(a))
    t_right = tangent_from(tip_low, c, r, left=True)           # below the circle, seen from the tip
    t_left = tangent_from((0, 0), c, r, left=False)
    start = (0, 0)
    segs = [("line", t_left), ("arc", c, t_right, True), ("line", tip_low), ("line", tip_top), ("line", (50, 0)),
            ("line", start)]
    s.sketch("Side", (0, 0, 0), (1, 0, 0), (0, 0, 1))                     # normal -Y
    s.loop(start, segs)
    s.cmd("sketch.circle.center", center=[18, -6.5], diameter=5)
    s.finish()
    s.cmd("solid.extrude", distance=W / 2, direction="symmetric", profiles=[{"point": [30, -1]}], name="Blade",
          body_name=s.body)
    v = (loop_area(start, segs) - math.pi * 6.25) * W
    # the fork slot, cut down through the blade (2.25 from one face: centred on Y = -0.5 for the 3 wide part)
    s.sketch("Fork slot", (0, 0, 2), (1, 0, 0), (0, -1, 0))                # normal -Z
    s.cmd("sketch.line", points=[[-1, 1], [25, 1], [25, -1], [10.5, -1], [10.5, -2], [-1, -2]],
          closed=True)
    s.finish()
    s.cmd("solid.extrude", distance=15, operation="cut", targets=[s.body], name="Fork slot")
    # the slot's area across the profile (by sampling the profile's height at each x)
    def height(x):
        top = 0.0
        if x <= t_left[0]:
            low = (t_left[1] / t_left[0]) * x
        elif x <= t_right[0]:
            dy = math.sqrt(max(r * r - (x - c[0]) ** 2, 0))
            low = c[1] - dy
        else:
            low = t_right[1] + (tip_low[1] - t_right[1]) * (x - t_right[0]) / (tip_low[0] - t_right[0])
        h = top - low
        if abs(x - 18) < 2.5:
            h -= 2 * math.sqrt(6.25 - (x - 18) ** 2)
        return h
    n, cut = 5000, 0.0
    for i in range(n):
        x = (i + 0.5) * 25 / n
        cut += height(x) * (3 if x < 10.5 else 2) * 25 / n
    return v - cut


@part("3-25D", "Drivers seat back rest", "Oak")
def seat_back_rest(s):
    """Sheet 06, 3-25D (scale 1:1.5): a wooden back rest 43.5 x 16, 8 thick, R7 corners in plan; the
    R7 rounding of its front edges and the 12° bend of its ends are not modelled. Oak density. XY
    plane."""
    L, W, R, T = 43.5, 16, 7, 8
    a, b = L / 2, W / 2
    start = (-a + R, -b)
    segs = [("line", (a - R, -b)), ("arc", (a - R, -b + R), (a, -b + R), True), ("line", (a, b - R)),
            ("arc", (a - R, b - R), (a - R, b), True), ("line", (-a + R, b)), ("arc", (-a + R, b - R), (-a, b - R), True),
            ("line", (-a, -b + R)), ("arc", (-a + R, -b + R), start, True)]
    s.sketch("Back rest", (0, 0, 0), (1, 0, 0), (0, 1, 0))
    s.loop(start, segs)
    s.finish()
    s.cmd("solid.extrude", distance=T, name="Back rest", body_name=s.body)
    return loop_area(start, segs) * T


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
    run = subprocess.run([ARGS.cli, "run", path, "--save", base + ".solvecraft", "--out", base + ".step", "--out",
                          stl, "--quiet"], capture_output=True, text=True)
    if run.returncode:
        print(f"{number}: FAIL {run.stderr.strip()[:400]}")
        return False
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
    ok = len(bodies) == n_bodies and not errors and abs(dv) < TOLERANCE[number] and (open_edges or abs(dm) < max(0.015, 3 * TOLERANCE[number]))
    mesh = f"{mesh_vol:.1f} ({dm * 100:+.2f} %)" if not open_edges else f"not closed ({open_edges} open edges)"
    print(f"{number}: {'OK  ' if ok else 'FAIL'} {len(bodies)}/{n_bodies} bodies, hand volume {estimate:.1f} mm³, "
          f"STL mesh {mesh}, SolidCraft {vol:.1f} ({dv * 100:+.2f} %), mass {mass:.1f} g, "
          f"box {' x '.join(f'{hi[i] - lo[i]:.2f}' for i in range(3))} from ({', '.join(f'{v:.2f}' for v in lo)})")
    for t in errors + notes:
        print(f"   {t['name']}: {t.get('error') or t.get('warning')}")
    # rendered from the script: a sketch hidden with browser.visibility shows again in a reopened
    # .solvecraft file (SolidCraft does not save sketch visibility)
    subprocess.run([ARGS.cli, "snapshot", path, "--out", base + ".png", "--view", "iso"],
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
