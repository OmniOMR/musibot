import Box from "@mui/material/Box";
import CircularProgress from "@mui/material/CircularProgress";
import Link from "@mui/material/Link";
import Typography from "@mui/material/Typography";
import { useMemo, useState } from "react";
import { Link as RouterLink, useParams } from "react-router";

import { downloadFiles } from "../api/download";
import { SessionExpired } from "../api/errors";
import ContentWidth from "../components/ContentWidth";
import { useNow } from "../page/expiry";
import { groupFiles } from "../page/files";
import { usePageState } from "../page/usePageState";
import * as paths from "../paths";
import { find, outputsAmong } from "../pipelines";
import { useSession } from "../session/useSession";
import { mono, paper, serif } from "../theme";
import OverviewPanel from "./page/OverviewPanel";
import PageHeader from "./page/PageHeader";

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

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);

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

      <Box sx={{ flex: 1, display: "flex", alignItems: "stretch", minHeight: 0 }}>
        <OverviewPanel
          executions={state.executions}
          sections={sections}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
          onDownload={(toDownload) => void download(toDownload)}
          logLineCount={0}
          onToggleLog={() => {}}
        />

        {/* ScenePanel and TranscriptionPanel go here. */}
        <Box
          sx={{
            flex: 1,
            minWidth: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            bgcolor: paper["150"],
            color: paper["600"],
            fontSize: "0.875rem",
          }}
        >
          {state.loading ? (
            <CircularProgress size={20} />
          ) : selectedKey === null ? (
            "Choose a file on the left to see it."
          ) : (
            <Box sx={{ fontFamily: mono, fontSize: "0.8125rem" }}>{selectedKey}</Box>
          )}
        </Box>
      </Box>
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
