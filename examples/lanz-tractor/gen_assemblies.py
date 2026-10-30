#!/usr/bin/env python3
"""Lanz mini tractor: subassemblies built from the part designs in parts/.

Each subassembly is a SolidCraft command script (assemblies/<name>.json) that links the part
designs (component.insert_design) and places every occurrence with a rigid move worked out from
how the parts mate: shafts in bores, shoulders on shoulders, holes on holes. The drawings' assembly
sheets (08 to 11) show the subassemblies only as 3D views, so every placement below says which
mating sizes fix it.

  python3 gen_assemblies.py                 # write the scripts
  python3 gen_assemblies.py --build         # also build, check interference and snapshot them

Outputs per subassembly in assemblies/: <name>.json, <name>.solvecraft, <name>.png.
"""
import argparse
import json
import math
import os
import shutil
import subprocess

_here = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(_here, "assemblies")
PARTS = os.path.join("..", "parts")                 # part designs, relative to assemblies/

_ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
_ap.add_argument("names", nargs="*", help="subassemblies to write (default: all)")
_ap.add_argument("--build", action="store_true", help="build, check interference and snapshot")
_ap.add_argument("--cli", default=os.environ.get("SOLVECRAFT_CLI") or shutil.which("solvecraft-cli")
                 or os.path.join(_here, "..", "..", "target", "release", "solvecraft-cli"))
ARGS = _ap.parse_args()

ASSEMBLIES = {}


def assembly(name, title):
    def reg(fn):
        ASSEMBLIES[name] = (title, fn)
        return fn
    return reg


# ----------------------------------------------------------------------------- rotations
def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


I3 = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
FLIP_X = [[1, 0, 0], [0, -1, 0], [0, 0, -1]]        # half a turn about X: Z points the other way


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def frame(x, y, z):
    """The rotation taking the part's X, Y, Z axes to the given (right-handed) directions."""
    return [[x[i], y[i], z[i]] for i in range(3)]


class Assembly:
    def __init__(self, name):
        self.name = name
        self.cmds = []
        self.count = {}
        self.placed = []                                # (occurrence, part, R, t, note)
        self.first = {}                                 # part: placement of its first occurrence

    def place(self, part, R=I3, t=(0, 0, 0), note="", sub=False):
        """Link the part's design (or, with sub, a finished subassembly's) and move its occurrence
        to x_world = R x_part + t."""
        n = self.count.get(part, 0) + 1
        self.count[part] = n
        path = f"{part}.solvecraft" if sub else os.path.join(PARTS, f"{part}.solvecraft")
        params = {"path": path, "name": part}
        if n > 1:
            params["reuse"] = True
        self.cmds.append({"command": "component.insert_design", "params": params})
        occ = f"{part}:{n}"
        # occurrence.move applies its matrix on top of the current placement, and a reused
        # occurrence starts where the part's first one is: move it by D F^-1
        if n == 1:
            self.first[part] = (R, t)
            Rm, tm = R, t
        else:
            RF, tF = self.first[part]
            Rm = [[sum(R[i][k] * RF[j][k] for k in range(3)) for j in range(3)] for i in range(3)]
            tm = [t[i] - sum(Rm[i][k] * tF[k] for k in range(3)) for i in range(3)]
        m = [round(v, 9) for row in ((Rm[i][0], Rm[i][1], Rm[i][2], tm[i]) for i in range(3)) for v in row]
        if m != [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0]:
            self.cmds.append({"command": "occurrence.move", "params": {"occurrence": occ, "space": "world",
                                                                       "matrix": m, "move_grounded": True}})
        self.placed.append((occ, part, R, tuple(t), note))
        return occ


