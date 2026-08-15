import { describe, expect, it } from "vitest";

import { guessExplanation, looksLikeSingleStaff, STAFF_ASPECT_RATIO } from "./chosenImage";

/** Real dimensions from the `UFAL.OmniOMR` corpus the threshold was measured on. */
const PORTRAIT_PAGE = { width: 2481, height: 3508 }; // 0.71
const LANDSCAPE_PAGE = { width: 4012, height: 3078 }; // 1.30
const WIDEST_PAGE = { width: 4012, height: 2709 }; // 1.48 — the extreme of the corpus
const NARROWEST_STAFF = { width: 1771, height: 383 }; // 4.62 — the other extreme
const TYPICAL_STAFF = { width: 2325, height: 120 }; // 19.4

describe("looksLikeSingleStaff", () => {
  it("calls a portrait page a page", () => {
    expect(looksLikeSingleStaff(PORTRAIT_PAGE)).toBe(false);
  });

  it("calls a landscape page a page", () => {
    // The bug this threshold was measured to fix: 41 of the corpus's 100 pages
    // are wider than they are tall, and the old test of width > height sent
    // every one of them to a model that reads a single staff.
    expect(looksLikeSingleStaff(LANDSCAPE_PAGE)).toBe(false);
  });

  it("calls a staff crop a staff", () => {
    expect(looksLikeSingleStaff(TYPICAL_STAFF)).toBe(true);
  });

  it("separates the two extremes the corpus actually contains", () => {
    // Nothing in the corpus falls between these two, which is why the exact
    // threshold does not matter as long as it sits in the gap.
    expect(looksLikeSingleStaff(WIDEST_PAGE)).toBe(false);
    expect(looksLikeSingleStaff(NARROWEST_STAFF)).toBe(true);
    expect(WIDEST_PAGE.width / WIDEST_PAGE.height).toBeLessThan(STAFF_ASPECT_RATIO);
    expect(NARROWEST_STAFF.width / NARROWEST_STAFF.height).toBeGreaterThan(STAFF_ASPECT_RATIO);
  });

  it("does not divide by a zero height", () => {
    expect(looksLikeSingleStaff({ width: 100, height: 0 })).toBe(false);
  });
});

describe("guessExplanation", () => {
  it("never tells a landscape page it is tall and narrow", () => {
    // The explanation sits beside the thumbnail it describes, so an untrue one
    // is untrue in plain sight.
    expect(guessExplanation(LANDSCAPE_PAGE)).toContain("whole page");
    expect(guessExplanation(LANDSCAPE_PAGE)).not.toMatch(/tall|narrow/i);
  });

  it("says what it assumed for a staff", () => {
    expect(guessExplanation(TYPICAL_STAFF)).toContain("single staff");
  });
});
