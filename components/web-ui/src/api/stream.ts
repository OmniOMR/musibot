import { apiFetch } from "./client";

/**
 * Reading one of the API's Server-Sent-Events streams.
 *
 * Every one of them is a `POST` read with `fetch` rather than an `EventSource`,
 * because they are authenticated like every other call — with a bearer token in
 * a header, which `EventSource` cannot send. The usual way round that is a
 * token in the query string, where it lands in proxy logs and browser history,
 * and the service declines to offer it; see `docs/http-api.md`.
 *
 * Nothing any of them carries is replayed: the service holds no buffer, so a
 * caller that wants a whole execution's worth opens the stream before starting
 * the execution, and a reconnection resumes rather than catches up.
 */
/** How long to wait before opening a stream again after it dropped. */
export const RECONNECT_MS = 2000;

export async function openStream<T>(
  path: string,
  token: string,
  signal?: AbortSignal,
): Promise<AsyncGenerator<T>> {
  const response = await apiFetch("POST", path, {
    token,
    signal,
    headers: { Accept: "text/event-stream" },
  });

  if (response.body === null) {
    throw new Error(`The stream at ${path} answered with no body`);
  }

  // Opening and reading are separated so that a caller can tell "the stream is
  // up" from "the stream said something": a watcher that reconnects wants to
  // stop saying so the moment it is connected, not when the next event happens
  // to arrive, which on a quiet page may be a minute later.
  return readEvents<T>(response.body.getReader());
}

async function* readEvents<T>(reader: ReadableStreamDefaultReader<Uint8Array>): AsyncGenerator<T> {
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
        const event = parseFrame<T>(frame);
        if (event !== null) {
          yield event;
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
 * One SSE frame as an event, or null if it carries none.
 *
 * A frame with no `data:` field is a keepalive comment (`: ping`), which is
 * what keeps a proxy from closing an idle stream and means nothing here.
 */
export function parseFrame<T>(frame: string): T | null {
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
    return JSON.parse(data) as T;
  } catch {
    // A frame this app cannot read is one event lost, and there is nothing
    // useful to do about it but keep reading the rest.
    return null;
  }
}
