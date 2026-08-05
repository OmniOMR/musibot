import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams } from "react-router";

import { downloadFiles } from "../api/download";
import { SessionExpired } from "../api/errors";
import ContentWidth from "../components/ContentWidth";
import NoticeCard from "../components/NoticeCard";
import { useNow } from "../page/expiry";
import { groupFiles } from "../page/files";
import { finishedEmpty } from "../page/outcome";
import { usePageLog } from "../page/log";
import { usePageState } from "../page/usePageState";
import * as paths from "../paths";
import { find, outputsAmong } from "../pipelines";
import { useSession } from "../session/useSession";
import { paper, serif } from "../theme";
import LogPanel from "./page/LogPanel";
import OverviewPanel from "./page/OverviewPanel";
import PageHeader from "./page/PageHeader";
import RunPipelineDialog from "./page/RunPipelineDialog";
import ScenePanel from "./page/ScenePanel";
import TranscriptionPanel from "./page/TranscriptionPanel";
import { opensTranscription } from "../transcription/transcription";

/**
 * One *MusicorpusPage* — the screen the work happens on.
 *
 * Full height and full width rather than set in a content column, because it is
 * a workspace and not a document: four panels that divide the window between
 * them, each scrolling on its own.
 *
 * A page can only be opened in the browser that created it. Reaching one needs
 * the token it was created under, which lives in this browser's `localStorage`
 * and is deliberately never in the URL — so a pasted link is not a way in, and
 * this screen says so rather than showing an empty workspace.
 */
export default function MusicorpusPageScreen() {
  const { pageId = "" } = useParams();
  const session = useSession();
  const now = useNow();

  const token = session.tokenForPage(pageId);
  const tracked = session.pages.find((page) => page.pageId === pageId);
  const state = usePageState(pageId, token);
  const log = usePageLog(pageId, token);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  /** Collapsed by default — the log is for a reader who has gone looking. */
  const [logOpen, setLogOpen] = useState(false);
  const [running, setRunning] = useState(false);

  /**
   * Which of the page's *Files* a running execution is about to replace.
   *
   * Read from the running pipelines' declared outputs rather than guessed. A
   * visitor about to download a file that is going to be rewritten in ten
   * seconds should hear it before they click.
   */
  const overwritten = useMemo(() => {
    const paths_ = state.files.map((file) => file.path);
    return state.executions
      .filter((execution) => execution.state === "running" || execution.state === "queued")
      .flatMap((execution) => {
        const pipeline = find(state.pipelines, {
          name: execution.pipeline_name,
          version: execution.pipeline_version,
        });
        return pipeline === undefined ? [] : outputsAmong(paths_, pipeline.signature);
      });
  }, [state.files, state.executions, state.pipelines]);

  const sections = useMemo(
    () =>
      groupFiles(state.files, {
        // What the visitor uploaded is the input of the first execution — the
        // one file on the page they already have a copy of.
        sourcePath: state.executions[0]?.input[0] ?? null,
        overwritten,
      }),
    [state.files, state.executions, overwritten],
  );

  const results = useMemo(
    () =>
      sections
        .flatMap((section) => section.rows.filter((row) => !row.isSource))
        .flatMap((row) => row.paths),
    [sections],
  );

  const empty = useMemo(
    () => finishedEmpty(state.executions, state.pipelines, state.files),
    [state.executions, state.pipelines, state.files],
  );

  /** The row the canvas is showing, which is the selection made whole. */
  const selectedRow = useMemo(
    () =>
      sections.flatMap((section) => section.rows).find((row) => row.key === selectedKey) ?? null,
    [sections, selectedKey],
  );

  async function download(toDownload: string[]) {
    if (token === null) {
      return;
    }
    setProblem(null);
    try {
      await downloadFiles(token, pageId, toDownload);
    } catch (error) {
      setProblem(error instanceof Error ? error.message : "That could not be downloaded.");
    }
  }

  if (token === null) {
    return <NotInThisBrowser />;
  }

  if (state.error instanceof SessionExpired) {
    return <Expired />;
  }

  return (
    <Box sx={{ height: "100vh", display: "flex", flexDirection: "column", minHeight: 0 }}>
      <PageHeader
        pageId={pageId}
        fileName={tracked?.fileName ?? null}
        expiresAt={session.expiryOf(pageId)}
        now={now}
        downloadable={results.length}
        onDownloadResults={() => void download(results)}
      />

      {problem !== null && (
        <Box
          role="alert"
          sx={{
            px: 2.5,
            py: 1.25,
            borderBottom: `1px solid ${paper["200"]}`,
            bgcolor: paper["100"],
            fontSize: "0.84375rem",
            color: paper["900"],
          }}
        >
          {problem}
        </Box>
      )}

      {/* Finished, succeeded, and produced nothing — the outcome that looks
          like no outcome at all. Said here rather than left to be inferred
          from a file list that has not changed. */}
      {empty !== null && (
        <Box
          sx={{ px: 2.5, py: 2, borderBottom: `1px solid ${paper["200"]}`, bgcolor: paper["100"] }}
        >
          <NoticeCard
            title="No music found on this page"
            actions={
              <>
                <Button variant="contained" onClick={() => setRunning(true)}>
                  Try another pipeline
                </Button>
                <Button variant="outlined" onClick={() => setLogOpen(true)}>
                  See the log
                </Button>
              </>
            }
          >
            {empty.pipeline_name} v{empty.pipeline_version} finished without error, but wrote
            nothing it said it would. Pages photographed at an angle, or scanned at a low
            resolution, are the usual cause — as is asking a pipeline to read a whole page when the
            image is one cropped staff, or the other way round.
          </NoticeCard>
        </Box>
      )}

      <Box sx={{ flex: 1, display: "flex", alignItems: "stretch", minHeight: 0 }}>
        <OverviewPanel
          executions={state.executions}
          sections={sections}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
          onDownload={(toDownload) => void download(toDownload)}
          onRunPipeline={() => setRunning(true)}
          logLineCount={log.lines.length}
          logOpen={logOpen}
          onToggleLog={() => setLogOpen((open) => !open)}
        />

        <ScenePanel pageId={pageId} token={token} selected={selectedRow} files={state.files} />

        {/* Only while there is a reading to put beside the scan. */}
        {opensTranscription(selectedRow) && (
          <TranscriptionPanel
            pageId={pageId}
            token={token}
            selected={selectedRow}
            files={state.files}
          />
        )}
      </Box>

      {/* Across the full width, under every panel: the log is about the page,
          not about whichever one of them is in focus. */}
      {logOpen && (
        <LogPanel
          lines={log.lines}
          streaming={log.streaming}
          real={log.real}
          onCollapse={() => setLogOpen(false)}
        />
      )}

      {running && (
        <RunPipelineDialog
          pageId={pageId}
          token={token}
          pipelines={state.pipelines}
          files={state.files}
          onClose={() => setRunning(false)}
          // Ask again immediately rather than waiting for the next poll: the
          // new execution is the thing the visitor is now watching for, and it
          // also restarts polling, which had stopped when the page went idle.
          onStarted={state.refresh}
        />
      )}
    </Box>
  );
}