# ----------------------------------------------------------------------------- SA-3-315
@assembly("SA-3-315", "Rear axle with differential and wheels")
def rear_axle(a):
    """SA-3-301 (differential and housings), SA-3-302/303 (the axles with their mounting plates) and
    the two wheels SA-3-304, as drawn on sheet 10. The axle runs along Z; Z = 0 is the end of
    3-04's tube. The stack is fixed by its mating sizes, and it closes exactly:
    - 3-03's Ø42 spigot enters 3-04's Ø42 cavity, the two flanges face to face (3-03 turned over);
      the drive gear 3-18 sits over 3-03's Ø20 hub against its flange, holes on 3-03's holes;
    - the side gears' Ø13 hubs bottom on the Ø14 bores' steps (Z 16 in 3-04, Z 58 in 3-03), which
      puts their pitch apexes 6.51 from the cross shaft at Z 37 (the Ø6 hole 15 from 3-04's
      flange face); the planet on the cross shaft then reaches the cavity wall (6.51 + 14.49 = 21);
    - each axle's shoulder sits on its side gear's hub, its Ø6 end in the gear's bore;
    - the axle's cross pin sits in 3-14's Ø4.5 cross hole, and 3-14's hub then meets the spacer
      3-13 exactly, which meets the bearing 3-08 in the housing's Ø20 bore;
    - the bearings 3-07 sit on the housing tubes against the Ø20 hubs, inside the bearing housings'
      Ø32 counterbores; the rims 3-15 are bolted to 3-14's flanges over their Ø20 hubs."""
    c = math.sqrt(0.5)
    u = (c, c, 0)                                      # the cross shaft's direction (3-04's hole)
    planet = frame((0, 0, 1), (c, -c, 0), u)
    a.place("3-04", note="base: Z 0 the tube's end, flange face at Z 52")
    a.place("3-03", FLIP_X, (0, 0, 74), "turned over, flange face on 3-04's at Z 52")
    a.place("3-18", rot_z(22.5), (0, 0, 54), "over 3-03's Ø20 hub, on its flange; holes on its holes")
    a.place("3-07", I3, (0, 0, 2), "on 3-04's tube, against the Ø20 hub at Z 12")
    a.place("3-07", I3, (0, 0, 62), "on 3-03's tube, against the Ø20 hub at Z 62")
    a.place("3-06", I3, (0, 0, -40.5), "its Ø32 counterbore over the bearing (Z 2 to 12)")
    a.place("3-05", FLIP_X, (0, 0, 87.5), "its Ø32 counterbore over the bearing (Z 62 to 72)")
    a.place("3-08", I3, (0, 0, -41.5), "in 3-06's Ø20 bore against its step (Z -33.5)")
    a.place("3-08", I3, (0, 0, 80.5), "in 3-05's Ø20 bore against its step (Z 80.5)")
    a.place("3-13", I3, (0, 0, -60.5), "against the bearing")
    a.place("3-13", I3, (0, 0, 88.5), "against the bearing")
    a.place("3-10", FLIP_X, (0, 0, 30.49), "side gear: hub on 3-04's Ø14 bore step (Z 16)")
    a.place("3-10", I3, (0, 0, 43.51), "side gear: hub on 3-03's Ø14 bore step (Z 58)")
    a.place("3-10", planet, tuple(6.51 * u[i] + (37 if i == 2 else 0) for i in range(3)),
            "planet on the cross shaft, its hub on the cavity wall")
    a.place("3-11", planet, tuple(-22.75 * u[i] + (37 if i == 2 else 0) for i in range(3)),
            "cross shaft through 3-04, centred")
    a.place("3-09B", I3, (0, 0, -78), "shoulder on the side gear's hub (Z 16); cross pin at Z -65.5")
    a.place("3-09A", FLIP_X, (0, 0, 125), "shoulder on the side gear's hub (Z 58); cross pin at Z 112.5")
    a.place("3-14", rot_z(-45), (0, 0, -84.5), "cross hole on the axle's pin; hub on the spacer (Z -60.5)")
    a.place("3-14", matmul(rot_z(45), FLIP_X), (0, 0, 131.5), "cross hole on the pin; hub on the spacer (Z 107.5)")
    a.place("3-15", rot_z(-45), (0, 0, -85.5), "web on 3-14's flange (Z -78.5), over its Ø20 hub")
    a.place("3-15", matmul(rot_z(45), FLIP_X), (0, 0, 132.5), "web on 3-14's flange (Z 125.5)")
    a.place("3-16", I3, (0, 0, -72.5), "on the rim's Ø132 floor")
    a.place("3-16", I3, (0, 0, 119.5), "on the rim's Ø132 floor")
    a.place("3-17", I3, (0, 0, -86.5), "spigot in 3-14's Ø8 bore, flange on its hub's end")
    a.place("3-17", FLIP_X, (0, 0, 133.5), "spigot in 3-14's Ø8 bore")


