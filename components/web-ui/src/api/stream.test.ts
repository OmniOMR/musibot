import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { openPageFileChanges } from "./fileChanges";
import { openPageLog } from "./logStream";
import { STALL_MS, StreamStalled, openStream, parseFrame } from "./stream";
import type { FileChangeView, LogLineView } from "./types";

const LINE: LogLineView = {
  execution_id: 1,
  seconds: 1.3,
  kind: "worker",
  source: "staff-detector",
  level: "info",
  message: "transcribing staff 3/12",
};

describe("an SSE frame", () => {
  it("carries one log line as JSON", () => {
    expect(parseFrame<LogLineView>(`data: ${JSON.stringify(LINE)}`)).toEqual(LINE);
  });

  it("is nothing when it is a keepalive comment", () => {
    // What travels down an idle stream so that a proxy does not close it.
    expect(parseFrame<LogLineView>(": ping")).toBeNull();
  });

  it("is nothing when it cannot be read", () => {
    // One line of a log lost, which is no reason to stop reading the rest.
    expect(parseFrame<LogLineView>("data: {not json")).toBeNull();
  });

  it("survives the carriage returns some proxies add", () => {
    expect(parseFrame<LogLineView>(`data: ${JSON.stringify(LINE)}\r`)).toEqual(LINE);
  });
});

/** A body that hands out exactly these chunks, as a socket would. */
function bodyOf(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

function answerWith(chunks: string[]): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(bodyOf(chunks), { status: 200 })),
  );
}

async function collect<T>(stream: AsyncGenerator<T>): Promise<T[]> {
  const lines: T[] = [];
  for await (const line of stream) {
    lines.push(line);
  }
  return lines;
}

describe("reading a stream", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("yields the events the service writes", async () => {
    answerWith([
      `data: ${JSON.stringify(LINE)}\n\n`,
      `: ping\n\n`,
      `data: ${JSON.stringify(LINE)}\n\n`,
    ]);

    expect(await collect(await openPageLog("token", "7Kf2mP9xLwQa"))).toEqual([LINE, LINE]);
  });

  it("reassembles a line that arrives in pieces", async () => {
    // A chunk is bytes off a socket, not a frame — assuming otherwise is the
    // way this breaks in production and never in a test that sends one chunk.
    const frame = `data: ${JSON.stringify(LINE)}\n\n`;
    answerWith([frame.slice(0, 10), frame.slice(10, 30), frame.slice(30)]);

    expect(await collect(await openPageLog("token", "7Kf2mP9xLwQa"))).toEqual([LINE]);
  });

  it("splits two lines that arrive together", async () => {
    const frame = `data: ${JSON.stringify(LINE)}\n\n`;
    answerWith([frame + frame]);

    expect(await collect(await openPageLog("token", "7Kf2mP9xLwQa"))).toEqual([LINE, LINE]);
  });

  it("stops at the end of the body", async () => {
    answerWith([]);

    expect(await collect(await openStream<LogLineView>("/anything", "token"))).toEqual([]);
  });
});

describe("the two page streams", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("read the log with the page's token, as a POST", async () => {
    // A POST because a GET invites `EventSource`, which cannot send this
    // header — see `docs/http-api.md`.
    answerWith([]);

    await openPageLog("s3cr3t", "7Kf2mP9xLwQa");

    const [url, options] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/musicorpus-pages/7Kf2mP9xLwQa/logs");
    expect(options.method).toBe("POST");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer s3cr3t");
  });

  it("read file changes from an endpoint of their own", async () => {
    // Separate from the log because a client that only wants to know about a
    // new File should not have to read a model's warnings to find out.
    const notice: FileChangeView = { execution_id: 1, paths: ["Staves/1/transcription.musicxml"] };
    answerWith([`data: ${JSON.stringify(notice)}\n\n`]);

    const notices = await collect(await openPageFileChanges("s3cr3t", "7Kf2mP9xLwQa"));

    expect(notices).toEqual([notice]);
    const [url] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/musicorpus-pages/7Kf2mP9xLwQa/file-changes");
  });
});

describe("a stream that goes silent", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("is presumed dead rather than waited on forever", async () => {
    // The service pings every 15 seconds, so silence for three of them is a
    // connection that has gone away without saying so — which a middlebox can
    // produce and the socket may never report. Nothing polls behind these
    // streams any more, so a stall nobody notices is a page that has stopped
    // updating.
    vi.stubGlobal(
      "fetch",
      vi.fn(
        async () =>
          new Response(
            new ReadableStream({
              start() {
                // Opens, and then says nothing at all.
              },
            }),
            { status: 200 },
          ),
      ),
    );

    const stream = await openStream<LogLineView>("/anything", "token");
    const reading = stream.next();
    const failed = expect(reading).rejects.toBeInstanceOf(StreamStalled);

    await vi.advanceTimersByTimeAsync(STALL_MS + 1);
    await failed;
  });
});
