import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";

import type { PipelineView } from "../../api/types";
import {
  PAGE_PIPELINE,
  same,
  STAFF_PIPELINE,
  unsupportedReason,
  type PipelineRef,
} from "../../pipelines";
import { cuni, mono, paper } from "../../theme";

/**
 * Every *Pipeline* the instance announces, defaults included.
 *
 * Shown whole and never filtered. An entry this app cannot drive from an
 * upload — one needing a *File* an earlier execution has to produce, or one
 * nothing is currently running — is displayed and disabled with the reason,
 * because a *Pipeline* somebody read about elsewhere and cannot find here is
 * worse than one they can see is unavailable.
 *
 * *ImplicitPipelines* are the single-*Model* pipelines Musibot offers for every
 * *Model* it knows about. They are labelled in muted plain text rather than
 * given a badge: they are not a special category to advertise, just a plainer
 * thing to run.
 */
export default function AllPipelines({
  pipelines,
  selected,
  onSelect,
}: {
  pipelines: PipelineView[];
  selected: PipelineRef | null;
  onSelect: (pipeline: PipelineRef) => void;
}) {
  if (pipelines.length === 0) {
    return (
      <Typography sx={{ mt: 1.25, fontSize: "0.78125rem", lineHeight: 1.5, color: paper["500"] }}>
        This instance is announcing no pipelines at all just now.
      </Typography>
    );
  }

  return (
    <>
      <Box
        sx={{
          mt: 1.25,
          border: `1px solid ${paper["200"]}`,
          borderRadius: 1.5,
          bgcolor: paper["100"],
          overflow: "hidden",
        }}
      >
        {pipelines.map((pipeline, index) => {
          const unsupported = unsupportedReason(pipeline);
          const isSelected = selected !== null && same(selected, pipeline);

          return (
            <ButtonBase
              key={`${pipeline.name}@${pipeline.version}`}
              disabled={unsupported !== null}
              onClick={() => onSelect({ name: pipeline.name, version: pipeline.version })}
              sx={{
                width: "100%",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                gap: 1.5,
                textAlign: "left",
                pr: 1.75,
                pl: 1.375,
                py: 1.125,
                borderBottom: index === pipelines.length - 1 ? "none" : `1px solid ${paper["200"]}`,
                // Red marks the selection here as it does on the two options
                // above, but as an edge rather than a full border: a ring round
                // one row of a bordered list reads as a nested box.
                borderLeft: `3px solid ${isSelected ? cuni.red : "transparent"}`,
                bgcolor: isSelected ? paper["000"] : "transparent",
                "&:hover": { bgcolor: paper["150"] },
                "&.Mui-disabled": { opacity: 0.55 },
              }}
            >
              <Box
                sx={{
                  fontFamily: mono,
                  fontSize: "0.78125rem",
                  lineHeight: 1.4,
                  color: paper["900"],
                }}
              >
                {pipeline.name}{" "}
                <Box component="span" sx={{ color: paper["500"] }}>
                  v{pipeline.version}
                </Box>
              </Box>

              <Box
                sx={{
                  fontSize: "0.75rem",
                  lineHeight: 1.3,
                  color: paper["600"],
                  textAlign: "right",
                }}
              >
                {tagFor(pipeline, unsupported)}
              </Box>
            </ButtonBase>
          );
        })}
      </Box>

      <Typography sx={{ mt: 1, fontSize: "0.78125rem", lineHeight: 1.5, color: paper["500"] }}>
        Implicit pipelines run one model on its own. Useful for checking a model; not what you want
        for a page.
      </Typography>
    </>
  );
}

/** The one thing worth saying about an entry, in order of what matters most. */
function tagFor(pipeline: PipelineView, unsupported: string | null): string {
  if (unsupported !== null) {
    return unsupported;
  }
  if (same(pipeline, PAGE_PIPELINE)) {
    return "default for tall pages";
  }
  if (same(pipeline, STAFF_PIPELINE)) {
    return "default for wide images";
  }
  return pipeline.implicit ? "implicit" : "";
}
