import { fit } from "./canvasSize";
import { readChosenImage, type ChosenImage } from "./chosenImage";

/**
 * Turning whatever the visitor picked into the bytes Musibot uploads.
 *
 * Everything the form accepts ends here, and what leaves is either the original
 * file untouched or a JPEG made from it. Which of the two is not a matter of
 * what the browser can read — it can read all of these — but of what should be
 * sent:
 *
 * - **JPEG and PNG pass through.** A scan is line art, and JPEG's ringing
 *   lands exactly on the thin dark strokes that OMR reads. Re-encoding a
 *   lossless PNG to gain a file extension would be paying in the one currency
 *   that matters here.
 * - **BMP is re-encoded**, because it is not compressed at all: a 300 DPI A4
 *   bitmap is around 25 MB of the same page a JPEG carries in one. Nothing
 *   limits an upload's size, so it would go through — slowly, over a
 *   conference's wifi, while the visitor watched.
 * - **TIFF is re-encoded**, because it has to be decoded here in any case: no
 *   browser hands one to an `<img>`, so the page could not even be measured or
 *   previewed as it arrived.
 * - **PDF is rasterised**, because there is no image in it to pass through.
 *
 * The three that are re-encoded come out as real JPEGs, so they reach
 * `image.jpg` honestly and are conforming *MusicorpusPages* — it is only the
 * PNG passing through that diverges from the standard. See
 * `ACCEPTED_UPLOAD_TYPES`.
 */

/**
 * How hard the re-encode leans on the picture.
 *
 * High, because what is being encoded is a page of music rather than a
 * photograph: JPEG spends its error budget on edges, and on a scan every mark
 * worth recognising is an edge. The bytes saved by going lower would be saved
 * out of the recognition.
 */
const JPEG_QUALITY = 0.92;

/** What Musibot will take, and what has to be done to it. */
type UploadKind = "jpeg" | "png" | "bmp" | "tiff" | "pdf";

/**
 * Recognised by media type first, by extension only as a fallback.
 *
 * `image/x-ms-bmp` and `image/x-tiff` are older registrations that some systems
 * still report.
 */
const BY_MEDIA_TYPE = new Map<string, UploadKind>([
  ["image/jpeg", "jpeg"],
  ["image/png", "png"],
  ["image/bmp", "bmp"],
  ["image/x-ms-bmp", "bmp"],
  ["image/tiff", "tiff"],
  ["image/x-tiff", "tiff"],
  ["application/pdf", "pdf"],
]);

const BY_EXTENSION: [RegExp, UploadKind][] = [
  [/\.jpe?g$/i, "jpeg"],
  [/\.png$/i, "png"],
  [/\.bmp$/i, "bmp"],
  [/\.tiff?$/i, "tiff"],
  [/\.pdf$/i, "pdf"],
];

/**
 * What the file picker offers, and what the drop zone will take.
 *
 * Extensions as well as media types: a browser that reports nothing for a file
 * dragged out of an archive still matches on the name, and `isAcceptedUpload`
 * below falls back the same way.
 *
 * **HACK — PNG diverges from the Musicorpus Specification.** A page's scan is
 * `image.jpg` there, and that name says what the bytes are; a PNG passed
 * through goes to that same path under that same name, so a page whose
 * `image.jpg` is a PNG is not a conforming *MusicorpusPage*, and anything
 * reading such a corpus by the standard rather than by sniffing is entitled to
 * be wrong about it. It works only because nothing downstream reads the name:
 * every *Model* opens the image with `cv.imread`, which decides on the magic
 * bytes. You can already run a PNG through Musibot by renaming it, and this is
 * that same hack with the rename taken off the visitor.
 *
 * BMP and PDF do not have this problem — they arrive as real JPEGs. The honest
 * fix for PNG is either the same treatment, which costs a lossless scan its
 * losslessness, or `image.{ext}` in a *Signature*, which is a change to the
 * standard. Neither is this app's to make alone, so the divergence stays, in
 * one place, written down.
 */
export const ACCEPTED_UPLOAD_TYPES = [
  ...BY_MEDIA_TYPE.keys(),
  ".jpg",
  ".jpeg",
  ".png",
  ".bmp",
  ".tif",
  ".tiff",
  ".pdf",
];

/**
 * What kind of file this is, or `null` if Musibot does not take it.
 *
 * The browser's own sniffing is trusted first; a file dragged from somewhere
 * that did not set a type falls back to its name, which is a guess but a better
 * one than refusing a page that would have worked.
 */
