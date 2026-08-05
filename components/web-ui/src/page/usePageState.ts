import { useCallback, useEffect, useRef, useState } from "react";

import { getPage, listFiles, listPipelines } from "../api/client";
import { ApiError } from "../api/errors";
import type { FileView, PipelineExecutionView, PipelineView } from "../api/types";

/**
 * What a page looks like right now, kept fresh by polling.
 *
 * **Polling, not streaming, and on purpose for now.** `docs/http-api.md`
 * promises an SSE stream and it is not implemented, so a running execution is
 * watched by asking. The consequence is visible and worth stating: a finished
 * execution's outputs appear together rather than one at a time, so this shows
 * a spinner and never a count of files-so-far. It must not be replaced by a
 * fabricated progress bar — an image-to-sequence model does not know its own
 * output length, so there is no percentage to report even once streaming
 * exists.
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
