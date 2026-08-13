import { apiFetch } from "./client";
import type { LogLineView } from "./types";

/**
 * The log of one *MusicorpusPage*, as it is written.
 *
 * A `POST` read with `fetch` rather than an `EventSource`, because the stream
 * is authenticated like every other call — with a bearer token in a header,
 * which `EventSource` cannot send. The usual way round that is a token in the
 * query string, where it lands in proxy logs and browser history, and the
 * service declines to offer it; see `docs/http-api.md`.
 *
 * Nothing is replayed. The service holds no buffer — a line produced while
 * nobody was watching is gone — so a caller that wants a whole execution's log
 * opens this before starting the execution, and a reconnection resumes rather
 * than catches up.
 */
export async function openPageLog(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<AsyncGenerator<LogLineView>> {
  const response = await apiFetch("POST", `/musicorpus-pages/${pageId}/logs`, {
    token,
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (response.body === null) {
    throw new Error("The log stream answered with no body");
  }

  // Opening and reading are separated so that a caller can tell "the stream is
  // up" from "the stream said something": a watcher that reconnects wants to
  // stop saying so the moment it is connected, not when the next line happens
  // to arrive, which for a silent *Model* may be a minute later.
  return readLines(response.body.getReader());
}

async function* readLines(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<LogLineView> {
  const decoder = new TextDecoder();
  let buffered = "";

  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) {
        return;
      }

      // A chunk is bytes off a socket, not a frame: one frame may arrive in
      // two chunks and two frames in one, so the boundary is found here rather
      // than assumed. `stream: true` keeps a multi-byte character split across
      // chunks from being decoded as two broken ones.
      buffered += decoder.decode(value, { stream: true });

      let boundary = buffered.indexOf("\n\n");
      while (boundary !== -1) {
        const frame = buffered.slice(0, boundary);
        buffered = buffered.slice(boundary + 2);
        const line = parseFrame(frame);
        if (line !== null) {
          yield line;
        }
        boundary = buffered.indexOf("\n\n");
      }
    }
  } finally {
    // Whoever stops reading — an unmount, a `break` — closes the connection,
    // which is what tells the service nobody is watching this page any more.
    await reader.cancel().catch(() => undefined);
  }
}

/**
 * One SSE frame as a log line, or null if it carries none.
 *
 * A frame with no `data:` field is a keepalive comment (`: ping`), which is
 * what keeps a proxy from closing an idle stream and means nothing here.
 */
export function parseFrame(frame: string): LogLineView | null {
  const data = frame
    .split("\n")
    .map((field) => field.replace(/\r$/, ""))
    .filter((field) => field.startsWith("data:"))
    .map((field) => field.slice("data:".length).trimStart())
    .join("\n");

  if (data === "") {
    return null;
  }

  try {
    return JSON.parse(data) as LogLineView;
  } catch {
    // A frame this app cannot read is one line of a log lost, and there is
    // nothing useful to do about it but keep reading the rest.
    return null;
  }
}
