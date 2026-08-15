import lieberSchatzThumbnail from "./thumbnails/lieber-schatz.jpg";
import posaunThumbnail from "./thumbnails/posaun.jpg";
import violoncelloThumbnail from "./thumbnails/violoncello.jpg";
import wisdomAndLoveThumbnail from "./thumbnails/wisdom-and-love.jpg";

/**
 * The four pages Musibot offers a visitor who has nothing to hand.
 *
 * They cover the four shapes the recognition behaves differently on — clean
 * print, handwriting, an already-cropped staff, and a photograph taken at an
 * angle — so that clicking any of them also demonstrates what Musibot is and is
 * not good at. Three are page-shaped and one is a strip, which means the
 * samples exercise both of `looksLikeSingleStaff`'s answers as well.
 *
 * Each sample is two files. The scan itself lives in `public/samples/` and is
 * fetched by name when somebody picks it, because it is a *File* the visitor is
 * about to upload rather than part of the interface. The thumbnail is imported
 * here instead, so that the bundler hashes it and it is cached like every other
 * asset — it is a few kilobytes and it is drawn on the landing page whether or
 * not anybody clicks.
 */
export interface SampleSheet {
  /** Stable identity, and what the upload flow names the sample by. */
  id: string;
  /** What kind of page this is, in the visitor's terms. */
  label: string;
  /** The file it arrives as, shown under the label in monospace. */
  fileName: string;
  /** A small copy of the scan, drawn in the picker. */
  thumbnail: string;
}

/**
 * How a sample being dragged says which sample it is.
 *
 * A drag has to carry the sample's identity rather than its picture. What is on
 * screen is a thumbnail a few kilobytes wide, and a browser dragging an `<img>`
 * will happily hand that over as a file — so a visitor who took up the offer to
 * drag one up would have uploaded the thumbnail and had it read back to them.
 * The scan is fetched by name on the drop instead, exactly as it is on a click.
 */
export const SAMPLE_DRAG_TYPE = "application/x-musibot-sample";

/** The sample a drag is carrying, if it is carrying one. */
export function draggedSample(transfer: DataTransfer): SampleSheet | undefined {
  const id = transfer.getData(SAMPLE_DRAG_TYPE);
  return id === "" ? undefined : SAMPLE_SHEETS.find((sample) => sample.id === id);
}

/**
 * Fetch a sample as though the visitor had chosen it from their own disk, so
 * that every route into the upload flow arrives carrying a `File`.
 *
 * The type is derived rather than assumed, because the samples are not all
 * JPEGs — a bilevel scan is a twelfth the size as a PNG and loses nothing, and
 * `prepareUpload` decides what to do with a file by asking what it is. Handing
 * it a PNG labelled as a JPEG would work by accident, since the bytes reach
 * `cv.imread` either way, and would be a lie in the one place the app is
 * pretending to be a file picker.
 */
export async function fetchSample(fileName: string): Promise<File> {
  // Relative to the deployment's base path, like everything else this app
  // addresses — see `api/base.ts` for why a leading slash would be wrong.
  const response = await fetch(`${import.meta.env.BASE_URL}samples/${fileName}`);
  if (!response.ok) {
    throw new Error(`The sample ${fileName} is not there (${response.status}).`);
  }
  return new File([await response.blob()], fileName, { type: mediaTypeOf(fileName) });
}

function mediaTypeOf(fileName: string): string {
  return fileName.toLowerCase().endsWith(".png") ? "image/png" : "image/jpeg";
}

export const SAMPLE_SHEETS: SampleSheet[] = [
  {
    id: "printed-page",
    label: "Printed page",
    fileName: "lieber-schatz.png",
    thumbnail: lieberSchatzThumbnail,
  },
  {
    id: "handwritten-page",
    label: "Handwritten page",
    fileName: "posaun.jpg",
    thumbnail: posaunThumbnail,
  },
  {
    id: "single-staff",
    label: "A single staff",
    fileName: "violoncello.jpg",
    thumbnail: violoncelloThumbnail,
  },
  {
    id: "phone-photo",
    label: "Phone photo",
    fileName: "wisdom-and-love.jpg",
    thumbnail: wisdomAndLoveThumbnail,
  },
];
