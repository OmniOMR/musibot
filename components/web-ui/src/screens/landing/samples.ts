/**
 * The four pages Musibot offers a visitor who has nothing to hand.
 *
 * They cover the four shapes the recognition behaves differently on — clean
 * print, handwriting, an already-cropped staff, and a photograph taken at an
 * angle — so that clicking any of them also demonstrates what Musibot is and is
 * not good at.
 *
 * The real JPEGs do not exist yet. Until they are added under `public/samples/`
 * the thumbnails are drawn rather than photographed; see `SampleArt`.
 */
export interface SampleSheet {
  /** Stable identity, and what the upload flow will name the sample by. */
  id: string;
  /** What kind of page this is, in the visitor's terms. */
  label: string;
  /** The file it will arrive as, shown under the label in monospace. */
  fileName: string;
  /** Which stand-in artwork to draw until a real scan is in `public/samples/`. */
  art: "printed" | "handwritten" | "staff" | "photo";
}

/**
 * Fetch a sample as though the visitor had chosen it from their own disk, so
 * that every route into the upload flow arrives carrying a `File`.
 *
 * The four JPEGs are not in `public/samples/` yet, so this currently fails and
 * the landing page says the sample could not be loaded. That is the intended
 * shape of the code; what is missing is four files.
 */
export async function fetchSample(fileName: string): Promise<File> {
  // Relative to the deployment's base path, like everything else this app
  // addresses — see `api/base.ts` for why a leading slash would be wrong.
  const response = await fetch(`${import.meta.env.BASE_URL}samples/${fileName}`);
  if (!response.ok) {
    throw new Error(`The sample ${fileName} is not there (${response.status}).`);
  }
  return new File([await response.blob()], fileName, { type: "image/jpeg" });
}

export const SAMPLE_SHEETS: SampleSheet[] = [
  { id: "printed-page", label: "Printed page", fileName: "kyrie-p3.jpg", art: "printed" },
  {
    id: "handwritten-page",
    label: "Handwritten page",
    fileName: "gloria-p1.jpg",
    art: "handwritten",
  },
  { id: "single-staff", label: "A single staff", fileName: "sanctus-s2.jpg", art: "staff" },
  { id: "phone-photo", label: "Phone photo", fileName: "agnus-photo.jpg", art: "photo" },
];
