import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";

import { mono, paper } from "../../theme";
import { SAMPLE_DRAG_TYPE, SAMPLE_SHEETS, type SampleSheet } from "./samples";

/**
 * "Nothing to hand? Take one of ours."
 *
 * Each thumbnail is both a button and a drag source. The design asks for both
 * and expects almost everyone to click — the drag exists because a drop zone
 * sits directly above and inviting a drag onto it is the one gesture the layout
 * suggests on its own.
 */
export default function SampleSheets({ onChoose }: { onChoose: (sample: SampleSheet) => void }) {
  return (
    <Box sx={{ mt: 2.75, pt: 2.25, borderTop: `1px solid ${paper["200"]}` }}>
      <Box
        sx={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: 1.25,
        }}
      >
        <Typography
          component="h2"
          sx={{ fontWeight: 600, fontSize: "0.8125rem", lineHeight: 1.3, color: paper["950"] }}
        >
          Nothing to hand? Take one of ours
        </Typography>
        <Typography sx={{ fontSize: "0.78125rem", color: paper["500"] }}>
          drag one up, or click it
        </Typography>
      </Box>

      <Box
        sx={{
          mt: 1.5,
          display: "grid",
          gridTemplateColumns: { xs: "repeat(2, 1fr)", sm: "repeat(4, 1fr)" },
          gap: 1.5,
        }}
      >
        {SAMPLE_SHEETS.map((sample) => (
          <ButtonBase
            key={sample.id}
            draggable
            onDragStart={(event: React.DragEvent) => {
              event.dataTransfer.setData(SAMPLE_DRAG_TYPE, sample.id);
              event.dataTransfer.effectAllowed = "copy";
            }}
            onClick={() => onChoose(sample)}
            sx={{
              display: "block",
              textAlign: "left",
              borderRadius: 1,
              cursor: "grab",
              "&:hover .sample-thumb": { borderColor: paper["400"] },
              "&:active": { cursor: "grabbing" },
            }}
          >
            <Box
              className="sample-thumb"
              sx={{
                height: 76,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                border: `1px solid ${paper["300"]}`,
                borderRadius: 1,
                // The drop zone's own surface, so the row of samples reads as
                // part of the way in rather than as four white cards stuck
                // underneath it. The scans bring their own white.
                bgcolor: paper["100"],
              }}
            >
              {/* Fitted rather than cropped, and inset rather than bled to the
                  edges: at this size the useful thing a thumbnail says is what
                  shape the page is. A staff crop is a strip and reads as one,
                  which is the distinction the label beside it is making.

                  No alt text. The label and file name below are the button's
                  accessible name already, and a second reading of "printed
                  page" is noise to somebody listening rather than looking. */}
              <Box
                component="img"
                src={sample.thumbnail}
                alt=""
                // Not the drag source. Chrome hands a dragged image over as a
                // file, so grabbing this would upload the four-kilobyte
                // thumbnail instead of the scan it stands for. The drag is the
                // button's, and it carries the sample's id — see
                // `SAMPLE_DRAG_TYPE`.
                draggable={false}
                sx={{ maxHeight: 56, maxWidth: "88%", display: "block" }}
              />
            </Box>
            <Typography
              sx={{
                mt: 0.75,
                fontWeight: 600,
                fontSize: "0.71875rem",
                lineHeight: 1.35,
                color: paper["900"],
              }}
            >
              {sample.label}
            </Typography>
            <Typography
              sx={{
                fontFamily: mono,
                fontSize: "0.65625rem",
                lineHeight: 1.4,
                color: paper["500"],
              }}
            >
              {sample.fileName}
            </Typography>
          </ButtonBase>
        ))}
      </Box>
    </Box>
  );
}
