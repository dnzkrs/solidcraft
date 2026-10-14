# Youth off-road go-kart: welded 25 × 2 steel tube frame

A complete, buildable go-kart modelled in SolidCraft. It was designed from an AI-generated concept
sketch ("marco tubular para go-kart"). That sketch had many errors, listed below; this design keeps
its idea of a small welded tube kart with off-road tyres and corrects everything needed for it to
work and be built.

| File | What it is |
|---|---|
| `gen_kart.py` | Parametric generator: every dimension is at the top. It writes `go_kart.json` and `cut_list.csv`. |
| `go_kart.json` | SolidCraft command script: 456 commands, 122 bodies |
| `cut_list.csv` | Tube cut list with the end preparation (cope or mitre) for each tube |
| `iso.png`, `side.png` | Renders made with `solvecraft-cli snapshot` |

```sh
python3 gen_kart.py                                   # regenerate after changing a parameter
solvecraft-cli run go_kart.json --save go_kart.solvecraft --out go_kart.step
solvecraft-cli snapshot go_kart.json --out iso.png --view iso
```

Axes: X points forward (the driver faces +X), Y points left, Z points up. The ground is Z = 0 and
the rear axle lies on the Y axis at X = 0. Units are mm.

![iso](iso.png)
![side](side.png)

## 1. Errors in the concept sketch, and the corrections

