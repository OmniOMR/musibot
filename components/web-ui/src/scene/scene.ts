import { cuni } from "../theme";
import type { FileRow } from "../page/files";
import type { FileView } from "../api/types";

/**
 * What the canvas shows, worked out from which *File* row is selected.
 *
 * Selecting a row gives that layer the canvas exclusively, which is why there
 * is no legend anywhere on the screen — one thing is displayed and the toolbar
 * names it. But a layer is rarely an image: `layout.json` is a set of boxes and
 * means nothing floating in space, so the scene is always *an image, and
 * possibly boxes over it*, and the selection decides both.
 *
 * The other rule the design is firm about: a staff-level selection shows
 * **every** staff at once, never one in isolation. A page cut into nine staves
 * is nine crops in a column, because the thing a reader wants to check is
 * whether the reading is right across the page, and isolating staff 4 hides
 * exactly that.
 */

/** One image in the scene, with its own coordinate frame. */
export interface Plate {
  /** The *File* the image comes from. */
  path: string;
  /** Which instance of a subdivision this is — `7` of `Staves/7/…`. */
  instance: string | null;
  /** Where it sits in world space. Page-level scenes have one plate at 0,0. */
  x: number;
  y: number;
  /** Boxes drawn over it, in its own pixel coordinates. Filled in later. */
  overlayPath: string | null;
}

export interface Scene {
  plates: Plate[];
  /** Colour for every box in the scene, or `null` when there are none. */
  overlayColour: string | null;
  /** What the toolbar says after "Showing". */
  description: string;
  /** Why there is nothing to draw, when there is nothing to draw. */
  empty: string | null;
}

/** Gap between stacked staff crops, in image pixels. */
const PLATE_GAP = 60;

/**
 * Staff regions are the university red; symbol detections are the blue.
 *
 * The blue exists only for this. It is the one place in the app where a second
 * saturated colour is allowed, because two kinds of box drawn over the same
 * image have to be told apart at a glance and nothing else on the page competes.
 */
function overlayColourFor(path: string): string | null {
  const name = fileNameOf(path);
  if (name === "layout.json") {
    return cuni.red;
  }
  if (name === "coco-object-detection.json") {
    return cuni.blue;
  }
  // A transcription is not spatially aligned to the image — there is no
  // coordinate in a MusicXML file — so it never gets boxes.
  return null;
}

export function fileNameOf(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

/** `Staves/7/image.jpg` → `Staves`, or `null` at page level. */
export function subdivisionOf(path: string): string | null {
  const segments = path.split("/");
  return segments.length >= 3 ? segments[0] : null;
}

/** `Staves/7/image.jpg` → `7`. */
export function instanceOf(path: string): string | null {
  const segments = path.split("/");
  return segments.length >= 3 ? segments[1] : null;
}

/**
 * What to call one crop, beside it on the canvas — "staff 7".
 *
 * This is the one place a subdivision folder is named rather than treated
 * syntactically, and the distinction is worth keeping straight: everything that
 * *decides* anything reads paths structurally, so a new subdivision level is
 * never a code change. This is copy. English has no rule that turns `Staves`
 * into `staff`, so the three the Musicorpus Specification defines are written
 * down and anything else falls back to its own folder name.
 */
const SINGULARS: Record<string, string> = {
  Staves: "staff",
  Grandstaves: "grandstaff",
  Systems: "system",
};

export function instanceLabel(path: string): string | null {
  const subdivision = subdivisionOf(path);
  const instance = instanceOf(path);
  if (subdivision === null || instance === null) {
    return null;
  }
  return `${SINGULARS[subdivision] ?? subdivision} ${instance}`;
}

/**
 * Build the scene for a selected row.
 *
 * `heights` supplies each image's height once it has loaded, which is what
 * stacks the staff crops without them overlapping. Before an image has loaded
 * its height is unknown and a placeholder is used; the scene is rebuilt when it
 * arrives.
 */
export function sceneFor(
  selected: FileRow | null,
  files: FileView[],
  heights: Map<string, number>,
): Scene {
  if (selected === null) {
    return { plates: [], overlayColour: null, description: "nothing", empty: null };
  }

  const subdivision = subdivisionOf(selected.paths[0]);
  const overlayColour = overlayColourFor(selected.paths[0]);
  const isImage = fileNameOf(selected.paths[0]) === "image.jpg";

  // Every scene stands on an image. If the selection is not one, the image
  // beside it in the same folder is what the boxes — or the transcription —
  // are about.
  const imagePaths = files
    .map((file) => file.path)
    .filter((path) => fileNameOf(path) === "image.jpg" && subdivisionOf(path) === subdivision)
    .sort(compareInstances);

  if (imagePaths.length === 0) {
    return {
      plates: [],
      overlayColour: null,
      description: selected.label,
      empty:
        subdivision === null
          ? "There is no page image to show this over."
          : `There are no ${subdivision.toLowerCase()} images to show this over.`,
    };
  }

  const overlayFor = (imagePath: string): string | null => {
    if (isImage || overlayColour === null) {
      return null;
    }
    // The overlay that belongs to *this* plate: a staff's detections live
    // beside that staff's image, not at the page level.
    const folder = imagePath.slice(0, imagePath.lastIndexOf("/") + 1);
    const wanted = folder + fileNameOf(selected.paths[0]);
    return selected.paths.includes(wanted) ? wanted : null;
  };

  let y = 0;
  const plates: Plate[] = imagePaths.map((path) => {
    const plate: Plate = {
      path,
      instance: instanceOf(path),
      x: 0,
      y,
      overlayPath: overlayFor(path),
    };
    y += (heights.get(path) ?? 200) + PLATE_GAP;
    return plate;
  });

  return {
    plates,
    overlayColour,
    description: selected.label,
    empty: null,
  };
}

/** Every *File* the scene needs fetched, images and overlays together. */
export function pathsOf(scene: Scene): string[] {
  return scene.plates.flatMap((plate) =>
    plate.overlayPath === null ? [plate.path] : [plate.path, plate.overlayPath],
  );
}

/**
 * Instance names are arbitrary path-safe strings in the Musicorpus
 * Specification, so nothing guarantees they are numbers — but when they are,
 * staff 10 belongs after staff 9 rather than after staff 1.
 */
function compareInstances(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true });
}
