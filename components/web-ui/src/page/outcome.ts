import type { FileView, PipelineExecutionView, PipelineView } from "../api/types";
import { find, matchesPattern } from "../pipelines";

/**
 * A *Pipeline Execution* that finished successfully and produced nothing.
 *
 * The unhappiest outcome Musibot has, because nothing about it looks like a
 * failure: the execution says `completed`, no error is reported, and the page
 * simply has no more files than it started with. A visitor left to work that
 * out from an unchanged file list will conclude the service is broken, when
 * what actually happened is that the recognition ran and found no music —
 * usually a photograph taken at an angle, or one scanned too small.
 *
 * It is read from the *Pipeline's* own declared outputs rather than from a
 * count of files, because "produced nothing" only means anything relative to
 * what the pipeline said it would produce. Optional outputs are ignored: a
 * pipeline that may or may not write a file has said so, and its absence is not
 * evidence of anything.
 *
 * Returns `null` whenever the question cannot be answered — an unfinished
 * execution, a pipeline no longer in the listing, one that declares no required
 * output. Saying nothing is right there: a false "nothing was found" on a page
 * that has results is worse than no message at all.
 */
export function finishedEmpty(
  executions: PipelineExecutionView[],
  pipelines: PipelineView[],
  files: FileView[],
): PipelineExecutionView | null {
  const last = executions.at(-1);
  if (last === undefined || last.state !== "completed") {
    return null;
  }

  const pipeline = find(pipelines, {
    name: last.pipeline_name,
    version: last.pipeline_version,
  });
  if (pipeline === undefined) {
    return null;
  }

  const promised = pipeline.signature.output.filter((pattern) => !pattern.endsWith("?"));
  if (promised.length === 0) {
    return null;
  }

  const produced = files.some((file) =>
    promised.some((pattern) => matchesPattern(file.path, pattern)),
  );
  return produced ? null : last;
}
