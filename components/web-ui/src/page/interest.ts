import { fileNameOf, subdivisionOf } from "../scene/scene";
import type { FileRow, FileSection } from "./files";

/**
 * Which *File* to show when the visitor has not asked for one.
 *
 * A page opens with nothing selected, and the canvas beside it is then empty
 * while a reading is plainly happening — which somebody who has just dropped a
 * scan in reads as a broken service rather than as a page they have not clicked
 * on yet. So one row is selected for them until they choose otherwise, and it
 * follows the recognition: the scan at first, the transcription once there is
 * one.
 *
 * "Most interesting" is a fixed order rather than anything clever, because the
 * question it answers is what a *reader* came for. A transcription is why they
 * uploaded the page; the boxes an earlier stage found are how they check it; the
 * scan itself is the thing they already have and the least worth showing back to
 * them. A page-level transcription outranks a staff-level one because it is the
 * whole answer rather than a piece of it.
 *
 * A *File* this list does not name is never chosen for somebody — a model may
 * write anything at all, and guessing at what a `debug.txt` means is worse than
 * showing the scan. The one exception is a page holding nothing else, where the
 * choice is between that file and an empty canvas.
 *
 * The levels are page and *subdivision*, not page and staff: `Staves`,
 * `Grandstaves` and `Systems` come from the Musicorpus Specification and Musibot
 * treats them all syntactically, so a rule written for staves holds for whatever
 * subdivision a future *Model* cuts a page into.
 */

type Level = "page" | "subdivision";

/** Everything Musibot draws as boxes over an image. */
function isAnnotation(name: string): boolean {
  return name.endsWith(".json");
}

function isMusicXml(name: string): boolean {
  return name.endsWith(".musicxml");
}

/**
 * The order, least interesting first. A row's rank is its index here.
 *
 * Extend it as models start writing new kinds of *File*; that is the whole of
 * what this decision is, and it is meant to be edited.
 */
const ORDER: { level: Level; matches: (name: string) => boolean }[] = [
  { level: "page", matches: (name) => name === "image.jpg" },
  { level: "page", matches: isAnnotation },
  { level: "subdivision", matches: (name) => name === "image.jpg" },
  { level: "subdivision", matches: isAnnotation },
  { level: "subdivision", matches: isMusicXml },
  { level: "page", matches: isMusicXml },
];

/** Where this row sits in the order, or -1 for one the order does not name. */
export function interestOf(row: FileRow): number {
  // A row stands for one path at page level and for every instance of one
  // pattern below it, and those instances are the same file under different
  // numbers — so the first is as good as any for deciding what the row is.
  const path = row.paths[0];
  if (path === undefined) {
    return -1;
  }

  const level: Level = subdivisionOf(path) === null ? "page" : "subdivision";
  const name = fileNameOf(path);

  return ORDER.findIndex((rule) => rule.level === level && rule.matches(name));
}

/**
 * The row to select for a visitor who has not selected one, or null.
 *
 * Null rather than a guess when nothing is recognised and there is more than
 * one candidate: showing an arbitrary file is a worse answer than showing none,
 * since a visitor cannot tell "this is what Musibot chose" from "this is what
 * Musibot produced".
 */
export function mostInteresting(sections: FileSection[]): FileRow | null {
  const rows = sections.flatMap((section) => section.rows);
  if (rows.length === 0) {
    return null;
  }

  const ranked = rows
    .map((row) => ({ row, interest: interestOf(row) }))
    .filter(({ interest }) => interest >= 0);

  if (ranked.length === 0) {
    // Nothing recognised. One file is still an obvious choice — it is that or
    // an empty canvas — and several are not.
    return rows.length === 1 ? rows[0] : null;
  }

  return ranked.reduce((best, next) => (next.interest > best.interest ? next : best)).row;
}
