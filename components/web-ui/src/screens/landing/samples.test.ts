import { describe, expect, it } from "vitest";

import { isAcceptedUpload } from "../../upload/prepareUpload";
import { draggedSample, SAMPLE_DRAG_TYPE, SAMPLE_SHEETS } from "./samples";

/** Just enough of a `DataTransfer` to answer `getData`. */
function carrying(entries: Record<string, string>): DataTransfer {
  return { getData: (type: string) => entries[type] ?? "" } as DataTransfer;
}

describe("draggedSample", () => {
  it("recognises a sample by the id it carries", () => {
    const sample = SAMPLE_SHEETS[0];

    expect(draggedSample(carrying({ [SAMPLE_DRAG_TYPE]: sample.id }))).toBe(sample);
  });

  it("recognises every one of them", () => {
    for (const sample of SAMPLE_SHEETS) {
      expect(draggedSample(carrying({ [SAMPLE_DRAG_TYPE]: sample.id }))).toBe(sample);
    }
  });

  it("has nothing to say about a file dragged in from outside", () => {
    // The visitor's own scan, which the drop zone then handles as a file.
    expect(draggedSample(carrying({}))).toBeUndefined();
    expect(draggedSample(carrying({ "text/plain": "printed-page" }))).toBeUndefined();
  });

  it("does not resolve an id that is not one of ours", () => {
    expect(draggedSample(carrying({ [SAMPLE_DRAG_TYPE]: "some-other-page" }))).toBeUndefined();
  });
});

describe("SAMPLE_SHEETS", () => {
  it("gives every sample its own id and its own file", () => {
    // The id is what a drag carries and the file name is what gets fetched, so
    // a duplicate of either would quietly serve the wrong page.
    expect(new Set(SAMPLE_SHEETS.map((sample) => sample.id)).size).toBe(SAMPLE_SHEETS.length);
    expect(new Set(SAMPLE_SHEETS.map((sample) => sample.fileName)).size).toBe(SAMPLE_SHEETS.length);
  });

  it("points every sample at a thumbnail and a scan", () => {
    for (const sample of SAMPLE_SHEETS) {
      expect(sample.thumbnail, `${sample.id} has a thumbnail`).toBeTruthy();
      expect(sample.fileName, `${sample.id} names a scan`).toMatch(/\.(jpg|png)$/);
    }
  });

  it("names every sample a format the upload flow takes", () => {
    // A sample is fetched and then goes through `prepareUpload` like anything
    // else, so one saved in a format the form refuses would fail on the click
    // rather than on the drop zone, where the message is about choosing a file.
    for (const sample of SAMPLE_SHEETS) {
      expect(isAcceptedUpload(new File([], sample.fileName)), sample.fileName).toBe(true);
    }
  });
});
