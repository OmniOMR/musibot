import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Typography from "@mui/material/Typography";
import { useRef, useState } from "react";

import { cuni, paper, serif } from "../../theme";
import { ACCEPTED_UPLOAD_TYPES } from "../../upload/prepareUpload";
import { draggedSample, type SampleSheet } from "./samples";

/**
 * Where a page arrives.
 *
 * Drop, choose from the file picker, or drag one of Musibot's own samples up
 * from below. What happens afterwards is not this component's business:
 * nothing here validates, uploads or navigates, and the two callbacks are the
 * seam the upload flow is written behind.
 *
 * A sample is its own callback rather than a `File` because a drag cannot carry
 * one. What is on screen is a thumbnail, and a browser hands a dragged image
 * over as a file — so a sample announces which sample it is and the scan is
 * fetched by name, the same way a click gets it.
 *
 * The dashed border is the one place in the design that is not a hairline, and
 * that is deliberate — a dashed rectangle is the web's idiom for "put something
 * here", and the drop zone is the only element on the page asking to be given
 * something.
 */
export default function DropZone({
  onChoose,
  onChooseSample,
}: {
  onChoose: (file: File) => void;
  /** One of Musibot's own samples, dragged up from the row below. */
  onChooseSample: (sample: SampleSheet) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [isOver, setOver] = useState(false);

  function firstFileOf(transfer: DataTransfer): File | undefined {
    return transfer.files.item(0) ?? undefined;
  }

  return (
    <Box>
      <Box
        onDragOver={(event) => {
          // Without cancelling the drag-over the browser refuses the drop and
          // navigates to the file instead, which loses the app.
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(event) => {
          event.preventDefault();
          setOver(false);

          // One of ours first. A sample carries its id and not its picture, so
          // that the scan is fetched by name rather than the thumbnail being
          // uploaded — a browser will hand a dragged image over as a file, and
          // that file is four kilobytes of nothing.
          const sample = draggedSample(event.dataTransfer);
          if (sample !== undefined) {
            onChooseSample(sample);
            return;
          }

          const file = firstFileOf(event.dataTransfer);
          if (file) {
            onChoose(file);
          }
        }}
        sx={{
          border: `2px dashed ${isOver ? cuni.red : paper["300"]}`,
          borderRadius: 1.5,
          bgcolor: isOver ? paper["150"] : paper["100"],
          px: 3.5,
          py: 5.5,
          textAlign: "center",
          transition: "background-color 120ms, border-color 120ms",
        }}
      >
        <Typography
          component="h2"
          sx={{
            fontFamily: serif,
            fontWeight: 600,
            fontSize: "1.25rem",
            lineHeight: 1.3,
            color: paper["950"],
          }}
        >
          Drop a page here
        </Typography>
        <Typography sx={{ mt: 0.75, fontSize: "0.875rem", color: paper["600"] }}>
          JPEG, PNG, BMP, TIFF or PDF · one page at a time
        </Typography>

        <Button
          variant="contained"
          onClick={() => input.current?.click()}
          sx={{ mt: 2.5, fontSize: "0.9375rem", px: 2.5, py: 1.5 }}
        >
          Choose a file
        </Button>

        <Box
          component="input"
          ref={input}
          type="file"
          accept={ACCEPTED_UPLOAD_TYPES.join(",")}
          sx={{ display: "none" }}
          onChange={(event: React.ChangeEvent<HTMLInputElement>) => {
            const file = event.target.files?.item(0);
            if (file) {
              onChoose(file);
            }
            // Cleared so that choosing the same file twice in a row still
            // fires — the input reports a change, not a selection.
            event.target.value = "";
          }}
        />
      </Box>

      <Typography sx={{ mt: 1.5, fontSize: "0.8125rem", lineHeight: 1.5, color: paper["600"] }}>
        No account needed. Your page and its results are deleted after about an hour.
      </Typography>
    </Box>
  );
}
