# Lanz mini tractor: parts modelled in SolidCraft

Single parts of the "Lanz Mini Tractor" model (live-steam style engine and chassis), modelled in
SolidCraft from the 13-sheet drawing set *LANZ-A3* by J.A.M. de Waal, JDW Draughting Services
(2014), after the original Dutch drawings by C.P. Hendrikx (1996). The drawings are copyrighted by
their author and are **not** in this repository; this folder holds only the models made from them,
for private use in this fork. Part numbers and names follow the drawings' parts list (sheet 02).

| File | What it is |
|---|---|
| `gen_parts.py` | Parametric generator: one function per part, every dimension in its parameter block with where it comes from |
| `parts/<part>.json` | SolidCraft command script that builds the part |
| `parts/<part>.solvecraft` | The part: open it in SolidCraft (`solvecraft parts/1-01.solvecraft`) |
| `parts/<part>.step` | STEP export |
| `parts/<part>.png` | Iso snapshot (`solvecraft-cli snapshot`) |

```sh
python3 gen_parts.py                 # write the scripts
python3 gen_parts.py --build         # build, save, export STEP + PNG and check every part
python3 gen_parts.py --build 1-02    # only some parts
```

`--build` fails a part unless it has the expected number of valid solids (one, or one per piece of
a pressed-together part such as the crankshaft) with no errors in its timeline, SolidCraft's
measured volume is within 0.1 % of a volume computed by hand from the drawing dimensions, and the
volume of the exported mesh agrees within 1.5 % (when the STL is closed; thin rods read low).

Units are mm. Each part has its own coordinate system, stated in its docstring in `gen_parts.py`.

How the parts were made, step by step, with the problems met on the way: [activity logs](activity-logs/README.md).

## Parts

<!-- parts -->
| Part | Name | Material | Bodies | Volume mm³ | Mass g |
|---|---|---|---:|---:|---:|
| 1-01 | Motor frame | Aluminum | 1 | 223,383.9 | 603.1 |
| 1-02 | Motor cylinder | Cast Iron | 1 | 60,778.4 | 437.6 |
| 1-03 | Motor cylinder gasket ring | Copper | 1 | 719.5 | 6.4 |
| 1-04 | Motor inner cylinder head | Cast Iron | 1 | 7,447.7 | 53.6 |
| 1-05 | Motor outer cylinder head | Cast Iron | 1 | 8,008.4 | 57.7 |
| 1-06 | Motor crank shaft ball bearing | Steel | 1 | 1,835.5 | 14.4 |
| 1-07 | Motor cylinder oiler base | Brass | 1 | 395.5 | 3.4 |
| 1-08 | Motor cylinder oiler glass base | Brass | 1 | 472.0 | 4.0 |
| 1-09 | Motor cylinder oiler glass | Polycarbonate | 1 | 835.6 | 1.0 |
| 1-10 | Motor cylinder oiler glass top | Brass | 1 | 460.3 | 3.9 |
| 1-11 | Motor block oil channel | Steel | 1 | 1,928.5 | 15.1 |
| 1-12 | Motor block oil valve part-1 | Brass | 1 | 1,169.1 | 9.9 |
| 1-13 | Motor block oil valve part-2 | Brass | 1 | 411.7 | 3.5 |
| 1-14 | Motor crank shaft | Stainless Steel, Steel | 5 | 28,817.5 | 227.8 |
| 1-15 | Motor crank shaft drive pulley | Brass | 1 | 3,447.3 | 29.3 |
| 1-17 | Motor crank shaft cam plate | Steel | 1 | 5,825.6 | 45.7 |
| 1-18 | Motor crank shaft cam follower lock nut | Brass | 1 | 1,351.2 | 11.5 |
| 1-19 | Motor crank shaft cam follower spacer | Brass | 1 | 537.3 | 4.6 |
| 1-20 | Motor flywheel hub | Brass | 1 | 7,713.5 | 65.6 |
| 1-21 | Motor flywheel | Brass | 1 | 74,187.7 | 630.6 |
| 1-22 | Motor piston | Cast Iron | 1 | 6,846.8 | 49.3 |
| 1-23 | Motor piston cross head | Brass | 1 | 811.9 | 6.9 |
| 1-24A | Motor piston rod | Stainless Steel, Steel | 2 | 2,566.7 | 20.2 |
| 1-24B | Motor piston rod big end part-1 | Brass | 1 | 1,342.5 | 11.4 |
| 1-24C | Motor piston rod big end part-2 | Brass | 1 | 3,318.1 | 28.2 |
| 1-25A | Motor cylinder slide valve-1 | Stainless Steel | 1 | 95.7 | 0.8 |
| 1-25B | Motor cylinder slide valve-2 | Stainless Steel | 1 | 97.2 | 0.8 |
| 1-26 | Motor valve rocking shaft bearing | Brass | 1 | 339.2 | 2.9 |
| 1-27 | Motor valve rocking shaft | Stainless Steel | 1 | 1,898.2 | 15.2 |
| 1-28 | Motor valve rod | Steel | 1 | 1,181.0 | 9.3 |
| 1-29 | Motor valve rod lock nut | Brass | 1 | 291.4 | 2.5 |
| 1-30 | Motor valve rod valve holder | Brass | 1 | 276.4 | 2.3 |
| 1-31 | Motor valve rocking arm | Steel | 1 | 1,754.5 | 13.8 |
| 1-32 | Motor rocking arm cam follower | Steel | 1 | 1,240.5 | 9.7 |
| 1-33 | Motor rocking arm cam follower axle | Steel | 1 | 376.9 | 3.0 |
| 1-34 | Motor rocking arm valve spring | Steel | 1 | 83.1 | 0.7 |
| 1-35 | Exhaust pipe holding bracket | Brass | 1 | 2,540.0 | 21.6 |
| 1-36 | Exhaust lower circular bracket | Aluminum | 1 | 12,826.8 | 34.6 |
| 1-37 | Exhaust base ring | Brass | 1 | 7,624.5 | 64.8 |
| 1-38 | Exhaust stack | Brass | 1 | 14,499.7 | 123.2 |
| 1-39 | Exhaust stack top ring | Brass | 1 | 1,363.9 | 11.6 |
| 1-40 | LH-flame protector | Brass | 1 | 2,371.6 | 20.2 |
| 1-41 | RH-flame protector | Brass | 1 | 2,371.6 | 20.2 |
| 1-42 | Front flame guard | Brass, Steel | 2 | 384.1 | 3.2 |
| 1-43 | Top steering shaft bracket | Aluminum | 1 | 725.3 | 2.0 |
| 1-44 | Accelerator bridge bracket | Steel | 1 | 3,632.8 | 28.5 |
| 1-45 | Accelerator lever-1 guide plate | Steel | 1 | 1,315.1 | 10.3 |
| 1-46 | Accelerator bridge shaft | Steel | 1 | 724.8 | 5.7 |
| 1-47 | Accelerator lever-1 | Steel | 1 | 476.6 | 3.7 |
| 1-48 | Accelerator lever-2 | Steel | 1 | 364.6 | 2.9 |
| 1-49 | Accelerator lever-3 | Brass, Steel | 2 | 1,073.8 | 8.9 |
| 1-50 | Accelerator lever-1 spring bolt | Steel | 1 | 146.1 | 1.1 |
| 1-51 | Accelerator lever-1 spring | Steel | 1 | 13.9 | 0.1 |
| 1-52 | Accelerator levers bolt | Steel | 1 | 119.4 | 0.9 |
| 1-53 | Accelerator crank | Steel | 1 | 1,574.5 | 12.4 |
<!-- /parts -->

