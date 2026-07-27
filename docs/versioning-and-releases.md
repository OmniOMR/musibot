# Versioning and releases

Musibot is a monorepo whose components are released independently — `core` and the HTTP API move at different speeds, and a *Worker Head* running in some model's virtual environment has no reason to be re-released because the Web UI changed. So a release here has to name a component, not just a version, and two conventions follow from that: git tags carry the component name, and each component's version number is read back out of those tags rather than written down by hand.

The second half is the part worth reading even if the first seems obvious. It is what makes `pip install` from a GitHub link behave.


## Tags name the component

A release is a git tag whose prefix is the component's folder under `components/`:

```
core/v0.1.0          api/v0.1.0          python-client/v0.1.0          worker-head/v0.1.0
```

Slashes are legal in git refs, and this is the same layout Go modules mandate for monorepos, so it is a well-trodden convention rather than a local invention. It answers the three questions you actually ask about a component:

```bash
git tag -l 'api/v*'                            # its release history
git describe --tags --match 'api/v*'           # where HEAD sits relative to its last release
git log api/v0.1.0..HEAD -- components/api     # what has changed since
```

Because `core` is the wire contract, a change there is a change to every component that depends on it, so its directory belongs in that last command too: `git log api/v0.1.0..HEAD -- components/api components/core`.

One small one-way door: once `api/v0.1.0` exists, git can never hold a plain tag named `api`, because a ref cannot be both a file and a directory. Nothing wants that tag, but it is worth knowing why it would fail.

Every tag gets a GitHub release page, whose notes are that component's [CHANGELOG.md](#the-changelog) entry for the version.


## The version number comes from the tags

None of the released components carry a `version` field. They declare the version *dynamic* and let [hatch-vcs](https://github.com/ofek/hatch-vcs) derive it from `git describe`:

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]

[project]
name = "musibot-core"
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"
raw-options.root = "../.."
raw-options.git_describe_command = ["git", "describe", "--dirty", "--tags", "--long", "--match", "core/v*"]
raw-options.tag_regex = '^core/v(?P<version>\d+\.\d+\.\d+.*)$'
```

Three of those lines are not guessable, and each fails in its own way if omitted:

- **`root = "../.."`** — setuptools-scm (which hatch-vcs wraps) refuses to run when `pyproject.toml` is not at the repository root. It *finds* the repository in a parent directory and then errors out telling you it found it, rather than using it. Every component in this repo is a subdirectory, so every component needs this.
- **`--match "core/v*"`** — without it, `git describe` returns whichever tag is nearest, and a component happily reports another component's version.
- **`tag_regex`** — strips the `core/v` prefix, so the tag `core/v0.1.0` yields the version `0.1.0`. Without it the prefix is not valid in a version string and the build fails.

What you get out:

| Where you are | Version built |
| --- | --- |
| Exactly on `core/v0.1.0` | `0.1.0` |
| 3 commits after it | `0.1.1.dev3+g2d478f1` |
| 3 commits after it, with uncommitted edits | `0.1.1.dev3+g2d478f1.d20260727` |
| Before the component's first tag | `0.1.dev31+g44da046` |

The `.dev` number counts commits since the tag, so it rises monotonically and every commit gets a distinct, correctly-ordered version. Note that the `0.1.1` part is a *guess* — setuptools-scm assumes the next release bumps the patch. It is not a promise about what the next release will be numbered; only the ordering matters, and a development build is not a release.


### Why not just write the version down

Because `pip` decides whether to reinstall a package by comparing **version strings, and nothing else**. It records the exact commit it installed from in `direct_url.json` and then ignores it when making that decision. With a hand-maintained version that stays `0.1.0` across a development cycle, the behaviour is:

| Situation | What pip does |
| --- | --- |
| Same version, new commit, plain install | **nothing, silently** |
| Same version, new commit, `pip install -U` | **nothing, silently** — `-U` does not help |
| Different version, plain install | installs it, no `-U` needed |
| Different version, older commit | downgrades — it syncs to whatever the URL builds |
| `--force-reinstall --no-deps` | always reinstalls |

The first two rows are the trap: a teammate re-installs from a newer commit, pip prints nothing alarming, and they keep running the old code. Deriving the version from git turns every commit into a distinct version, which lands you in row three — the one where things simply work.


## What this covers

| Component | Released | Versioning |
| --- | --- | --- |
| `core` | yes | From tags, as above. Semver on the wire contract. |
| `api` | yes | From tags. Semver on the HTTP API. |
| `python-client` | yes | From tags. Semver, independent of the API's cadence. |
| `worker-head` | yes | From tags. Semver on the IPC contract. |
| `orchestrator-head` | not yet | No implementation yet — same scheme when there is one. |
| `orchestrators` | no | A *Pipeline* is identified by name and version; see its README. |
| `models` | no | A *Model*'s version is a domain concept — it is what a *Pipeline* pins and what discovery announces — so it stays a written-down constant in the model's `pyproject.toml`, not something derived from repository history. |
| `web-ui` | not yet | Node toolchain; its own version, decoupled from the API it targets. |

Each component's README states what its version *means*; this page only says where the number comes from.


## Installing a released component

Nothing is published to a package index yet — while Musibot is on `0.x` and only the team is running it, git links are the whole distribution story. That has one consequence worth stating plainly: **`musibot-core` has to be supplied explicitly**, because it is named as a dependency but no index can resolve it.

```bash
pip install \
  'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
  'musibot-api @ git+https://github.com/OmniOMR/musibot.git@api/v0.1.0#subdirectory=components/api'