# ----------------------------------------------------------------------------- SA-2-206
@assembly("SA-2-206", "Front wheel")
def front_wheel(a):
    """The front wheel (sheet 09's SA-2-206) with its bearing and axle. The rim's hub face is Z 0, the
    web toward +Z. The hub cap 2-33's Ø16 spigot (1 high) fills the top of the rim's 9 deep Ø16
    counterbore, which leaves 8 for the bearing 2-29 (8 wide) against the Ø14 step at Z 9; the
    wheel axle 2-28's Ø6 x 8 fills the bearing, its Ø8 head in the cap's Ø14 recess and its Ø5
    and M4 end out through the web. The cap's Ø3 holes are on the rim's M3 holes (Ø24 PCD); the
    tyre sits on the rim's Ø62 floor."""
    a.place("2-31", note="base: hub face at Z 0")
    a.place("2-33", matmul(rot_z(45), FLIP_X), (0, 0, 1), "spigot in the Ø16 counterbore, flange on the hub face")
    a.place("2-29", I3, (0, 0, 1), "in the counterbore under the cap's spigot, against the Ø14 step")
    a.place("2-28", I3, (0, 0, -1), "Ø6 x 8 in the bearing, head in the cap's recess")
    a.place("2-32", I3, (0, 0, 11.8), "on the Ø62 floor")


# ----------------------------------------------------------------------------- SA-2-202
@assembly("SA-2-202", "Front axle yoke")
def front_axle_yoke(a):
    """The front axle yoke (sheet 09's SA-2-202): X across the tractor, Y forward, Z up. The arms
    stand upright, 2-20 in front with its rear face on Y = 0, 2-18 behind with its front face on
    Y = -118.5 (the tie rods' Ø5 length). The fits that place them:
    - the tie rods 2-19 run through both arms' Ø3 holes at X ±47 (2-20's hole line on Z = 0,
      2-18's 10 below its Ø12), their M3 ends 7 long through the 4 thick arms;
    - both arms' Ø12 holes are then on one axis (Z 10), and the bearings 2-21 sit in them, the
      bushes' 4.1 spigots in the 4 thick arms, flanges and pin heads outside;
    - the hinge brackets 2-22 lie on 2-20's front face, their M4 and M3 holes (14 apart) on its Ø4
      at 64.5 and Ø3 at 78.5, the eyes vertical beyond the arm's ends (that they are on the front
      face, not the back, is read from sheet 09's 3D view, which does not show it clearly)."""
    up_front = frame((1, 0, 0), (0, 0, 1), (0, -1, 0))  # part X across, part Y up, part Z backward
    a.place("2-20", up_front, (0, 4, 0), "front arm: rear face on Y = 0, hole line on Z = 0")
    a.place("2-18", up_front, (0, -118.5, 10), "rear arm: front face on Y = -118.5, its holes on Z = 0")
    rod = frame((1, 0, 0), (0, 0, 1), (0, -1, 0))
    for x in (-47, 47):
        a.place("2-19", rod, (x, 7, 0), "Ø5 between the arms, M3 ends through them")
    a.place("2-21", up_front, (0, 11, 10), "bush in 2-20's Ø12, flange on its front face")
    a.place("2-21", frame((1, 0, 0), (0, 0, -1), (0, 1, 0)), (0, -129.5, 10), "bush in 2-18's Ø12, flange behind")
    a.place("2-22", frame((1, 0, 0), (0, 0, 1), (0, -1, 0)), (57.5, 4, 0), "on 2-20's front face, holes at X 64.5 / 78.5")
    a.place("2-22", frame((-1, 0, 0), (0, 0, -1), (0, -1, 0)), (-57.5, 4, 0), "on 2-20's front face, holes at X -64.5 / -78.5")


# ----------------------------------------------------------------------------- SA-1-110
@assembly("SA-1-110", "Exhaust stack")
def exhaust_stack(a):
    """The exhaust stack (sheet 08's SA-1-110) on its axis Z, the bracket's base on Z 0:
    - the base ring 1-37's Ø33 x 7 counterbore goes over the bracket 1-36's Ø33 x 7 band (Z 31 to
      38), its Ø3 holes 3.5 up on the bracket's M3 holes 3.5 below the band's top;
    - the stack 1-38's Ø33 flange sits on the ring's Ø33 cone top (Z 47), its Ø24 bore continuing
      the bracket's Ø24 bore;
    - the top ring 1-39's 4 deep Ø19 bore goes over the stack's Ø19 x 4 top band (Z 143)."""
    a.place("1-36", note="base on Z 0")
    a.place("1-37", I3, (0, 0, 31), "counterbore over the bracket's band")
    a.place("1-38", I3, (0, 0, 47), "flange on the ring's cone top")
    a.place("1-39", I3, (0, 0, 143), "over the stack's top band")


