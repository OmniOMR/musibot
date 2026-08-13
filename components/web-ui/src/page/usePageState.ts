import { useCallback, useEffect, useRef, useState } from "react";

import { getPage, listFiles, listPipelines } from "../api/client";
import { ApiError } from "../api/errors";
import { openPageFileChanges } from "../api/fileChanges";
import { openExecutionResults } from "../api/results";
import { RECONNECT_MS } from "../api/stream";
import type { FileView, PipelineExecutionView, PipelineView } from "../api/types";

/**
 * What a page looks like right now, kept fresh by two streams.
 *
 * **Nothing is polled.** The page is asked about once when the screen opens,
 * and after that the service says what changed: the file-change stream when an
 * execution writes a *File*, and the result stream when one ends. An idle page
 * costs two open connections and no requests at all, where polling cost a
 * request every 1.5 seconds for as long as anything was running.
 *
 * **Every connection reconciles.** Neither stream replays, so an execution that
 * ended while the connection was down is never announced — which is why the
 * page is asked about again on each *re*connect rather than trusted to have
 * been told everything. A stream that goes silent for 45 seconds is presumed
 * dead and reconnected (see `api/stream.ts`), which is what makes dropping the
 * poll safe: without that, a connection killed by a middlebox would leave a
 * page that has simply stopped updating.
 *
 * There is still no percentage anywhere, and there must not be: an
 * image-to-sequence model does not know how long its own output will be, so
 * Musibot reports no progress at all — a running execution shows a spinner, and
 * its log says what it is doing.
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

/** An error that means asking again will not help. */
function isFinal(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 401 || error.status === 404);
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

  /** What the page holds and what has run, both from the service. */
  const load = useCallback(
    async (signal?: AbortSignal) => {
      const [page, listing] = await Promise.all([
        getPage(token!, pageId, signal),
        listFiles(token!, pageId, signal),
      ]);
      setExecutions(page.executions);
      setFiles(listing.files);
      setError(null);
    },
    [pageId, token],
  );

  // The one unconditional ask: when the screen opens, and whenever something
  // asks for it again.
  useEffect(() => {
    if (token === null) {
      return;
    }
    const controller = new AbortController();

    void (async () => {
      try {
        await load(controller.signal);
      } catch (caught) {
        if (!controller.signal.aborted) {
          setError(caught instanceof Error ? caught : new Error(String(caught)));
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      }
    })();

    return () => controller.abort();
  }, [load, token, nonce]);

  // Executions, from the result stream. It is scoped to the *User*, so it
  // carries every page of this token's identity and this filters to ours —
  // which costs nothing and is what lets one connection serve a client holding
  // many pages at once.
  const connected = useRef(false);
  useEffect(() => {
    if (token === null) {
      return;
    }

    connected.current = false;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function watch() {
      try {
        const results = await openExecutionResults(token!, controller.signal);

        // Reconnecting means having missed whatever ended in the meantime, and
        // nothing is replayed. The first connection needs no such catching up:
        // the effect above has just asked.
        if (connected.current) {
          await load(controller.signal).catch(() => undefined);
        }
        connected.current = true;

        for await (const result of results) {
          if (result.page_id !== pageId) {
            continue; // another page of this identity, and none of our business
          }
          setExecutions((shown) => replaceExecution(shown, result.execution));
        }
      } catch (caught) {
        if (controller.signal.aborted || isFinal(caught)) {
          return; // an unmount, or a page that is gone; the fetch above reports it
        }
      }
      if (!controller.signal.aborted) {
        timer = setTimeout(() => void watch(), RECONNECT_MS);
      }
    }

    void watch();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [pageId, token, load]);

  // Files, from the file-change stream: a notice means "ask again now", and
  // asking is what makes a *File* appear as it is written. It has to be open
  // before an execution starts, since nothing is replayed.
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
            const listing = await listFiles(token!, pageId, controller.signal);
            if (!controller.signal.aborted) {
              setFiles(listing.files);
            }
          } catch {
            // Not fatal: the next notice, or the next reconnect, asks again.
          }
        }
      } catch (caught) {
        if (controller.signal.aborted || isFinal(caught)) {
          return;
        }
      }
      if (!controller.signal.aborted) {
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

/**
 * The executions, with this one's news folded in.
 *
 * An execution the app has not seen is appended rather than ignored: a result
 * can arrive before the fetch that would have introduced it, and a finished
 * execution nobody displays is worse than one that appears in its final state.
 */
export function replaceExecution(
  shown: PipelineExecutionView[],
  ended: PipelineExecutionView,
): PipelineExecutionView[] {
  const known = shown.some((execution) => execution.execution_id === ended.execution_id);
  return known
    ? shown.map((execution) => (execution.execution_id === ended.execution_id ? ended : execution))
    : [...shown, ended];
}
