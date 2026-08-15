import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

import { fit } from "./canvasSize";

/**
 * The first page of a PDF, drawn onto a canvas.
 *
 * **This module exists to be imported dynamically.** `pdfjs-dist` is a whole
 * PDF engine and its worker is the largest single file this app can ship; the
 * landing page must not pay for it, because most visitors will never drop a
 * PDF. Nothing here may be imported from a module on the eager path — see
 * `prepareUpload`, which is the only caller and reaches this with `await
 * import()`. The worker URL comes in with Vite's `?url`, which emits it as an
 * asset beside the bundle rather than inlining it.
 *
 * Only the first page, always. A scanner asked for a PDF of one sheet produces
 * a one-page document, and that is the case this is for. A longer document is
 * not read further and is not silently truncated either: `pageCount` comes back
 * so the flow can say so.
 */

/** PDF user space is 1/72 inch, so this is the scale that means "one point". */
const POINTS_PER_INCH = 72;

/**
 * What the page is rasterised at.
 *
 * 300 is the resolution OMR is written for and the one flatbed scanners default
 * to, so for the case this is for — a scan wrapped in a PDF — rendering here
 * substantially recovers the image that is already inside the file rather than
 * approximating it. A born-digital score exported from notation software has no
 * native resolution at all and simply renders cleanly at whatever it is asked
 * for; 300 gives Musibot a better page than most scans.
 *
 * On A4 this is 2480 × 3508, which is 8.7 megapixels — comfortably inside every
 * browser's canvas limit, including the ones on phones.
 */
const DPI = 300;

export interface RenderedPdfPage {
  canvas: HTMLCanvasElement;
  /** How many pages the document holds. Anything above 1 went unread. */
  pageCount: number;
}

export async function renderFirstPage(file: File): Promise<RenderedPdfPage> {
  GlobalWorkerOptions.workerSrc = workerUrl;

  const loading = getDocument({ data: await file.arrayBuffer() });
  try {
    const document_ = await loading.promise;
    const page = await document_.getPage(1);

    // Asked for at 300 DPI, then scaled back only if that would be outsized.
    // Rendering at the reduced scale rather than shrinking a finished drawing:
    // the point of the cap is the canvas that would never have been allocated.
    const wanted = DPI / POINTS_PER_INCH;
    const atWanted = page.getViewport({ scale: wanted });
    const capped = fit(atWanted.width, atWanted.height);
    const viewport =
      capped.scale === 1 ? atWanted : page.getViewport({ scale: wanted * capped.scale });

    const canvas = window.document.createElement("canvas");
    canvas.width = Math.round(viewport.width);
    canvas.height = Math.round(viewport.height);

    await page.render({
      canvas,
      viewport,
      // The default, said out loud because it is load-bearing here rather than
      // cosmetic: a PDF page is transparent where nothing is drawn, JPEG has no
      // transparency, and an unpainted canvas encodes to a black rectangle.
      background: "rgb(255, 255, 255)",
    }).promise;

    return { canvas, pageCount: document_.numPages };
  } finally {
    // Tears down the worker's copy of the document. The canvas is ours and
    // outlives this.
    await loading.destroy();
  }
}