function kindOf(file: File): UploadKind | null {
  const byType = BY_MEDIA_TYPE.get(file.type.toLowerCase());
  if (byType !== undefined) {
    return byType;
  }
  if (file.type !== "") {
    // The browser knows what this is and it is not one of ours.
    return null;
  }
  return BY_EXTENSION.find(([pattern]) => pattern.test(file.name))?.[1] ?? null;
}

/** Whether Musibot will take this file at all. */
export function isAcceptedUpload(file: File): boolean {
  return kindOf(file) !== null;
}

/**
 * The chosen file, ready to upload and measured.
 *
 * Throws with a sentence fit to show the visitor. Everything that can fail here
 * fails on a file they chose, so there is always something specific to say
 * about it.
 */
export async function prepareUpload(file: File): Promise<ChosenImage> {
  const kind = kindOf(file);

  if (kind === "pdf") {
    const { renderFirstPage } = await import("./pdfPage");
    let page;
    try {
      page = await renderFirstPage(file);
    } catch {
      throw new Error(
        "That PDF could not be rendered. It may be password-protected, or damaged in transfer.",
      );
    }
    return {
      ...(await readChosenImage(await jpegFromCanvas(page.canvas, file.name))),
      notice:
        page.pageCount > 1
          ? `That PDF has ${page.pageCount} pages and Musibot has taken the first. Upload the others one at a time.`
          : null,
    };
  }

  if (kind === "tiff") {
    const { decodeFirstPage } = await import("./tiffPage");
    let page;
    try {
      page = await decodeFirstPage(file);
    } catch {
      throw new Error(
        "That TIFF could not be read. Musibot decodes the compressions a scanner or an archive produces, but not every one the format allows — saving it as a JPEG or PNG will work.",
      );
    }
    return {
      ...(await readChosenImage(await jpegFrom(page.image, file.name))),
      notice:
        page.pageCount > 1
          ? `That TIFF holds ${page.pageCount} pages and Musibot has taken the first. Upload the others one at a time.`
          : null,
    };
  }

  if (kind === "bmp") {
    return { ...(await readChosenImage(await jpegFrom(file, file.name))), notice: null };
  }

  return { ...(await readChosenImage(file)), notice: null };
}

/**
 * Draw a decoded picture onto a canvas and encode it out as JPEG.
 *
 * Takes either a file the browser decodes itself — a BMP — or pixels something
 * else has already decoded, which is how a TIFF arrives. `drawImage` is given
 * an explicit destination size rather than being trusted to use the bitmap's
 * own, so that an oversized page is scaled down on the way in rather than
 * asking for a canvas the browser will not give.
 */
async function jpegFrom(source: File | ImageData, name: string): Promise<File> {
  let bitmap;
  try {
    bitmap = await createImageBitmap(source);
  } catch {
    throw new Error(
      "That file is named like an image but could not be read as one. It may be truncated, or saved in another format under that name.",
    );
  }

  try {
    const size = fit(bitmap.width, bitmap.height);
    const canvas = document.createElement("canvas");
    canvas.width = size.width;
    canvas.height = size.height;

    const context = canvas.getContext("2d");
    if (context === null) {
      throw new Error("This browser would not give Musibot a canvas to convert the image on.");
    }
    // JPEG has no transparency, and an unpainted canvas encodes to black. A
    // TIFF transparency mask is the case that reaches this.
    context.fillStyle = "rgb(255, 255, 255)";
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.drawImage(bitmap, 0, 0, size.width, size.height);

    return await jpegFromCanvas(canvas, name);
  } finally {
    bitmap.close();
  }
}

async function jpegFromCanvas(canvas: HTMLCanvasElement, name: string): Promise<File> {
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", JPEG_QUALITY),
  );
  if (blob === null) {
    throw new Error("That page was converted but could not be encoded as a JPEG.");
  }
  return new File([blob], jpegNameFor(name), { type: "image/jpeg" });
}

/**
 * `sanctus.pdf` → `sanctus.jpg`.
 *
 * The visitor sees this name on the choice card and in their page list, and it
 * is the honest one: what Musibot holds is a JPEG made from their PDF, not the
 * PDF. It is also what the downloaded MusicXML is eventually named after, where
 * the extension is dropped either way.
 */
function jpegNameFor(name: string): string {
  const stem = name.replace(/\.[^.]*$/, "").trim();
  return stem === "" ? "page.jpg" : `${stem}.jpg`;
}
