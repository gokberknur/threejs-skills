# Updating the skills to a new three.js release

three.js ships monthly (`r187` = `three@0.187.x`, and so on). The skills have two
layers, and they age differently:

| Layer | Files | How it updates |
|---|---|---|
| Corpus (mechanical) | `threejs/references/api/`, `api-index.txt`, `examples-index.md`, `threejs-tsl-webgpu/references/tsl-reference.md`, `tsl-guide/`, `tools/corpus/` | `tools/update-corpus.py` regenerates all of it from threejs.org in about a minute |
| Digests (written) | every other `references/*.md` and the four `SKILL.md` | re-reviewed by hand or by an agent, guided by the updater's change report |

## Procedure

1. **Regenerate the corpus**

   ```sh
   python3 tools/update-corpus.py --dry-run     # report only
   python3 tools/update-corpus.py               # latest npm version, writes files
   python3 tools/update-corpus.py 0.187.0       # or pin a version
   ```

   Read the report: added/removed API pages, new migration-guide sections, and
   files still mentioning the previous release's version string.

2. **Read the new migration-guide section** in `tools/corpus/migration.md`
   (`## 186 → 187`). Every line there is a potential wrong statement in a digest.
   `grep -rn` each renamed/removed symbol across `*/SKILL.md` and
   `*/references/*.md` (excluding `api/`, `tsl-guide/`, `tsl-reference.md`) and fix.

3. **Bump version strings** in the four `SKILL.md` files and `README.md`:
   `0.187.0` → new version, `r187` → new revision. The import-map snippets pin
   the exact version on purpose.

4. **Re-digest what changed.** For small releases, editing by hand is enough.
   For releases that touch a whole area (a renderer change, a TSL rename wave,
   a new post-processing API), rerun the matching digest prompt from
   `tools/digest-prompts.md` with a subagent, pointing it at the fresh corpus,
   and diff the result against the old reference file before replacing it.
   Agents have been reliable at API names when told to grep the local docs,
   and unreliable at version facts when not; keep that instruction in.

5. **Append to `threejs/references/versions-and-migration.md`**: new per-release
   changelog entries (from the migration guide) and move the "upcoming" section
   forward.

6. **Re-run the evals** (`*/evals/evals.json`, three prompts per skill) with
   the skill-creator plugin and compare against the previous benchmark. The
   assertions include "no deprecated APIs"; update those lists when something
   new is deprecated.

7. Commit with the version in the message, e.g. `threejs skills: r187`.

## Sources the updater reads

- `https://threejs.org/docs/` index and `https://threejs.org/docs/pages/<Name>.html` (JSDoc output, includes `TSL.html`)
- `https://threejs.org/manual/list.json` and `https://threejs.org/manual/pages/<slug>.html`
- `https://threejs.org/tsl/content/Guide.md` (the TSL guide, `<page name="...">` blocks)
- `https://threejs.org/docs/llms.txt` (upstream guidance for LLMs; `llms-full.txt` is the same guide inlined)
- `https://raw.githubusercontent.com/wiki/mrdoob/three.js/Migration-Guide.md`
- `https://raw.githubusercontent.com/mrdoob/three.js/r<N>/examples/files.json`

If a URL layout changes upstream, the updater fails loudly; fix the URL in
`tools/update-corpus.py`, nothing else depends on it.

## Things that bit us at r186

Keep these in mind when reviewing a new release; they are the kind of change
that memory gets wrong:

- `PostProcessing` → `RenderPipeline` (r183), `Clock` → `Timer` (r183),
  `RGBELoader` → `HDRLoader` (r180), `PCFSoftShadowMap` removed (r186),
  `renderAsync`/`hasFeatureAsync` deprecated (r181), `colorBufferType` →
  `outputBufferType` (r182), `WebGLRenderer.setEffects()` added.
- `src/Three.Legacy.js` is empty; old names throw rather than warn.
- TSL renames land without aliases (`tslFn`, `timerLocal`, `cond`,
  `storageObject` are gone); always verify against `tsl-reference.md`.

## Things that bit us at r187

- The wiki's `Migration-Guide.md` switched to CRLF line endings, so every
  section looked "new" in the change report. `update-corpus.py` now normalizes
  line endings before diffing.
- The Migration Guide misses some removals. r187 deleted everything deprecated
  in r177 (#34517, e.g. `ColorManagement.fromWorkingColorSpace`) and dropped
  TSL `transformedNormalView/World` and `VarIntent`, none of it in the guide.
  Check three more sources:
  - the GitHub release notes;
  - the TSL guide diff: its `> AI:` notes carried the r187 integer-truncation
    and compute-dispatch changes
    (`git diff -U0 -- threejs-tsl-webgpu/references/tsl-guide | grep '^+> AI:'`);
  - members removed per API page, where signature changes hide
    (`LightProbeGrid.falloff`, the PMREM return type), plus removed
    `tsl-reference.md` entries (`git diff | grep '^-### '`).
- Signature changes hide in `tsl-reference.md` too: `grayscale()` returns a
  `float` since r187, not a `vec3`.
