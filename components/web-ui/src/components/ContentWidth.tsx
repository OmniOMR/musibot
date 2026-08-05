import Box from "@mui/material/Box";
import type { ReactNode } from "react";

/**
 * The column the page's content is set in.
 *
 * The app is full-bleed — the ivory runs edge to edge and there is no card,
 * frame or sheet around it — but text set across a 2560-pixel monitor is
 * unreadable, so the *content* is bounded even though the page is not. That
 * distinction is the whole point of this component: put it *inside* a
 * full-width band rather than around one, so a section's hairline rule still
 * spans the window while the words stop where the eye does.
 */
export default function ContentWidth({
  maxWidth = 1120,
  children,
}: {
  /** How wide the column may grow. The design's landing layout is 1080px. */
  maxWidth?: number;
  children: ReactNode;
}) {
  return <Box sx={{ maxWidth, mx: "auto", px: { xs: 3, md: 5 } }}>{children}</Box>;
}
