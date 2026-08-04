import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Container from "@mui/material/Container";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import { paper } from "./theme";

/**
 * Placeholder.
 *
 * This is not the landing page — it is a swatch, here so the theme can be
 * looked at rather than read. It exercises the pieces that are easy to get
 * wrong (serif headings against sans body, a filled red button, an outlined
 * input's border, a divider, a raised surface) so that a change to
 * `theme/palette.ts` has somewhere to show itself.
 *
 * Replace it wholesale when the real layout and user flow are built.
 */
export default function App() {
  return (
    <Container sx={{ py: 8, maxWidth: "var(--measure-prose)" }}>
      <Stack spacing={4}>
        <Box>
          <Typography variant="h1" gutterBottom>
            Musibot reads sheet music
          </Typography>
          <Typography
            variant="body1"
            color="text.secondary"
            sx={{ maxWidth: "var(--measure-body)" }}
          >
            Upload a scan or a photograph of a page of music notation and Musibot returns it in a
            machine-readable format such as MusicXML. Číst notový zápis — ěščřžýáíé, so the
            diacritics get looked at too.
          </Typography>
        </Box>

        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          <Button variant="contained">Upload a page</Button>
          <Button variant="outlined">Browse pipelines</Button>
          <Link href="#">Read the API docs</Link>
        </Stack>

        <Divider />

        <Paper variant="outlined" sx={{ p: 3, bgcolor: paper["100"] }}>
          <Typography variant="h3" gutterBottom>
            A surface, raised off the page
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom>
            Separated by a hairline rule and half a step of tone, not a drop shadow.
          </Typography>
          <TextField label="Pipeline name" size="small" sx={{ mt: 2 }} />
        </Paper>

        <Box>
          <Typography variant="overline" color="text.secondary">
            The warm ramp
          </Typography>
          <Stack direction="row" sx={{ mt: 1 }}>
            {Object.entries(paper).map(([step, hex]) => (
              <Box
                key={step}
                title={`${step} — ${hex}`}
                sx={{
                  flex: 1,
                  height: 56,
                  bgcolor: hex,
                  border: `1px solid ${paper["200"]}`,
                  borderRight: 0,
                  "&:last-of-type": { borderRight: `1px solid ${paper["200"]}` },
                }}
              />
            ))}
          </Stack>
        </Box>
      </Stack>
    </Container>
  );
}
