import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Paper from "@mui/material/Paper";
import Typography from "@mui/material/Typography";
import { Link as RouterLink, useNavigate } from "react-router";

import ContentWidth from "../components/ContentWidth";
import SiteHeader from "../components/SiteHeader";
import { formatRemaining, useNow } from "../page/expiry";
import * as paths from "../paths";
import { useSessionPages, type SessionPageView } from "../session/useSessionPages";
import { cuni, mono, paper, serif } from "../theme";

/**
 * Everything this browser has uploaded and can still reach.
 *
 * Read from the ledger rather than from the server, because the API has no
 * endpoint that lists a user's pages — if the app did not write down what it
 * uploaded, nothing would know. What the server *is* asked, once per page, is
 * how the reading went, since that is the part that changes after the upload
 * is over.
 *
 * The copy about accounts and tabs is the point of the screen as much as the
 * list is. Everything here disappears within the hour and there is no way to
 * get it back, so a visitor who assumes this is a library of their work is
 * going to lose it. Saying so once, plainly, at the top, is cheaper than any
 * amount of explaining afterwards.
 */
export default function SessionScreen() {
  const pages = useSessionPages();
  const now = useNow();
  const navigate = useNavigate();

  return (
    <>
      <SiteHeader />
      <ContentWidth maxWidth={720}>
        <Box sx={{ py: { xs: 4, md: 6 } }}>
          <Paper variant="outlined" sx={{ borderColor: paper["300"], overflow: "hidden" }}>
            <Box sx={{ px: 3.5, pt: 3, pb: 1.75, borderBottom: `1px solid ${paper["200"]}` }}>
              <Typography
                component="h1"
                sx={{
                  fontFamily: serif,
                  fontWeight: 600,
                  fontSize: "1.5rem",
                  lineHeight: 1.2,
                  color: paper["950"],
                }}
              >
                Pages in this session
              </Typography>
              <Typography
                sx={{ mt: 0.75, fontSize: "0.84375rem", lineHeight: 1.55, color: paper["600"] }}
              >
                {pages.length === 0
                  ? "Nothing here yet. Pages are kept for about an hour from upload."
                  : `${count(pages.length)}, kept for about an hour from upload. Nothing here is stored under an account, and closing the tab does not extend it.`}
              </Typography>
            </Box>

            {pages.map((entry) => (
              <PageRow key={entry.page.pageId} entry={entry} now={now} />
            ))}

            <Box sx={{ px: 3.5, py: 2, borderTop: `1px solid ${paper["200"]}` }}>
              <Button
                variant="contained"
                onClick={() => void navigate(paths.LANDING)}
                sx={{ fontSize: "0.875rem", px: 2.25, py: 1.375 }}
              >
                Upload another page
              </Button>
            </Box>
          </Paper>
        </Box>
      </ContentWidth>
    </>
  );
}

function PageRow({ entry, now }: { entry: SessionPageView; now: Date }) {
  const { page } = entry;

  return (
    <Box
      component={RouterLink}
      to={paths.musicorpusPagePath(page.pageId)}
      sx={{
        display: "flex",
        gap: 1.75,
        alignItems: "center",
        px: 3.5,
        py: 1.75,
        borderBottom: `1px solid ${paper["200"]}`,
        textDecoration: "none",
        "&:hover": { bgcolor: paper["100"] },
      }}
    >
      {/* Drawn from the copy made at upload, so the list costs no network. */}
      <Box
        sx={{
          width: 38,
          height: 52,
          flex: "none",
          border: `1px solid ${paper["300"]}`,
          borderRadius: "3px",
          bgcolor: paper["000"],
          overflow: "hidden",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {page.thumbnail == null ? null : (
          // Already cropped to this shape at upload, so it fills the box
          // exactly and nothing is scaled twice.
          <Box
            component="img"
            src={page.thumbnail}
            alt=""
            sx={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        )}
      </Box>

      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box
          sx={{
            fontFamily: mono,
            fontSize: "0.78125rem",
            lineHeight: 1.4,
            color: paper["900"],
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {page.fileName}
        </Box>
        <Box
          sx={{
            mt: 0.375,
            fontSize: "0.78125rem",
            lineHeight: 1.4,
            color: entry.tone === "error" ? cuni.redDark : paper["600"],
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {entry.status}
        </Box>
      </Box>

      <Box
        sx={{
          flex: "none",
          fontFamily: mono,
          fontSize: "0.71875rem",
          lineHeight: 1.4,
          color: paper["500"],
        }}
      >
        {entry.expiresAt === null ? "" : formatRemaining(entry.expiresAt, now)}
      </Box>
    </Box>
  );
}

function count(pages: number): string {
  const words = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];
  const word = words[pages] ?? String(pages);
  return `${word} page${pages === 1 ? "" : "s"}`;
}
