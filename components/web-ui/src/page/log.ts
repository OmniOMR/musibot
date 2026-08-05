import { useEffect, useState } from "react";

/**
 * The recognition log of a *MusicorpusPage*.
 *
 * One log for the page rather than one per *Pipeline Execution*: a page may be
 * read twice, and somebody debugging a reading wants the whole story in the
 * order it happened, not two stories to interleave by hand.
 *
 *
 * ## The lines below are fake, and this is the file that has to change
 *
 * Nothing real produces them yet. The api service has no log endpoint and the
 * SSE protocol behind it is not designed — `docs/http-api.md` marks streaming
 * TBA. What is written here is a stand-in that arrives on a timer, so that the
 * panel can be built and looked at properly: the zebra striping needs several
 * lines to be visible at all, the pill's count needs something to count, and
 * "does it scroll sensibly as lines arrive" is not a question a static mock
 * answers.
 *
 * When the endpoint exists, **the change is to this file and to nothing that
 * renders**. `LogPanel` already takes the shape below; replace `simulate` with
 * a subscription that appends to the same state and the panel will not know the
 * difference. Concretely, what the real implementation has to do that this one
 * does not:
 *
 * - open the stream for `pageId`, authenticated with `token` — both are already
 *   parameters here for that reason, and both are already correct at the call
 *   site;
 * - keep the connection across a re-render, and close it on unmount;
 * - reconnect when it drops, without replaying lines already shown;
 * - accumulate rather than replace, because the transport delivers increments
 *   and the panel wants the whole page's history;
 * - stop when every execution has finished, the way `usePageState` stops
 *   polling, so that an idle tab is not a standing load on a shared tier.
 *
 * The one thing that must survive the swap is the timestamp. It is seconds
 * elapsed since the page's first execution began, not a wall clock, because
 * what a reader is judging is how long a step took rather than what time of day
 * it was.
 */

/** One line of the log, as the panel draws it. */
export interface LogLine {
  /** Seconds since the first execution began, already formatted. */
  at: string;
  text: string;
  /** `error` is the only line worth colouring; everything else is ink. */
  tone: "normal" | "error";
}

export interface PageLog {
  lines: LogLine[];
  /** True while lines are still arriving, which the panel shows as a cursor. */
  streaming: boolean;
  /**
   * False until a real log exists. The panel says so rather than letting the
   * stand-in be mistaken for the recognition that actually ran.
   */
  real: boolean;
}

/**
 * A plausible reading, borrowed from the design's own simulation.
 *
 * Deliberately not derived from the page's real executions. A stand-in that
 * quoted the actual pipeline names would be much harder to tell from a real
 * log, and the one thing this must not do is be mistaken for one.
 */
const SIMULATED: LogLine[] = [
  { at: "00.0", text: "POST /api/musicorpus-pages → 201", tone: "normal" },
  { at: "00.2", text: "execution 1: page-to-musicxml v1.2 queued", tone: "normal" },
  { at: "01.1", text: "staff-detector v0.4: 7 staves", tone: "normal" },
  { at: "01.3", text: "layout.json written (2.1 kB)", tone: "normal" },
  { at: "02.0", text: "crnn-handwritten v2.1: staff 1/7", tone: "normal" },
  { at: "02.9", text: "crnn-handwritten v2.1: staff 2/7", tone: "normal" },
  { at: "03.7", text: "crnn-handwritten v2.1: staff 3/7", tone: "normal" },
  { at: "04.4", text: "staff 3: low confidence on 2 symbols", tone: "error" },
  { at: "05.1", text: "crnn-handwritten v2.1: staff 4/7", tone: "normal" },
  { at: "06.0", text: "crnn-handwritten v2.1: staff 5/7", tone: "normal" },
  { at: "06.8", text: "crnn-handwritten v2.1: staff 6/7", tone: "normal" },
  { at: "07.6", text: "crnn-handwritten v2.1: staff 7/7", tone: "normal" },
  { at: "08.1", text: "assembling transcription.musicxml", tone: "normal" },
  { at: "08.4", text: "transcription.musicxml written (41 kB)", tone: "normal" },
  { at: "08.4", text: "execution 1 finished in 8.4 s", tone: "normal" },
];

/**
 * How fast the stand-in plays.
 *
 * The timestamps are the ones a real run would print; playing them back at
 * full speed would mean nine seconds of watching, which is a long time to wait
 * to see whether a panel scrolls. A quarter of that is enough to see lines
 * arrive one at a time.
 */
const PLAYBACK = 0.25;

export function usePageLog(pageId: string, token: string | null): PageLog {
  const [lines, setLines] = useState<LogLine[]>([]);

  useEffect(() => {
    if (token === null) {
      return;
    }

    // A different page is a different log. Without this, switching pages would
    // show the previous one's lines until the new ones caught up.
    setLines([]);

    const timers = SIMULATED.map((line, index) =>
      setTimeout(
        () => setLines((shown) => [...shown, line]),
        Number.parseFloat(line.at) * 1000 * PLAYBACK + index,
      ),
    );

    return () => {
      for (const timer of timers) {
        clearTimeout(timer);
      }
    };
  }, [pageId, token]);

  return { lines, streaming: lines.length < SIMULATED.length, real: false };
}
