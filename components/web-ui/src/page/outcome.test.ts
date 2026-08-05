import { describe, expect, it } from "vitest";

import type { FileView, PipelineExecutionView, PipelineView } from "../api/types";
import { finishedEmpty } from "./outcome";

function file(path: string): FileView {
  return { path, size: 10, last_modified: "2026-08-05T12:00:00Z" };
}

function execution(overrides: Partial<PipelineExecutionView> = {}): PipelineExecutionView {
  return {
    execution_id: 1,
    pipeline_name: "reader",
    pipeline_version: "1",
    input: ["image.jpg"],
    state: "completed",
    error: null,
    ...overrides,
  };
}

function pipeline(output: string[]): PipelineView {
  return {
    name: "reader",
    version: "1",
    signature: { input: ["image.jpg"], output },
    implicit: false,
    orchestrators: [],
    instances: 1,
  };
}

const READER = [pipeline(["Staves/{*}/image.jpg", "transcription.musicxml"])];

describe("finishedEmpty", () => {
  it("reports an execution that succeeded and wrote none of its outputs", () => {
    // The unhappiest outcome Musibot has: `completed`, no error, and a file
    // list that has not changed. Nothing about it looks like a failure.
    expect(finishedEmpty([execution()], READER, [file("image.jpg")])).not.toBeNull();
  });

  it("says nothing when an output was written", () => {
    const files = [file("image.jpg"), file("transcription.musicxml")];

    expect(finishedEmpty([execution()], READER, files)).toBeNull();
  });

  it("says nothing when even one instance of a set output was written", () => {
    const files = [file("image.jpg"), file("Staves/1/image.jpg")];

    expect(finishedEmpty([execution()], READER, files)).toBeNull();
  });

  it("says nothing while the execution is still running", () => {
    expect(
      finishedEmpty([execution({ state: "running" })], READER, [file("image.jpg")]),
    ).toBeNull();
  });

  it("leaves a failure to speak for itself", () => {
    // A failed execution already says why on its own row; this message is for
    // the case that reports success.
    const failed = execution({ state: "failed", error: "no staves found" });

    expect(finishedEmpty([failed], READER, [file("image.jpg")])).toBeNull();
  });

  it("says nothing when the pipeline is no longer in the listing", () => {
    // Without its signature there is no way to know what it promised, and a
    // false "nothing was found" is worse than no message at all.
    expect(finishedEmpty([execution()], [], [file("image.jpg")])).toBeNull();
  });

  it("says nothing when every declared output was optional", () => {
    // A pipeline that may or may not write a file has said so, and its absence
    // is not evidence of anything.
    const maybe = [pipeline(["layout.json?"])];

    expect(finishedEmpty([execution()], maybe, [file("image.jpg")])).toBeNull();
  });

  it("judges the last execution, not the first", () => {
    // A second run is usually a correction of the first; if it produced
    // nothing, that is the news.
    const executions = [
      execution({ execution_id: 1 }),
      execution({ execution_id: 2, pipeline_name: "other" }),
    ];
    const listing = [...READER, { ...pipeline(["never-written.json"]), name: "other" }];

    expect(finishedEmpty(executions, listing, [file("transcription.musicxml")])?.execution_id).toBe(
      2,
    );
  });

  it("has nothing to say about a page nothing has run on", () => {
    expect(finishedEmpty([], READER, [file("image.jpg")])).toBeNull();
  });
});
