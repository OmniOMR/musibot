import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import CircularProgress from "@mui/material/CircularProgress";
import Dialog from "@mui/material/Dialog";
import Typography from "@mui/material/Typography";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router";

import { listPipelines } from "../../api/client";
import { ApiError, RateLimited } from "../../api/errors";
import type { PipelineView } from "../../api/types";
import * as paths from "../../paths";
import {
  find,
  PAGE_PIPELINE,
  same,
  STAFF_PIPELINE,
  uploadPathFor,
  type PipelineRef,
} from "../../pipelines";
import { useSession } from "../../session/useSession";
import { mono, paper, serif } from "../../theme";
import {
  guessExplanation,
  looksLikeSingleStaff,
  thumbnailOf,
  type ChosenImage,
} from "../../upload/chosenImage";
import { startRecognition } from "../../upload/startRecognition";
import AllPipelines from "./AllPipelines";
import PipelineOption from "./PipelineOption";

/**
 * "How should this be read?" — the step between choosing a file and uploading it.
 *
 * Not a route. It is a step of the upload flow and it has no address of its
 * own: nothing has been created on the server yet, so there is nothing an
 * address could name, and a reload here should land back on the landing page
 * rather than on a card describing a file the browser no longer holds.
 *
 * A token is taken as soon as this opens rather than at "Start reading",
 * because listing *Pipelines* is itself an authenticated call. That is not a
 * loosening of the minting rule: the visitor has chosen a file, an upload is
 * imminent, and `tokenForNewPage` reuses the current session unless it is
 * nearly over.
 */
