import { describe, expect, it } from "vitest";

import type { PipelineView } from "./api/types";
import {
  find,
  PAGE_PIPELINE,
  runOptionsFor,
  STAFF_PIPELINE,
  unsupportedReason,
  uploadPathFor,
} from "./pipelines";

function pipeline(overrides: Partial<PipelineView> = {}): PipelineView {
  return {
    name: "a-pipeline",
    version: "1",
    signature: { input: ["image.jpg"], output: ["transcription.musicxml"] },
    implicit: false,
    orchestrators: [],
    instances: 1,
    ...overrides,
  };
}

describe("uploadPathFor", () => {
  it("leaves a slot-free pattern alone", () => {
    expect(uploadPathFor({ input: ["image.jpg"], output: [] })).toBe("image.jpg");
  });

  it("fills a slot, so a staff-level pipeline gets a staff-level path", () => {
    // The failure this prevents: uploading to `image.jpg` and naming it as the
    // input of a `Staves/{staff}/image.jpg` pipeline, which the api service
    // rejects with a 400 for not fitting the signature.
    expect(uploadPathFor({ input: ["Staves/{staff}/image.jpg"], output: [] })).toBe(
      "Staves/1/image.jpg",
    );
  });

  it("treats a set slot as a set of one, since one image is what is uploaded", () => {
    expect(uploadPathFor({ input: ["Staves/{*s}/image.jpg"], output: [] })).toBe(
      "Staves/1/image.jpg",
    );
  });

  it("ignores optional inputs when counting what is required", () => {
    expect(uploadPathFor({ input: ["image.jpg", "layout.json?"], output: [] })).toBe("image.jpg");
  });

  it("refuses a pipeline needing more than the one uploaded file", () => {
    expect(uploadPathFor({ input: ["image.jpg", "layout.json"], output: [] })).toBeNull();
  });

  it("refuses a pipeline that reads nothing", () => {
    expect(uploadPathFor({ input: [], output: [] })).toBeNull();
  });

  it("does not mistake a brace inside a segment for a slot", () => {
    // A slot occupies a whole path segment by definition — see
    // docs/signatures.md. Anything else is a literal name.
    expect(uploadPathFor({ input: ["image.{s}.jpg"], output: [] })).toBe("image.{s}.jpg");
  });
});

describe("unsupportedReason", () => {
  it("passes a pipeline this app can drive", () => {
    expect(unsupportedReason(pipeline())).toBeNull();
  });

  it("names a pipeline needing a file an earlier execution has to produce", () => {
    const needsLayout = pipeline({
      signature: { input: ["image.jpg", "layout.json"], output: [] },
    });

    expect(unsupportedReason(needsLayout)).toBe("needs more than the one page you upload");
  });

  it("names a pipeline nothing is running", () => {
    // Listed because something announced it moments before going away. An
    // execution would be accepted and then time out with nothing to run it.
    expect(unsupportedReason(pipeline({ instances: 0 }))).toBe("nothing is running it just now");
  });
});

describe("runOptionsFor", () => {
  const PAGE_FILES = ["image.jpg", "layout.json"];
  const STAFF_FILES = [
    "image.jpg",
    "Staves/1/image.jpg",
    "Staves/2/image.jpg",
    "Staves/10/image.jpg",
  ];

  it("offers one run for a pipeline whose inputs name themselves", () => {
    const splitter = pipeline({
      signature: { input: ["image.jpg", "layout.json"], output: ["Staves/{*}/image.jpg"] },
    });

    expect(runOptionsFor(splitter, PAGE_FILES).options).toEqual([
      { label: "image.jpg, layout.json", input: ["image.jpg", "layout.json"] },
    ]);
  });

  it("says which file is missing rather than offering a run that would fail", () => {
    const splitter = pipeline({ signature: { input: ["image.jpg", "layout.json"], output: [] } });

    expect(runOptionsFor(splitter, ["image.jpg"]).reason).toBe("needs layout.json");
  });

  it("offers one run per instance for a single-instance slot", () => {
    // `{s}` means one instance per execution — see docs/signatures.md — so a
    // page of three staves is three separate ways to run it, and choosing
    // which staff is the whole of the choice.
    const transcriber = pipeline({
      signature: {
        input: ["Staves/{s}/image.jpg"],
        output: ["Staves/{s}/transcription.musicxml"],
      },
    });

    expect(runOptionsFor(transcriber, STAFF_FILES).options).toEqual([
      { label: "Staves/1/image.jpg", input: ["Staves/1/image.jpg"] },
      { label: "Staves/2/image.jpg", input: ["Staves/2/image.jpg"] },
      { label: "Staves/10/image.jpg", input: ["Staves/10/image.jpg"] },
    ]);
  });

  it("offers one run over the whole set for a set slot", () => {
    // A joiner has to see every staff at once to decide the grouping, which is
    // what `{*}` declares.
    const joiner = pipeline({
      signature: {
        input: ["Staves/{*}/transcription.musicxml"],
        output: ["Systems/{*}/transcription.musicxml"],
      },
    });
    const files = ["Staves/1/transcription.musicxml", "Staves/2/transcription.musicxml"];

    expect(runOptionsFor(joiner, files).options).toEqual([
      { label: "all 2 of Staves/{*}/transcription.musicxml", input: files },
    ]);
  });

  it("refuses to guess when slots would have to be bound to each other", () => {
    // Binding a slot across patterns is the fan-out the api service
    // deliberately does not do; inventing it here would mean inventing a
    // policy for partial failure that nothing else in Musibot has.
    const awkward = pipeline({
      signature: { input: ["Staves/{s}/image.jpg", "Staves/{s}/layout.json"], output: [] },
    });

    expect(runOptionsFor(awkward, STAFF_FILES).reason).toBe(
      "needs several files matched to each other",
    );
  });

  it("has nothing to offer when no file matches the pattern", () => {
    const transcriber = pipeline({ signature: { input: ["Staves/{s}/image.jpg"], output: [] } });

    expect(runOptionsFor(transcriber, ["image.jpg"]).reason).toBe(
      "no file matches Staves/{s}/image.jpg",
    );
  });

  it("offers nothing for a pipeline nothing is running", () => {
    expect(runOptionsFor(pipeline({ instances: 0 }), PAGE_FILES).options).toEqual([]);
  });

  it("ignores an optional input when deciding what is needed", () => {
    const forgiving = pipeline({ signature: { input: ["image.jpg", "layout.json?"], output: [] } });

    expect(runOptionsFor(forgiving, ["image.jpg"]).options).toEqual([
      { label: "image.jpg", input: ["image.jpg"] },
    ]);
  });
});

describe("the two defaults", () => {
  it("are found in a listing by name and version together", () => {
    const listing = [
      pipeline({ name: "mzk-page", version: "1" }),
      pipeline({ name: "mzk-staff", version: "2" }),
    ];

    expect(find(listing, PAGE_PIPELINE)?.name).toBe("mzk-page");
    // Right name, wrong version: not the pipeline this app means.
    expect(find(listing, STAFF_PIPELINE)).toBeUndefined();
  });

  it("are absent from a listing that does not announce them", () => {
    const listing = [pipeline({ name: "zod-bw-auth-ft", version: "2026-07-20-153411-e40" })];

    expect(find(listing, PAGE_PIPELINE)).toBeUndefined();
    expect(find(listing, STAFF_PIPELINE)).toBeUndefined();
  });
});
