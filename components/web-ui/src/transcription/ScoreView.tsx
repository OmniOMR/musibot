import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import { useEffect, useRef, useState } from "react";

import { paper } from "../theme";
import { preprocessMusicXmlForOSMD } from "./transcription";

/**
 * One reading, engraved.
 *
 * OpenSheetMusicDisplay does the engraving, and it is loaded on demand rather
 * than bundled with the app. It ships as a single prebuilt file of about
 * 1.3 MB with VexFlow and JSZip already inside it, so it cannot be tree-shaken
 * and would otherwise be paid for by every visitor who ever loads the landing
 * page — most of whom will never open a transcription. A dynamic import puts it
 * in a chunk of its own, fetched the first time somebody actually wants
 * notation.
 *
 * OSMD writes its own DOM into the container, so the container is rendered
 * empty by React and never given a child — the same division that lets d3 own
 * the ruler on the canvas. It also has to be told to render again whenever the
 * panel's width changes, since engraving is a layout decision and not a style.
 *
 * A single staff is engraved as one unbroken line, so a long reading is a wide
 * one. The container stays at the panel's width and lets the drawing overflow
 * it; the card around it scrolls sideways. Growing the container to the drawing
 * instead would make its `clientWidth` a measure of the content rather than of
 * the space available, and the resize check below would then be watching the
 * thing it causes.
 */

/**
 * How large the engraving is drawn.
 *
 * OSMD's own scale is chosen for a page of music on a screen; in a panel beside
 * the scan it is bigger than it needs to be, and each staff pushes the next one
 * further down. Three fifths fits appreciably more of a reading into the same
 * column while staying comfortably legible.
 */
const ZOOM = 0.6;

export default function ScoreView({
  musicXml,
  singleStaff,
}: {
  musicXml: string;
  /**
   * Whether this reading is one staff rather than a whole page.
   *
   * A staff crop is a single line of music, and breaking it into systems the
   * way a page is laid out would be Musibot inventing a structure the crop does
   * not have. A page has its own systems, written in the MusicXML, and running
   * them together into one endless line is just as wrong the other way.
   */
  singleStaff: boolean;
}) {
  const container = useRef<HTMLDivElement | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const element = container.current;
    if (element === null) {
      return;
    }

    let cancelled = false;
    // `unknown` because the type only exists once the chunk has arrived, and
    // importing it for its types would defeat the point of loading it lazily.
    let display: { render: () => void; clear: () => void } | null = null;
    let observer: ResizeObserver | null = null;

    void (async () => {
      try {
        const { OpenSheetMusicDisplay } = await import("opensheetmusicdisplay");
        if (cancelled) {
          return;
        }

        const osmd = new OpenSheetMusicDisplay(element, {
          backend: "svg",
          // Musibot already says whose page this is, in the header and in the
          // panel's own label; `compacttight` is the preset that drops the
          // title, subtitle, composer and part names a file repeats above every
          // staff, and tightens the spacing between systems while it is there.
          drawingParameters: "compacttight",
          drawMeasureNumbers: false,
          // Beaming is a notational decision, and the transcription already
          // made it. Letting OSMD beam by its own rules would show something
          // other than what Musibot read.
          autoBeam: false,
          // Engraving is re-run on resize below, which is finer control than
          // OSMD's own listener gives.
          autoResize: false,
          renderSingleHorizontalStaffline: singleStaff,
          newSystemFromXML: true,
          autoGenerateMultipleRestMeasuresFromRestMeasures: false,
          // OSMD has some peculiarities about what it renders and what not, and
          // `preprocessMusicXmlForOSMD` works around them. It has to run here
          // rather than on the way into `load` below, because it re-serialises
          // the document and loses the `<?xml` declaration — which is the only
          // thing by which `load` recognises a string as a score at all, rather
          // than as a URL to fetch one from.
          onXMLRead: preprocessMusicXmlForOSMD,
        });

        await osmd.load(musicXml);
        if (cancelled) {
          return;
        }
        osmd.zoom = ZOOM;
        osmd.render();
        display = osmd;
        setState("ready");

        let width = element.clientWidth;
        observer = new ResizeObserver(() => {
          // Width alone: engraving decides line breaks, so a change in height
          // is a consequence of rendering and re-rendering for it would loop.
          if (element.clientWidth !== width && element.clientWidth > 0) {
            width = element.clientWidth;
            osmd.render();
          }
        });
        observer.observe(element);
      } catch (error) {
        if (!cancelled) {
          setProblem(
            error instanceof Error
              ? error.message
              : typeof error?.toString == "function"
                ? error.toString()
                : "This transcription could not be rendered.",
          );
          setState("failed");
        }
      }
    })();

    return () => {
      cancelled = true;
      observer?.disconnect();
      display?.clear();
      // OSMD's own cleanup leaves the container's children behind when it never
      // finished loading, and React will not tidy them because it does not know
      // they are there.
      element.replaceChildren();
    };
  }, [musicXml, singleStaff]);

  return (
    <Box sx={{ position: "relative", minHeight: state === "ready" ? 0 : 96 }}>
      {/* OSMD's. Never give this a React child. */}
      <Box ref={container} sx={{ width: "100%" }} />

      {state === "loading" && (
        <Overlay>
          <CircularProgress size={18} />
        </Overlay>
      )}
      {state === "failed" && (
        <Overlay>
          <Box sx={{ maxWidth: "48ch" }}>
            Musibot could not engrave this transcription. The file is still on the page and can be
            downloaded.
            {problem !== null && (
              <Box sx={{ mt: 0.5, fontSize: "0.75rem", color: paper["500"] }}>{problem}</Box>
            )}
          </Box>
        </Overlay>
      )}
    </Box>
  );
}

function Overlay({ children }: { children: React.ReactNode }) {
  return (
    <Box
      sx={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        textAlign: "center",
        color: paper["600"],
        fontSize: "0.8125rem",
        px: 2,
      }}
    >
      {children}
    </Box>
  );
}
