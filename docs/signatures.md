# Signatures

A *Signature* is the I/O declaration of a *Model* or a *Pipeline*: the *Files* it reads out of a *Musicorpus Page* and the *Files* it writes back into it. This page defines what a *Signature* can say, how it relates to the input list carried by an execution request, and what Musibot does and does not check.

The vocabulary of file paths comes from the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md) — `image.jpg`, `layout.json`, `transcription.musicxml` at the page level, and the `Staves/`, `Grandstaves/` and `Systems/` subdivisions beneath it. Musibot does not know what any of those mean; it only moves them around.


## Why a Signature exists at all

Not to move *Files* around. What the *Worker Head* downloads is the `input` list of the execution request, an exact set of paths chosen for that one execution. A *Signature* names no *Files* at all — it says which sets of *Files* are admissible in the first place.

The reason to declare that is that Musibot has no static registry of anything. *Models* and *Pipelines* are plugged into a running system just by connecting to RabbitMQ, and the `api` service learns of them only through [Discovery](discovery.md); nothing about them is written down in a configuration file. A listing that says `staff-transcriber` version `1.0.0` exists, and nothing more, leaves a *User* with no way to construct an input list — no way to know whether to send `image.jpg` or `Staves/7/image.jpg`, and no way to know that a `layout.json` has to have been produced first. Without a *Signature*, the one mechanism Musibot has for finding out what exists cannot say what any of it is for.

So the primary job of a *Signature* is to make the listing **actionable**. Two more jobs follow from it: it is the reference the `api` service checks a requested input list against, which turns a wrong request into a `400` instead of a puzzling failure three hops away; and two *Orchestrators* announcing the same *Pipeline* with different signatures is how the `conflicting-signatures` warning in [Discovery](discovery.md) is detected.

