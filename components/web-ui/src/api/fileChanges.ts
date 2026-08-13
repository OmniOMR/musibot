import { openStream } from "./stream";
import type { FileChangeView } from "./types";

/**
 * The *Files* a page's executions write, announced as they are written.
 *
 * A notice is an **invitation to look**, not a description of the page: it
 * names paths and nothing else, and the answer to one is to list the page
 * again — which is where a *File's* size and modification time come from, and
 * which is true across a *File* a later execution overwrote.
 *
 * So a missed notice costs latency and nothing else, and this app does not try
 * to build a file list out of the notices it has seen. It reads them as "ask
 * again now" and nothing more.
 */
export function openPageFileChanges(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<AsyncGenerator<FileChangeView>> {
  return openStream<FileChangeView>(`/musicorpus-pages/${pageId}/file-changes`, token, signal);
}
