import type { PipelineView, SignatureView } from "./api/types";

/**
 * Which *Pipelines* this app offers, and where a visitor's upload has to land
 * for one of them to accept it.
 *
 *
 * ## The two defaults
 *
 * The design gives a visitor two choices — a whole page or a single staff —
 * and those map to two named *Pipelines*. They are written down here rather
 * than discovered, because "the one we recommend" is a product decision and
 * there is nothing in a *Pipeline's* announcement that could express it.
 *
 * Nothing guarantees they are deployed. *Pipelines* are announced over
 * RabbitMQ by whatever is connected (see `docs/discovery.md`), so an instance
 * may be running neither, and the picker has to say so rather than offering a
 * choice that will fail.
 */
export interface PipelineRef {
  name: string;
  version: string;
}

/** A whole page: find every staff, then transcribe each one. */
export const PAGE_PIPELINE: PipelineRef = { name: "mzk-page", version: "1" };

/** One image that is already a single cropped staff. */
export const STAFF_PIPELINE: PipelineRef = { name: "mzk-staff", version: "1" };

/** MZK is the Moravian Library — Moravská zemská knihovna — whose work these are for. */
export function isDefaultPipeline(pipeline: PipelineRef): boolean {
  return same(pipeline, PAGE_PIPELINE) || same(pipeline, STAFF_PIPELINE);
}

export function same(a: PipelineRef, b: PipelineRef): boolean {
  return a.name === b.name && a.version === b.version;
}

export function find(listing: PipelineView[], wanted: PipelineRef): PipelineView | undefined {
  return listing.find((pipeline) => same(pipeline, wanted));
}

/**
 * Where this app must upload the visitor's image for a given *Pipeline*.
 *
 * A *Signature* declares *patterns* — `Staves/{s}/image.jpg` — while an
 * execution names *concrete paths*, and the api service rejects an input list
 * that does not fit the pattern with a `400`. So the destination is not a
 * constant: a page-level pipeline wants `image.jpg`, and a staff-level one
 * wants the same bytes at `Staves/1/image.jpg`. Uploading to the wrong one
 * fails at the edge with a legible message, which is better than the
 * alternative but is still a failure a visitor should never see.
 *
 * Filling a slot with `1` is the honest instantiation for this app, because it
 * uploads exactly one image: `{s}` asks for one instance and `{*s}` for a set,
 * and a set of one is a set. The instance name is arbitrary in the Musicorpus
 * Specification, so `1` is a choice rather than a rule.
 *
 * Returns `null` when the app cannot drive the *Pipeline* at all — see
 * `unsupportedReason`.
 */
export function uploadPathFor(signature: SignatureView): string | null {
  const required = signature.input.filter((pattern) => !pattern.endsWith("?"));
  if (required.length !== 1) {
    return null;
  }
  return instantiate(required[0]);
}

/**
 * Why the app cannot offer a *Pipeline*, or `null` if it can.
 *
 * The listing is shown whole — hiding an entry would leave a visitor with a
 * *Pipeline* they were told about elsewhere and cannot find here — so entries
 * this app cannot drive are shown and disabled, with the reason.
 */
export function unsupportedReason(pipeline: PipelineView): string | null {
  const required = pipeline.signature.input.filter((pattern) => !pattern.endsWith("?"));
  if (required.length === 0) {
    return "takes no input file";
  }
  if (required.length > 1) {
    // Something like `image.jpg` plus a `layout.json` an earlier execution had
    // to produce. Reachable by running the earlier pipeline first, from the
    // page screen — not from an upload, which carries one file.
    return "needs more than the one page you upload";
  }
  if (pipeline.instances === 0) {
    // Listed because something announced it moments before going away. An
    // execution would be accepted and then time out with nothing to run it.
    return "nothing is running it just now";
  }
  return null;
}

/**
 * Whether a concrete path is one of the *Files* a pattern describes.
 *
 * The reverse of `instantiate`, and the same rule read the other way: a slot
 * occupies a whole segment, so matching is segment by segment with slots
 * matching anything. `{s}` and `{*s}` are the same here — how *many* instances
 * a pattern admits is not a question about one path.
 *
 * Used to say which of a page's existing *Files* a running execution is about
 * to overwrite, which is worth flagging before it happens rather than
 * explaining afterwards.
 */
