# Lanz mini tractor in SolidCraft: activity logs

7 activities, written after the work, in the order it happened.

| # | Activity | Date | What it covers |
| --- | --- | --- | --- |
| 01 | [Inspect the Lanz drawing set](01-inspect-the-drawing-set.md) | 2026-10-25 | Twelve uploaded A3 drawing sheets of a model Lanz tractor were identified sheet by sheet, the copyright and SolidWorks origin were flagged, and the scope was agreed: single parts, modelled in SolidCraft, under `examples/` of the owner's private fork |
| 02 | [Build the modelling pipeline and the first parts](02-modelling-pipeline-and-first-parts.md) | 2026-10-25 | A parametric generator that writes SolidCraft scripts and checks every part against a hand-computed volume was built, the first five motor parts (1-01 to 1-04, 1-09) were modelled with it, and a SolidCraft bug that makes blind holes 3.42 mm short was found and worked around |
| 03 | [Model the crankshaft, flywheel, piston and valve gear](03-crankshaft-flywheel-piston-valve-gear.md) | 2026-10-29 | Eleven moving motor parts (1-14 to 1-31) were modelled, the generator gained multi-body parts and a self-updating parts table, undimensioned sizes were measured from the PDF's own vector lines, and the hand-volume check caught a wrong formula in the checker itself |
| 04 | [Finish the sheet-03 motor parts](04-rest-of-sheet-03.md) | 2026-10-29 | The remaining nineteen motor parts on sheet 03 (oiler, big end, slide valves, valve holder, cam follower, exhaust bracket) were modelled, part names were corrected against the parts list, and a SolidCraft limit with tangent faces was found and avoided |
| 05 | [Model the exhaust stack parts](05-exhaust-parts.md) | 2026-10-29 | The four turned parts of the exhaust stack on sheet 04 (1-36 to 1-39) were read from the drawing's vector lines and modelled, and the readings were confirmed by how the parts fit each other |
| 06 | [Model the accelerator linkage and steering bracket](06-accelerator-linkage-and-steering-bracket.md) | 2026-10-29 | Eleven parts from sheet 04 (1-43 to 1-53) were modelled, using SolidCraft's sheet-metal tools for the folded bracket and its coil command for a spring, and a second SolidCraft bug (hidden sketches reappear after reopening) was found |
| 07 | [Model the flame guards and the valve spring](07-flame-guards-and-valve-spring.md) | 2026-10-29 | The two perforated flame protectors (1-40, 1-41), the front flame guard (1-42) and the wire valve spring (1-34) were modelled, completing the motor group 1-01 to 1-53, after several construction approaches failed and a third SolidCraft bug (an inside-out pipe) was found |

Figures live in `figures/` and are referenced relatively, so keep the
folder next to the Markdown files when moving them.
