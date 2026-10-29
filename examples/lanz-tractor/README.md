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
| 2-01 | Chassis front end | Aluminum | 1 | 91,743.5 | 247.7 |
| 2-03 | LH-steering and fuel tank bracket | Aluminum | 1 | 11,360.1 | 30.7 |
| 2-04 | RH-steering and fuel tank bracket | Aluminum | 1 | 11,360.1 | 30.7 |
| 2-05 | Steering floor bracket | Aluminum | 1 | 701.7 | 1.9 |
| 2-06 | Fuel tank | Brass | 1 | 13,925.4 | 118.4 |
| 2-07 | Fuel tank spout | Brass | 1 | 1,462.4 | 12.4 |
| 2-08 | Fuel tank spout cover | Brass | 1 | 1,131.2 | 9.6 |
| 2-09 | Fuel tank inner wick holding pipe | Brass | 1 | 1,411.9 | 12.0 |
| 2-10 | Fuel tank gear wheel axle bracket | Brass | 1 | 3,000.3 | 25.5 |
| 2-12 | Fuel tank gearwheel and shaft | Brass, Steel | 2 | 1,790.6 | 14.6 |
| 2-13 | Fuel tank gear wheel shaft handle collar | Brass, Steel | 2 | 1,797.1 | 15.0 |
| 2-14 | Fuel tank wick holder | Brass | 1 | 2,909.3 | 24.7 |
| 2-15 | Fuel tank wick | Default | 1 | 4,047.3 | 5.2 |
| 2-16 | Axle body support bracket | Aluminum | 1 | 7,201.2 | 19.4 |
| 2-17 | Front axle yoke support bracket | Aluminum | 1 | 2,393.4 | 6.5 |
| 2-18 | Rear axle yoke arm | Aluminum | 1 | 4,961.7 | 13.4 |
| 2-19 | Front axle yoke tie rod | Steel | 1 | 2,425.3 | 19.0 |
| 2-20 | Front axle yoke arm | Aluminum | 1 | 11,099.4 | 30.0 |
| 2-21 | Front axle yoke bearing | Brass, Steel | 2 | 1,815.8 | 14.8 |
| 2-22 | Front axle yoke wheel hinge bracket | Brass | 1 | 3,615.2 | 30.7 |
| 2-23 | Wheel pivot axle | Brass, Steel | 2 | 3,630.3 | 28.5 |
| 2-24 | Wheel pivot axle connector bracket | Steel | 1 | 745.2 | 5.8 |
| 2-25 | Wheel pivot axle steering arm | Steel | 1 | 1,046.2 | 8.2 |
| 2-26 | Wheel pivot axle connecting rod | Steel | 1 | 2,939.3 | 23.1 |
| 2-27A | Wheel pivot spacer ring-1 | Steel | 1 | 30.6 | 0.2 |
| 2-27B | Wheel pivot spacer ring-2 | Steel | 1 | 186.9 | 1.5 |
| 2-28 | Wheel axle | Steel | 1 | 714.5 | 5.6 |
| 2-29 | Wheel axle ball bearing | Steel | 1 | 1,382.3 | 10.9 |
| 2-30 | Connecting rod screw | Steel | 1 | 155.2 | 1.2 |
| 2-31 | Front wheel rim | Aluminum | 1 | 27,922.1 | 75.4 |
| 2-32 | Front wheel tyre | Default | 1 | 122,633.5 | 158.2 |
| 2-33 | Front wheel hub cap | Brass | 1 | 2,084.2 | 17.7 |
| 2-34 | Steering lay shaft | Steel | 1 | 2,476.3 | 19.4 |
| 2-35 | Steering lay shaft crank | Brass, Steel | 2 | 2,806.7 | 23.4 |
| 2-36 | Steering lay shaft gear wheel | Brass | 1 | 6,226.8 | 52.9 |
| 2-37 | Steering tie rod | Steel | 1 | 1,174.0 | 9.2 |
| 2-38 | Steering tie rod end | Steel | 1 | 444.8 | 3.5 |
| 2-39 | Steering tie rod end plug | Steel | 1 | 214.4 | 1.7 |
| 2-40 | Steering tie rod end balljoint | Steel | 1 | 257.3 | 2.0 |
| 2-41 | Steering column and worm gear | Brass, Steel | 4 | 5,671.9 | 46.1 |
| 2-42 | Steering wheel | Aluminum | 1 | 8,062.4 | 21.8 |
| 2-43 | Accelerator link | Steel | 1 | 349.1 | 2.7 |
| 2-44 | Front lighting main beam | Brass | 1 | 863.7 | 7.3 |
| 2-45 | Front lighting lampstand | Brass, Stainless Steel | 4 | 1,539.9 | 13.0 |
| 2-46 | Pulling hook | Steel | 1 | 807.5 | 6.3 |
| 2-47 | Motor side cover | Brass | 2 | 12,294.1 | 104.5 |
| 2-48 | Motor top cover | Brass | 1 | 5,042.4 | 42.9 |
| 2-49 | Motor side cover air cover | Steel | 1 | 596.4 | 4.7 |
| 3-01 | Chassis rear end | Aluminum | 1 | 85,739.4 | 231.5 |
| 3-02 | Rear axle support bracket | Aluminum | 1 | 18,343.9 | 49.5 |
| 3-03 | Differential housing part-1 | Steel | 1 | 10,134.7 | 79.6 |
| 3-04 | Differential housing part-2 | Steel | 1 | 20,630.1 | 161.9 |
| 3-05 | Rear axle main bearing housing part-1 | Aluminum | 1 | 7,312.4 | 19.7 |
| 3-06 | Rear axle main bearing housing part-2 | Aluminum | 1 | 12,653.9 | 34.2 |
| 3-07 | Rear axle main housing ball bearing-1 | Steel | 1 | 6,715.0 | 52.7 |
| 3-08 | Rear axle main housing ball bearing-2 | Steel | 1 | 2,111.1 | 16.6 |
| 3-09A | Rear axle-1 | Steel | 1 | 3,946.7 | 31.0 |
| 3-09B | Rear axle-2 | Steel | 1 | 5,303.6 | 41.6 |
| 3-10 | Differential gear wheel | Brass | 1 | 2,252.8 | 19.1 |
| 3-11 | Differential gear wheel shaft | Stainless Steel | 1 | 1,115.2 | 8.9 |
| 3-13 | Rear wheel spacer | Brass | 1 | 1,945.2 | 16.5 |
| 3-14 | Rear wheel mounting plate | Steel | 1 | 11,281.7 | 88.6 |
| 3-15 | Rear wheel rim | Aluminum | 1 | 66,225.2 | 178.8 |
| 3-16 | Rear wheel tyre | Default | 1 | 467,298.4 | 602.8 |
| 3-17 | Rear wheel hub cap | Brass | 1 | 541.4 | 4.6 |
| 3-18 | Rear wheel drive gear wheel | Brass | 1 | 10,229.7 | 87.0 |
| 3-19 | Drivers console side frame | Aluminum | 1 | 23,636.2 | 63.8 |
| 3-21 | Accelerator control lever | Brass, Steel | 2 | 1,423.4 | 11.6 |
| 3-22 | Accelerator control lever handle | Brass | 1 | 647.2 | 5.5 |
| 3-23 | Rear wheel LH-mud guard | Brass | 1 | 18,882.4 | 160.5 |
| 3-24 | Rear wheel RH-mud guard | Brass | 1 | 18,882.4 | 160.5 |
| 3-25A | Drivers seat base | Brass | 1 | 4,811.7 | 40.9 |
| 3-25B | Drivers seat | Oak | 1 | 27,807.3 | 20.9 |
| 3-25D | Drivers seat back rest | Oak | 1 | 5,231.3 | 3.9 |
| 3-26A | Bumper-towbar mounting bracket | Steel | 1 | 1,426.9 | 11.2 |
| 3-26B | Bumper-towbar | Steel | 1 | 2,814.3 | 22.1 |
| 3-27A | Hand brake shaft | Steel | 1 | 728.7 | 5.7 |
| 3-27B | Hand break handle | Steel | 1 | 1,134.5 | 8.9 |
| 3-27C | Hand brake pivot | Brass | 1 | 620.5 | 5.3 |
| 3-27D | Hand brake teethed bracket plate | Brass | 1 | 705.3 | 6.0 |
| 3-27E | Hand break release handle | Brass | 1 | 1,618.5 | 13.8 |
| 3-27F | Hand brake release handle spring | Steel | 3 | 11.7 | 0.1 |
| 3-27G | Hand brake release crank | Steel | 1 | 171.0 | 1.3 |
| 3-27H | Hand brake release crank break band holder | Brass | 1 | 212.9 | 1.8 |
| 3-27I | Hand brake band | Stainless Steel | 1 | 602.6 | 4.8 |
| 3-27J | Hand brake bandend strap | Brass | 1 | 135.7 | 1.2 |
| 3-27K | Hand brake spring screw | Steel | 1 | 204.6 | 1.6 |
| 3-28 | Reversing operating handle | Brass | 1 | 1,166.3 | 9.9 |
| 3-29 | Rev operating handle crank and spindle | Brass, Steel | 3 | 2,652.9 | 21.3 |
| 3-30 | Rev spindle locking collar | Brass | 1 | 778.8 | 6.6 |
| 3-31 | Coupling operating handle | Brass, Steel | 3 | 2,118.1 | 17.5 |
| 3-32 | Coupling operating pulley and shaft | Brass, Steel | 2 | 5,882.4 | 49.5 |
| 3-33 | Shaft adjuster | Brass | 1 | 1,088.5 | 9.3 |
| 3-34 | Shaft spacer | Brass | 1 | 663.7 | 5.6 |
| 3-35 | Accelerator levers bolt | Steel | 1 | 119.4 | 0.9 |
| 3-36 | Accelerator connector lever | Steel | 1 | 739.2 | 5.8 |
| 3-37 | Rear stop lights | Brass, Polycarbonate | 2 | 1,135.2 | 9.3 |
| 4-01 | GB RH-side plate | Brass | 1 | 9,460.0 | 80.4 |
| 4-02 | GB LH-side plate | Brass | 1 | 8,893.5 | 75.6 |
| 4-03 | GB side plate spacer | Steel | 1 | 932.9 | 7.3 |
| 4-04 | Coupling unit outer bearing plate | Brass | 1 | 4,946.0 | 42.0 |
| 4-05 | Coupling unit outer plate ball bearing | Steel | 1 | 1,474.1 | 11.6 |
| 4-06 | Coupling drive pulley | Steel | 1 | 4,159.1 | 32.6 |
| 4-07 | Coupling plate | Brass | 1 | 3,597.6 | 30.6 |
| 4-08 | Coupling spacer | Steel | 1 | 62.8 | 0.5 |
| 4-09 | Coupling spring | Steel | 1 | 40.1 | 0.3 |
| 4-10 | Coupling spring retainer | Steel | 1 | 727.6 | 5.7 |
| 4-11 | Coupling spring retainer ball bearing | Steel | 1 | 447.7 | 3.5 |
| 4-12 | Coupling ball bearing retainer | Steel | 1 | 253.8 | 2.0 |
| 4-13 | Coupling shaft and gearwheel-1 | Stainless Steel, Steel | 2 | 1,194.7 | 9.5 |
| 4-14 | Coupling RH-pulley plate | Steel | 1 | 2,684.3 | 21.1 |
| 4-15 | Coupling RH-pulley shaft | Steel | 1 | 802.5 | 6.3 |
| 4-16 | Coupling RH-pulley | Brass | 1 | 1,369.6 | 11.6 |
| 4-17 | GB-gearwheel type-A | Stainless Steel, Steel | 2 | 3,901.3 | 30.7 |
| 4-18 | GB-gearwheel type-B | Steel | 1 | 518.4 | 4.1 |
| 4-19 | GB-gearwheel type-C | Stainless Steel, Steel | 2 | 4,417.4 | 34.7 |
| 4-20 | GB-driver shaft spacer | Brass | 1 | 31.4 | 0.3 |
| 4-21 | GB-idler shaft-1 spacer | Brass | 1 | 78.5 | 0.7 |
| 4-22 | GB-idler shaft-2 spacer | Brass | 1 | 235.6 | 2.0 |
| 4-23 | GB-output shaft reversing gearwheel | Brass, Stainless Steel, Steel | 5 | 5,561.2 | 44.3 |
| 4-24 | GB-external output shaft gearwheel | Brass, Steel | 2 | 5,917.9 | 47.0 |
| 4-25 | Reversing shaft bearing plate | Steel | 1 | 3,140.0 | 24.6 |
| 4-27 | Reversing shaft rack | Brass | 1 | 4,278.7 | 36.4 |
| 4-28 | Reversing shaft rack cover plate | Brass | 1 | 638.1 | 5.4 |
| 4-29 | Reversing shaft pinion | Brass, Steel | 3 | 1,357.5 | 11.0 |
| 4-30 | V-belt | Default | 1 | 2,632.9 | 3.4 |
| 4-31 | Coupling guide pillar | Brass | 1 | 492.4 | 4.2 |
| 5-01 | Belt | Nylon | 2 | 565.5 | 0.6 |
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
- **2-01**: material not on the drawing; aluminium assumed (its 3D view is shaded like the
  aluminium parts). Detail "A" is drawn from below: the 8 wide, 3 deep recess is in the underside,
  between the Ø6 hole at (236, −16) and the centre line (vector lines). The window's R4 corners are
  measured. **2-03/2-04**: the leg's flanks and R4 corners are read off the vector lines.
