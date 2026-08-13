import { useEffect, useState } from "react";

import { ApiError, SessionExpired } from "../api/errors";
import { openPageLog } from "../api/logStream";
import { RECONNECT_MS } from "../api/stream";
import type { LogLineView } from "../api/types";

/**
 * The recognition log of a *MusicorpusPage*.
 *
 * One log for the page rather than one per *Pipeline Execution*: a page may be
 * read twice, and somebody debugging a reading wants the whole story in the
 * order it happened, not two stories to interleave by hand.
 *
 * The stream is held open for as long as this screen is, and not only while
 * something is running. Nothing is replayed — the service keeps no buffer, so a
 * line produced while nobody was watching is gone — and a stream opened only
 * once an execution had started would miss its first lines. The cost is one
 * idle connection per open page, which the service is happy to hold.
 *
 * Lines accumulate here rather than in the panel, so collapsing the panel and
 * opening it again shows the whole log rather than whatever arrived since. A
 * browser reload does lose it, which is what "no buffer" means.
 */

/** One line of the log, as the panel draws it. */
export interface LogLine {
  /** Seconds into its *Pipeline Execution*, already formatted. */
  at: string;
  text: string;
  /** `error` is the only line worth colouring; everything else is ink. */
  tone: "normal" | "error";
}

export interface PageLog {
  lines: LogLine[];
  /** Set when the log is not being watched and will not resume by itself. */
  problem: string | null;
}

/**
 * How the panel draws one line.
 *
 * The service's own lines carry the story of the execution — what was started,
 * what it produced, how long it took — and are shown unattributed, because
 * "api:" in front of them would be noise. Everything else is named by the
 * *Model* or *Pipeline* that printed it, which is the only way to tell two
 * models apart in one reading.
 */
export function toLogLine(view: LogLineView): LogLine {
  return {
    at: view.seconds.toFixed(1).padStart(4, "0"),
    text: view.kind === "api" ? view.message : `${view.source}: ${view.message}`,
    // A `warning` stays ink: a *Model's* stderr is forwarded at that level, and
    // libraries write perfectly ordinary chatter there.
    tone: view.level === "error" ? "error" : "normal",
  };
}

export function usePageLog(pageId: string, token: string | null): PageLog {
  const [lines, setLines] = useState<LogLine[]>([]);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    if (token === null) {
      return;
    }

    // A different page is a different log. Without this, switching pages would
    // show the previous one's lines until the new ones caught up.
    setLines([]);
    setProblem(null);

    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function watch() {
      try {
        const stream = await openPageLog(token!, pageId, controller.signal);
        // Connected. Said now rather than when the next line arrives, which for
        // a page nothing is being done to may be never.
        setProblem(null);

        for await (const view of stream) {
          setLines((shown) => [...shown, toLogLine(view)]);
        }
        // The service ended the stream: the page is gone, or the service
        // restarted. Either way there is nothing further to watch.
        if (!controller.signal.aborted) {
          setProblem("The log stream ended.");
        }
      } catch (caught) {
        if (controller.signal.aborted) {
          return; // an unmount, not a failure
        }
        if (
          caught instanceof SessionExpired ||
          (caught instanceof ApiError && caught.status === 404)
        ) {
          setProblem("This page is no longer available.");
          return;
        }
        // A dropped connection, most likely. Try again — a *User* watching a
        // page being read should not have to reload to keep watching.
        setProblem("Reconnecting…");
        timer = setTimeout(() => void watch(), RECONNECT_MS);
      }
    }

    void watch();

    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [pageId, token]);

  return { lines, problem };
}
