import Box from "@mui/material/Box";
import { Link as RouterLink } from "react-router";

import * as paths from "../paths";
import { useSession } from "../session/useSession";
import { cuni, mono, paper } from "../theme";

/**
 * "3 pages this session · All pages →", floating at the bottom right.
 *
 * Absent, not empty, for a visitor who has uploaded nothing — the landing page
 * of a first visit should say nothing about sessions, because there is nothing
 * to say and the word would only raise a question the page then has to answer.
 *
 * It is the only element in the design that floats over the page rather than
 * sitting in it, which is the point: it is a way back to work in progress, and
 * work in progress does not belong in the reading order of a pitch.
 */
export default function SessionPill() {
  const { pages } = useSession();

  if (pages.length === 0) {
    return null;
  }

  return (
    <Box
      component={RouterLink}
      to={paths.SESSION}
      sx={{
        position: "fixed",
        right: 24,
        bottom: 24,
        display: "flex",
        alignItems: "center",
        gap: 1.25,
        px: 2,
        py: 1.375,
        border: `1px solid ${paper["300"]}`,
        borderRadius: 2,
        bgcolor: paper["050"],
        textDecoration: "none",
        "&:hover": { borderColor: paper["400"] },
      }}
    >
      <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: cuni.red }} />
      <Box sx={{ fontWeight: 600, fontSize: "0.8125rem", lineHeight: 1, color: paper["900"] }}>
        {pages.length === 1 ? "1 page this session" : `${pages.length} pages this session`}
      </Box>
      <Box sx={{ fontFamily: mono, fontSize: "0.75rem", lineHeight: 1, color: paper["500"] }}>
        All pages →
      </Box>
    </Box>
  );
}
