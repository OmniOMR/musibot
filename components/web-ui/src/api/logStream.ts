import { openStream } from "./stream";
import type { LogLineView } from "./types";

/**
 * The log of one *MusicorpusPage*, as it is written.
 *
 * One stream per page rather than per *Pipeline Execution*, since a page may be
 * read several times and the whole story in order is what a reader wants; each
 * line names the execution it belongs to. Nothing is replayed — see
 * `api/stream.ts` for what that means and why.
 */
export function openPageLog(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<AsyncGenerator<LogLineView>> {
  return openStream<LogLineView>(`/musicorpus-pages/${pageId}/logs`, token, signal);
}