- **2-05**: the second bend's 45° is drawn, not dimensioned. **2-06**: the end plates are modelled
  1 thick, set 2 in; the Ø10 hole at 45° through the top edge is inferred from the 7 mm openings in
  the top and side views; the tube's R2 corners are read from section F-F.
- **2-12**: 12 teeth counted on the drawing; straight-flanked teeth. **2-15**: no wick material in
  SolidCraft's library; the default density is used. **2-11** (tank hanger) is not yet modelled:
  its length and rod positions are not in its view.
- **2-18**: the top edges are the outer tangents from the R4.5 ends to the R9.5 boss (their virtual
  sharp comes out 10 above the Ø12, as dimensioned); the R20 is a concave round where the bottom
  edges meet. **2-20**: the Ø12 is 10 above the hole line and the R11 is taken as centred on it,
  the top edges tangent to it from the straight end portions; the R50 rounds the bottom centre.
- **2-21**: measured from the section's lines: pin head Ø12 x 3 (R1 round), bush 8.1 long (4 flange,
  4.1 spigot for the arm's Ø12), M6 x 10, Ø2 drilled through. **2-23**: the Ø1.5 x 9 pin is
  modelled in brass (the label on the 3D view); its end form ("2PF") is not modelled.
- **2-13**: the Ø4 cross hole goes right through the collar (a pin hole for the Ø4 shaft).
  **2-24**: the 90° twist is a loft between the 8 x 2 and 2 x 8 sections from X = 6 to 22
  (measured), so its faces are flat where the drawing shows curved outlines; steel assumed.