export function matchesPattern(path: string, pattern: string): boolean {
  const patternSegments = pattern.replace(/\?$/, "").split("/");
  const pathSegments = path.split("/");
  if (patternSegments.length !== pathSegments.length) {
    return false;
  }
  return patternSegments.every(
    (segment, index) => isSlot(segment) || segment === pathSegments[index],
  );
}

/** Which of these paths the pipeline says it will write. */
export function outputsAmong(paths: string[], signature: SignatureView): string[] {
  return paths.filter((path) => signature.output.some((pattern) => matchesPattern(path, pattern)));
}

/**
 * One way of running a *Pipeline* on the *Files* a page already holds.
 *
 * A pipeline plus a concrete input list, which is what an execution request
 * needs — the api service passes an input list through and does not expand
 * patterns, fan out or gather (see `docs/signatures.md`), so working out which
 * files to name is the caller's job and therefore this app's.
 */
export interface RunOption {
  /** What the choice is called, in the reader's terms. */
  label: string;
  input: string[];
}

/**
 * The ways a *Pipeline* could be run against a page's current contents.
 *
 * Three shapes of *Signature* are handled, which between them cover every
 * example in `docs/signatures.md`:
 *
 * - **No slots at all** — `image.jpg`, or `image.jpg` plus `layout.json`. One
 *   way to run it, if every named *File* is there.
 * - **One required pattern with a single-instance slot** — `Staves/{s}/image.jpg`.
 *   One way to run it *per matching file*, because that is what `{s}` means:
 *   one instance per execution. A page of nine staves offers nine runs.
 * - **One required pattern with a set slot** — `Staves/{*}/transcription.musicxml`.
 *   One way to run it, over the whole set at once.
 *
 * Anything else — several patterns whose slots would have to be bound to each
 * other — is refused with a reason rather than guessed at. Binding slots across
 * patterns is the fan-out that the api service deliberately does not do, and
 * doing it here would be inventing a policy for partial failure that nothing
 * else in Musibot has.
 */
export function runOptionsFor(
  pipeline: PipelineView,
  files: string[],
): { options: RunOption[]; reason: string | null } {
  if (pipeline.instances === 0) {
    return { options: [], reason: "nothing is running it just now" };
  }

  const required = pipeline.signature.input.filter((pattern) => !pattern.endsWith("?"));
  if (required.length === 0) {
    return { options: [], reason: "takes no input file" };
  }

  const slotted = required.filter(hasSlot);

  if (slotted.length === 0) {
    const missing = required.filter((pattern) => !files.includes(pattern));
    if (missing.length > 0) {
      return { options: [], reason: `needs ${missing.join(", ")}` };
    }
    return { options: [{ label: required.join(", "), input: required }], reason: null };
  }

  if (required.length > 1) {
    return { options: [], reason: "needs several files matched to each other" };
  }

  const pattern = required[0];
  const matching = files.filter((path) => matchesPattern(path, pattern)).sort(byInstance);
  if (matching.length === 0) {
    return { options: [], reason: `no file matches ${pattern}` };
  }

  // A set slot takes every instance in one execution; a single-instance slot
  // takes one, so each match is its own way to run it.
  if (isSetPattern(pattern)) {
    return {
      options: [{ label: `all ${matching.length} of ${pattern}`, input: matching }],
      reason: null,
    };
  }
  return { options: matching.map((path) => ({ label: path, input: [path] })), reason: null };
}

function hasSlot(pattern: string): boolean {
  return pattern.split("/").some(isSlot);
}

/** `{*}` and `{*name}` mean every instance; `{}` and `{name}` mean one. */
function isSetPattern(pattern: string): boolean {
  return pattern.split("/").some((segment) => isSlot(segment) && segment.startsWith("{*"));
}

function byInstance(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true });
}

/** A pattern with its slots filled in — `Staves/{s}/image.jpg` → `Staves/1/image.jpg`. */
function instantiate(pattern: string): string {
  return pattern
    .split("/")
    .map((segment) => (isSlot(segment) ? "1" : segment))
    .join("/");
}

/**
 * A slot occupies a whole path segment, by definition — `image.{s}.jpg` is not
 * a slot and is not allowed to be one. See `docs/signatures.md`.
 */
function isSlot(segment: string): boolean {
  return segment.startsWith("{") && segment.endsWith("}");
}