export default function PipelineChoice({
  image,
  onClose,
}: {
  image: ChosenImage;
  onClose: () => void;
}) {
  const session = useSession();
  const navigate = useNavigate();

  const [pipelines, setPipelines] = useState<PipelineView[] | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [selected, setSelected] = useState<PipelineRef | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [starting, setStarting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    void (async () => {
      try {
        const current = await session.tokenForNewPage();
        const listing = await listPipelines(current.token);
        if (cancelled) {
          return;
        }
        setToken(current.token);
        setPipelines(listing.pipelines);

        // Preselect what the shape suggests, but only if it is actually there.
        const wanted = looksLikeSingleStaff(image) ? STAFF_PIPELINE : PAGE_PIPELINE;
        if (find(listing.pipelines, wanted) !== undefined) {
          setSelected(wanted);
        } else {
          // Nothing is preselected and the list is where the visitor has to
          // look, so open it for them rather than telling them to.
          setShowAll(true);
        }
      } catch (error) {
        if (!cancelled) {
          setProblem(messageFor(error));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // Deliberately once per opened card: re-running would re-list and could
    // overwrite a choice the visitor has already made. The card is mounted per
    // chosen image, so "once" is once per image.
  }, []);

  const pageAvailable = pipelines !== null && find(pipelines, PAGE_PIPELINE) !== undefined;
  const staffAvailable = pipelines !== null && find(pipelines, STAFF_PIPELINE) !== undefined;
  const chosen = selected === null || pipelines === null ? null : find(pipelines, selected);
  const uploadPath =
    chosen === undefined || chosen === null ? null : uploadPathFor(chosen.signature);

  async function start() {
    if (token === null || selected === null || uploadPath === null) {
      return;
    }
    setStarting(true);
    setProblem(null);
    try {
      const pageId = await startRecognition({
        token,
        file: image.file,
        uploadPath,
        pipeline: selected,
      });
      session.rememberPage({
        pageId,
        token,
        fileName: image.file.name,
        // Made from the bytes already in hand. Once this card closes the file
        // is gone, and the session list would otherwise have to fetch the
        // whole scan back to draw it small.
        thumbnail: await thumbnailOf(image),
      });
      session.notePipeline(pageId, selected.name, selected.version);
      void navigate(paths.musicorpusPagePath(pageId));
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        // The token is dead however much life we recorded for it. Drop the
        // session; the next attempt mints. Never done for a 429.
        session.forget(token);
      }
      setProblem(messageFor(error));
      setStarting(false);
    }
  }

  return (
    <Dialog
      open
      onClose={starting ? undefined : onClose}
      maxWidth="sm"
      fullWidth
      slotProps={{
        paper: {
          variant: "outlined",
          sx: { bgcolor: paper["050"], borderColor: paper["300"], borderRadius: 2 },
        },
      }}
    >
      <Box sx={{ px: 3.75, pt: 3.25, pb: 1 }}>
        <Typography
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
          Ready to read
        </Typography>
        <Typography
          component="h2"
          sx={{
            mt: 1,
            fontFamily: serif,
            fontWeight: 600,
            fontSize: "1.625rem",
            lineHeight: 1.2,
            color: paper["950"],
          }}
        >
          How should this be read?
        </Typography>
      </Box>

      <Box sx={{ px: 3.75, py: 2, display: "flex", gap: 2.25, alignItems: "flex-start" }}>
        <Box sx={{ width: 104, flex: "none" }}>
          <Box
            component="img"
            src={image.previewUrl}
            alt=""
            sx={{
              width: "100%",
              maxHeight: 140,
              objectFit: "contain",
              display: "block",
              border: `1px solid ${paper["300"]}`,
              borderRadius: 1,
              bgcolor: paper["000"],
            }}
          />
          <Box
            sx={{
              mt: 0.75,
              fontFamily: mono,
              fontSize: "0.6875rem",
              lineHeight: 1.4,
              color: paper["500"],
            }}
          >
            {image.file.name}
            <br />
            {image.width} × {image.height}
          </Box>
        </Box>

        <Box sx={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 1.25 }}>
          <Typography sx={{ fontSize: "0.875rem", lineHeight: 1.55, color: paper["700"] }}>
            {guessExplanation(image)}
          </Typography>

          {pipelines === null && problem === null ? (
            <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, py: 2 }}>
              <CircularProgress size={18} />
              <Typography sx={{ fontSize: "0.875rem", color: paper["600"] }}>
                Asking what this instance can run…
              </Typography>
            </Box>
          ) : (
            <Box role="radiogroup" sx={{ display: "flex", flexDirection: "column", gap: 1.25 }}>
              <PipelineOption
                title="Read a whole page"
                description="Finds every staff, then transcribes each one. Returns layout and one MusicXML for the page."
                selected={selected !== null && same(selected, PAGE_PIPELINE)}
                disabled={!pageAvailable}
                onSelect={() => setSelected(PAGE_PIPELINE)}
              />
              <PipelineOption
                title="Read a single staff"
                description="For an image that is already one cropped staff."
                selected={selected !== null && same(selected, STAFF_PIPELINE)}
                disabled={!staffAvailable}
                onSelect={() => setSelected(STAFF_PIPELINE)}
              />
            </Box>
          )}

          {pipelines !== null && !(pageAvailable && staffAvailable) && (
            <Typography sx={{ fontSize: "0.8125rem", lineHeight: 1.55, color: paper["700"] }}>
              Musibot&rsquo;s default pipelines are not available on this instance just now. Choose
              one from the pipelines below.
            </Typography>
          )}
        </Box>
      </Box>

      {pipelines !== null && (
        <Box sx={{ mx: 3.75, borderTop: `1px solid ${paper["200"]}`, pt: 1.75 }}>
          <Box
            component="button"
            type="button"
            onClick={() => setShowAll((open) => !open)}
            sx={{
              border: 0,
              background: "none",
              p: 0,
              cursor: "pointer",
              fontSize: "0.84375rem",
              fontFamily: "inherit",
              color: paper["600"],
            }}
          >
            All pipelines
          </Box>
          {showAll && (
            <AllPipelines pipelines={pipelines} selected={selected} onSelect={setSelected} />
          )}
        </Box>
      )}

      {problem !== null && (
        <Typography
          role="alert"
          sx={{
            mx: 3.75,
            mt: 2,
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

      <Box
        sx={{
          mt: 2.75,
          px: 3.75,
          py: 2,
          borderTop: `1px solid ${paper["200"]}`,
          display: "flex",
          alignItems: "center",
          gap: 1.75,
        }}
      >
        <Button
          variant="contained"
          disabled={selected === null || uploadPath === null || starting}
          onClick={() => void start()}
          sx={{ fontSize: "0.9375rem", px: 2.5, py: 1.5 }}
        >
          {starting ? "Starting…" : "Start reading"}
        </Button>
        <Button
          variant="outlined"
          disabled={starting}
          onClick={onClose}
          sx={{ fontSize: "0.9375rem", px: 2.25, py: 1.5 }}
        >
          Choose a different file
        </Button>
      </Box>
    </Dialog>
  );
}

/** What to tell the visitor, given what went wrong. */
function messageFor(error: unknown): string {
  if (error instanceof RateLimited) {
    return error.retryAfterSeconds === null
      ? "Musibot is at its public limit just now. Deleting a page you have finished with will make room."
      : `Musibot is at its public limit just now. Try again in about ${Math.ceil(error.retryAfterSeconds / 60)} minutes.`;
  }
  if (error instanceof ApiError) {
    return error.detail ?? error.message;
  }
  return "Something went wrong talking to Musibot.";
}
