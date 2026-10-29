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

## Parts

<!-- parts -->
| Part | Name | Material | Bodies | Volume mm³ | Mass g |
|---|---|---|---:|---:|---:|
| 1-01 | Motor frame | Aluminum | 1 | 223,383.9 | 603.1 |
| 1-02 | Motor cylinder | Cast Iron | 1 | 60,778.4 | 437.6 |
| 1-03 | Motor cylinder gasket ring | Copper | 1 | 719.5 | 6.4 |
| 1-04 | Motor inner cylinder head | Cast Iron | 1 | 7,447.7 | 53.6 |
| 1-09 | Motor cylinder oiler glass | Polycarbonate | 1 | 835.6 | 1.0 |
| 1-14 | Motor crank shaft | Stainless Steel, Steel | 5 | 28,817.5 | 227.8 |
| 1-17 | Motor crank shaft cam plate | Steel | 1 | 5,825.6 | 45.7 |
| 1-18 | Motor crank shaft cam follower lock nut | Brass | 1 | 1,351.2 | 11.5 |
| 1-19 | Motor crank shaft cam follower spacer | Brass | 1 | 537.3 | 4.6 |
| 1-20 | Motor flywheel hub | Brass | 1 | 7,713.5 | 65.6 |
| 1-21 | Motor flywheel | Brass | 1 | 74,187.7 | 630.6 |
| 1-22 | Motor piston | Cast Iron | 1 | 6,846.8 | 49.3 |
| 1-26 | Motor valve rocking shaft bearing | Brass | 1 | 339.2 | 2.9 |
| 1-27 | Motor valve rocking shaft | Stainless Steel | 1 | 1,898.2 | 15.2 |
| 1-28 | Motor valve rod | Steel | 1 | 1,181.0 | 9.3 |
| 1-31 | Motor valve rocking arm | Steel | 1 | 1,754.5 | 13.8 |
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
- **1-04**: from the detail: a 20 wide, 0.5 deep valve channel across the face, with 0.5 wide,
  1 deep relief grooves along its edges; the Ø10 port countersunk 90° to Ø15 on the other face.
- **1-05**: its thickness is not on the drawing ("refer to 1-04"): not modelled yet.

## SolidCraft issue found while modelling

Adding blind holes one at a time with `solid.hole` to 1-01 left most of them **3.42 mm too
shallow**. The timeline only shows a warning ("Boolean retry: temporary coincident-face separation
up to 3.423684e0 mm per face"); the temporary separation stays in the result. The generator
therefore makes every hole pattern one sketch of circles and one cut extrude, and `--build`
treats any "coincident-face separation" retry as an error.