- **2-25**: the bend's start (16 from the upright's back), the arm's outer R23.5 and the first hole
  (13.4 along the bent leg) are read from the vector lines; both holes are taken as M4.
  **2-26**: the crank's bend radii are not dimensioned: R1 inside, R3 outside.
- **2-29** is a bought-in bearing, modelled as its Ø16 / Ø6 x 8 envelope. **2-30**: the head's
  slot is not dimensioned and not modelled. **2-32**: no rubber in SolidCraft's materials; the
  default density (1.29) with the "Rubber - Black" appearance.
- **2-31** and **2-33**: every radius and step read from the sections' vector lines (2-33's Ø10 /
  Ø12.5 lip is 1 high, its Ø14 recess 2.5 deep). 2-31's holes are placed at 45° (the drawing's
  pattern turned, which a round part does not notice), off the revolve's seam.
- **2-35**: the collar's bore is taken as Ø6, the 2-34 lay shaft's size. **2-36**: the tooth width
  (6) is measured; the teeth are straight-sided and their R5 throat for the worm is not modelled.
- **2-38**: read from section C-C's lines (Ø6 x 7, Ø5 to 12, coned to Ø4 at 13.5, M4 beyond; the
  slot 4 wide over 13.5); the cone from the hex to the Ø6 neck is not modelled. **2-39**: the R2.5
  ball seat (about 0.2 deep) and the slot are not modelled. **2-40**: the hex's 10° chamfer is not
  modelled.
