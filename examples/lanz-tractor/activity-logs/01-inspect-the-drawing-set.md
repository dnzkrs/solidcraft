# Inspect the Lanz drawing set

*Activity 01 · 2026-10-25*

**Twelve uploaded A3 drawing sheets of a model Lanz tractor were identified sheet by sheet, the copyright and SolidWorks origin were flagged, and the scope was agreed: single parts, modelled in SolidCraft, under `examples/` of the owner's private fork.**

## Aim

The owner uploaded PDF drawings in three batches without saying what to do with them: sheets 01–05, then 06–10, then 11–12 with the request "Design this drawing with solidgraph". Before any modelling, the drawings had to be understood: what each sheet contains, how the parts are numbered, and whether anything about their origin limits how they may be used in the SolidCraft repository.

Done meant: a description of every sheet, the open questions settled with the owner (which tool, what scope, where the results go), and nothing modelled on a guess about those three points.

The repository's `CLAUDE.md` set the constraints: SolidCraft must not use test data, measurements or files produced with commercial CAD products, and every committed asset needs a row in `ATTRIBUTION.md`.

## Tools

| Tool | Version | Used for |
| --- | --- | --- |
| poppler `pdfinfo`, `pdftotext` | system | Sheet metadata (creator, page size) and text: part numbers, titles |
| poppler `pdftoppm` | system | Rendering sheets to PNG to look at them |
| Read tool | — | Viewing the rendered PNGs |
| AskUserQuestion | — | Settling tool, scope and output location with the owner |

## Process

### 1. Reading metadata and text from the first five sheets

The first upload came with no instruction, so the sheets were inspected with poppler.

*Metadata and the first lines of text of every sheet*

```bash
for f in *.pdf; do echo "== $f"; pdfinfo "$f" 2>/dev/null | grep -E "Pages|Page size|Title|Creator"; pdftotext -layout "$f" - 2>/dev/null | head -40; done
```

```text
== 40234a13-lanz-a3-sheet-01.pdf
Title:           LANZ-A3-SHEET-01
Creator:         SolidWorks 2011 SP0.0 (2010276)
Page size:       1190.55 x 841.89 pts (A3)
...
NOTES: ORIGINAL DRAWINGS BY C.P.HENDRIKX 1996. (ORIGINAL DRAWINGS WERE IN DUTCH LANGUAGE)
  LANZ MINI TRACTOR        GENERAL ARRANGEMENT        JDW DRAUGHTING SERVICES
                                                      Copyright © J.A.M. DE WAAL PAPAKURA NZ
```

*Figure 1 — The metadata that set the ground rules*

> Two lines matter. `Creator: SolidWorks 2011` is on every sheet, so the drawings were produced with a commercial CAD product, which the repository's rules exclude as test or reference data. "Copyright © J.A.M. de Waal" means the drawings and anything copied from them are not free to publish. Both were reported to the owner before any work started.

Sheet 02 turned out to be the parts list: about 200 part numbers in groups (1-xx motor, 2-xx motor housing, 3-xx chassis, 4-xx gearbox), with screws, notes and material codes (ALUM, CI, BRS, BMS, S/S, SPS).

### 2. Mapping the later sheets

For sheets 06–10 the part numbers on each sheet were pulled out of the text layer, which tells what each sheet covers without reading the whole drawing.

```bash
pdftotext "$f" - | grep -oE "\b[0-9]-[0-9]{2}[A-Z]?\b|SA-[0-9]-[0-9]+|SHEET:[0-9]+ OF [0-9]+|DRAWING CONTENTS.*" | sort -u | tr '\n' ' '
```

Output for sheet 08: `1-01 1-02 … 1-52 4-27 4-29 4-30 … SA-1-101 … SA-1-115 SHEET:08 OF 13`

Sheets 11 and 12 had almost no text, so they were rendered and looked at: sheet 11 shows exploded sub-assemblies (gearbox SA-4-401, the drive belt 5-01) and sheet 12 a rendered isometric picture of the finished tractor.

![Contents of the drawing set](figures/01-inspect-the-drawing-set-fig2.svg)

*Figure 2 — What each of the twelve received sheets holds*

> The dimensioned single parts, the material for modelling, are on sheets 03–07; sheets 08–11 are exploded 3D views that show how the parts go together but carry few dimensions. The set says "13 sheets"; sheet 13 was never uploaded.

### 3. Resolving "solidgraph", scope and location

The request named "solidgraph". The workspace had no such tool: a search of `/home/user` and the SolidCraft sources for the word found nothing, and the only CAD tool present was SolidCraft (`solvecraft-cli`). Rather than guess, three questions went to the owner:

| Question | Owner's answer |
| --- | --- |
| Which tool is "solidgraph"? | SolidCraft |
| What first: simplified whole tractor, one sub-assembly, or single parts? | Single parts |
| Where should results go, given the copyright and SolidWorks origin? | "this is private forked repository, design under examples/" |

The third answer overrode the cautious default (keep the models outside the repository). That shaped the later work: models are committed under `examples/lanz-tractor/`, the drawings themselves are never committed, and the asset rows in `ATTRIBUTION.md` say "private use; dimensions from copyrighted drawings".

## Results

- A sheet-by-sheet description of the twelve received sheets (figure 2) and the parts list structure.
- The ground rules on record: SolidWorks-produced, copyrighted drawings; models for private use only, in the owner's fork; the drawings stay out of the repository.
- An agreed plan: model single parts in SolidCraft under `examples/lanz-tractor/`, starting with the motor on sheet 03.

### Limits and what was left

- Sheet 13 was never received; the parts list on sheet 02 also omits 1-53, which appears on sheet 04.
- "solidgraph" was taken to mean SolidCraft on the owner's confirmation; no other tool was looked for outside the workspace.

---

*Written retrospectively from the session transcript*
