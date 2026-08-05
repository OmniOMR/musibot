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