| # | Error in the sketch | Why it is a problem | Correction in this design |
|---|---|---|---|
| 1 | **Rear axle "Ø12 mm"** | Each rear wheel carries ≈ 380 N about 100 mm from its bearing, which gives about 115 N·m with a ×3 bump factor. Ø12 gives σ ≈ 680 MPa in bending and τ ≈ 230 MPa under engine torque: it bends or breaks. | **Ø25 h9 C45 live axle**: σ ≈ 75 MPa, τ ≈ 25 MPa, safety factor > 4. Runs in UCFL205 bearings. |
| 2 | **Dimensions disagree**: width is given as both 60 cm and 55 cm, and the tyres are drawn outside a frame that would then be only about 30 cm wide | There is no room for a seated driver. A track that narrow tips over in a turn. | Rear track 760 mm and front track 640 mm; overall width 888 mm. Static rollover threshold ≈ 1.3–1.4 g, so the kart slides before it tips. |
| 3 | The **"12 mm" callout points at a frame tube** | This contradicts the parts list, which says the frame is Ø25 tube. | The whole frame is 25 × 2.0 tube (EN 10305-3 E235, or 1" × 14 ga DOM). |
| 4 | **Handlebar with no steering mechanism**: no column, kingpins, stub axles, steering arms or tie rods, and the front wheels sit on a fixed axle | The kart cannot steer. | Steering wheel and column, pitman arm, two adjustable tie rods with rod ends, kingpin brackets, and welded knuckles with Ø20 stub axles. The steering arms point at the rear-axle centre (Ackermann geometry). |
| 5 | **Front frame passes through the space the front wheels sweep** | The front wheels hit the frame as soon as they steer. | The foot box narrows to ±150 mm. At **±30° lock** the tyre stops 15 mm from the frame; this was checked by rotating the corner about the kingpin in the model. |
| 6 | **Drivetrain missing**: a sprocket floats beside the seat with no engine, clutch, chain or mount | The kart has no drive. | 196–212 cc engine on a slotted plate, centrifugal clutch (10T #35), #35 chain of 88 links, and a 72T sprocket on a keyed hub. |
| 7 | **No brake, no pedals, no throttle** | Unsafe. | Mechanical disc brake (Ø180 disc) on the axle with a cable from a pivoting brake pedal. The throttle pedal pulls a cable to the engine. |
| 8 | **Rear axle has no bearings or mounts** | The axle would run in a frame tube. | Two UCFL205 flange bearings on 8 mm plates welded to the rails. |
| 9 | **"Joint detail" shows 5–6 tubes meeting at one point** | Impossible to fit up and weld well; the joint would be weak and full of heat cracks. | At most two tubes are coped onto a through-tube at any node. Crowded nodes are offset by ≥ 25 mm (rear uprights at X = −230, side rail at Z = 220, braces moved off the cross-tube stations). |
| 10 | **Seat and floor pan are not attached** to anything | Unsafe. | Seat crosses with welded tabs (4 × M8), seat-back tabs on the deck cross, and a 1.5 mm floor pan riveted or stitch-welded under the rails. |
| 11 | The hoop around the seat looks like roll protection but is **lower than the driver's head** | It gives false confidence. | It is not claimed as roll protection. The kart is a low, wide, open kart: helmet required, no seat belt, as in normal karting. |
| 12 | **Top and side views do not match the 3D view** (different tube layouts and wheel sizes) | The drawing cannot be built as drawn. | A single 3D model; every view and the cut list come from it. |
| 13 | **Parts list incomplete**: no tyre size, bearings, chain, fasteners, steering or brake parts | The kart cannot be ordered or built from it. | Full list of commercial parts (section 3) and list of parts to make (section 4). |

## 2. Main data

| Item | Value |
|---|---|
| Driver | Youth, about 130–160 cm tall, ≤ 60 kg |
| Overall L × W × H | 1345 × 888 × 596 mm (top of the steering wheel) |
| Wheelbase / track (rear, front) | 900 / 760, 640 mm |
| Tyres | 13x5.00-6 (Ø330 mm), axle height 165 mm |
| Ground clearance | Frame and floor pan 76 mm; chain guard 48 mm (lowest point) |
| Engine | 196–212 cc horizontal-shaft OHV (Honda GX200 type), governed at 3600 rpm, 3/4" keyed shaft |
| Final drive | 10T / 72T #35 (ratio 7.2), **≈ 31 km/h** at 3600 rpm; 88-link chain at 201.6 mm centres |
| Steering | Ø280 wheel, column at 32.5° to horizontal, ±30° lock, Ackermann steering arms 80 mm long |
| Frame | 25 × 2.0 steel tube, **10.8 m** cut length (≈ 12.1 kg); plates 1.5–8 mm |
| Estimated dry mass | ≈ 70 kg with the engine. The model reports 90 kg because the rims, engine and seat are solid envelopes. |

**Faster or more ground clearance:** a 60T sprocket raises the lowest point to about 70 mm, but the
top speed rises to ≈ 37 km/h, which is too fast for a youth kart. Bigger tyres (16x6.50-8) need a
jackshaft to keep the speed down. Both are owner decisions; the parameters are at the top of
`gen_kart.py`.

## 3. Commercial parts (buy)

| # | Part | Specification | Qty |
|---|---|---|---|
| C13 | Engine | 196–212 cc horizontal-shaft OHV, 3/4" (19.05) keyed PTO, GX160/GX200 mounting pattern. Measure the bolt pattern before cutting the engine-plate slots. | 1 |
| C12 | Centrifugal clutch | 3/4" bore, 10T **#35**, dry, engages at ≈ 2000 rpm | 1 |
| C11 | Roller chain | ANSI #35 (ISO 06C-1), **88 links** including the connecting link | 1 |
| C09/C10 | Axle sprocket + hub | 72T #35 bolt-on sprocket, with a sprocket hub for a **25 mm** bore and 8 mm keyway | 1+1 |
| C07 | Rear bearings | **UCFL205** 2-bolt flange unit, 25 mm bore, set-screw insert; M10 × 40 8.8 bolts and nylock nuts | 2 |
| C08 | Shaft collars | Ø25 set-screw collar | 2 |
| C06 | Rear wheel hubs | Bolt-on hub, 25 mm bore, 8 mm key, flange to suit the rims | 2 |
| C04 | Tyres | **13x5.00-6** off-road / knobby, tubeless | 4 |
| C05 | Rims | 6 × 4.5" steel, 2-piece. Front rims take 2 × 6204 bearings; rear rims to suit the hubs. | 4 |
| C01 | Front wheel bearings | **6204-2RS** (20 × 47 × 14) | 4 |
| — | Kingpin bushes | Flanged PTFE-lined bush 12 × 14 × 12 (e.g. PCMF 121412E) | 4 |
| C03 | Kingpins | M12 × 90 hex bolt, class 8.8, nylock nut and 2 washers | 2 |
| C02 | Stub-axle nuts | M20 × 1.5 nylock nut with washer | 2 |
| C22/C23 | Rod ends | M8 female rod end, 2 right-hand + 2 left-hand (DIN ISO 12240-4 E series, e.g. SI 8 E / SIL 8 E); M8 × 30 8.8 bolts | 4 |
| C19 | Steering wheel | Ø280–300 kart wheel, 3-bolt, with hub for a Ø20 column | 1 |
| C21 | Column lower bearing | **UCFL204** (20 mm), bolts at 90 mm | 1 |
| C20 | Column upper bush | Split nylon column bush, Ø20 | 1 |
| C14/C15 | Brake disc + hub | Ø180 × 4 steel disc and a disc hub for 25 mm with 8 mm key | 1+1 |
| C16 | Brake caliper | Mechanical (cable) disc caliper for a 4 mm disc. Drill the bracket to match its bolt pattern. | 1 |
| — | Cables | Brake cable with housing, 1.5 m; throttle cable with housing, 1.5 m | 1+1 |
| C17 | Seat | Composite kart seat, cadet / size S (≈ 300 mm wide), M8 bolts with large washers | 1 |
| — | Keys | 8 × 7 × 30 DIN 6885 (sprocket hub, brake hub, wheel hubs) | 4 |
| — | Pedal return springs, end plugs | Extension springs ≈ 50 N; 25 × 2 tube end plugs | 2 + 6 |

## 4. Parts to make

**Frame tubes**: see `cut_list.csv`. The table gives the length to the long point, and for each
end the cope angle and depth or the mitre angle. Tubes meet node to node in the model, so the copes
are calculated rather than modelled. Cut the copes with a hole saw or a printed paper wrap. F01
(rear rails) and F15 and F16 (deck crosses) run 12.5 mm past the last joint and get end plugs.

**Plates** (laser-cut S235; sizes from the model):

| # | Part | Size | Holes / notes | Qty |
|---|---|---|---|---|
| P01 | Floor pan | 700 × 525 outline, 1.5 mm | Follows the rails | 1 |
| P02 | Rear bearing plate | 150 × 157 × 8 | Ø45 centre, 2 × Ø12 at 99 mm (UCFL205) | 2 |
| P03 | Kingpin back plate | 40 × 62 × 6 | Welds to the end of the front axle beam | 2 |
| P04 | Kingpin ear | 40 × 39 × 6, R20 end | Ø12.2, ears 50 mm apart | 4 |
| P05 | Engine plate | 390 × 300 × 5 | 4 slots 8.5 × 30 on the engine's pattern | 1 |
| P06 | Chain guard | 1.5 mm, follows the chain | Ø66 hole for the axle hub; fold a 15 mm lip | 1 |
| P07 | Caliper bracket | 80 × 92.5 × 6 | 2 × Ø8.5 (match the caliper) | 1 |
| P08 | Seat tab | 40 × 30 × 4 | Ø8.5 | 4 |
| P09 | Seat-back tab | 18.5 × 30 × 4 | Ø8.5 | 2 |
| P10 | Column upper bracket | 50 × 55 × 6 | Ø20.5 | 1 |
| P11 | Column lower bracket | 120 × 65 × 6 | Ø30 + 2 × Ø10.5 at 90 mm (UCFL204) | 1 |
| P12 | Pedal clevis tab | 30 × 25 × 4 | Ø8.5 | 4 |
| P13 | Pedal pad | 70 × 60 × 8 | Knurl or weld beads for grip | 2 |

**Machined parts:**

| # | Part | Material | Work | Qty |
|---|---|---|---|---|
| M05 | Rear axle | Ø25 h9 C45 bright bar, 860 long | Keyway 8 × 4 at the hubs, sprocket and brake; 1 × 45° chamfers | 1 |
| M01 | Knuckle sleeve | 22 × 4 tube (S355), 48 long | Ream 14 H7 for the flanged bushes after welding | 2 |
| M02 | Stub axle | Ø20 S355 bright bar, 162 long | Saddle onto the sleeve; M20 × 1.5 thread 25 long; Ø3 cotter-pin hole | 2 |
| M03 | Steering arm | 6 mm plate | Ø8.2 hole; weld to the sleeve 2 mm above the lower ear | 2 |
| M04 | Stub-axle spacer | 28 × 4 tube, 44.5 long | Face both ends square | 2 |
| M06 | Steering column | 20 × 2.5 tube, 510 long | Wheel hub at the top; pitman arm welded 12 mm from the bottom | 1 |
| M07 | Pitman arm | 6 mm plate | Ø20.5 + 2 × Ø8.2 at ±45 | 1 |
| M08 | Tie rod | Ø12 bright bar, ≈ 165 long | Tap M8 right-hand at one end and M8 left-hand at the other, 20 deep; jam nuts. Set toe-in to 0–2 mm. | 2 |
| M09 | Pedal arm | Ø16 × 2 tube, 171 long | Weld a Ø8.5 pivot boss at the bottom and the pad at the top | 2 |

## 5. Assembly and welding notes

1. **Jig the bottom frame flat.** Clamp F01–F05 on a flat table and tack the mitres. Then fit the
   crosses F06–F10, which are coped onto the rails. Check the diagonals agree within 2 mm before
   welding out.
2. **Rear deck.** Weld uprights F13 and F14, then the deck crosses F15 and F16 (capped ends), the
   deck rails F17, and the braces F18 and F19.
3. **Bearing plates P02.** Weld them to the outer side of the rails with a Ø25 rod through both
   bores, so the bearings line up.
4. **Front axle beam F12.** Weld the kingpin back plates and ears with an M12 rod through both
   pairs of ears, so the kingpins are parallel and vertical. Then fit F12 onto the front uprights
   F11.
5. **Hoop and side rails.** Weld F20–F23, then the column brackets P10 and P11 with the column in
   place and the UCFL204 bolted on.
6. **Weld in short, alternating runs** (MIG/MAG, 0.8 mm wire). Leave the frame to cool on the jig,
   then check the axle and kingpin alignment again. Drill a Ø3 vent hole in each closed tube
   section.
7. **Knuckles.** Weld the stub axle M02 square to the sleeve M01 in a fixture, then the steering
   arm M03. Ream the sleeve to 14 H7 after welding.
8. **Drivetrain.** Line up the sprocket with the clutch using a straightedge (chain line at
   Y = +180). Tension the chain by sliding the engine in its slots so the chain has 10 mm of slack.
9. **Before the first drive.** Brake test, with the brake cable stop set so the pedal stays firm.
   Check every nylock nut and every set screw (with Loctite 243), and fit the chain guard.
10. **Finish.** Degrease and powder-coat or paint the frame.

**Safety:** this is an off-road recreational vehicle. Use it only with a helmet, on private ground,
with adult supervision. Keep the engine governor; the 72T gearing is chosen for about 31 km/h.

## 6. How the design was checked (SolidCraft)

- The whole assembly (122 bodies) rebuilds from `go_kart.json` with no errors. It saves, reopens,
  and exports to STEP.
- **Clash check** (`inspect.interference`) over the whole assembly: the only overlaps reported are
  weld joints (frame nodes, plates on tubes, knuckle welds), the chain meshing with its sprockets,
  parts that are made as one piece (steering-wheel spokes, pedal pads), and bolted stacks.
  No moving part touches the frame.
- **Steering lock:** the left front corner (knuckle, wheel, bearings and rod end) was rotated ±30°
  about the kingpin and checked against the frame, floor pan, column brackets and pitman arm. The
  only contacts reported were weld joints, and the tyre clears the frame by 15 mm.
- Strength checks (hand calculations, ×3 dynamic factor):

  | Part | Stress | Safety factor |
  |---|---|---|
  | Rear axle | 75 MPa bending, 25 MPa torsion | > 4 |
  | Stub axle (Ø20 S355) | 87 MPa | 4 |
  | #35 chain | 780 N pull against ≈ 7.8 kN breaking load | 10 |

**Known limits of the model:**
- The SolidCraft kernel cannot yet make booleans between angled cylinders, so tube copes are given
  in the cut list instead of being modelled.
- Commercial parts are simplified envelopes: tyre, rim, engine, seat, caliper and bearings.
  Rod-end and caliper bolt patterns must be checked against the parts actually bought.
