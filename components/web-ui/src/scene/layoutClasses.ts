import type { Box, CocoLayer } from "./coco";
import { overlay } from "../theme";

/**
 * The classes of box a `layout.json` holds, and how each is drawn.
 *
 * The Musicorpus Specification defines seven, in three families and one
 * outlier: a staff, a grand staff and a system, each with the measures within
 * it, and the empty staff. A family shares a colour, and its measures are drawn
 * dashed — so a measure reads as belonging to the thing it divides without a
 * legend having to say so. A model may write classes of its own as well, and
 * those are drawn rather than dropped: in green, beside the empty staff, as the
 * classes nothing here knows the meaning of.
 */

export interface ClassStyle {
  colour: string;
  dashed: boolean;
}

/**
 * The specification's classes, in the order the panel lists them — which is
 * also the order they are drawn in, bottom first: the structures that contain
 * others under the things they contain, and every kind of measure on top.
 */
const KNOWN: { name: string; style: ClassStyle; shownByDefault: boolean }[] = [
  { name: "system", style: { colour: overlay.blue, dashed: false }, shownByDefault: true },
  { name: "grandstaff", style: { colour: overlay.yellow, dashed: false }, shownByDefault: true },
  { name: "staff", style: { colour: overlay.red, dashed: false }, shownByDefault: true },
  { name: "emptyStaff", style: { colour: overlay.green, dashed: false }, shownByDefault: true },
  // Measures are off until asked for. A page has a few staves and a few
  // hundred measures, and the boxes most people open this to check are the
  // first kind.
  { name: "systemMeasure", style: { colour: overlay.blue, dashed: true }, shownByDefault: false },
  {
    name: "grandstaffMeasure",
    style: { colour: overlay.yellow, dashed: true },
    shownByDefault: false,
  },
  { name: "staffMeasure", style: { colour: overlay.red, dashed: true }, shownByDefault: false },
];

/** What a box whose category has no name is listed as. */
export const UNNAMED = "(unnamed)";

const UNKNOWN_STYLE: ClassStyle = { colour: overlay.green, dashed: false };

export function classOf(box: Box): string {
  return box.label ?? UNNAMED;
}

export function styleOf(name: string): ClassStyle {
  return KNOWN.find((known) => known.name === name)?.style ?? UNKNOWN_STYLE;
}

/** The classes hidden before anyone has touched the toggles. */
export function hiddenByDefault(): Set<string> {
  return new Set(KNOWN.filter((known) => !known.shownByDefault).map((known) => known.name));
}

/** Whether a class is visible before anyone has touched the toggles. */
export function shownByDefault(name: string): boolean {
  return KNOWN.find((known) => known.name === name)?.shownByDefault ?? true;
}

export interface ClassCount {
  name: string;
  count: number;
}

/**
 * Every class that occurs in `layers`, with how many boxes it has.
 *
 * The specification's classes come first, in its own order, and anything else
 * after them alphabetically. A class the file lists in `categories` but never
 * uses is left out: there is nothing of it to show or hide.
 */
export function classesIn(layers: CocoLayer[]): ClassCount[] {
  const counts = new Map<string, number>();
  for (const layer of layers) {
    for (const box of layer.boxes) {
      const name = classOf(box);
      counts.set(name, (counts.get(name) ?? 0) + 1);
    }
  }

  const known = KNOWN.filter(({ name }) => counts.has(name)).map(({ name }) => name);
  const unknown = [...counts.keys()]
    .filter((name) => !KNOWN.some((known) => known.name === name))
    .sort((a, b) => a.localeCompare(b));

  return [...known, ...unknown].map((name) => ({ name, count: counts.get(name) ?? 0 }));
}

/**
 * Where a class is drawn, bottom first.
 *
 * A class the specification does not name goes just above the empty staff and
 * below every measure: nothing says how large its boxes are, and measures are
 * the small boxes that would be the hardest to point at if something covered
 * them.
 */
function depthOf(name: string): number {
  const index = KNOWN.findIndex((known) => known.name === name);
  if (index !== -1) {
    return index;
  }
  return KNOWN.findIndex((known) => known.name === "emptyStaff") + 0.5;
}

/**
 * The boxes to draw, in the order to draw them: by class, bottom first, and
 * the largest first within a class.
 *
 * A system is drawn under the staves inside it, and a staff under its
 * measures, so that every box can be hovered for its name — the box on top
 * under the pointer is the one somebody pointing at it means.
 */
export function boxesToDraw(layer: CocoLayer, hidden: ReadonlySet<string>): Box[] {
  return layer.boxes
    .filter((box) => !hidden.has(classOf(box)))
    .sort(
      (a, b) =>
        depthOf(classOf(a)) - depthOf(classOf(b)) || b.width * b.height - a.width * a.height,
    );
}

/**
 * What soloing `name` does to the hidden set.
 *
 * Soloing a class that is already the only one showing undoes the solo and
 * shows everything — so the same button that isolates a class is the way back
 * out of it, without hunting for the other toggles.
 */
export function solo(name: string, all: string[], hidden: ReadonlySet<string>): Set<string> {
  const alone = all.every((other) => (other === name) !== hidden.has(other));
  return alone ? new Set() : new Set(all.filter((other) => other !== name));
}
