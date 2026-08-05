import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import ButtonBase from "@mui/material/ButtonBase";
import Dialog from "@mui/material/Dialog";
import Typography from "@mui/material/Typography";
import { useMemo, useState } from "react";

import { startExecution } from "../../api/client";
import { ApiError, RateLimited } from "../../api/errors";
import type { FileView, PipelineView } from "../../api/types";
import { runOptionsFor, type RunOption } from "../../pipelines";
import { cuni, mono, paper, serif } from "../../theme";

/**
 * Run another *Pipeline* on a page that already has one.
 *
 * A secondary action, and mostly for somebody developing a model: try a second
 * pipeline against the same scan, or run one model on its own to see what it
 * does with a staff the first pipeline cut out. It is also the reason the file
 * list is not grouped by execution — once a page can be read twice, a *File*
 * belongs to the page rather than to the run that happened to write it.
 *
 * What can be offered is decided by matching each *Pipeline's* *Signature*
 * against the *Files* the page actually holds, because the api service passes
 * an input list through and expands nothing: whatever is named here is what
 * runs. A pipeline that could be run several ways — one per staff — is listed
 * once per way, since choosing the staff is the whole of the choice.
 */
export default function RunPipelineDialog({
  pageId,
  token,
  pipelines,
  files,
  onClose,
  onStarted,
}: {
  pageId: string;
  token: string;
  pipelines: PipelineView[];
  files: FileView[];
  onClose: () => void;
  onStarted: () => void;
}) {
  const [chosen, setChosen] = useState<{ pipeline: PipelineView; option: RunOption } | null>(null);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const paths = useMemo(() => files.map((file) => file.path), [files]);
  const entries = useMemo(
    () => pipelines.map((pipeline) => ({ pipeline, ...runOptionsFor(pipeline, paths) })),
    [pipelines, paths],
  );

  async function run() {
    if (chosen === null) {
      return;
    }
    setStarting(true);
    setProblem(null);
    try {
      await startExecution(token, pageId, {
        pipeline_name: chosen.pipeline.name,
        pipeline_version: chosen.pipeline.version,
        input: chosen.option.input,
      });
      onStarted();
      onClose();
    } catch (error) {
      setProblem(messageFor(error));
      setStarting(false);
    }
  }

  return (
    <Dialog
      open
      onClose={starting ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      slotProps={{
        paper: {
          variant: "outlined",
          sx: { bgcolor: paper["050"], borderColor: paper["300"], borderRadius: 2 },
        },
      }}
    >
      <Box sx={{ px: 3.75, pt: 3.25, pb: 1.5 }}>
        <Typography
          component="h2"
          sx={{
            fontFamily: serif,
            fontWeight: 600,
            fontSize: "1.375rem",
            lineHeight: 1.2,
            color: paper["950"],
          }}
        >
          Run another pipeline
        </Typography>
        <Typography
          sx={{ mt: 0.75, fontSize: "0.84375rem", lineHeight: 1.55, color: paper["600"] }}
        >
          On the files this page already holds. A pipeline that could run on several of them is
          listed once for each.
        </Typography>
      </Box>

      <Box sx={{ px: 3.75, maxHeight: 340, overflow: "auto" }}>
        {entries.length === 0 && (
          <Typography sx={{ py: 2, fontSize: "0.84375rem", color: paper["600"] }}>
            This instance is announcing no pipelines just now.
          </Typography>
        )}

        {entries.map(({ pipeline, options, reason }) => (
          <Box key={`${pipeline.name}@${pipeline.version}`} sx={{ mb: 1.75 }}>
            <Box
              sx={{
                fontFamily: mono,
                fontSize: "0.78125rem",
                lineHeight: 1.4,
                color: reason === null ? paper["900"] : paper["500"],
              }}
            >
              {pipeline.name}{" "}
              <Box component="span" sx={{ color: paper["500"] }}>
                v{pipeline.version}
              </Box>
              {pipeline.implicit && (
                <Box component="span" sx={{ ml: 1, fontFamily: "inherit", color: paper["500"] }}>
                  implicit
                </Box>
              )}
            </Box>

            {reason !== null ? (
              <Typography sx={{ mt: 0.25, fontSize: "0.75rem", color: paper["500"] }}>
                {reason}
              </Typography>
            ) : (
              <Box sx={{ mt: 0.75, display: "flex", flexDirection: "column", gap: 0.5 }}>
                {options.map((option) => {
                  const selected =
                    chosen?.pipeline === pipeline && chosen.option.label === option.label;
                  return (
                    <ButtonBase
                      key={option.label}
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setChosen({ pipeline, option })}
                      sx={{
                        justifyContent: "flex-start",
                        textAlign: "left",
                        px: 1.25,
                        py: 0.875,
                        borderRadius: 1,
                        border: `1px solid ${selected ? cuni.red : paper["200"]}`,
                        bgcolor: selected ? paper["150"] : paper["100"],
                        fontFamily: mono,
                        fontSize: "0.75rem",
                        color: paper["900"],
                        "&:hover": { bgcolor: paper["150"] },
                      }}
                    >
                      {option.label}
                    </ButtonBase>
                  );
                })}
              </Box>
            )}
          </Box>
        ))}
      </Box>

      {problem !== null && (
        <Typography
          role="alert"
          sx={{
            mx: 3.75,
            mt: 1,
            px: 1.75,
            py: 1.25,
            border: `1px solid ${paper["300"]}`,
            borderRadius: 1.5,
            bgcolor: paper["100"],
            fontSize: "0.84375rem",
            lineHeight: 1.55,
            color: paper["900"],
          }}
        >
          {problem}
        </Typography>
      )}

      <Box
        sx={{
          mt: 2,
          px: 3.75,
          py: 2,
          borderTop: `1px solid ${paper["200"]}`,
          display: "flex",
          gap: 1.75,
        }}
      >
        <Button
          variant="contained"
          disabled={chosen === null || starting}
          onClick={() => void run()}
          sx={{ fontSize: "0.875rem", px: 2.25, py: 1.25 }}
        >
          {starting ? "Starting…" : "Run"}
        </Button>
        <Button
          variant="outlined"
          disabled={starting}
          onClick={onClose}
          sx={{ fontSize: "0.875rem", px: 2, py: 1.25 }}
        >
          Cancel
        </Button>
      </Box>
    </Dialog>
  );
}

function messageFor(error: unknown): string {
  if (error instanceof RateLimited) {
    return error.retryAfterSeconds === null
      ? "Musibot is at its public limit just now. Deleting a page you have finished with will make room."
      : `Musibot is at its public limit just now. Try again in about ${Math.ceil(error.retryAfterSeconds / 60)} minutes.`;
  }
  if (error instanceof ApiError) {
    return error.detail ?? error.message;
  }
  return "Something went wrong talking to Musibot.";
}
