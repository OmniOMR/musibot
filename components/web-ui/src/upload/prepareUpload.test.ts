import { describe, expect, it } from "vitest";

import { ACCEPTED_UPLOAD_TYPES, isAcceptedUpload } from "./prepareUpload";

describe("isAcceptedUpload", () => {
  it("trusts the browser's type when there is one", () => {
    expect(isAcceptedUpload(new File([], "scan.jpg", { type: "image/jpeg" }))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.png", { type: "image/png" }))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.bmp", { type: "image/bmp" }))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.tif", { type: "image/tiff" }))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.pdf", { type: "application/pdf" }))).toBe(true);
  });

  it("takes the older registrations some systems still report", () => {
    expect(isAcceptedUpload(new File([], "scan.bmp", { type: "image/x-ms-bmp" }))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.tif", { type: "image/x-tiff" }))).toBe(true);
  });

  it("falls back to the name when a drag carried no type", () => {
    expect(isAcceptedUpload(new File([], "scan.JPEG"))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.PNG"))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.BMP"))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.PDF"))).toBe(true);
  });

  it("takes a TIFF under either of its extensions", () => {
    expect(isAcceptedUpload(new File([], "scan.tif"))).toBe(true);
    expect(isAcceptedUpload(new File([], "scan.TIFF"))).toBe(true);
  });

  it("turns away what Musibot has nothing to do with", () => {
    expect(isAcceptedUpload(new File([], "notes.txt", { type: "text/plain" }))).toBe(false);
    expect(isAcceptedUpload(new File([], "score.mscz"))).toBe(false);
    expect(isAcceptedUpload(new File([], "no-extension"))).toBe(false);
  });

  it("goes by what the browser says over what the name says", () => {
    // The name is consulted only when the browser offers nothing better, so a
    // file it has already typed is judged on that and not on a misleading
    // extension.
    expect(isAcceptedUpload(new File([], "scan.jpg", { type: "video/mp4" }))).toBe(false);
  });
});

describe("ACCEPTED_UPLOAD_TYPES", () => {
  it("offers the picker every media type and every extension", () => {
    // Both, because the two checks in `isAcceptedUpload` are both reachable: a
    // file the browser types, and one dragged from somewhere that typed
    // nothing. A picker narrower than the check would hide a file that would
    // in fact have been accepted.
    expect(ACCEPTED_UPLOAD_TYPES).toEqual(
      expect.arrayContaining([
        "image/jpeg",
        "image/png",
        "image/bmp",
        "image/tiff",
        "application/pdf",
        ".jpg",
        ".jpeg",
        ".png",
        ".bmp",
        ".tif",
        ".tiff",
        ".pdf",
      ]),
    );
  });

  it("offers nothing the check would then refuse", () => {
    for (const accepted of ACCEPTED_UPLOAD_TYPES) {
      const file = accepted.startsWith(".")
        ? new File([], `scan${accepted}`)
        : new File([], "scan", { type: accepted });
      expect(isAcceptedUpload(file), `the picker offers ${accepted}`).toBe(true);
    }
  });
});
