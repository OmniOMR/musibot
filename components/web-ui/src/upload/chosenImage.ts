/**
 * The image a visitor picked, before anything has been decided about it.
 *
 * Its dimensions are read in the browser rather than asked of the server,
 * because they decide which *Pipeline* is offered first and that choice has to
 * be on screen before any upload happens. Which also means the guess costs
 * nothing if the visitor changes their mind.
 */
export interface ChosenImage {
  file: File;
  width: number;
  height: number;
  /** An object URL for the thumbnail. Revoke it when the flow ends. */
  previewUrl: string;
}

/**
 * Musibot reads JPEG and nothing else.
 *
 * The browser's own sniffing is trusted first; a file dragged from somewhere
 * that did not set a type falls back to its name, which is a guess but a better
 * one than refusing a page that would have worked.
 */
export function isJpeg(file: File): boolean {
  if (file.type !== "") {
    return file.type === "image/jpeg";
  }
  return /\.jpe?g$/i.test(file.name);
}

/** Load the file far enough to know how big it is. */
export function readChosenImage(file: File): Promise<ChosenImage> {
  return new Promise((resolve, reject) => {
    const previewUrl = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      resolve({ file, width: image.naturalWidth, height: image.naturalHeight, previewUrl });
    };
    image.onerror = () => {
      URL.revokeObjectURL(previewUrl);
      reject(new Error("That image could not be read."));
    };

    image.src = previewUrl;
  });
}

/**
 * Where a page stops being a page and starts being a staff, as a ratio of
 * width to height.
 *
 * This was measured rather than guessed. Every page image and every staff crop
 * in `UFAL.OmniOMR` — 100 pages and 1184 staves — binned by aspect ratio on a
 * log scale:
 *
 * ```
 *  ratio             # = page image   = = staff crop
 *   0.5-0.6
 *   0.6-0.7   #                                    10 pages
 *   0.7-0.8   ###                                  46 pages
 *   0.8-1.0                                         3 pages
 *   1.0-1.2                                         4 pages
 *   1.2-1.4   ###                                  36 pages
 *   1.4-1.7                                         1 page
 *   1.7-2.0                                        ← the gap
 *   2.0-2.4
 *   2.4-2.9
 *   2.9-3.5                                        ← 3.0 sits here
 *   3.5-4.1
 *   4.1-4.9                                         1 staff
 *   4.9-5.9   =                                    10 staves
 *   5.9-7.0   ====                                 49 staves
 *   7.0-8.4   ===========                         154 staves
 *   8.4-10.0  =====================               290 staves
 *  10.0-11.9  ================================    470 staves
 *  11.9-14.2  ==========                          142 staves
 *  14.2-16.9  ====                                 50 staves
 *  16.9-20.1  =                                    18 staves
 *  20.1-24.0
 * ```
 *
 * Two things fall out of it. The populations are separated by an empty band
 * four bins wide — no image in the corpus has a ratio between 1.5 and 4.6 —
 * so the threshold is not a fine judgement and anything from 2 to 4 would
 * behave identically on this data.
 *
 * And the old threshold of 1.0 was badly wrong: **41 of the 100 pages are
 * landscape**, so two pages in five were being called staves and handed to a
 * model that reads one staff. That is not an edge case, it is the second
 * biggest cluster in the histogram.
 *
 * 3.0 is the geometric middle of the two medians (0.83 and 10.23 give 2.91),
 * rounded. It leans very slightly towards calling an image a page, which is
 * the safer way to be wrong: a staff read as a page has its one staff found
 * and transcribed, while a page read as a staff is transcribed as though the
 * whole sheet were a single line.
 */
export const STAFF_ASPECT_RATIO = 3.0;

/**
 * Whether the image looks like a whole page or a single staff.
 *
 * Shape is all there is to go on before anything has been recognised. It is a
 * guess, it is stated as one — "Musibot has assumed" — and the card exists so
 * that it can be overruled in one click.
 */
export function looksLikeSingleStaff(image: { width: number; height: number }): boolean {
  return image.height > 0 && image.width / image.height >= STAFF_ASPECT_RATIO;
}

/**
 * The sentence the picker opens with, explaining what was assumed and why.
 *
 * It no longer says "tall and narrow" for a page, because two pages in five
 * are wider than they are tall and the explanation would be visibly untrue of
 * the image sitting next to it. What separates the two is not portrait against
 * landscape but page-shaped against strip-shaped.
 */
export function guessExplanation(image: { width: number; height: number }): string {
  return looksLikeSingleStaff(image)
    ? "A long horizontal strip, so Musibot has assumed a single staff."
    : "Page-shaped rather than a strip, so Musibot has assumed a whole page.";
}
