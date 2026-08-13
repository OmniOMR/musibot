import { afterEach, describe, expect, it, vi } from "vitest";

import { openPageLog, parseFrame } from "./logStream";
import type { LogLineView } from "./types";

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
    expect(parseFrame(`data: ${JSON.stringify(LINE)}`)).toEqual(LINE);
  });

  it("is nothing when it is a keepalive comment", () => {
    // What travels down an idle stream so that a proxy does not close it.
    expect(parseFrame(": ping")).toBeNull();
  });

  it("is nothing when it cannot be read", () => {
    // One line of a log lost, which is no reason to stop reading the rest.
    expect(parseFrame("data: {not json")).toBeNull();
  });

  it("survives the carriage returns some proxies add", () => {
    expect(parseFrame(`data: ${JSON.stringify(LINE)}\r`)).toEqual(LINE);
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

async function collect(stream: AsyncGenerator<LogLineView>): Promise<LogLineView[]> {
  const lines: LogLineView[] = [];
  for await (const line of stream) {
    lines.push(line);
  }
  return lines;
}

describe("the log stream", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("yields the lines the service writes", async () => {
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

  it("asks for the stream with the page's token", async () => {
    answerWith([]);

    await openPageLog("s3cr3t", "7Kf2mP9xLwQa");

    const [url, options] = vi.mocked(fetch).mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/musicorpus-pages/7Kf2mP9xLwQa/logs");
    expect(options.method).toBe("POST");
    expect((options.headers as Record<string, string>).Authorization).toBe("Bearer s3cr3t");
  });
});
