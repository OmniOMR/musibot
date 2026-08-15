import { describe, expect, it } from "vitest";

import type { FileView } from "../api/types";
import type { FileRow } from "../page/files";
import {
  opensTranscription,
  pathsOf,
  preprocessMusicXmlForOSMD,
  readingsFor,
  tokensOf,
} from "./transcription";

function file(path: string): FileView {
  return { path, size: 100, last_modified: "2026-08-05T12:00:00Z" };
}

function row(label: string, paths: string[]): FileRow {
  return {
    key: label,
    label,
    prefix: label.slice(0, label.lastIndexOf("/") + 1),
    // As `groupFiles` splits it: the file name, and the folders before it.
    name: label.slice(label.lastIndexOf("/") + 1),
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
  });

  it("leaves the tokens out when the notation is what was selected", () => {
    // Most visitors came to see whether Musibot read their music correctly, and
    // a wall of LMX under every staff is only in the way of the next one.
    const readings = readingsFor(row("transcription.musicxml", ["transcription.musicxml"]), PAGE);

    expect(readings[0].lmxPath).toBeNull();
  });

  it("shows the notation too when the tokens are what was selected", () => {
    // The other direction is not symmetric: the tokens are the specialist view
    // and the notation is what the same answer looks like to everybody.
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
    // overview lists, but there is nothing this panel could do with it. The
    // LMX is left unfetched for the same reason: it is not going to be shown.
    const files = [
      file("Staves/1/transcription.musicxml"),
      file("Staves/1/transcription.lmx"),
      file("Staves/1/transcription.mscz"),
    ];
    const readings = readingsFor(row("Staves/{s}/transcription.musicxml", [files[0].path]), files);

    expect(pathsOf(readings)).toEqual(["Staves/1/transcription.musicxml"]);
  });

  it("asks for both when the tokens were selected", () => {
    const files = [file("Staves/1/transcription.musicxml"), file("Staves/1/transcription.lmx")];
    const readings = readingsFor(row("Staves/{s}/transcription.lmx", [files[1].path]), files);

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

describe("preprocessMusicXmlForOSMD", () => {
  function score(...parts: string[]): string {
    return `<?xml version="1.0" encoding="UTF-8"?>
<score-partwise version="4.0">${parts.join("")}</score-partwise>`;
  }

  function part(id: string, divisions: number, notes: string): string {
    return `<part id="${id}"><measure number="1">
      <attributes><divisions>${divisions}</divisions></attributes>${notes}
    </measure></part>`;
  }

  it("gives a measure rest the four beats OSMD insists on", () => {
    const out = preprocessMusicXmlForOSMD(
      score(part("P1", 8, `<note><rest measure="yes"/></note>`)),
    );

    expect(out).toContain("<duration>32</duration>");
  });

  it("counts those beats in each part's own divisions", () => {
    // divisions is per-part, so a document whose parts disagree must not have
    // the first one's value written into the second.
    const out = preprocessMusicXmlForOSMD(
      score(
        part("P1", 8, `<note><rest measure="yes"/></note>`),
        part("P2", 3, `<note><rest measure="yes"/></note>`),
      ),
    );

    expect(out).toContain("<duration>32</duration>");
    expect(out).toContain("<duration>12</duration>");
  });

  it("leaves a rest that already states its duration alone", () => {
    const out = preprocessMusicXmlForOSMD(
      score(part("P1", 8, `<note><rest measure="yes"/><duration>16</duration></note>`)),
    );

    expect(out).toContain("<duration>16</duration>");
    expect(out).not.toContain("<duration>32</duration>");
  });

  it("has nothing to add to rests that are not measure rests", () => {
    const out = preprocessMusicXmlForOSMD(score(part("P1", 8, `<note><rest/></note>`)));

    expect(out).not.toContain("<duration>");
  });
});