And it stops there. A *Signature* is a declaration about a *Model* or *Pipeline*, not a contract enforced on every hop, which is why [What is checked](#what-is-checked) is a short section.


## A Signature declares patterns, an execution names files

These are two different things, and conflating them is the mistake to avoid:

| | Lives on | Contains |
| --- | --- | --- |
| **Signature** | A *Model* or *Pipeline* description, announced over [Discovery](discovery.md) | *Patterns* — `Staves/{s}/image.jpg` |
| **Input list** | One execution request (`ModelExecutionStart`, `PipelineExecutionStart`) | *Concrete paths* — `Staves/7/image.jpg` |

A *Signature* describes a shape that many pages fit. An execution is about specific *Files* in one page. For a page-level model the two look identical, because a pattern with no slots in it is its own instantiation.


## Slots

A path segment in a *Signature* may be a **slot**, written with braces:

| Token | Meaning |
| --- | --- |
| `{}` | Exactly one instance, anonymous. |
| `{name}` | Exactly one instance, bound: the same `name` elsewhere in the *Signature* means the same instance. |
| `{*}` | Every instance, zero or more, anonymous. |
| `{*name}` | Every instance, bound: the same `*name` elsewhere means the same set, matched one instance to one instance. |

Two axes, then — how many, and whether it is tied to another slot — and the anonymous forms are simply names that nobody repeats.

An input slot is bound by the *Files* the execution actually names. A slot that appears **only** in the output is bound by the *Model*, which invents the names: that is how a model that cuts a page into staves declares that it produces however many staves it happens to find.

This is the whole vocabulary. It expresses the models we expect to deploy:

| Model | Signature |
| --- | --- |
| Page layout detection | `image.jpg` → `layout.json` |
| Page-level transcription | `image.jpg` → `transcription.musicxml` |
| Staff transcription | `Staves/{s}/image.jpg` → `Staves/{s}/transcription.musicxml` |
| Page splitter | `image.jpg`, `layout.json` → `Staves/{*}/image.jpg` |
| Staff-to-system joiner | `Staves/{*}/transcription.musicxml` → `Systems/{*}/transcription.musicxml` |
| Grandstaff splitter | `Grandstaves/{*}/image.jpg` → `Staves/{*}/image.jpg` |

Note the last two: the `{*}` on each side is anonymous, so the two sets are unrelated — staff `2` does not become system `2`, and there are fewer systems than staves. Had they been written `{*x}` on both sides they would have had to correspond one to one, which is the batch-of-staves case rather than the joining case.

On the wire nothing changes shape. A *Signature* is still two arrays of strings:

```json
"signature": {
  "input": ["Staves/{s}/image.jpg"],
  "output": ["Staves/{s}/transcription.musicxml"]
}
```

Every *Signature* written before slots existed is still a valid *Signature*, because a path with no braces in it means exactly what it always meant.


### The small print

**A slot occupies a whole path segment.** `Staves/{s}/image.jpg` is a slot; `image.{s}.jpg` is not allowed. Musibot deliberately does not know that the segment before a slot is called `Staves` — a future subdivision level should not be a change to Musibot, for the same reason a new file format is not one (see [Domain model](domain-model.md)). Validation of a pattern is therefore purely syntactic.

**Braces, not a glob.** `Staves/*/image.jpg` would invite `*.jpg` and `**/`, and answering those invitations means owning a glob engine and the questions that come with it. Braces say *slot* and nothing else. Musibot is an OMR service, not a path-matching library.

**`{` and `}` are not allowed in concrete file paths.** `musibot.core.page` refuses them in a *File* path, so a pattern never needs escaping and a page can never contain a file whose name looks like a slot.

**A `{*}` slot names a set, not a sequence.** Nothing in a *Signature* says what order the instances come in, and nothing should — instance names are arbitrary path-safe strings in the Musicorpus Specification, so there is no ordering a *Signature* could impose that would mean anything. A *Model* that cares, such as a joiner deciding which staves belong to one system, takes the order of the input list it was handed, and deciding that order is the *Pipeline's* business.

**A trailing `?` marks an entry as optional.** On the input side `layout.json?` means an input list that omits that file is still valid; on the output side it means the *Model* may or may not produce it. Optional inputs have to be declared rather than read opportunistically: an undeclared *File* would be rejected by the validation below if a *User* named it, and never staged if they did not, so the *Model* would not find it either way. A `{*}` slot is already optional in this sense, since it matches zero instances happily.


## Writing a Model signature: `{s}` or `{*}`

A *Model* that transcribes staves could declare either `Staves/{s}/image.jpg` — one staff per execution — or `Staves/{*s}/image.jpg` — all the staves of a page in one execution. The rule:

> Use `{s}` when the *Model* treats instances **independently**, and set `supports_batching` so the *Worker Head* batches them. Use `{*}` only when the *Model* must see the **whole set** to do its work.

The staff transcriber is independent: staff 7 is transcribed without reference to staff 8, so it takes `{s}`. The staff-to-system joiner is not: it decides the grouping by looking at all the staves at once, so `{*}` is the only honest declaration it can make.

This is a correctness rule, not a style preference, and the reason is the failure model in [Worker IPC](worker-ipc.md). A batch reports one `completed` or `failed` per `execution_id`, so one bad sample fails one sample and no more. With `{s}` the unit of work and the unit of reporting are the same thing and that guarantee holds. With `{*s}`, a single unreadable staff inside a twelve-staff execution has no message to be reported in: the *Model* can only fail all twelve or silently skip one. A `{*}` *Model* that also batches is nesting two levels of grouping over a flat reporting channel.

Following the rule makes the problem disappear rather than papering over it, because a *Model* that genuinely needs the whole set genuinely has one indivisible outcome — for which one result per execution is the truth.


## The input list

Both start messages carry an `input` array of concrete paths, supplied by whoever requested the execution:

```json
{
  "type": "pipeline-execution-start",
  "page_id": "7Kf2mP9xLwQ",
  "execution_id": 1,
  "pipeline": { "name": "staff-transcriber", "version": "1.0.0" },
  "input": ["Staves/7/image.jpg"],
  "parameters": {},
  "timeout_seconds": 300
}
```

The two messages use the same field with the same shape, but it does not oblige the receiver in quite the same way:

| | `ModelExecutionStart.input` | `PipelineExecutionStart.input` |
| --- | --- | --- |
| Means | The staging list. The *Worker Head* downloads exactly these and the *Model* sees nothing else in the page folder. | What the execution is about. |
| Bounds what may be read | Yes, absolutely. | No. A *Pipeline* reads and writes intermediate *Files* nobody named — the splitter's staff images do not exist when the *Pipeline* starts. |

**The *User* supplies it, and the `api` service does not invent it.** A *User* knows which *Files* they want processed; they uploaded them. The `api` service does not: a *MusicorpusPage* in its domain model holds an ID, an owner and a list of executions, and says so — the *Files* live in MinIO. Uploads travel over presigned PUT URLs, so the service knows which URLs it minted and never learns which ones were used. "Everything that was uploaded" is therefore not a question the server can answer honestly, and it will not guess by listing the bucket on the execution path.

The [Python client](using-python-client.md) can and does default it, because it is holding the files it just uploaded. `process_page` fills `input` from its own upload set; `start_execution` takes it explicitly, which is what a caller holding one page open across several executions needs anyway.


## What is checked

Little, and in known places. [Discovery](discovery.md) is a directory that expires and is allowed to be wrong by design; a *Signature* is a declaration, not a contract enforced on every hop.

| Check | Where | On failure |
| --- | --- | --- |
| A pattern is syntactically well formed | `core`, parsing an announcement off the wire | The announcement is rejected. |
| The requested input list fits the *Pipeline's* or *Model's* input patterns | `api` service, on the execution request | `400`, naming the mismatch. |
| Every *File* in the input list exists | *Worker Head*, staging | The execution fails with `InputFileMissing`. |
| Every declared, slot-free, non-optional output *File* was written | *Worker Head*, after the command | The execution fails. |

The second is the one that makes a *Signature* more than decoration: handing twelve staves to a `Staves/{s}/image.jpg` *Model* is rejected at the edge with a legible message instead of becoming a confusing failure three hops away. It is cheap — matching concrete strings against patterns, with no access to storage — and it is not the same thing as expanding a pattern into paths, which needs the page contents and happens nowhere in the `api` service.

The last one catches the most common *Model* bug there is, writing output to the wrong path, which otherwise shows up as a *Pipeline* that succeeds and produces nothing. Files the *Model* wrote that the *Signature* did not declare are still uploaded, and logged; filtering them away would silently swallow a diagnostic file somebody meant to keep.

Everything else is left to fail where it will. A *Signature* is not meant to be infinitely malleable: a *Model* whose real expectations are narrower than anything expressible here should announce the wider *Signature* and report a plain error for input that satisfies it but not the model.


## Implicit pipelines are exactly the Model's signature

An *ImplicitPipeline* has the *Signature* of the *Model* behind it, unchanged. If a *Model* declares `Staves/{s}/image.jpg`, its *ImplicitPipeline* takes one staff, and a *User* who wants a whole page processed runs it once per staff.

It is tempting to do better — to have the `api` service offer a `{*s}` pipeline for every `{s}` *Model*, fanning out one execution per staff and gathering the results. It is rejected deliberately. Fan-out needs grouping by slot binding, a policy for partial failure, and a decision about what to do with models taking several *Files* per instance or mixing page-level and staff-level inputs. That is a *Pipeline* engine, and building a second one inside the `api` service — the one service that does not scale horizontally — to sit beside the *Orchestrator* would be the wrong place for all of it.

So the boundary is: the `api` service **passes an input list through**; it does not expand patterns, fan out, or gather.

*ImplicitPipelines* exist so a *Model* can be exercised in isolation during development, as [Domain model](domain-model.md) says. They are marked `implicit` in the `GET /pipelines` listing and that is what the marking is for. A friendlier per-page staff-transcription *Pipeline* is a real *Pipeline*, written in an *Orchestrator* — and writing it is a good way to find out what fan-out and gather primitives the *Orchestrator Head* API ought to expose.


## Open questions

- **Nested slots** — `Systems/{sys}/Staves/{staff}/image.jpg` is syntactically fine and semantically meaningless today, since the Musicorpus Specification nests subdivisions exactly one level deep. Nothing forbids it, and nothing supports it either.
- **Signature-to-signature matching** — the output patterns of one *Pipeline* against the input patterns of the next would answer "can these be chained", and matching input patterns against a page's real contents would answer "what can I run on this page right now". Both are useful, neither is needed yet.
