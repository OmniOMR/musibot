import Box from "@mui/material/Box";

import { paper } from "../../theme";
import type { SampleSheet } from "./samples";

/**
 * A sample page, drawn rather than photographed.
 *
 * There are no sample JPEGs in the repository yet, and this is what stands in
 * for them — the same stand-in the design file used: ruled lines at the density
 * and angle that say which kind of page this is. It reads as "a page of music"
 * at 76 pixels tall, which is all a thumbnail has to do, and it is unmistakably
 * not a photograph of anything, which is the point. A placeholder that looked
 * real would ship unnoticed.
 *
 * Delete this when `public/samples/` has the four scans in it.
 */

/** One-pixel rules every `gap`, tilted by `angle`. A page of staves, from afar. */
function ruled(angle: string, gap: string): string {
  return `repeating-linear-gradient(${angle}${paper["700"]} 0 1px, transparent 1px ${gap})`;
}

const ART = {
  printed: { width: 34, height: 56, background: ruled("", "5px"), opacity: 0.5 },
  handwritten: { width: 34, height: 56, background: ruled("115deg, ", "6px"), opacity: 0.45 },
  staff: { width: 72, height: 18, background: ruled("", "5px"), opacity: 0.5 },
  photo: {
    width: 38,
    height: 52,
    background: ruled("94deg, ", "5px"),
    opacity: 0.4,
    transform: "rotate(-4deg)",
  },
};

export default function SampleArt({ art }: { art: SampleSheet["art"] }) {
  return <Box aria-hidden sx={ART[art]} />;
}
