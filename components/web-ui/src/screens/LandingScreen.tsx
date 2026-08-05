import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

/**
 * Placeholder.
 *
 * The one screen a crawler and a link-preview scraper are meant to reach, so
 * the heading and the pitch are here already and are the same sentences as the
 * `<noscript>` body and the Open Graph description in `index.html`. Those three
 * have to agree — see the README's *Search engines*.
 *
 * Everything else the landing page owes — the header, the drop zone, the four
 * sample pages, the 01–04 steps, the affiliation footer and the funding line,
 * and the floating session pill — is still to come.
 */
export default function LandingScreen() {
  return (
    <Container sx={{ py: 8, maxWidth: "var(--measure-prose)" }}>
      <Stack spacing={2}>
        <Typography variant="h1">Musibot reads sheet music</Typography>
        <Typography variant="body1" sx={{ maxWidth: "var(--measure-body)" }}>
          Upload a scan or a photograph of a page of music notation and Musibot returns it in a
          machine-readable format such as MusicXML.
        </Typography>
      </Stack>
    </Container>
  );
}
