# Rough edges

Known simplifications and gaps in the current design. They are deliberately deferred so we can get a prototype running quickly, and will be cleaned up as we reach the relevant parts of the codebase. This page exists so we don't forget them.


## Deferred items

- **Page eviction vs. active executions** — the `api` service may evict *Musicorpus Pages* under disk pressure, but the policy is undefined. At minimum it should not evict a page that has a running *Pipeline Execution*, and the client-visible behaviour of hitting an evicted page (a sudden `404` while polling) needs deciding.
- **Stray-write garbage in MinIO** — after a `DELETE` or a timed-out execution, a still-running *Worker* or *Model* may keep writing into a page folder that the `api` service no longer tracks, leaking disk until the next `api` startup wipe. Acceptable for now.
- **Path traversal** — `core` now validates page IDs and file paths (`musibot.core.page`), and refuses anything that could leave a page's folder, symbolic links included. What remains is making sure every call site actually uses it: the file endpoints in the `api` service, and the paths a *Worker Head* accepts back from a *Model*.
- **File-change detection in the worker head** — the *Worker Head* uploads "changed" files back to MinIO after a model run; the detection mechanism (mtime vs. content hash) and whether *file deletions* propagate are unspecified.
- **Per-model timeout** — only the pipeline-level timeout exists today, so a hung *Model* ties up a *Worker* for the whole pipeline budget. A per-model watchdog may be worth adding.
- **Pipeline file-access API (async vs. local path)** — undecided whether a *Pipeline* fetches *Files* straight from MinIO (asynchronous, needs `await`) or operates on a local `pathlib.Path` mirror of the page that is synced around *Model* executions. This drives the `ctx.read_file` / `ctx.write_file` shape. Revisit when coding the *Orchestrator Head*.
