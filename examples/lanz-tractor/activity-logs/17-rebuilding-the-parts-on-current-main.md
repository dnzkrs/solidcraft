# Rebuild the parts on the current main

*Activity 17 · 2026-10-30*

**An attempt to rebuild all 183 parts with the current `main`'s `solidcraft-cli` found that `main` now reads a symmetric extrude's distance as the total thickness, not per side: five parts came out half as thick or failed. The fix was found and tested on those parts, but the rebuild was cancelled and the branch keeps the earlier build.**

## Aim

The owner asked for a pull request. The fork's `main` had moved on since the parts were built: the product's old working name was replaced by "SolidCraft" throughout. The binary became `solidcraft-cli`, designs `.solidcraft`, and `AGENTS.md` says the old name may not be added anywhere new.

The example used the old names everywhere: the generator called `solvecraft-cli` and saved `.solvecraft` files. Done meant the example built and checked with the CLI from current `main`, under the new names. That is also a test of whether the parts still build on today's kernel.

## Tools

| Tool | Version | Used for |
| --- | --- | --- |
| `cargo build --release -p solidcraft-cli` | current `main` (v0.22.0) | The CLI the example should now use |
| `solidcraft-cli commands` | same | Reading `solid.extrude`'s parameter description |
| `gen_parts.py --build` | session | Rebuilding and checking every part |

## Process

### 1. Renaming in the generator

The CLI default, the design extension and the README examples were switched to the new names. The rest of the logs keep the old names, because they quote commands exactly as they ran. A note in the log index says so.

*The generator's CLI default after the change*

```python
_ap.add_argument("--cli", default=os.environ.get("SOLIDCRAFT_CLI") or shutil.which("solidcraft-cli")
                 or os.path.join(_here, "..", "..", "target", "release", "solidcraft-cli"))
```

### 2. Five parts break

The CLI from `main` took 9 min 16 s to build. The full rebuild then ran in the background. After 42 parts, five had failed:

```text
1-01: FAIL error: step 43 (solid.fillet): invalid parameters for `solid.fillet`: no edge at [6, 28, 100]: the nearest edge is 14.000 mm away
1-11: FAIL 1/1 bodies, hand volume 1928.5 mm³, … SolidCraft 964.3 (-50.00 %)
1-24C: FAIL 1/1 bodies, hand volume 3318.1 mm³, … SolidCraft 1523.8 (-54.08 %)
1-25B: FAIL 1/1 bodies, hand volume 97.2 mm³, … SolidCraft 47.6 (-51.01 %)
1-35: FAIL 1/1 bodies, hand volume 2540.0 mm³, … SolidCraft 2144.0 (-15.59 %)
```

Three came out almost exactly half their volume. All five use `direction="symmetric"`.

### 3. The cause

The current `solid.extrude` description says:

```text
direction?: positive|negative|symmetric (distance is total thickness, split evenly around the start plane);
convention?: total_distance|legacy_per_side (default total_distance; legacy preserves older symmetric extents)
```

The generator had been written for the earlier reading, where the distance was per side. So `distance=W / 2` gave the full width W then, and now gives W/2. 1-01's fillet failed because its frame was half as wide: the edge the fillet named was 14 mm away.

![Symmetric extrude readings](figures/17-rebuilding-the-parts-on-current-main-fig1.svg)

*Figure 1 — The same call under the two readings*

> On the left is the old per-side reading: `distance = W/2` reaches W/2 either side of the sketch plane, W in total. On the right, `main` builds W/2 in total for the same call. The fix is to pass the total, W.

### 4. The fix

Twelve symmetric extrudes were changed to pass their total thickness: ten `distance=W / 2` became `distance=W`, and two literal half-thicknesses were doubled.

*The change, as applied to the generator*

```python
g = g.replace('distance=W / 2, direction="symmetric"', 'distance=W, direction="symmetric"')
```

Output: `12 10` (twelve symmetric extrudes, ten of them the `W / 2` form)

The rebuild was restarted with the fix. It had reached 14 parts with no failures when the owner asked to open the PR straight away.

### 5. Why it was cancelled

The rename belonged with a rebase of only the Lanz commits onto `main`. That was done locally by cherry-picking the 26 commits, resolving `ATTRIBUTION.md` on each. Publishing it needed a force push of the branch, which was blocked. Given the choice, the owner cancelled. The rebuild was stopped, the working tree restored, and the checkout returned to the original branch.

## Results

- No change to the pushed branch. The parts stay as built with the old CLI, and the PR (opened later) records this.
- Two findings for a later rebuild on `main`:
  - every symmetric extrude in `gen_parts.py` must pass its total thickness (12 calls; the change above);
  - `main` keeps the old names working, so the existing `.solvecraft` designs still open.
- The 14 parts rebuilt with the fix before the stop all checked, including 1-01, 1-11 and 1-14.

### Limits and what was left

- The full rebuild on `main` was not finished, so whether other command changes affect later parts is not known.
- The local rebased branch `lanz-rebase` still holds the cherry-picked commits and the rename.

---

*Written retrospectively from the session transcript*
