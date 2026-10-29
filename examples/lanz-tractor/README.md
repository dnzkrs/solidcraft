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

`--build` fails a part unless it is one valid solid with no errors in its timeline, SolidCraft's
measured volume is within 0.1 % of a volume computed by hand from the drawing dimensions, and the
volume of the exported mesh agrees within 0.5 % (when the STL is closed).

Units are mm. Each part has its own coordinate system, stated in its docstring in `gen_parts.py`.

## Parts

| Part | Name | Material | Volume mm³ | Mass g | Sheet |
|---|---|---|---:|---:|---|
| 1-01 | Motor frame | Aluminium | 223 384 | 603.1 | 03 |
| 1-02 | Motor cylinder | Cast iron | 60 778 | 437.6 | 03 |
| 1-03 | Motor cylinder gasket ring | Copper | 719.5 | 6.4 | 03 |
| 1-04 | Motor inner cylinder head | Cast iron | 7 448 | 53.6 | 03 |
| 1-09 | Motor cylinder oiler glass | Polycarbonate (plastic tubing) | 835.6 | 1.0 | 03 |

Masses use SolidCraft's library densities (Al 2.70, cast iron 7.20, Cu 8.96, PC 1.20 g/cm³).
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
- **1-04**: from the detail: a 20 wide, 0.5 deep valve channel across the face, with 0.5 wide,
  1 deep relief grooves along its edges; the Ø10 port countersunk 90° to Ø15 on the other face.
- **1-05**: its thickness is not on the drawing ("refer to 1-04"): not modelled yet.

## SolidCraft issue found while modelling

Adding blind holes one at a time with `solid.hole` to 1-01 left most of them **3.42 mm too
shallow**. The timeline only shows a warning ("Boolean retry: temporary coincident-face separation
up to 3.423684e0 mm per face"); the temporary separation stays in the result. The generator
therefore makes every hole pattern one sketch of circles and one cut extrude, and `--build`
treats any "coincident-face separation" retry as an error.
