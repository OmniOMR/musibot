import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

/**
 * Placeholder.
 *
 * Everything this browser has uploaded while its session lasts, which is about
 * an hour and is not tied to an account. The API has no endpoint that lists a
 * user's pages, so this screen will read the ledger the app keeps for itself
 * rather than ask for one.
 */
export default function SessionScreen() {
  return (
    <Container sx={{ py: 8, maxWidth: "var(--measure-prose)" }}>
      <Stack spacing={2}>
        <Typography variant="h1">Pages in this session</Typography>
      </Stack>
    </Container>
  );
}
