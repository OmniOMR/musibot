import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import Typography from "@mui/material/Typography";

import { mono, paper } from "../../theme";
import SampleArt from "./SampleArt";
import { SAMPLE_SHEETS, type SampleSheet } from "./samples";

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
                // White, because a thumbnail is a scan held up off the sheet —
                // the one place the top of the ramp is right.
                bgcolor: sample.art === "photo" ? paper["100"] : paper["000"],
              }}
            >
              <SampleArt art={sample.art} />
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
