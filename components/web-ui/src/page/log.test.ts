import { describe, expect, it } from "vitest";

import type { LogLineView } from "../api/types";
import { toLogLine } from "./log";

function view(overrides: Partial<LogLineView> = {}): LogLineView {
  return {
    execution_id: 1,
    seconds: 1.3,
    kind: "worker",
    source: "staff-detector",
    level: "info",
    message: "7 staves",
    ...overrides,
  };
}

describe("a log line", () => {
  it("is stamped with seconds into its execution", () => {
    // Not a time of day: what a reader is judging is how long a step took.
    expect(toLogLine(view({ seconds: 1.34 })).at).toBe("01.3");
    expect(toLogLine(view({ seconds: 12.5 })).at).toBe("12.5");
    expect(toLogLine(view({ seconds: 0 })).at).toBe("00.0");
  });

  it("names the model that printed it", () => {
    expect(toLogLine(view()).text).toBe("staff-detector: 7 staves");
  });

  it("leaves the service's own lines unattributed", () => {
    // "api: completed in 1.2s" would be noise; these lines are the story of
    // the execution rather than something a model said.
    expect(toLogLine(view({ kind: "api", source: "api", message: "completed in 1.2s" })).text).toBe(
      "completed in 1.2s",
    );
  });

  it("colours an error and nothing else", () => {
    expect(toLogLine(view({ level: "error" })).tone).toBe("error");
    // A Model's stderr is forwarded as `warning`, and libraries write perfectly
    // ordinary chatter there.
    expect(toLogLine(view({ level: "warning" })).tone).toBe("normal");
    expect(toLogLine(view({ level: "info" })).tone).toBe("normal");
  });
});
