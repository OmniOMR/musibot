import { describe, expect, it } from "vitest";

import type { FileView } from "../api/types";
import type { FileRow } from "../page/files";
import { opensTranscription, pathsOf, readingsFor, tokensOf } from "./transcription";

function file(path: string): FileView {
  return { path, size: 100, last_modified: "2026-08-05T12:00:00Z" };
}

function row(label: string, paths: string[]): FileRow {
  return {
    key: label,
    label,
    prefix: "",
    name: label,
    paths,
    size: 100,
    instances: paths.length > 1 ? paths.length : null,
    isSource: false,
    willBeOverwritten: false,
  };
}

describe("opensTranscription", () => {
  it("opens for either transcription format", () => {
    expect(opensTranscription(row("transcription.musicxml", ["transcription.musicxml"]))).toBe(
      true,
    );
    expect(opensTranscription(row("transcription.lmx", ["transcription.lmx"]))).toBe(true);
  });

  it("stays shut for anything the panel has nothing to say about", () => {
    // Half a canvas is worth more than a column explaining that it is empty.
    expect(opensTranscription(row("layout.json", ["layout.json"]))).toBe(false);
    expect(opensTranscription(row("image.jpg", ["image.jpg"]))).toBe(false);
    expect(opensTranscription(null)).toBe(false);
  });
});

describe("readingsFor", () => {
  const PAGE = [file("image.jpg"), file("transcription.musicxml"), file("transcription.lmx")];

  it("gives one reading for a page-level transcription, with no label", () => {
    const readings = readingsFor(row("transcription.musicxml", ["transcription.musicxml"]), PAGE);

    expect(readings).toHaveLength(1);
    expect(readings[0].label).toBeNull();
    expect(readings[0].musicXmlPath).toBe("transcription.musicxml");
    expect(readings[0].lmxPath).toBe("transcription.lmx");
  });

  it("finds both formats however the selection was made", () => {
    // Selecting the tokens shows the notation too; they are two views of one
    // answer and nobody wants to click twice.
    const readings = readingsFor(row("transcription.lmx", ["transcription.lmx"]), PAGE);

    expect(readings[0].musicXmlPath).toBe("transcription.musicxml");
    expect(readings[0].lmxPath).toBe("transcription.lmx");
  });

  it("gives one reading per staff, labelled and in numeric order", () => {
    const files = [
      file("Staves/1/transcription.musicxml"),
      file("Staves/2/transcription.musicxml"),
      file("Staves/10/transcription.musicxml"),
    ];
    const readings = readingsFor(
      row(
        "Staves/{s}/transcription.musicxml",
        files.map((f) => f.path),
      ),
      files,
    );

    expect(readings.map((reading) => reading.label)).toEqual(["staff 1", "staff 2", "staff 10"]);
  });

  it("reports a format the folder does not hold as absent rather than guessing", () => {
    const files = [file("Staves/1/transcription.lmx")];
    const readings = readingsFor(row("Staves/{s}/transcription.lmx", [files[0].path]), files);

    expect(readings[0].lmxPath).toBe("Staves/1/transcription.lmx");
    expect(readings[0].musicXmlPath).toBeNull();
  });

  it("asks for only the files it can show", () => {
    // A transcription.mscz beside them is a File the page holds and the
    // overview lists, but there is nothing this panel could do with it.
    const files = [
      file("Staves/1/transcription.musicxml"),
      file("Staves/1/transcription.lmx"),
      file("Staves/1/transcription.mscz"),
    ];
    const readings = readingsFor(row("Staves/{s}/transcription.musicxml", [files[0].path]), files);

    expect(pathsOf(readings)).toEqual([
      "Staves/1/transcription.musicxml",
      "Staves/1/transcription.lmx",
    ]);
  });

  it("has nothing to show for a selection that is not a transcription", () => {
    expect(readingsFor(row("image.jpg", ["image.jpg"]), PAGE)).toEqual([]);
  });
});

describe("tokensOf", () => {
  it("splits on whitespace and nothing else", () => {
    // LMX is a format this app does not own. Anything cleverer than a
    // whitespace split would be Musibot's opinion about somebody else's
    // vocabulary.
    expect(tokensOf("note C4 quarter  note D4\n  half\n")).toEqual([
      "note",
      "C4",
      "quarter",
      "note",
      "D4",
      "half",
    ]);
  });

  it("has no tokens for an empty document", () => {
    expect(tokensOf("")).toEqual([]);
    expect(tokensOf("   \n ")).toEqual([]);
  });
});
