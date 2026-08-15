/**
 * How large a picture Musibot will draw before it starts scaling one down.
 *
 * Every format that is re-encoded goes onto a canvas on the way, and a canvas
 * is the one step in the flow with a hard ceiling: a browser asked for one
 * larger than it allows does not throw, it hands back a blank — which would
 * reach the visitor as a page that read as empty rather than as an error.
 *
 * 25 megapixels leaves everything ordinary at its full resolution. A4 at 300
 * DPI is 8.7, A3 and tabloid are around 17. What it catches is a 600 DPI
 * archival TIFF, which is 35 for the same sheet of paper, and the outsized
 * MediaBox of a PDF that was never a sheet of paper at all. A reading at a
 * lower resolution is worth having; a reading of a blank canvas is not.
 */
export const MAX_PIXELS = 25_000_000;

/** The size to draw at: what was asked for, or as much of it as will fit. */
export function fit(
  width: number,
  height: number,
): { width: number; height: number; scale: number } {
  const pixels = width * height;
  if (pixels <= MAX_PIXELS || pixels === 0) {
    return { width, height, scale: 1 };
  }
  // Rounded down, not to nearest: rounding both sides up puts the result back
  // over the ceiling this exists to stay under.
  const scale = Math.sqrt(MAX_PIXELS / pixels);
  return {
    width: Math.max(1, Math.floor(width * scale)),
    height: Math.max(1, Math.floor(height * scale)),
    scale,
  };
}
