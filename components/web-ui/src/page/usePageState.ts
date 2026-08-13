import { useCallback, useEffect, useRef, useState } from "react";

import { getPage, listFiles, listPipelines } from "../api/client";
import { ApiError } from "../api/errors";
import { openPageFileChanges } from "../api/fileChanges";
import { RECONNECT_MS } from "../api/stream";
import type { FileView, PipelineExecutionView, PipelineView } from "../api/types";

/**
 * What a page looks like right now: polled, and nudged by the file-change
 * stream.
 *
 * **Execution state is polled**, because nothing pushes it yet — a stream of
 * execution results is planned at the *User* level rather than the page level,
 * for a client holding many pages at once. So a running execution is still
 * watched by asking every 1.5 seconds, and this shows a spinner and never a
 * count. It must not be replaced by a fabricated progress bar — an
 * image-to-sequence model does not know its own output length, so there is no
 * percentage to report, which is why Musibot reports none anywhere.
 *
 * **Files are pushed.** A notice on the file-change stream means "ask again
 * now", and this asks — rather than building a listing out of the paths it has
 * been told about, which would be a second, worse copy of what object storage
 * already knows, and would go stale the moment an execution overwrote a *File*.
 * A missed notice therefore costs nothing but the wait until the next poll.
 *
 * Polling stops the moment nothing is running. An idle page costs one request
 * on arrival and nothing after it, which matters when the public tier is one
 * shared pool and every visitor's open tab would otherwise be a permanent load.
 */
export interface PageState {
  executions: PipelineExecutionView[];
  files: FileView[];
  /** The listing, for reading signatures. Fetched once. */
  pipelines: PipelineView[];
  /** True until the first answer arrives. */
  loading: boolean;
  /** Set when the page cannot be shown at all. */
  error: ApiError | Error | null;
  /** Ask again now — after starting an execution, say. */
  refresh: () => void;
}

const POLL_INTERVAL_MS = 1500;

/** A state the service will not move out of on its own. */
function isFinished(execution: PipelineExecutionView): boolean {
  return execution.state === "completed" || execution.state === "failed";
}

export function usePageState(pageId: string, token: string | null): PageState {
  const [executions, setExecutions] = useState<PipelineExecutionView[]>([]);
  const [files, setFiles] = useState<FileView[]>([]);
  const [pipelines, setPipelines] = useState<PipelineView[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | Error | null>(null);

  /** Bumped to ask again out of turn. */
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((n) => n + 1), []);

  /**
   * Whether anything is running, as the poll loop sees it. A ref rather than
   * state because the loop reads it between ticks and re-reading it must not
   * be a reason to restart the loop.
   */
  const running = useRef(true);

  useEffect(() => {
    if (token === null) {
      return;
    }

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const [page, listing] = await Promise.all([
          getPage(token!, pageId),
          listFiles(token!, pageId),
        ]);
        if (cancelled) {
          return;
        }
        setExecutions(page.executions);
        setFiles(listing.files);
        setError(null);
        running.current = page.executions.some((execution) => !isFinished(execution));
      } catch (caught) {
        if (cancelled) {
          return;
        }
        setError(caught instanceof Error ? caught : new Error(String(caught)));
        // Stop asking. Whatever went wrong — the session ended, the page was
        // deleted — will not be fixed by asking again every second and a half.
        running.current = false;
      } finally {
        if (!cancelled) {
          setLoading(false);
          if (running.current) {
            timer = setTimeout(() => void poll(), POLL_INTERVAL_MS);
          }
        }
      }
    }

    running.current = true;
    void poll();

    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [pageId, token, nonce]);

  // The file-change stream, held open for as long as this page is: a notice
  // means "ask again now", and asking is what makes a *File* appear as it is
  // written rather than up to a poll later. It has to be open before an
  // execution starts, since nothing is replayed.
  useEffect(() => {
    if (token === null) {
      return;
    }

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function watch() {
      try {
        const notices = await openPageFileChanges(token!, pageId, controller.signal);
        // The paths a notice carries are deliberately not read: what the page
        // holds is object storage's to answer, and a listing built from
        // notices would go stale the moment an execution overwrote a *File*.
        for await (const notice of notices) {
          void notice;
          try {
            const listing = await listFiles(token!, pageId);
            if (!controller.signal.aborted) {
              setFiles(listing.files);
            }
          } catch {
            // The poll will catch up. A notice is only an invitation to look.
          }
        }
      } catch (caught) {
        if (controller.signal.aborted) {
          return; // an unmount, not a failure
        }
        if (caught instanceof ApiError && (caught.status === 401 || caught.status === 404)) {
          return; // the session ended or the page is gone; polling reports it
        }
        timer = setTimeout(() => void watch(), RECONNECT_MS);
      }
    }

    void watch();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [pageId, token]);

  // The listing is asked for once: it is about the instance rather than the
  // page, and it is only read for signatures.
  useEffect(() => {
    if (token === null) {
      return;
    }
    let cancelled = false;
    void (async () => {
      try {
        const listing = await listPipelines(token);
        if (!cancelled) {
          setPipelines(listing.pipelines);
        }
      } catch {
        // Not fatal. Without it a file cannot be flagged as about to be
        // overwritten, which is a missing hint rather than a broken page.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  return { executions, files, pipelines, loading, error, refresh };
}