- **2-43**: the eyes' Ø4.5 is taken as the wire's centre line (the drawn eyes are about 6.5 over
  the wire); the eyes are closed rings at right angles to each other, and the drawn sharp kink is
  bent R3. The legs stop 0.3 outside the eyes' centre lines (see below).
- **2-41**: the worm's thread is a square-section helix (2.2 x 2.2, lead 3.96 from the 6° lead
  angle on Ø12, 3 turns) instead of the drawn trapezoid; the column's last 10 (past the end pin) is
  measured. **2-42**: the rim is square-edged. **2-44**: the Ø8 hole is modelled Ø7.98 (see below).
- **2-45**: the housing's cone wall and the stainless reflector are read off the 1:1 half section;
  the stem's position (4 from the back) and length (30) are measured and dimensioned.
- **2-47** is real sheet metal (`sheet.flange` from the flat blank with every edge feature, the
  windows cut flat, two `sheet.fold`s; K-factor 0.5, so its inside comes to 57.6 where the end view
  says 58). The 59.5 x 5 tab under the middle cannot be folded (its corners fall inside the bend
  zones) and is a second solid of the same brass. **2-48**: a line 4 short of the open end in the
  plan (119.5 of 123.5) is not explained by the views; the skirts run the full length.
- **2-49**: the gauze (0.5 wire, 2.0 openings at 2.5, measured) is a 0.5 sheet with square holes;
  the openings the edge cuts through are left closed, and the drawn bulge of the 3D view is not
  modelled.