The table is written by `gen_parts.py --build`. Masses use SolidCraft's library densities (Al 2.70,
cast iron 7.20, steel 7.85, stainless 8.00, brass 8.50, Cu 8.96, PC 1.20 g/cm³).
Tapped holes are modelled at the tap drill (M4 → Ø3.3, M6 → Ø5.0); threads are not modelled.

## Readings and assumptions

- **1-01**: third-angle views at 1:1.5 and section A-A at 1:2. The U floor is 35 (the drawing
  also gives 100 − 65.5 = 34.5; section A-A suggests 36.5 at the crank pit). The crank pit is
  71.5 × 18 from X = 19 down to Z = 24 (section A-A). Which side of the underside carries the
  54-pitch M4 pair (+Y here) depends on the projection of the bottom view: check it against the
  mating chassis part. Not yet modelled: the Ø6 × 15 deep holes of the plan view, the M6 × 15 and
  the small horizontal oil hole at X = 26, and the dashed nut pockets in the end view.
- **1-02**: the 4 × M4 × 10 deep holes on the 5 mm flange break into the first fin gap, as drawn.
  The oiler hole is M4 radially through the wall, 4.5 from the 9 mm flange end.
- **1-14**: built up from five bodies (two M/S webs, S/S crankpin and shafts, press fits). The
  crank throw is 22 (stroke 44), measured on the drawing's vector lines; so are the web ends, 34.5
  beyond the main axis on the crankpin side and 30 on the other. **The web width is not on the
  drawing**: 14 is an estimate from the iso view (parameter `crank_web_w`). The left shaft has a
  Ø4 cross hole 9.5 from its journal.
- **1-17**: the flanks are straight, at 37.5° to the centre line, tangent to R16 and joined to the
  R25 lobe by R4. Section D-D: Ø19 × 2.5 counterbore, M16 bore.
