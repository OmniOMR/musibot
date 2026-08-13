import { describe, expect, it } from "vitest";

import type { PipelineExecutionView } from "../api/types";
import { replaceExecution } from "./usePageState";

function execution(id: number, state: string): PipelineExecutionView {
  return {
    execution_id: id,
    pipeline_name: "hello-world",
    pipeline_version: "1.0.0",
    input: ["image.jpg"],
    state,
    error: null,
  };
}

describe("folding a result into what is shown", () => {
  it("settles the execution it names", () => {
    const shown = [execution(1, "running"), execution(2, "running")];

    const after = replaceExecution(shown, execution(1, "completed"));

    expect(after.map((e) => [e.execution_id, e.state])).toEqual([
      [1, "completed"],
      [2, "running"],
    ]);
  });

  it("keeps an execution it has never seen", () => {
    // A result can arrive before the fetch that would have introduced it. A
    // finished execution nobody displays is worse than one that turns up
    // already in its final state.
    const after = replaceExecution([], execution(3, "failed"));

    expect(after).toEqual([execution(3, "failed")]);
  });

  it("does not reorder the ones it keeps", () => {
    const shown = [execution(1, "running"), execution(2, "running"), execution(3, "running")];

    const after = replaceExecution(shown, execution(2, "completed"));

    expect(after.map((e) => e.execution_id)).toEqual([1, 2, 3]);
  });
});
