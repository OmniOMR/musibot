import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useParams } from "react-router";

import { mono } from "../theme";

/**
 * Placeholder.
 *
 * One *MusicorpusPage*, and the screen the work actually happens on: four
 * panels — the executions and files overview, the pannable scan, the
 * transcription beside it, and the recognition log along the bottom. None of
 * them exist yet; the ID is read from the route so the wiring can be seen to
 * work.
 */
export default function MusicorpusPageScreen() {
  const { pageId } = useParams();

  return (
    <Container sx={{ py: 8, maxWidth: "var(--measure-prose)" }}>
      <Stack spacing={2}>
        <Typography variant="h1">MusicorpusPage</Typography>
        <Typography variant="body1" sx={{ fontFamily: mono }}>
          {pageId}
        </Typography>
      </Stack>
    </Container>
  );
}
