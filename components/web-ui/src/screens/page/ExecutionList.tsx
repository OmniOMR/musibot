import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";

import type { PipelineExecutionView } from "../../api/types";
import { cuni, mono, paper } from "../../theme";

/**
 * Every *Pipeline Execution* this page has had, in the order they were run.
 *
 * More than one is normal rather than exceptional: a page can be re-read after
 * the first run finishes, which is what a model developer comparing two
 * pipelines does, and is the reason the file list below is not grouped by
 * execution.
 *
 * A running execution gets a spinner and no number. Nothing here may show a
 * percentage: an image-to-sequence model does not know how long its own output
 * will be, so any figure would be invented — and until the SSE stream exists
 * the app cannot see partial progress at all.
 */
export default function ExecutionList({ executions }: { executions: PipelineExecutionView[] }) {
  if (executions.length === 0) {
    return (
      <Box sx={{ px: 2.25, pb: 1.5, fontSize: "0.75rem", color: paper["500"] }}>
        Nothing has been run on this page yet.
      </Box>
    );
  }

  return (
    <>
      {executions.map((execution, index) => (
        <Box
          key={execution.execution_id}
          sx={{
            px: 2.25,
            pb: 1.5,
            pt: index === 0 ? 0.25 : 1.25,
            borderTop: index === 0 ? "none" : `1px solid ${paper["200"]}`,
          }}
        >
          <Box
            sx={{ fontWeight: 600, fontSize: "0.8125rem", lineHeight: 1.3, color: paper["950"] }}
          >
            {execution.pipeline_name}{" "}
            <Box
              component="span"
              sx={{ fontFamily: mono, fontSize: "0.71875rem", color: paper["500"] }}
            >
              v{execution.pipeline_version}
            </Box>
          </Box>
          <Box
            sx={{
              mt: 0.25,
              display: "flex",
              alignItems: "center",
              gap: 0.75,
              fontSize: "0.75rem",
              color: colourOf(execution),
            }}
          >
            {!isFinished(execution) && <CircularProgress size={11} thickness={6} />}
            {statusOf(execution)}
          </Box>
        </Box>
      ))}
    </>
  );
}

function isFinished(execution: PipelineExecutionView): boolean {
  return execution.state === "completed" || execution.state === "failed";
}

/**
 * What the state means, in the visitor's words rather than the service's.
 *
 * A failure says why on the same line: `error` is the one thing a visitor can
 * act on, and hiding it behind "failed" costs them the answer.
 */
function statusOf(execution: PipelineExecutionView): string {
  switch (execution.state) {
    case "queued":
      return "waiting for a worker";
    case "running":
      return "reading";
    case "completed":
      return "read";
    case "failed":
      return execution.error === null ? "failed" : `failed — ${execution.error}`;
    default:
      return execution.state;
  }
}

function colourOf(execution: PipelineExecutionView): string {
  if (execution.state === "failed") {
    return cuni.redDark;
  }
  return execution.state === "completed" ? paper["600"] : paper["700"];
}