- **1-04**: from the detail: a 20 wide, 0.5 deep valve channel across the face, with 0.5 wide,
  1 deep relief grooves along its edges; the Ø10 port countersunk 90° to Ø15 on the other face.
- **1-05**: its thickness is not on the drawing ("refer to 1-04"): not modelled yet.

- **3-01**: the flange's depth under the plate (31.5) is measured; the M4 and M6 holes are taken as
  through. **3-02**: the clamp screw is Ø5 clearance from the foot to the slot and M4 18 deep above.
- **3-03/3-04**: read from their sections' lines; the 8 flange holes are turned 22.5° from the
  drawing (off the revolve's seam), and 3-04's Ø6 radial hole is placed at 45° for the same reason.

- **3-07/3-08** are bought-in bearings, modelled as their envelopes. **3-10** is modelled as its
  bevel gear blank (from the lines); its teeth (about 20, not dimensioned) are not cut. **3-17**:
  the spigot's Ø5.5 bore is measured; its cross slot is turned 45° (off the revolve's seam).
- **3-15**: the rim's profile is read from section B-B's lines (about 2 thick, a 3 thick web).
  **3-18**: the teeth's R5 flanks are straightened. **3-19**: the second M4 in the front edge (45
  up) is measured, and the M4 at 66 in the underside is modelled 9 deep (see the issues below).
- **3-22**: the knob's taper to Ø8.4 is measured. **3-25A**: the angle round the tray is taken as
  6 high overall (the side view), so the back wall's pilot holes nick its flat leg.
  **3-25B**: oak; its R6 top round is modelled R5 (SolidCraft refuses 5.5 and more on the 6 high
  top).

- **3-26A**: the bends are modelled sharp. **3-27D**: its R15's centre height (9.5) is measured; 21
  teeth (1 deep, 1.5 pitch over ±63°); the bends of its feet are sharp. **3-27F**: 2.5 turns
  (1.75 long at most); its legs are separate solids touching the coil's ends.
- **3-27G** and **3-36**: thicknesses (1.5) are not dimensioned. **3-27I**: the band is taken 0.5
  thick and 6 wide, the copper lining is not modelled, and following the drawn shape it comes to
  201 long, where the drawing says "approx 175" stretched. **3-27J**'s R2 bend is sharp.
- **3-29**: the hub's height (6.5) and the pins' heights are partly measured. **3-32**: the pin's
  position (25.6) is measured. **3-37**: the lens (Ø7.5 x 1, red) is modelled in polycarbonate.
- **3-27E**: its fork slot (3 wide for 10.5, then 2 wide to 25) is read from the top view and
  taken right through the blade's height. **3-25D**: oak; the R7 rounding of its front edges and
  the 12° bend of its ends are not modelled.
