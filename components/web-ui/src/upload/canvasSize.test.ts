import { describe, expect, it } from "vitest";

import { fit, MAX_PIXELS } from "./canvasSize";

describe("fit", () => {
  it("leaves an ordinary page exactly as it is", () => {
    // A4 at 300 DPI — the size everything in this flow aims at.
    expect(fit(2480, 3508)).toEqual({ width: 2480, height: 3508, scale: 1 });
  });

  it("leaves the large paper sizes alone too", () => {
    // A3 and tabloid at 300 DPI, around 17 megapixels. The cap is not meant to
    // reach these, and a scan of one arriving downscaled would be a surprise.
    expect(fit(3508, 4961).scale).toBe(1);
    expect(fit(3300, 5100).scale).toBe(1);
  });

  it("scales an outsized page down to the cap", () => {
    // A4 at 600 DPI: 34.8 megapixels, which is where a browser starts handing
    // back a blank canvas instead of an error.
    const fitted = fit(4960, 7016);

    expect(fitted.scale).toBeLessThan(1);
    expect(fitted.width * fitted.height).toBeLessThanOrEqual(MAX_PIXELS);
  });

  it("keeps the proportions of what it scales", () => {
    const fitted = fit(20000, 10000);

    expect(fitted.width / fitted.height).toBeCloseTo(2, 2);
    expect(fitted.width * fitted.height).toBeLessThanOrEqual(MAX_PIXELS);
  });

  it("has nothing to do to an empty picture", () => {
    // Guards the division: a zero dimension must not become a NaN scale that
    // then becomes a canvas of NaN by NaN.
    expect(fit(0, 0)).toEqual({ width: 0, height: 0, scale: 1 });
  });
});
