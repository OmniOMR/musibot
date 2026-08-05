/**
 * Reading boxes out of a COCO file.
 *
 * Both spatial layers a page carries are COCO, which is worth saying because
 * the design describes them as two different things: `layout.json` holds the
 * staff regions found on a page, `coco-object-detection.json` holds the symbols
 * found within an image, and they arrive in the same schema with the same
 * fields. One reader, used twice, with the colour and the source file being the
 * whole of the difference.
 *
 * Only `bbox` is read. Every annotation also carries `segmentation`, and it is
 * deliberately ignored: it is polygon arrays in one file and run-length encoding
 * in another, so drawing it would mean shipping an RLE decoder to render shapes
 * that the boxes already locate — and thousands of polygons are the one thing
 * that makes an SVG scene slow, where thousands of rectangles do not.
 */

/** A box, in the pixel coordinates of the image the file is about. */
export interface Box {
  id: number;
  x: number;
  y: number;
  width: number;
  height: number;
  /** The category's name, when the file names it. Shown on hover. */
  label: string | null;
}

/** What a COCO file says, as far as this app needs it. */
export interface CocoLayer {
  boxes: Box[];
  /** The image the coordinates are relative to, if the file states it. */
  imageWidth: number | null;
  imageHeight: number | null;
}

interface RawCoco {
  images?: { width?: unknown; height?: unknown }[];
  annotations?: { id?: unknown; bbox?: unknown; category_id?: unknown }[];
  categories?: { id?: unknown; name?: unknown }[];
}

/**
 * Parse a COCO document.
 *
 * Forgiving, because this file was written by a *Model* rather than by Musibot
 * — Musibot never parses a *File*, it only moves them around, so nothing has
 * checked this before it arrives here. An annotation that does not carry a
 * usable `bbox` is skipped rather than made into a reason the page will not
 * render.
 */
export function readCoco(document: unknown): CocoLayer {
  if (typeof document !== "object" || document === null) {
    return { boxes: [], imageWidth: null, imageHeight: null };
  }
  const raw = document as RawCoco;

  const names = new Map<number, string>();
  for (const category of raw.categories ?? []) {
    if (typeof category.id === "number" && typeof category.name === "string") {
      names.set(category.id, category.name);
    }
  }

  const boxes: Box[] = [];
  for (const [index, annotation] of (raw.annotations ?? []).entries()) {
    const bbox = annotation.bbox;
    if (!Array.isArray(bbox) || bbox.length < 4 || !bbox.slice(0, 4).every(isFinite_)) {
      continue;
    }
    const [x, y, width, height] = bbox as number[];
    boxes.push({
      id: typeof annotation.id === "number" ? annotation.id : index,
      x,
      y,
      width,
      height,
      label:
        typeof annotation.category_id === "number"
          ? (names.get(annotation.category_id) ?? null)
          : null,
    });
  }

  const image = raw.images?.[0];
  return {
    boxes,
    imageWidth: typeof image?.width === "number" ? image.width : null,
    imageHeight: typeof image?.height === "number" ? image.height : null,
  };
}

function isFinite_(value: unknown): boolean {
  return typeof value === "number" && Number.isFinite(value);
}
