import { describe, expect, it } from "vitest";

import { theme } from "./theme";
import { cuni, paper } from "./palette";

/**
 * These guard the two decisions in the theme that are invisible until they
 * break, and that a routine "tidy up the theme" edit would silently undo.
 */
describe("theme", () => {
  it("replaces MUI's cool grey ramp with the warm one", () => {
    // The whole paper look rests on this. MUI's stock greys are blue-tinted
    // and reach into dividers, disabled states and input outlines, so a
    // single leftover step shows up as a cold stain on an ivory page.
    expect(theme.palette.grey[100]).toBe(paper["100"]);
    expect(theme.palette.grey[500]).toBe(paper["500"]);
    expect(theme.palette.grey[900]).toBe(paper["900"]);
    expect(theme.palette.divider).toBe(paper["200"]);
  });

  it("keeps the university red for fills and its darker red for text", () => {
    // cuni.red is only 4.75:1 on the page background — AA, but with no
    // headroom for small text. See palette.ts.
    expect(theme.palette.primary.main).toBe(cuni.red);
    expect(theme.palette.primary.dark).toBe(cuni.redDark);
  });

  it("sets headings in the serif and body in the sans", () => {
    expect(theme.typography.h1.fontFamily).toMatch(/Source Serif 4/);
    expect(theme.typography.h6.fontFamily).toMatch(/Source Serif 4/);
    expect(theme.typography.body1.fontFamily).toMatch(/Source Sans 3/);
    expect(theme.typography.fontFamily).toMatch(/Source Sans 3/);
  });
});
