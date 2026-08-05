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
