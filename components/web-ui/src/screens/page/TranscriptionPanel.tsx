import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";

import type { FileView } from "../../api/types";
import type { FileRow } from "../../page/files";
import { useSceneData } from "../../scene/useSceneData";
import { mono, paper } from "../../theme";
import ScoreView from "../../transcription/ScoreView";
import { pathsOf, readingsFor, tokensOf, type Reading } from "../../transcription/transcription";

/**
 * What Musibot read, beside what it read it from.
 *
 * Present only while a transcription is selected, and gone otherwise: it would
 * have nothing to say about a `layout.json`, and half the canvas is worth more
 * than an empty column explaining itself. It carries the same 46-pixel header
 * as the canvas beside it so the two toolbars line up, and takes an equal share
 * of the width, because comparing the reading against the scan is the whole
 * reason for looking at either.
 *
 * Each reading shows the notation engraved from MusicXML and, underneath, the
 * LMX the model actually emitted. The second is not a fallback for the first —
 * they are for two different readers. A musician checks whether the notation
 * looks right; somebody working on the model reads the token sequence, where a
 * wrong duration is a wrong token rather than a subtly wrong stem.
 */
export default function TranscriptionPanel({
  pageId,
  token,
  selected,
  files,
}: {
  pageId: string;
  token: string | null;
  selected: FileRow | null;
  files: FileView[];
}) {
  const readings = readingsFor(selected, files);
  const data = useSceneData(pageId, token, pathsOf(readings), files);

  return (
    <Box
      sx={{
        flex: 1,
        minWidth: 0,
        display: "flex",
        flexDirection: "column",
        minHeight: 0,
        borderLeft: `1px solid ${paper["200"]}`,
      }}
    >
      <Box
        sx={{
          height: 46,
          flex: "none",
          boxSizing: "border-box",
          display: "flex",
          alignItems: "center",
          px: 2,
          borderBottom: `1px solid ${paper["200"]}`,
          bgcolor: paper["050"],
          fontSize: "0.78125rem",
          color: paper["600"],
        }}
      >
        {readings.length === 1
          ? "The reading"
          : `The reading · ${readings.length} ${readings.length === 1 ? "part" : "parts"}`}
      </Box>

      <Box sx={{ flex: 1, minHeight: 0, overflow: "auto", bgcolor: paper["050"] }}>
        {data.loading && data.texts.size === 0 ? (
          <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
            <CircularProgress size={20} />
          </Box>
        ) : (
          readings.map((reading) => (
            <ReadingView
              key={reading.folder}
              reading={reading}
              musicXml={
                reading.musicXmlPath === null ? undefined : data.texts.get(reading.musicXmlPath)
              }
              lmx={reading.lmxPath === null ? undefined : data.texts.get(reading.lmxPath)}
            />
          ))
        )}

        {data.error !== null && (
          <Box sx={{ px: 2.5, py: 3, fontSize: "0.8125rem", color: paper["600"] }}>
            {data.error}
          </Box>
        )}
      </Box>
    </Box>
  );
}

function ReadingView({
  reading,
  musicXml,
  lmx,
}: {
  reading: Reading;
  musicXml: string | undefined;
  lmx: string | undefined;
}) {
  return (
    <Box sx={{ borderBottom: `1px solid ${paper["200"]}`, "&:last-of-type": { borderBottom: 0 } }}>
      {reading.label !== null && (
        <Box
          sx={{
            px: 2.5,
            pt: 1.75,
            fontFamily: mono,
            fontWeight: 600,
            fontSize: "0.6875rem",
            letterSpacing: "0.08em",
            textTransform: "uppercase",
            color: paper["600"],
          }}
        >
          {reading.label}
        </Box>
      )}

      {/* The scroller. A staff is engraved unbroken, so a long reading is wider
          than the panel and this is where it runs off the edge — beside the
          notation rather than at the foot of the whole column, so the scrollbar
          sits against the thing that moves and the tokens below go on wrapping
          to the width that is actually visible. */}
      <Box
        sx={{
          px: 1.5,
          py: 1.5,
          bgcolor: paper["000"],
          mx: 2.5,
          my: 1.75,
          borderRadius: 1,
          overflowX: "auto",
        }}
      >
        {musicXml === undefined ? (
          <Box sx={{ py: 3, textAlign: "center", fontSize: "0.8125rem", color: paper["600"] }}>
            {reading.musicXmlPath === null
              ? "This one has no MusicXML — only the tokens below."
              : "…"}
          </Box>
        ) : (
          <ScoreView musicXml={musicXml} />
        )}
      </Box>

      {lmx !== undefined && <Tokens lmx={lmx} />}
    </Box>
  );
}

/**
 * The LMX, token by token.
 *
 * Set as separated words rather than as a paragraph of text, because what is
 * being read is a sequence and the boundaries are the content — a reader
 * counting tokens against notes needs to see where each one ends. Wrapping
 * rather than scrolling sideways: a long reading is long, and a horizontal
 * scrollbar would hide the end of it.
 */
function Tokens({ lmx }: { lmx: string }) {
  const tokens = tokensOf(lmx);

  return (
    <Box sx={{ px: 2.5, pb: 2.25 }}>
      <Box
        sx={{
          fontFamily: mono,
          fontWeight: 600,
          fontSize: "0.6875rem",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: paper["600"],
          mb: 0.75,
        }}
      >
        LMX · {tokens.length} tokens
      </Box>
      <Box
        sx={{
          display: "flex",
          flexWrap: "wrap",
          gap: "3px 5px",
          p: 1.25,
          border: `1px solid ${paper["200"]}`,
          borderRadius: 1,
          bgcolor: paper["100"],
          maxHeight: 220,
          overflow: "auto",
        }}
      >
        {tokens.map((tokenText, index) => (
          <Box
            key={`${index}-${tokenText}`}
            component="span"
            sx={{
              fontFamily: mono,
              fontSize: "0.71875rem",
              lineHeight: 1.5,
              color: paper["900"],
              bgcolor: paper["000"],
              border: `1px solid ${paper["200"]}`,
              borderRadius: "3px",
              px: 0.5,
            }}
          >
            {tokenText}
          </Box>
        ))}
      </Box>
    </Box>
  );
}
