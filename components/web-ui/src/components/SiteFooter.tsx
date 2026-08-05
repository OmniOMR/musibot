import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ContentWidth from "./ContentWidth";
import { paper, serif } from "../theme";

/**
 * Who made this and who paid for it.
 *
 * The five affiliations are set as text rather than as logos, because no logo
 * assets exist yet. When they do, this is where they go — the layout is a row
 * of marks either way, and setting them in the heading face is what keeps a
 * row of plain words from reading as a list of links.
 */
const AFFILIATIONS = [
  "Charles University",
  "Institute of Formal and Applied Linguistics",
  "Prague Music Computing Group",
  "OmniOMR",
  "LINDAT",
];

/**
 * The funding acknowledgement, which is a condition of the grant and is
 * reproduced word for word. It is not copy — do not rewrite it, shorten it or
 * translate it.
 */
const FUNDING =
  "This software was funded by OmniOMR — an applied research project of the 2023–2030 NAKI III " +
  "programme, supported by the Ministry of Culture of the Czech Republic (DH23P03OVV008).";

export default function SiteFooter() {
  return (
    <Box component="footer" sx={{ borderTop: `1px solid ${paper["200"]}` }}>
      <ContentWidth>
        <Box sx={{ pt: 3.25, pb: 2.75 }}>
          <Stack direction="row" useFlexGap sx={{ flexWrap: "wrap", columnGap: 4.5, rowGap: 1.5 }}>
            {AFFILIATIONS.map((affiliation) => (
              <Box
                key={affiliation}
                sx={{
                  fontFamily: serif,
                  fontWeight: 600,
                  fontSize: "0.8125rem",
                  lineHeight: 1,
                  letterSpacing: "0.01em",
                  color: paper["500"],
                }}
              >
                {affiliation}
              </Box>
            ))}
          </Stack>

          <Typography
            sx={{
              mt: 2,
              fontSize: "0.75rem",
              lineHeight: 1.6,
              color: paper["500"],
              maxWidth: "72ch",
            }}
          >
            {FUNDING}
          </Typography>
        </Box>
      </ContentWidth>
    </Box>
  );
}
