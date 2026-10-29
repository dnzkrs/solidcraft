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
