import { describe, expect, it } from "vitest";

import type { FileView } from "../api/types";
import { formatSize, groupFiles } from "./files";

function file(path: string, size = 100): FileView {
  return { path, size, last_modified: "2026-08-05T12:00:00Z" };
}

describe("groupFiles", () => {
  it("puts page-level files under Page, one row each", () => {
    const sections = groupFiles([file("image.jpg"), file("layout.json")], {
      sourcePath: "image.jpg",
    });

    expect(sections).toHaveLength(1);
    expect(sections[0].heading).toBe("Page");
    expect(sections[0].rows.map((row) => row.label)).toEqual(["image.jpg", "layout.json"]);
  });

  it("collapses a subdivision's files into one row per file name", () => {
    // Twelve staves is twenty-four files, which would bury the page-level ones
    // a visitor is looking for. They also behave as one thing downstream:
    // selecting staff transcriptions shows all of them at once.
    const sections = groupFiles(
      [
        file("Staves/1/image.jpg", 10),
        file("Staves/2/image.jpg", 20),
        file("Staves/1/transcription.musicxml", 5),
        file("Staves/2/transcription.musicxml", 7),
      ],
      { sourcePath: null },
    );

    expect(sections).toHaveLength(1);
    expect(sections[0].heading).toBe("Staves");
    expect(sections[0].rows.map((row) => row.label)).toEqual([
      "Staves/{s}/image.jpg",
      "Staves/{s}/transcription.musicxml",
    ]);
    expect(sections[0].rows[0].instances).toBe(2);
    expect(sections[0].rows[0].size).toBe(30);
    expect(sections[0].rows[0].paths).toEqual(["Staves/1/image.jpg", "Staves/2/image.jpg"]);
  });

  it("names a subdivision after its own folder rather than assuming Staves", () => {
    // Musibot treats paths purely syntactically so that a new subdivision level
    // is not a change to Musibot. Neither should it be a change here.
    const sections = groupFiles([file("Systems/1/transcription.musicxml")], { sourcePath: null });

    expect(sections[0].heading).toBe("Systems");
    expect(sections[0].rows[0].label).toBe("Systems/{s}/transcription.musicxml");
  });

  it("puts Page first and subdivisions after it", () => {
    const sections = groupFiles([file("Staves/1/image.jpg"), file("image.jpg")], {
      sourcePath: "image.jpg",
    });

    expect(sections.map((section) => section.heading)).toEqual(["Page", "Staves"]);
  });

  it("marks the uploaded file, wherever the signature sent it", () => {
    // A staff-level pipeline puts the visitor's own upload at Staves/1/image.jpg,
    // so the source is not always the page-level image.
    const sections = groupFiles([file("Staves/1/image.jpg"), file("Staves/1/transcription.lmx")], {
      sourcePath: "Staves/1/image.jpg",
    });

    const rows = sections[0].rows;
    expect(rows.find((row) => row.label === "Staves/{s}/image.jpg")?.isSource).toBe(true);
    expect(rows.find((row) => row.label === "Staves/{s}/transcription.lmx")?.isSource).toBe(false);
  });

  it("flags a row a running execution is about to replace", () => {
    const sections = groupFiles([file("layout.json"), file("image.jpg")], {
      sourcePath: "image.jpg",
      overwritten: ["layout.json"],
    });

    const rows = sections[0].rows;
    expect(rows.find((row) => row.label === "layout.json")?.willBeOverwritten).toBe(true);
    expect(rows.find((row) => row.label === "image.jpg")?.willBeOverwritten).toBe(false);
  });

  it("flags a collapsed row when any of its files will be replaced", () => {
    const sections = groupFiles(
      [file("Staves/1/transcription.musicxml"), file("Staves/2/transcription.musicxml")],
      { sourcePath: null, overwritten: ["Staves/2/transcription.musicxml"] },
    );

    expect(sections[0].rows[0].willBeOverwritten).toBe(true);
  });

  it("has nothing to show for an empty page", () => {
    expect(groupFiles([], { sourcePath: null })).toEqual([]);
  });
});

describe("formatSize", () => {
  it("reads at a glance rather than exactly", () => {
    expect(formatSize(0)).toBe("0 B");
    expect(formatSize(505)).toBe("505 B");
    expect(formatSize(2143)).toBe("2.1 kB");
    expect(formatSize(84698)).toBe("84.7 kB");
    expect(formatSize(1_200_000)).toBe("1.2 MB");
  });
});