```

Given both in one command, pip uses the explicit `musibot-core` to satisfy the one `musibot-api` asks for, and never consults an index. Omit it and you get a clear failure rather than a subtle one:

```
ERROR: Could not find a version that satisfies the requirement musibot-core>=0.1.0 (from musibot-api)
```

The `[tool.uv.sources]` block in each `pyproject.toml` points `musibot-core` at its sibling directory, which is what makes an editable checkout work during development — but it is uv-specific and pip ignores it, so it does not help here.

A *Worker* is the same shape, installed alongside its model:

```bash
pip install \
  'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
  'musibot-worker-head @ git+https://github.com/OmniOMR/musibot.git@worker-head/v0.1.0#subdirectory=components/worker-head'
```

To follow development rather than a release, put a branch name or a commit SHA where the tag goes. Because each commit builds a distinct version, a plain `pip install` of a newer commit replaces what is there — no `--force-reinstall` needed.


## Cutting a release

Say `api` is going to `0.1.0`.

1. Move the component's `CHANGELOG.md` entries from *Unreleased* into a `## 0.1.0 — 2026-07-27` section.
2. Commit that, and anything else the release needs. There is **no version to bump** — that is the point of deriving it.
3. Tag and push:

   ```bash
   git tag api/v0.1.0
   git push origin main api/v0.1.0
   ```

4. Open the release page and paste that changelog section in as its notes. From the command line that is:

   ```bash
   gh release create api/v0.1.0 --title "api 0.1.0" --notes "$(cat notes.md)"
   ```

   Doing it in GitHub's web form is equally fine, and is what we do today.

5. Sanity-check that the tag builds clean, with no `.dev` suffix:

   ```bash
   pip download --no-deps -d /tmp/check \
     'musibot-api @ git+https://github.com/OmniOMR/musibot.git@api/v0.1.0#subdirectory=components/api'
   ```

Releasing several components at the same commit is normal — the prototype release is four tags on one commit. They are still independent releases; they merely happen to coincide.


## When the build needs git

The version is computed at build time by running `git`, so the build needs a repository:

- **A source archive has no history.** GitHub's "Download ZIP", `git archive`, or a `COPY` into a Docker image that excludes `.git` will all fail to build with `unable to detect version`. Installing from a `git+https://` link is fine — pip clones, so the history is there.
- **It needs the tags, not just the history.** A working copy with no `core/v*` tag in it builds core as something like `0.1.dev31+g44da046`, and PEP 440 orders that *below* `0.1.0` — so the `musibot-core>=0.1.0` floor that `api`, `worker-head` and `python-client` declare becomes unsatisfiable, and an editable development install fails with `ResolutionImpossible`. A normal `git clone` fetches tags and is fine; a shallow or `--no-tags` clone, typical in CI, is not. `git fetch --tags` fixes it.
- **The escape hatch is `SETUPTOOLS_SCM_PRETEND_VERSION`**, which forces a version when there is no repository to read. Note that the more precise `SETUPTOOLS_SCM_PRETEND_VERSION_FOR_<NAME>` form does *not* work under hatch-vcs, which does not pass the distribution name through; use the plain variable.
- **Git worktrees work**, including the editable installs the component READMEs describe, even though `.git` is a file rather than a directory there.
- **The `+g<sha>` local segment cannot be uploaded to PyPI.** It is not a problem now, and it never appears on a tagged commit anyway, but it is the thing to remember on the day we publish.


## The changelog

Each released component keeps a `CHANGELOG.md` next to its `pyproject.toml`, in [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) form: an *Unreleased* section at the top that accumulates entries as work lands, and one section per released version below it. It is the source text for the GitHub release notes, and it is the only human-written record of what a version contains — the tag says when, the changelog says what.

Entries are written for whoever installs the component, so they describe behaviour and contracts rather than commits.


## Later: package indexes

When external users appear — the [Web UI's general public](who-are-the-users.md), or library users writing against `python-client` — git links stop being reasonable: they need git and a build toolchain on the installing machine, they defeat wheel caching, and they cannot express a constraint like `musibot-core>=0.2`, only a frozen SHA.

At that point `core` and `python-client` are the ones to publish to PyPI, with `orchestrator-head` and `worker-head` following if external model and pipeline authors are expected to install them. The `musibot-*` distribution names are all unclaimed as of this writing, which is worth fixing sooner than the publishing itself. The migration is small: drop the explicit `musibot-core @ git+...` from install commands and let the ordinary `musibot-core>=0.1.0` constraint already in each `pyproject.toml` resolve from the index. That constraint is deliberately a plain requirement and not a URL, because PyPI rejects distributions whose dependencies are direct references — pinning core by URL here would be a decision to unpick later.

Components that are *deployed* rather than *installed* — `api`, `web-ui`, and the orchestrators — have no reason to go to an index at all. If their deployment ever needs to be more repeatable than a git link, container images are the answer, not packages.