# ----------------------------------------------------------------------------- SA-1-102
@assembly("SA-1-102", "Cylinder oiler")
def cylinder_oiler(a):
    """The cylinder oiler (sheet 08's SA-1-102) on its axis Z, the base's stud end on Z 0:
    - the glass base 1-08's M6 screws into the oiler base 1-07's M6 hole, its flange on the hex's
      top (Z 15.5); threads are modelled at their major diameter and tapped holes at the tap drill,
      so the thread shows as an overlap (43 mm³ of the 48.7 checked; the rest is the Ø4 nozzle
      reaching about 1 below the 8 deep tapped hole, a small conflict in the read sizes);
    - the glass 1-09 stands in 1-08's Ø15 x 1 recess (Z 16.5), and the top 1-10's Ø15 x 1 recess
      caps it (the M3 screw that holds them, into 1-08's boss, is not a part of the list)."""
    a.place("1-07", note="stud end on Z 0")
    a.place("1-08", I3, (0, 0, 6.5), "M6 in 1-07's tapped hole, flange on the hex (Z 15.5)")
    a.place("1-09", I3, (0, 0, 16.5), "in 1-08's recess")
    a.place("1-10", I3, (0, 0, 34.5), "recess over the glass's top (Z 35.5)")


# ----------------------------------------------------------------------------- SA-1-101
@assembly("SA-1-101", "Engine block")
def engine_block(a):
    """The engine block (sheet 08's SA-1-101) in the frame's own axes: X along the engine (X 0 the
    cylinder upright's outer face), Y across, Z up from the frame's underside; the cylinder axis
    is X at Z 70.
    - the cylinder 1-02 bolts to the upright's outer face on the same 4 x M4 / Ø4.5 pattern (PCD
      44 at 45°), its 9 mm oiler flange against the frame and the radial oiler hole up;
    - the gasket ring 1-03's Ø32 spigot goes into the bore's outer end, then the inner head 1-04
      (its countersunk face toward the cylinder, the valve channel outward) and the outer head
      1-05 (its countersunk face outward), all on the same bolt pattern;
    - the crankshaft bearings 1-06 (9 wide) fill the 9 thick cheeks' Ø19 bores at X 68, Z 70;
    - the cylinder oiler SA-1-102 screws into the oiler hole, 4.5 from the flange's end, its
      collar on the flange (Z 98)."""
    cyl = frame((0, 0, 1), (0, -1, 0), (1, 0, 0))          # part Z along X, part X up
    a.place("1-01", note="base: the frame's own axes")
    a.place("1-02", cyl, (-71, 0, 70), "oiler flange on the upright's outer face, axis at Z 70")
    a.place("1-03", cyl, (-73, 0, 70), "spigot in the bore's outer end")
    a.place("1-04", cyl, (-76.5, 0, 70), "countersunk face on the gasket, channel outward")
    a.place("1-05", cyl, (-80, 0, 70), "on the inner head, countersunk face outward")
    brg = frame((1, 0, 0), (0, 0, -1), (0, 1, 0))
    a.place("1-06", brg, (68, 19, 70), "in the cheek's Ø19 bore")
    a.place("1-06", brg, (68, -28, 70), "in the other cheek's Ø19 bore")
    a.place("SA-1-102", I3, (-4.5, 0, 92), "stud in the cylinder's oiler hole, collar on the flange", sub=True)


# ----------------------------------------------------------------------------- SA-1-103, SA-1-104, SA-1-105
@assembly("SA-1-103", "Flywheel with drive pulley")
def flywheel_pulley(a):
    """A flywheel on its hub (sheet 08's SA-1-103), in the hub's axes (Z 0 its threaded end): the
    flywheel 1-21's 6 thick web (Ø16 bore) on the hub 1-20's Ø16 thread against its collar (Z 13.5
    to 19.5), and the drive pulley 1-15 screwed on against the web, boss first."""
    a.place("1-20", note="base: threaded end on Z 0, collar from Z 19.5")
    a.place("1-21", I3, (0, 0, 7), "web on the thread against the collar")
    a.place("1-15", FLIP_X, (0, 0, 13.5), "screwed on against the web, boss first")


