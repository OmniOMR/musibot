import { describe, expect, it } from "vitest";

import type { FileView } from "../api/types";
import { groupFiles } from "./files";
import { interestOf, mostInteresting } from "./interest";

function listing(...paths: string[]): FileView[] {
  return paths.map((path) => ({ path, size: 1, last_modified: "2026-08-13T12:00:00Z" }));
}

function sectionsOf(...paths: string[]) {
  return groupFiles(listing(...paths), { sourcePath: null });
}

function chosen(...paths: string[]): string | null {
  return mostInteresting(sectionsOf(...paths))?.label ?? null;
}

describe("what is worth showing", () => {
  it("is the scan, when the scan is all there is", () => {
    expect(chosen("image.jpg")).toBe("image.jpg");
  });

  it("is the boxes rather than the scan they are drawn over", () => {
    expect(chosen("image.jpg", "layout.json")).toBe("layout.json");
  });

  it("is a staff crop rather than the whole page it came from", () => {
    // A page that has been cut up has moved on from the scan a visitor
    // uploaded; the crops are what the next stage will read.
    expect(chosen("image.jpg", "layout.json", "Staves/1/image.jpg")).toBe("Staves/{s}/image.jpg");
  });

  it("is the reading rather than the crop it was read from", () => {
    expect(chosen("image.jpg", "Staves/1/image.jpg", "Staves/1/transcription.musicxml")).toBe(
      "Staves/{s}/transcription.musicxml",
    );
  });

  it("is the whole page's reading rather than one staff's", () => {
    // The answer a visitor came for, rather than a piece of it.
    expect(chosen("Staves/1/transcription.musicxml", "transcription.musicxml")).toBe(
      "transcription.musicxml",
    );
  });

  it("prefers a staff's reading to the boxes over its crop", () => {
    expect(
      chosen(
        "Staves/1/image.jpg",
        "Staves/1/coco-object-detection.json",
        "Staves/1/transcription.musicxml",
      ),
    ).toBe("Staves/{s}/transcription.musicxml");
  });

  it("is nothing at all on a page with no files", () => {
    expect(chosen()).toBeNull();
  });
});

describe("a file the order does not name", () => {
  it("is not chosen while anything recognised is there", () => {
    // A model may write anything, and guessing at what a `notes.txt` means is
    // worse than showing the scan.
    expect(chosen("image.jpg", "notes.txt")).toBe("image.jpg");
  });

  it("is chosen when it is the only thing to show", () => {
    // The choice is between that and an empty canvas.
    expect(chosen("notes.txt")).toBe("notes.txt");
  });

  it("is not chosen when there are several and nothing recognised", () => {
    // "This is what Musibot chose" and "this is what Musibot produced" are not
    // things a visitor can tell apart, so an arbitrary pick is worse than none.
    expect(chosen("notes.txt", "warnings.log")).toBeNull();
  });

  it("ranks as unknown", () => {
    const [{ rows }] = sectionsOf("notes.txt");
    expect(interestOf(rows[0])).toBe(-1);
  });
});

describe("a subdivision Musibot has never heard of", () => {
  it("is ranked by the same rules as staves", () => {
    // `Staves`, `Grandstaves` and `Systems` come from the Musicorpus
    // Specification and Musibot treats a path syntactically, so a rule written
    // for staves has to hold for whatever a future *Model* cuts a page into.
    expect(chosen("image.jpg", "Systems/1/image.jpg", "Systems/1/transcription.musicxml")).toBe(
      "Systems/{s}/transcription.musicxml",
    );
  });
});
