# Changelog for `omniomr-orchestrator`

Released as `omniomr-orchestrator/vX.Y.Z` git tags — see [Versioning and releases](../../../docs/versioning-and-releases.md).

**This version is not what a *User* pins.** A *User* pins a *Pipeline* — `mzk-page` `1` — and that number moves when the same page would come out different. This one versions the *program*: its configuration, its dependencies, and which *Pipelines* it provides. The two are deliberately independent, and the entries below say which of them moved.


## Unreleased


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
