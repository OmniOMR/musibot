# Changelog for `pmcg-orchestrator`

Released as `pmcg-orchestrator/vX.Y.Z` git tags — see [Versioning and releases](../../../docs/versioning-and-releases.md).

**This version is not what a *User* pins.** A *User* pins a *Pipeline* — `mzk-page` `1` — and that number moves when the same page would come out different. This one versions the *program*: its configuration, its dependencies, and which *Pipelines* it provides. The two are deliberately independent, and the entries below say which of them moved.


## Unreleased


### Changed

- **Renamed from `omniomr-orchestrator` to `pmcg-orchestrator`**, because it now hosts *Pipelines* for the Prague Music Computing Group and its partners rather than for the OmniOMR project alone. Everything that carries the name moved with it: the folder, the python package (`pmcg_orchestrator`), the distribution and its console script (`musibot-pmcg-orchestrator`), the name the *Orchestrator* announces itself under (`pmcg`), and the release tags (`pmcg-orchestrator/vX.Y.Z`). A deployment installs the new distribution into a fresh virtual environment and runs it as `musibot-orchestrator@pmcg`. The 0.1.0 entry below was released under the old name and tag.

- **Nothing about how a *Pipeline* behaves is configuration any more.** Its name and version are a contract with the *User*, so the implementation, the *Models* it runs, its slicing margin and the name and version it is announced under are all written down in the source, and changing any of them is a re-deployment. The settings `page_pipeline_name`, `page_pipeline_version`, `staff_pipeline_name`, `staff_pipeline_version`, `layout_model`, `staff_model`, `staff_padding_ratio` and `layout_confidence` are gone; a deployment that still sets them is unaffected, since unknown settings are ignored, but they no longer do anything. `layout_confidence` was unset everywhere, so the layout *Model* keeps using its own default.

- **`mzk-staff` `1` takes any number of staff crops**, `Staves/{*s}/image.jpg`, rather than exactly one, running the transcription *Model* over each of them at once. One crop is still a valid request, and is what the *Web UI* sends, so nothing written against it breaks. A staff that fails is said in the log while the rest are transcribed; the request fails only when every staff did. Implemented by `StavesFromStaffPipeline`.


### Added

- **`mzk-page` `2`** — the page's staves are grouped into instruments using the layout's `system` and `grandstaff` boxes, and each instrument becomes a `<part>`: grand staves are zipped into two-staff parts, staves sharing a system are padded to the same number of measures, an instrument missing from a system is written as hidden measure rests, and the clef, key and time signature a staff does not print are carried over from the instrument's preceding staff. Implemented as `PageFromStaffPipelineV2`, with the gluing in `pmcg_orchestrator.gluing.v2`.

  **`mzk-page` `1` is still published beside it**, unchanged, for anyone pinning it — now as `PageFromStaffPipelineV1`, with its gluing in `pmcg_orchestrator.gluing.v1`. The two share their layout reading, slicing and transcription steps through a common base class.

- **`pmcg-slice` `1`** — a page and its `layout.json` in, a crop per staff out: step 2 of `mzk-page` on its own, cutting the same crops.

- **`pmcg-glue` `1` and `2`** — a `layout.json`, the staff crops and their transcriptions in, a page-level MusicXML file out: step 4 of `mzk-page` on its own, in both of its versions. Staff folders must be integers, may have gaps, and are paired with the layout's `staff` boxes in reading order; a staff with a crop and no transcription becomes a placeholder.

- **`--only-pipelines name@version`**, for development: announce only the named *Pipelines* rather than all of them. A *Pipeline* under development is registered with a `-dev` version and started alone, so that unfinished code takes no work from the *Pipelines* already published.


### Notes

- **A new dependency, `linearized-musicxml`**, pinned to a commit of its git repository, which the version 2 gluing of `mzk-page` `2` and `pmcg-glue` `2` uses to zip grand staves and to carry clefs, keys and time signatures over. A deployment's `pip install` needs to reach GitHub for it.
- **The *Web UI* offers `mzk-staff` differently on a page that already holds several crops**: one run over all of them rather than one run per crop, because the *Signature* now names a set. Uploading a single crop works as before.


## 0.1.0 — 2026-08-14

First release. It provides the two *Pipelines* the *Web UI* offers, and both are `1`.


### Added

- **`mzk-page` `1`** — a page scan in, a page-level MusicXML file out. A layout *Model* finds the staves, this cuts the page along them with a margin proportional to each staff's height, a transcription *Model* reads every crop at once, and the measures are concatenated into one `<part>` with a system break where each staff begins.

  One staff failing does not fail the page: a scan of a real book has stains, cropped systems and pages the detector was too generous about, so a failed staff is said in the log and takes up a marked system in the score, and the rest of the page still comes back. A page where *every* staff failed does fail.

- **`mzk-staff` `1`** — one staff crop in, its transcription out. Step for step what the transcription *Model's* own *ImplicitPipeline* does, and it exists for the name: an *ImplicitPipeline* is called after the *Model* behind it and so is renamed whenever a better snapshot is deployed, while this is not.

- **Both *Pipelines'* names and versions are settings**, along with the two *Models* they run, so a development deployment is this same program started with different ones rather than a second codebase. `--help` lists them.


### Notes

- The default *Model* pins are the snapshots this deployment runs today — `dvorak-ola@2.0-2025-03-09` and `ayce-long@2026-08-03-192253-final` — so it starts with no arguments against the development stack. **A deployment pins both explicitly**: a superseded snapshot is what a default quietly goes on pointing at.
- Requires an *Orchestrator Head* of 0.1.0 or newer, and through it python 3.11+.
- The slicing and the concatenation are *Musicorpus* logic rather than *Musibot* logic, kept in modules of their own so they can move to the `musicorpus` package when it has somewhere for them to land.