@assembly("SA-1-104", "Flywheel with cam plate")
def flywheel_cam(a):
    """A flywheel on its hub with the cam plate (sheet 08's SA-1-104), in the hub's axes: the
    flywheel as on SA-1-103, the cam plate 1-17 screwed on against its web, and the lock nut 1-18
    whose Ø19 collar enters the cam's Ø19 counterbore (2.5 deep) and stops on its floor."""
    a.place("1-20", note="base: threaded end on Z 0, collar from Z 19.5")
    a.place("1-21", I3, (0, 0, 7), "web on the thread against the collar")
    a.place("1-17", FLIP_X, (0, 0, 13.5), "against the web, its counterbore outward")
    a.place("1-18", I3, (0, 0, 3), "collar in the cam's counterbore, on its floor (Z 11)")


@assembly("SA-1-105", "Crankshaft and flywheels")
def crankshaft(a):
    """The crankshaft with both flywheels, in the engine block's axes (SA-1-101): the crank axis is Y
    at X 68, Z 70, the crankpin toward the cylinder (top dead centre). Each hub's collar is 2 clear
    of the cheek (Y ±30), which puts the hub's M6 grub screw exactly on the left shaft's Ø4 cross
    hole (Y -38) on the -Y side. Which side carries the cam plate and which the drive pulley is
    not clear on the drawings: the cam plate is taken on +Y."""
    a.place("1-14", frame((-1, 0, 0), (0, 0, 1), (0, 1, 0)), (68, 0, 70), "journals in the 1-06 bearings")
    a.place("SA-1-104", frame((1, 0, 0), (0, 0, 1), (0, -1, 0)), (68, 64.5, 70), "hub collar at Y 30", sub=True)
    a.place("SA-1-103", frame((1, 0, 0), (0, 0, -1), (0, 1, 0)), (68, -64.5, 70), "hub collar at Y -30, grub on the cross hole", sub=True)


# ----------------------------------------------------------------------------- driver
def write(name):
    title, fn = ASSEMBLIES[name]
    a = Assembly(name)
    fn(a)
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"{name}.json")
    with open(path, "w") as f:
        json.dump({"commands": a.cmds}, f, indent=1)
        f.write("\n")
    return path, a


def build(name, path, a):
    base = os.path.join(OUT, name)
    run = subprocess.run([ARGS.cli, "run", os.path.basename(path), "--save", name + ".solvecraft", "--quiet"],
                         cwd=OUT, capture_output=True, text=True)
    if run.returncode:
        print(f"{name}: FAIL {run.stderr.strip()[:400]}")
        return False
    check = os.path.join(OUT, f".{name}.check.json")
    with open(path) as f:
        cmds = json.load(f)["commands"]
    cmds.append({"command": "inspect.interference", "params": {"budget_s": 1800}})
    with open(check, "w") as f:
        json.dump({"commands": cmds}, f)
    res = subprocess.run([ARGS.cli, "run", os.path.basename(check), "--results"], cwd=OUT, capture_output=True, text=True)
    os.remove(check)
    hits, unchecked = [], []
    try:
        out = json.loads(res.stdout[res.stdout.index("["):])
        hits = out[-1].get("interferences", [])
        unchecked = out[-1].get("unchecked", [])
    except (ValueError, IndexError, AttributeError):
        print(f"{name}: interference check failed: {res.stderr.strip()[:300]}")
    snap = subprocess.run([ARGS.cli, "snapshot", os.path.basename(path), "--out", name + ".png", "--view", "iso",
                           "--width", "1200", "--height", "900"], cwd=OUT, capture_output=True, text=True)
    print(f"{name}: {len(a.placed)} occurrences, {len(hits)} overlapping pairs"
          + ("" if snap.returncode == 0 else f", snapshot failed: {snap.stderr.strip()[:200]}"))
    for h in hits:
        print(f"   {h.get('a')} / {h.get('b')}: {h.get('volume_mm3', 0):.2f} mm³ at {[round(v, 1) for v in h.get('center', [])]}")
    for u in unchecked:
        print(f"   not checked: {u.get('a')} / {u.get('b')}: {u.get('reason', '')[:120]}")
    return True


def main():
    names = ARGS.names or list(ASSEMBLIES)
    for name in names:
        path, a = write(name)
        if ARGS.build:
            build(name, path, a)
        else:
            print(f"{name}: {path}")


if __name__ == "__main__":
    main()
