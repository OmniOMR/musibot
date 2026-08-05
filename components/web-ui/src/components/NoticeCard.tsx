import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import type { ReactNode } from "react";

import { paper, serif } from "../theme";

/**
 * When something has gone wrong, or has finished and found nothing.
 *
 * One shape for all of them, because they have one job: say what happened in a
 * sentence, say what caused it if that is knowable, and offer the thing a
 * visitor would do next. The design draws three of these — a file that is not a
 * JPEG, an allowance that is spent, a reading that found nothing — and they
 * differ only in their words.
 *
 * No icon, no red panel, no exclamation mark. A refused upload is not an
 * emergency, and a page dressed as one teaches a visitor to stop reading the
 * words. The red in this app fills the button somebody is meant to press, and
 * spending it on the border of a warning would leave nothing to say "press
 * here" with.
 */
export default function NoticeCard({
  title,
  children,
  actions,
}: {
  title: string;
  children: ReactNode;
  /** What to do next. The first is the one to press. */
  actions?: ReactNode;
}) {
  return (
    <Paper
      variant="outlined"
      role="alert"
      sx={{ borderColor: paper["300"], bgcolor: paper["050"], px: 2.75, py: 2.5 }}
    >
      <Typography
        component="h2"
        sx={{
          fontFamily: serif,
          fontWeight: 600,
          fontSize: "1.0625rem",
          lineHeight: 1.3,
          color: paper["950"],
        }}
      >
        {title}
      </Typography>

      <Box
        sx={{
          mt: 0.875,
          fontSize: "0.84375rem",
          lineHeight: 1.6,
          color: paper["700"],
          "& a": { color: undefined },
        }}
      >
        {children}
      </Box>

      {actions !== undefined && (
        <Box sx={{ mt: 1.75, display: "flex", flexWrap: "wrap", gap: 1.25 }}>{actions}</Box>
      )}
    </Paper>
  );
}
