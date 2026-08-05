import Box from "@mui/material/Box";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import ContentWidth from "../components/ContentWidth";
import SessionPill from "../components/SessionPill";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";
import * as links from "../links";
import { paper } from "../theme";
import { isJpeg, readChosenImage, type ChosenImage } from "../upload/chosenImage";
import DropZone from "./landing/DropZone";
import HowItWorks from "./landing/HowItWorks";
import PipelineChoice from "./landing/PipelineChoice";
import { fetchSample } from "./landing/samples";
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
 * The upload flow lives here rather than in the drop zone because it is not
 * the drop zone's: a file arrives by drop, by file picker or by sample, and all
 * three end at the same two questions — is it a JPEG, and how should it be
 * read. The second is `PipelineChoice`, which opens over this page rather than
 * replacing it. It is a step and not a route, because nothing has been created
 * on the server yet and so there is nothing an address could name.
 */
export default function LandingScreen() {
  const [image, setImage] = useState<ChosenImage | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

  async function choose(file: File) {
    if (!isJpeg(file)) {
      setProblem(
        "That file isn’t a JPEG. Musibot reads JPEG scans and photographs; a PDF needs exporting to one JPEG per page first.",
      );
      return;
    }
    setProblem(null);
    try {
      setImage(await readChosenImage(file));
    } catch {
      setProblem("That image could not be read.");
    }
  }

  async function chooseSample(fileName: string) {
    setProblem(null);
    try {
      await choose(await fetchSample(fileName));
    } catch {
      setProblem("That sample page could not be loaded.");
    }
  }

  function closeChoice() {
    if (image !== null) {
      URL.revokeObjectURL(image.previewUrl);
    }
    setImage(null);
  }

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
            <DropZone onChoose={(file) => void choose(file)} />
            {problem !== null && (
              <Typography
                role="alert"
                sx={{
                  mt: 1.5,
                  px: 1.75,
                  py: 1.25,
                  border: `1px solid ${paper["300"]}`,
                  borderRadius: 1.5,
                  bgcolor: paper["100"],
                  fontSize: "0.84375rem",
                  lineHeight: 1.55,
                  color: paper["900"],
                }}
              >
                {problem}
              </Typography>
            )}
            <SampleSheets onChoose={(sample) => void chooseSample(sample.fileName)} />
          </Box>
        </Box>
      </ContentWidth>

      <HowItWorks />
      <SiteFooter />
      <SessionPill />

      {image !== null && <PipelineChoice image={image} onClose={closeChoice} />}
    </>
  );
}
