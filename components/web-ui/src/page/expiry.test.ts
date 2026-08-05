import { describe, expect, it } from "vitest";

import { formatRemaining } from "./expiry";

const NOW = new Date("2026-08-05T12:00:00Z");

function inSeconds(seconds: number): Date {
  return new Date(NOW.getTime() + seconds * 1000);
}

describe("formatRemaining", () => {
  it("rounds up to whole minutes, so the figure is never optimistic", () => {
    expect(formatRemaining(inSeconds(58 * 60 + 1), NOW)).toBe("59 minutes");
    expect(formatRemaining(inSeconds(58 * 60), NOW)).toBe("58 minutes");
  });

  it("stops counting minutes below one", () => {
    expect(formatRemaining(inSeconds(30), NOW)).toBe("under a minute");
  });

  it("does not report a negative time for a page that has run out", () => {
    // The ledger prunes an expired session, but the clock can pass while the
    // screen is open — and "-3 minutes" would read as a bug rather than a page
    // that is gone.
    expect(formatRemaining(inSeconds(-180), NOW)).toBe("any moment now");
  });
});
