/**
 * The image a visitor picked, before anything has been decided about it.
 *
 * Its dimensions are read in the browser rather than asked of the server,
 * because they decide which *Pipeline* is offered first and that choice has to
 * be on screen before any upload happens. Which also means the guess costs
 * nothing if the visitor changes their mind.
 */
export interface ChosenImage {
  /** The bytes that will be uploaded — see `prepareUpload`, not always what was picked. */
  file: File;
  width: number;
  height: number;
  /** An object URL for the thumbnail. Revoke it when the flow ends. */
  previewUrl: string;
  /**
   * Something about the file the visitor should be told, or `null`.
   *
   * Not a problem — the upload is going ahead. It is for what Musibot decided
   * on their behalf and they would otherwise never learn, which so far is one
   * thing: a PDF of several pages, of which only the first is being read.
   */
  notice: string | null;
}

/**
 * Load the file far enough to know how big it is.
 *
 * Which formats reach this, and which of them arrive re-encoded, is
 * `prepareUpload`'s business. By here it is always something the browser
 * decodes natively.
 */
export function readChosenImage(file: File): Promise<ChosenImage> {
  return new Promise((resolve, reject) => {
    const previewUrl = URL.createObjectURL(file);
    const image = new Image();

    image.onload = () => {
      resolve({
        file,
        width: image.naturalWidth,
        height: image.naturalHeight,
        previewUrl,
        notice: null,
      });
    };
    image.onerror = () => {
      URL.revokeObjectURL(previewUrl);
      reject(
        new Error(
          "That file is named like an image but could not be read as one. It may be truncated, or saved in another format under that name.",
        ),
      );
    };

    image.src = previewUrl;
  });
}

/**
 * The shape the session list draws a thumbnail in, from the design: 38 by 52.
 * Doubled here so the picture is still sharp on a dense screen.
 */
const THUMBNAIL = { width: 76, height: 104 };

/**
 * A small copy of the image, as a data URL, for the session list.
 *
 * Made here in the browser from bytes already in memory, never fetched back. A
 * page scan is several megabytes, so drawing the list from the real images
 * would mean pulling every one of them each time somebody glances at their
 * pages, in order to render each at forty pixels wide. It is kept in the ledger
 * beside the page it belongs to, which is what lets the list render with no
 * network at all — two or three kilobytes each, against a `localStorage` budget
 * of a few megabytes.
 *
 * It is **centre-cropped to the list's own shape rather than fitted to it**,
 * and that is not a matter of taste. Fitted, a staff crop — nineteen times
 * wider than it is tall — becomes a two-pixel line across an otherwise empty
 * box, which reads as a broken image rather than as a wide one. Cropping is
 * also the sharper of the two, because the window is taken from the original
 * at full resolution and scaled once, instead of a whole strip being reduced
 * to a few pixels of height and then blown back up to fill anything.
 *
 * What is lost is that a thumbnail no longer shows an image's proportions. The
 * row says the filename and the pipeline beside it, which is where that
 * belongs anyway, and the design draws every row's thumbnail the same size.
 *
 * Returns `null` rather than throwing if the canvas refuses: a missing
 * thumbnail is a duller list, not a failed upload.
 */
export async function thumbnailOf(image: ChosenImage): Promise<string | null> {
  try {
    const canvas = document.createElement("canvas");
    canvas.width = THUMBNAIL.width;
    canvas.height = THUMBNAIL.height;

    const context = canvas.getContext("2d");
    if (context === null) {
      return null;
    }

    // The largest window of the source that has the thumbnail's proportions,
    // taken from the middle.
    const wanted = THUMBNAIL.width / THUMBNAIL.height;
    const source =
      image.width / image.height > wanted
        ? { width: image.height * wanted, height: image.height }
        : { width: image.width, height: image.width / wanted };

    const bitmap = await createImageBitmap(image.file);
    context.drawImage(
      bitmap,
      (image.width - source.width) / 2,
      (image.height - source.height) / 2,
      source.width,
      source.height,
      0,
      0,
      canvas.width,
      canvas.height,
    );
    bitmap.close();

    return canvas.toDataURL("image/jpeg", 0.6);
  } catch {
    return null;
  }
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
