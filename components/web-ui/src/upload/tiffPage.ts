import * as UTIF from "utif2";

/**
 * The first page of a TIFF, decoded to pixels.
 *
 * **This module exists to be imported dynamically**, for the same reason
 * `pdfPage` does: nothing on the eager path may import it. See `prepareUpload`,
 * its only caller.
 *
 * No browser this app targets decodes a TIFF — Safari does it through macOS,
 * Chrome and Firefox have never done it at all — so unlike every other format
 * here, the decoding is Musibot's own work rather than the platform's. UTIF
 * covers the compressions an archive or a flatbed scanner actually produces,
 * CCITT Group 4 among them, which is what a bilevel scan is nearly always
 * stored as. The tail it does not cover — 16-bit samples, CMYK, JPEG inside
 * TIFF — throws, and the visitor is told the file could not be read.
 *
 * Only the first page, as with PDF, and for the same reason: a TIFF is a
 * container and a scanner filling one with a stack of sheets is ordinary.
 * `pageCount` comes back so the flow can say what it left.
 */

export interface DecodedTiffPage {
  image: ImageData;
  /** How many pages the file holds. Anything above 1 went unread. */
  pageCount: number;
}

export async function decodeFirstPage(file: File): Promise<DecodedTiffPage> {
  const buffer = await file.arrayBuffer();

  const pages = UTIF.decode(buffer).filter(isPage);
  if (pages.length === 0) {
    throw new Error("no image in this TIFF");
  }

  const page = pages[0];
  UTIF.decodeImage(buffer, page);
  const rgba = UTIF.toRGBA8(page);
  if (rgba.length !== page.width * page.height * 4) {
    throw new Error("this TIFF decoded to something that is not a picture");
  }

  return {
    // A view rather than a copy: `toRGBA8` has just allocated this and nobody
    // else holds it, and at 600 DPI it is well over a hundred megabytes. The
    // cast narrows `ArrayBufferLike` to the plain `ArrayBuffer` that a freshly
    // allocated `Uint8Array` always has — `ImageData` will not take the union.
    image: new ImageData(
      new Uint8ClampedArray(rgba.buffer as ArrayBuffer, rgba.byteOffset, rgba.byteLength),
      page.width,
      page.height,
    ),
    pageCount: pages.length,
  };
}

/**
 * Whether this directory is one of the file's pages.
 *
 * A TIFF's directories are not all pages. Some carry only metadata — EXIF
 * blocks have no width at all — and a file may hold a reduced-resolution
 * thumbnail of a page as a directory of its own, flagged in `NewSubfileType`.
 * Rendering that thumbnail as though it were the scan would be a page read at
 * a hundred pixels wide, which fails as a bad recognition rather than as a bad
 * file.
 */
function isPage(ifd: UTIF.IFD): boolean {
  const REDUCED_RESOLUTION = 1;
  return first(ifd.t256) !== undefined && ((first(ifd.t254) ?? 0) & REDUCED_RESOLUTION) === 0;
}

/** A TIFF tag holds an array even when it holds one number. */
function first(tag: UTIF.IFD[string] | undefined): number | undefined {
  if (typeof tag === "number") {
    return tag;
  }
  if (tag === undefined || typeof tag === "string") {
    return undefined;
  }
  const value: unknown = tag[0];
  return typeof value === "number" ? value : undefined;
}
