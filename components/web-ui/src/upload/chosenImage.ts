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
 * Whether the image looks like a whole page or a single staff.
 *
 * Shape is all there is to go on before anything has been recognised, and the
 * shapes are far apart: a page is taller than it is wide, a cropped staff is a
 * wide strip. It is a guess, it is stated as one — "Musibot has assumed" — and
 * the card exists so that it can be overruled in one click.
 */
export function looksLikeSingleStaff(image: { width: number; height: number }): boolean {
  return image.width > image.height;
}

/** The sentence the picker opens with, explaining what was assumed and why. */
export function guessExplanation(image: { width: number; height: number }): string {
  return looksLikeSingleStaff(image)
    ? "Wide and short, so Musibot has assumed a single staff."
    : "Tall and narrow, so Musibot has assumed a whole page.";
}
