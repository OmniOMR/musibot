import Box from "@mui/material/Box";
import ButtonBase from "@mui/material/ButtonBase";
import { useEffect, useRef } from "react";

import type { LogLine } from "../../page/log";
import { cuni, mono, paper } from "../../theme";

/**
 * The recognition log, across the bottom.
 *
 * One log for the whole *MusicorpusPage* rather than one per *Pipeline
 * Execution*: a page may be read twice, and somebody debugging a reading wants
 * the whole story in the order it happened, not two stories to interleave.
 *
 * The paper is the point. Continuous-feed dot-matrix stock: a punch-hole strip
 * down each edge and alternating line tints, which is what a machine printing a
 * log onto paper actually produced. The holes are inside the scrolling
 * container rather than pinned beside it, so they travel with the lines the way
 * perforations travel with a sheet — a fixed strip would read as a border and
 * lose the whole idea.
 *
 * The lines arrive over SSE as they are printed; `page/log.ts` holds the stream
 * and this draws whatever it has. `problem` is the one thing it says for
 * itself: a log that has stopped being watched must not look like a reading
 * that has gone quiet.
 */
export default function LogPanel({
  lines,
  streaming,
  problem,
  onCollapse,
}: {
  lines: LogLine[];
  /** Something is still being read, which the panel shows as a cursor. */
  streaming: boolean;
  problem: string | null;
  onCollapse: () => void;
}) {
  const scroller = useRef<HTMLDivElement | null>(null);
  /**
   * Whether the view is at the foot of the log.
   *
   * A log that jumps to the bottom on every line is unreadable the moment
   * somebody scrolls up to look at one, so following is a state the reader
   * enters by scrolling to the end and leaves by scrolling away from it.
   */
  const following = useRef(true);

  useEffect(() => {
    const element = scroller.current;
    if (element !== null && following.current) {
      element.scrollTop = element.scrollHeight;
    }
  }, [lines]);

  return (
    <Box
      component="section"
      sx={{
        flex: "none",
        height: 150,
        display: "flex",
        flexDirection: "column",
        borderTop: `1px solid ${paper["200"]}`,
        bgcolor: paper["100"],
      }}
    >
      <Box
        sx={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 2,
          px: 2,
          py: 1,
          borderBottom: `1px solid ${paper["200"]}`,
        }}
      >
        <Box sx={{ display: "flex", alignItems: "baseline", gap: 1.5, minWidth: 0 }}>
          <Box
            sx={{
              fontFamily: mono,
              fontWeight: 600,
              fontSize: "0.6875rem",
              lineHeight: 1,
              letterSpacing: "0.08em",
              textTransform: "uppercase",
              color: paper["600"],
            }}
          >
            Recognition log
          </Box>
          {problem !== null && (
            <Box
              sx={{ fontFamily: mono, fontSize: "0.6875rem", lineHeight: 1, color: cuni.redDark }}
            >
              {problem}
            </Box>
          )}
        </Box>
        <ButtonBase
          onClick={onCollapse}
          sx={{
            fontFamily: mono,
            fontSize: "0.71875rem",
            lineHeight: 1,
            color: paper["500"],
            p: 0.5,
            flex: "none",
            "&:hover": { color: paper["700"] },
          }}
        >
          collapse ‹
        </ButtonBase>
      </Box>

      <Box
        ref={scroller}
        onScroll={(event) => {
          const element = event.currentTarget;
          // Two pixels of slack: a scroll position is fractional at some zoom
          // levels and an exact comparison would drop out of following on its
          // own.
          following.current = element.scrollHeight - element.scrollTop - element.clientHeight < 2;
        }}
        sx={{ flex: 1, overflow: "auto", minHeight: 0 }}
      >
        {/* `min-height: 100%` so the perforations run the full depth of the
            panel even when there are fewer lines than there is room for. */}
        <Box sx={{ display: "flex", minHeight: "100%" }}>
          <Perforation />

          <Box sx={{ flex: 1, minWidth: 0, py: 1 }}>
            {lines.length === 0 ? (
              <Box sx={{ px: 1.5, fontFamily: mono, fontSize: "0.71875rem", color: paper["500"] }}>
                Nothing yet.
              </Box>
            ) : (
              lines.map((line, index) => (
                <Box
                  key={`${index}-${line.at}`}
                  sx={{
                    display: "flex",
                    gap: 1.5,
                    px: 1.5,
                    py: "2px",
                    fontFamily: mono,
                    fontSize: "0.71875rem",
                    lineHeight: 1.55,
                    // The zebra is the paper, not a table: alternate rows were
                    // tinted by the ribbon, so it follows the line's position
                    // and nothing about the line itself.
                    bgcolor: index % 2 === 1 ? paper["150"] : "transparent",
                  }}
                >
                  <Box component="span" sx={{ flex: "none", color: paper["400"] }}>
                    {line.at}
                  </Box>
                  <Box
                    component="span"
                    sx={{ color: line.tone === "error" ? cuni.redDark : paper["700"] }}
                  >
                    {line.text}
                  </Box>
                </Box>
              ))
            )}

            {streaming && (
              <Box
                sx={{
                  px: 1.5,
                  fontFamily: mono,
                  fontSize: "0.71875rem",
                  lineHeight: 1.55,
                  color: paper["400"],
                  // No percentage anywhere: an image-to-sequence model does not
                  // know how much output is left, so a bar would be invented.
                  "@keyframes blink": { "50%": { opacity: 0 } },
                  animation: "blink 1.1s step-end infinite",
                }}
              >
                ▌
              </Box>
            )}
          </Box>

          <Perforation />
        </Box>
      </Box>
    </Box>
  );
}

/** The sprocket holes down one edge of the paper. */
function Perforation() {
  return (
    <Box
      aria-hidden
      sx={{
        width: 16,
        flex: "none",
        backgroundImage: `radial-gradient(circle, ${paper["300"]} 32%, transparent 34%)`,
        backgroundSize: "16px 20px",
      }}
    />
  );
}
