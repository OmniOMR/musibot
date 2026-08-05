import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import { Link as RouterLink } from "react-router";

import ContentWidth from "./ContentWidth";
import * as links from "../links";
import * as paths from "../paths";
import { paper, serif } from "../theme";

/**
 * The wordmark and the three links out.
 *
 * Not an `AppBar`: it does not float, it does not cast a shadow and it is not
 * fixed to the viewport — it is the top of the page, divided from the rest by
 * the same hairline as everything else. `AppBar` would bring position and
 * elevation machinery only to be told to switch it off.
 *
 * The rule under it spans the window while the wordmark and the links stop at
 * the content column, which is what keeps a full-bleed page from looking like
 * a narrow one that forgot to grow.
 *
 * All three links leave the app. Two go to documentation that exists elsewhere
 * and would only be duplicated here, and the third stands in for an about page
 * until there is something to say that the project's README does not.
 */
export default function SiteHeader() {
  return (
    <Box component="header" sx={{ borderBottom: `1px solid ${paper["200"]}` }}>
      <ContentWidth>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 2,
            py: 1.75,
          }}
        >
          <Link
            component={RouterLink}
            to={paths.LANDING}
            underline="none"
            sx={{
              fontFamily: serif,
              fontWeight: 600,
              fontSize: "1.1875rem",
              lineHeight: 1,
              color: paper["950"],
            }}
          >
            Musibot
          </Link>

          <Stack component="nav" direction="row" spacing={2.75}>
            <Link href={links.HTTP_API_DOCS} underline="none" sx={{ fontSize: "0.875rem" }}>
              HTTP API
            </Link>
            <Link href={links.PYTHON_CLIENT} underline="none" sx={{ fontSize: "0.875rem" }}>
              Python client
            </Link>
            <Link href={links.PROJECT} underline="none" sx={{ fontSize: "0.875rem" }}>
              About
            </Link>
          </Stack>
        </Box>
      </ContentWidth>
    </Box>
  );
}
