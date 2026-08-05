import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";

import ContentWidth from "../components/ContentWidth";
import SessionPill from "../components/SessionPill";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";
import * as links from "../links";
import { paper } from "../theme";
import DropZone from "./landing/DropZone";
import HowItWorks from "./landing/HowItWorks";
import SampleSheets from "./landing/SampleSheets";

/**
 * The landing page: the pitch on the left, the way in on the right.
 *
 * This is the only screen meant to be indexed, and the only one most visitors
 * will ever see. Two things follow from that.
 *
 * The copy is final and is not placeholder text — the design fixed it, and the
 * `<noscript>` body and Open Graph description in `index.html` say the same
 * things in the same order, because for a link-preview scraper those tags *are*
 * this page. Changing a sentence here means changing it there. See the README's
 * *Search engines*.
 *
 * And the paragraph pointing libraries at an email address is load-bearing
 * rather than polite. The public tier is capped as one pool and is sized for a
 * conference demo; a library that discovers Musibot here and starts feeding a
 * collection through it will not get far, and would be occupying the tier while
 * failing. Sending them to a person is the correct answer, not a softer one.
 *
 * Nothing is uploaded yet. `DropZone` and `SampleSheets` both call back with
 * what the visitor picked and this screen drops it on the floor — the flow that
 * catches it (validation, the pipeline choice, the upload) is the next piece of
 * work, and this is the seam it plugs into.
 */
export default function LandingScreen() {
  return (
    <>
      <SiteHeader />

      <ContentWidth>
        <Box
          sx={{
            pt: { xs: 5, md: 7 },
            pb: 5,
            display: "flex",
            flexDirection: { xs: "column", md: "row" },
            gap: { xs: 5, md: 6 },
            alignItems: "flex-start",
          }}
        >
          <Box sx={{ flex: "1.05 1 0", minWidth: 0 }}>
            <Typography variant="h1" sx={{ mb: 2, maxWidth: "16ch", textWrap: "pretty" }}>
              Musibot reads sheet music
            </Typography>
            <Typography
              sx={{
                mb: 1.75,
                fontSize: "1.0625rem",
                lineHeight: 1.65,
                color: paper["900"],
                maxWidth: "52ch",
                textWrap: "pretty",
              }}
            >
              Upload a scan or a photograph of a page of music notation and Musibot returns it in a
              machine-readable format such as MusicXML.
            </Typography>
            <Typography
              sx={{
                fontSize: "0.9375rem",
                lineHeight: 1.6,
                color: paper["700"],
                maxWidth: "52ch",
                textWrap: "pretty",
              }}
            >
              The models behind it come from Optical Music Recognition research at Charles
              University, Institute of Formal and Applied Linguistics. Libraries and archives with a
              whole collection to read should write to{" "}
              <Link href={`mailto:${links.CONTACT_EMAIL}`}>{links.CONTACT_EMAIL}</Link> — the public
              allowance here is far too small for that work.
            </Typography>
          </Box>

          <Box sx={{ flex: "1 1 0", minWidth: 0, width: "100%" }}>
            <DropZone onChoose={() => {}} />
            <SampleSheets onChoose={() => {}} />
          </Box>
        </Box>
      </ContentWidth>

      <HowItWorks />
      <SiteFooter />
      <SessionPill />
    </>
  );
}
