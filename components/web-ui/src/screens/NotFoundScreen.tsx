import Container from "@mui/material/Container";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { Link as RouterLink } from "react-router";

import * as paths from "../paths";

/**
 * Placeholder.
 *
 * Anything under the base path that no other route claims. A *MusicorpusPage*
 * that has expired arrives at its own route rather than here, and says so
 * there — this screen is only for an address that never named anything.
 */
export default function NotFoundScreen() {
  return (
    <Container sx={{ py: 8, maxWidth: "var(--measure-prose)" }}>
      <Stack spacing={2}>
        <Typography variant="h1">There is nothing here</Typography>
        <Typography variant="body1" sx={{ maxWidth: "var(--measure-body)" }}>
          <Link component={RouterLink} to={paths.LANDING}>
            Start from the beginning
          </Link>
        </Typography>
      </Stack>
    </Container>
  );
}