/** The page is real, but not reachable from here. */
function NotInThisBrowser() {
  return (
    <ContentWidth>
      <Box sx={{ py: 10, maxWidth: "var(--measure-body)" }}>
        <Typography variant="h1" sx={{ fontSize: "2.25rem", mb: 2 }}>
          This page was not uploaded from this browser
        </Typography>
        <Typography sx={{ mb: 2, color: paper["700"], lineHeight: 1.65 }}>
          Musibot has no accounts. A page is reached with the token it was created under, which is
          kept in the browser that uploaded it and never travels in the address — so a Musibot link
          cannot be passed to somebody else, or opened on another machine.
        </Typography>
        <Link component={RouterLink} to={paths.LANDING}>
          Upload a page
        </Link>
      </Box>
    </ContentWidth>
  );
}

/** The hour ran out, or the service restarted. Same consequence either way. */
function Expired() {
  return (
    <ContentWidth>
      <Box sx={{ py: 10, maxWidth: "var(--measure-body)" }}>
        <Typography variant="h1" sx={{ fontFamily: serif, fontSize: "2.25rem", mb: 2 }}>
          This page has been deleted
        </Typography>
        <Typography sx={{ mb: 2, color: paper["700"], lineHeight: 1.65 }}>
          Pages and their results are kept for about an hour from upload and are then removed.
          Nothing here was stored under an account, so there is no copy to restore.
        </Typography>
        <Link component={RouterLink} to={paths.LANDING}>
          Read another page
        </Link>
      </Box>
    </ContentWidth>
  );
}
