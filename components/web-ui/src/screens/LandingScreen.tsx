import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useState } from "react";

import ContentWidth from "../components/ContentWidth";
import NoticeCard from "../components/NoticeCard";
import SessionPill from "../components/SessionPill";
import SiteFooter from "../components/SiteFooter";
import SiteHeader from "../components/SiteHeader";
import * as links from "../links";
import { paper } from "../theme";
import type { ChosenImage } from "../upload/chosenImage";
import { isAcceptedUpload, prepareUpload } from "../upload/prepareUpload";
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
 * three end at the same two questions — is it an image Musibot takes, and how
 * should it be read. The second is `PipelineChoice`, which opens over this page rather than
 * replacing it. It is a step and not a route, because nothing has been created
 * on the server yet and so there is nothing an address could name.
 */
export default function LandingScreen() {
  const [image, setImage] = useState<ChosenImage | null>(null);
  const [problem, setProblem] = useState<{ title: string; body: string } | null>(null);

  async function choose(file: File) {
    if (!isAcceptedUpload(file)) {
      setProblem({
        title: "Musibot can’t read that kind of file",
        body: "It takes a scan or a photograph — JPEG, PNG, BMP or TIFF — or a PDF of a scanned page.",
      });
      return;
    }
    setProblem(null);
    try {
      setImage(await prepareUpload(file));
    } catch (error) {
      setProblem({
        title: "That file could not be opened",
        body:
          error instanceof Error && error.message !== ""
            ? error.message
            : "Musibot could not make a page out of it. Another copy of the file, or another format, usually works.",
      });
    }
  }

  async function chooseSample(fileName: string) {
    setProblem(null);
    try {
      await choose(await fetchSample(fileName));
    } catch {
      setProblem({
        title: "That sample could not be loaded",
        body: "Musibot could not fetch its own example page, which is a fault on this instance rather than anything you did. Your own file will still work.",
      });
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
            <DropZone
              onChoose={(file) => void choose(file)}
              onChooseSample={(sample) => void chooseSample(sample.fileName)}
            />
            {problem !== null && (
              <Box sx={{ mt: 1.5 }}>
                <NoticeCard
                  title={problem.title}
                  actions={
                    <Button variant="outlined" onClick={() => setProblem(null)}>
                      Choose another file
                    </Button>
                  }
                >
                  {problem.body}
                </NoticeCard>
              </Box>
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
