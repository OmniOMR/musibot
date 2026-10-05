import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import ContentWidth from "./ContentWidth";
import cuni from "./logos/cuni.svg";
import lindat from "./logos/lindat.svg";
import omniomr from "./logos/omniomr.svg";
import pmcg from "./logos/pmcg.svg";
import ufal from "./logos/ufal.svg";
import { paper } from "../theme";

/**
 * Who made this and who paid for it.
 *
 * The five marks are drawn in the page's own warm grey rather than in their
 * colours: five institutional palettes side by side would be the loudest thing
 * on the page, beneath a design that keeps saturated colour for the one thing a
 * visitor is meant to do. So each file is used only for its shape — a CSS mask,
 * filled with `paper.500` — and its colour, whatever it is, never shows. A mark
 * drawn partly translucent keeps that translucency, as a lighter grey.
 *
 * Heights are per mark and set by eye rather than equal: a one-line wordmark
 * as wide as Prague Music Computing Group's looks far heavier at a given height
 * than a compact two-line one, and the university's file carries a margin of
 * its own around the crest.
 */
const AFFILIATIONS: { name: string; logo: string; height: number }[] = [
  { name: "Charles University", logo: cuni, height: 102 },
  { name: "Institute of Formal and Applied Linguistics", logo: ufal, height: 63 },
  { name: "Prague Music Computing Group", logo: pmcg, height: 48 },
  { name: "OmniOMR", logo: omniomr, height: 63 },
  { name: "LINDAT", logo: lindat, height: 63 },
];

/**
 * One mark, as a grey shape.
 *
 * The invisible `<img>` is what gives the box its size: it takes the file's own
 * proportions, so a mark can be replaced by a differently trimmed file without
 * a number here having to change. The visible part is the box behind it,
 * painted grey through the same file as a mask.
 */
function Logo({ name, logo, height }: { name: string; logo: string; height: number }) {
  return (
    <Box
      role="img"
      aria-label={name}
      title={name}
      sx={{
        position: "relative",
        display: "inline-flex",
        flex: "none",
        bgcolor: paper["500"],
        maskImage: `url("${logo}")`,
        maskSize: "contain",
        maskRepeat: "no-repeat",
        maskPosition: "center",
      }}
    >
      <Box component="img" src={logo} alt="" sx={{ height, width: "auto", visibility: "hidden" }} />
    </Box>
  );
}

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
          <Stack
            direction="row"
            useFlexGap
            sx={{ flexWrap: "wrap", alignItems: "center", columnGap: 4.5, rowGap: 2 }}
          >
            {AFFILIATIONS.map((affiliation) => (
              <Logo key={affiliation.name} {...affiliation} />
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
