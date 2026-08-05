import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

import ContentWidth from "../../components/ContentWidth";
import { mono, paper, serif } from "../../theme";

/**
 * The four steps, numbered like a printed instruction sheet.
 *
 * Ordinary marketing copy, with one job that is not: the last step names the
 * notation software MusicXML opens in. "Machine-readable" means nothing to a
 * musician, and "it opens in MuseScore" means everything.
 */
const STEPS = [
  {
    number: "01",
    title: "Upload a page",
    body: "A full page or a single staff. Musibot works out which from the shape of the image.",
  },
  {
    number: "02",
    title: "Watch it being read",
    body: "Staves are found first, then transcribed. Results appear on the scan as they arrive.",
  },
  {
    number: "03",
    title: "Take the MusicXML",
    body: "Download it, or read the notation Musibot rendered back from it to check the reading.",
  },
  {
    number: "04",
    title: "Open it anywhere",
    body: "MusicXML loads into most notation software, including Sibelius, Dorico and MuseScore.",
  },
];

export default function HowItWorks() {
  return (
    <Box sx={{ borderTop: `1px solid ${paper["200"]}` }}>
      <ContentWidth>
        <Box
          sx={{
            py: 4,
            display: "grid",
            gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(4, 1fr)" },
            gap: 4,
          }}
        >
          {STEPS.map((step) => (
            <Box key={step.number}>
              <Box
                sx={{
                  fontFamily: mono,
                  fontWeight: 600,
                  fontSize: "0.75rem",
                  lineHeight: 1,
                  color: paper["400"],
                }}
              >
                {step.number}
              </Box>
              <Typography
                component="h2"
                sx={{
                  mt: 1,
                  mb: 0.5,
                  fontFamily: serif,
                  fontWeight: 600,
                  fontSize: "1rem",
                  lineHeight: 1.35,
                  color: paper["950"],
                }}
              >
                {step.title}
              </Typography>
              <Typography sx={{ fontSize: "0.875rem", lineHeight: 1.6, color: paper["700"] }}>
                {step.body}
              </Typography>
            </Box>
          ))}
        </Box>
      </ContentWidth>
    </Box>
  );
}
