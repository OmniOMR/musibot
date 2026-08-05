import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import { Link as RouterLink } from "react-router";

import { formatRemaining } from "../../page/expiry";
import * as paths from "../../paths";
import { mono, paper, serif } from "../../theme";

/**
 * The bar across the top of a page's screen.
 *
 * Not `SiteHeader`. This one identifies the page rather than the site, and the
 * three things on the right are the three things a visitor needs from here: how
 * long they have, the way back to their other pages, and their results.
 *
 * The expiry is stated in words and rounded to minutes. It is the single most
 * important fact on the screen — nothing here survives the hour, and a visitor
 * who does not know that will lose work — but a ticking countdown would turn a
 * generous hour into a deadline to watch.
 */
export default function PageHeader({
  pageId,
  fileName,
  expiresAt,
  now,
  onDownloadResults,
  downloadable,
}: {
  pageId: string;
  fileName: string | null;
  expiresAt: Date | null;
  now: Date;
  onDownloadResults: () => void;
  /** How many *Files* "Download results" would fetch. Zero disables it. */
  downloadable: number;
}) {
  return (
    <Box
      component="header"
      sx={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        flexWrap: "wrap",
        gap: 2,
        px: 2.5,
        py: 1.5,
        borderBottom: `1px solid ${paper["200"]}`,
        bgcolor: paper["050"],
      }}
    >
      <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.75, minWidth: 0 }}>
        <Box
          component={RouterLink}
          to={paths.LANDING}
          sx={{
            fontFamily: serif,
            fontWeight: 600,
            fontSize: "1rem",
            lineHeight: 1,
            color: paper["950"],
            textDecoration: "none",
          }}
        >
          Musibot
        </Box>
        <Box
          sx={{
            fontFamily: mono,
            fontSize: "0.78125rem",
            // Room for descenders. A line box of exactly one em is the design's
            // figure, but `overflow: hidden` then clips the tail off every `g`,
            // `j` and `p` — and a page ID is a random string, so which
            // characters it contains is luck. The row aligns on the baseline,
            // so the extra height does not move the text.
            lineHeight: 1.4,
            color: paper["600"],
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          page/{pageId}
          {fileName !== null && ` · ${fileName}`}
        </Box>
      </Box>

      <Box sx={{ display: "flex", alignItems: "center", gap: 1.75 }}>
        {expiresAt !== null && (
          <Box sx={{ fontSize: "0.8125rem", color: paper["600"] }}>
            Deleted in{" "}
            <Box component="strong" sx={{ color: paper["900"], fontWeight: 600 }}>
              {formatRemaining(expiresAt, now)}
            </Box>
          </Box>
        )}
        <Button
          component={RouterLink}
          to={paths.SESSION}
          variant="outlined"
          sx={{ fontSize: "0.84375rem", px: 1.75, py: 1.125 }}
        >
          All pages
        </Button>
        <Button
          variant="contained"
          disabled={downloadable === 0}
          onClick={onDownloadResults}
          sx={{ fontSize: "0.84375rem", px: 1.75, py: 1.125 }}
        >
          Download results
        </Button>
      </Box>
    </Box>
  );
}