- **1-20**: the M16 part is modelled at Ø16 over its full 19.5 (thread 14).
- **1-21**: the spoke windows' outer corners are left sharp (they look slightly rounded on the
  drawing, radius not given).
- **1-05**: the drawing says "refer to 1-04 for all dimension details" and gives no thickness:
  modelled as the 1-04 disc (3.5 thick) without the valve channel.
- **1-06**: a bought ball bearing Ø19 × Ø9.5 × 9, modelled as an envelope only.
- **1-08**: read off the drawing's vector lines; the 15° Ø2 drain hole crosses the bore axis at
  Z = 10.53. The nozzle's small 30° tip chamfer is not modelled (it would leave a knife edge on
  the Ø3 bore).
- **1-15**: the V-groove is 4 wide at the top and 2.5 at its Ø20 flat bottom (vector lines).
- **1-24A**: the rod is Ø4.9 for 10 (through the piston crown) and Ø6 for 79; the cross pin is
  27 long (vector lines). **1-24B/C**: the cap's screw holes are Ø4.3, an M4 clearance per sheet 02
  note 3; the block is tapped M4.
- **1-25B**: the R162 bow over the middle 36 gives the 1.1 overall depth drawn; the ends are flat.
- **1-32**: the roller's thrust face and recess are read from the section; the bore in the
  assembly is the 1-33 axle.
- **1-35**: the bends are modelled sharp; the 38° joggle is set by its 10.5 offset over 14.5.
- Parts built from a hex or a square with a turned part of the same size (1-07, 1-12, 1-13,
  1-24B) overlap the two solids: butting them, or turning the bar down, fails in SolidCraft where
  the round is tangent to the flats.
- **1-34**: a Ø1 wire on R150 from the eye to the free end (86 along, 30.5 down), flat at the
  free end; the eye is 300° of a loop (Ø4 inside) so the wire does not run into itself.
- **1-40 / 1-41**: built with a sharp bend (the drawn 78° between the legs): the bent cross-section
  is extruded across the part and each leg trimmed to its flat-pattern outline. SolidCraft's fold
  cannot be used here: the drawn fold line runs through the tab's corner and into the R28 edge.
  1-41 is 1-40 mirrored. **1-42**: the short leg's perforations are not dimensioned; 2 rows assumed.
  It is made with the sheet-metal tools (bend radius 0.2); the hinge rod is a second body.
- **1-43**: made with SolidCraft's sheet-metal tools (base flange from the drawn flat pattern,
  then a 46° fold; bend radius 0.2, K-factor 0.5, so the volume is the flat area × 1.5). The fold
  line sits 0.43 past the drawn one: SolidCraft needs the bend zone clear of the tab's step, which
  lies on the drawn fold line. The tab is folded toward −Z.
- **1-44**: bends modelled sharp, as drawn; the arc centre (32.2 below the strip) and the M2 hole
  (1.93 above it) are read off the vector lines; the M2 hole is modelled at Ø1.6.
- **1-45**: the Ø2 hole's countersink is not dimensioned and not modelled.
- **1-51**: 5 turns, counted on the drawing; modelled free (7 long). Its 0.5 wire is measured to
  about 0.5 %, so its check tolerance is 1 %.
- **1-53** is drawn on sheet 04 but missing from the parts list; "Accelerator crank" is our name.
  The inside radius of the top bend is R3.5 as drawn; the lower bend (R3.5 on the centre line)
  ends at the collar.
- **1-04**: from the detail: a 20 wide, 0.5 deep valve channel across the face, with 0.5 wide,
  1 deep relief grooves along its edges; the Ø10 port countersunk 90° to Ø15 on the other face.
- **1-05**: its thickness is not on the drawing ("refer to 1-04"): not modelled yet.

## SolidCraft issue found while modelling

Adding blind holes one at a time with `solid.hole` to 1-01 left most of them **3.42 mm too
shallow**. The timeline only shows a warning ("Boolean retry: temporary coincident-face separation
up to 3.423684e0 mm per face"); the temporary separation stays in the result. The generator
therefore makes every hole pattern one sketch of circles and one cut extrude, and `--build`
treats any "coincident-face separation" retry as an error.

`solid.pipe` along a path of two arcs that bend different ways (1-34: the eye and the R150 bend)
gives an inside-out solid, with negative volume and mass and no warning; each arc on its own is
fine, so 1-34 joins two pipes. Its checks were met with a 1 % tolerance (a Ø1 wire).

A sketch hidden with `browser.visibility` (1-43's flat pattern) is shown again when the saved
`.solvecraft` file is reopened: SolidCraft does not save sketch visibility. The snapshots are
therefore rendered from the scripts.