- **3-23/3-24** (mudguards): their flat pattern's folds cross notches and slanted edges, which
  `sheet.fold` refuses, so they are built folded with sharp bends from overlapping solids (top and
  facets, lip, side panel, end wall, flange), the volume checked by inclusion-exclusion of the
  overlaps. The folded shape (which way each panel turns) is read from the 3D views on sheets 06
  and 10; the lip's R10 ends are not rounded.
- Not modelled: **3-20** (console top plate): the flat pattern does not show which regions fold
  which way, and the side view does not settle it; **3-25C** (seat leg) has too few views of
  its bends; **4-26** (reversing shaft operating ring) cannot be read unambiguously (its hub's
  size and shape); **2-11** (tank hanger) lacks its length and rod positions.

- **Group 4** (sheet 07): 4-05 and 4-11 are bought-in bearings modelled as their envelopes (their
  labelled bores, Ø8.5 and Ø6.5, as given). 4-06, 4-10 and 4-15 are read from high-resolution
  renders of their sections. The gears have straight flanks: the 30 tooth gears 0.5 wide at the
  tip and 1.5 at the root (assumed), the 10 tooth pinions as 4-13 (0.75 / 1.5), 4-24's 19 teeth as
  3-18 (1 / 2.5). The Ø8 collars and hubs against the pinions are Ø7.9 so they stay inside the
  pinions' roots. 4-14's two Ø3 holes are placed as 4-25's. Not yet modelled: 4-26 (reversing
  shaft operating ring).
- **4-27**: the Ø29 step on the flange's back is not modelled. **4-29**: the shaft is drawn broken;
  its length (68) is assumed. **4-30**: rubber, default density, black. **5-01**: nylon, taken 3
  wide and 0.5 thick; its two loops are separate sweeps meeting at the sharp corner (R2 drawn).

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

Joining a 12 x 13 x 2 plate to the end face of a loft built before it (2-24's twist) gave a body
0.98 mm³ larger than the two solids, with no warning; built the other way round the join needed a
separation retry. 2-24 therefore starts the (flat-faced) loft 1 mm inside the plate, so the solids
cross instead of touching.

Counterbores on 2-31's Ø24 PCD needed a separation retry (and came out 46 mm³ short) when one of
them sat on the revolved rim's seam, the XZ half plane the profile was sketched in. Turning the
pattern 45° off the seam fixed it.

Revolving a profile whose arc runs across a ball's equator (2-40's ball, from the neck over the
equator to the pole) gives an inside-out solid with negative volume, like the pipe above; split
into two arcs at the equator it is right. A Ø2 wire ended on the centre line of a Ø2-wire eye
(2-43) touches the eye's tube tangentially and cannot be joined; ended 0.3 short it can.

A hole exactly tangent to the inside of a tube's walls (2-44's Ø8 in a tube 8 wide inside) cannot
be cut; Ø7.98 can. Joining a square-section coil of more than about 2 turns to a cylinder stops
with "lumps: contact work exceeds the limit"; 2-41's 3-turn worm thread is joined as two
1.5-turn coils end to end, onto an unbored core that is bored afterwards.

On the large 0.5 mm brass covers (2-47, 2-48) cuts go wrong without a warning: a pocket cut leaving
a 0.5 top took the top away, and cuts across the bottom edge of the bent-up 2-47 went 1 to 1.75 too
deep (on a 0.5 sheet the boolean's tolerance, about 0.35 mm, and its 1 mm nudge are as large as
the wall). Interior cut-outs are right. 2-48 is therefore hollowed with `solid.shell` and 2-47
built with the sheet-metal commands, which give the exact volumes.

A cut whose end face lies in the plane of another face of the part needs a separation retry and
can come out deeper, even when the two faces are far apart: 3-19's M4 at 66, ending in the plane
of the notch's floor (Y = 8), was cut 2.5 too deep. It ends at Y = 9 instead.

Cutting two regions of one sketch picked by points, a rectangle less a circle and a smaller
circle inside it (3-27J's end round and hole), removed 13.15 mm³ instead of 19.44; as two cuts
both are right.

Where two solids touch, the boolean's fallback needs planar faces on both: a gear prism (planar)
could not be joined onto a revolved hub it touched, nor a prism carrying a bore circle onto a
bored core. The gears are built prisms first, the round parts joined reaching 0.5 into them, and
bored last.
