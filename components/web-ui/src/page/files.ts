import type { FileView } from "../api/types";

/**
 * A page's *Files*, arranged the way the design shows them.
 *
 * Two things about the arrangement are decisions rather than presentation.
 *
 * **It is not grouped by execution.** A page's folder is flat storage that any
 * number of executions have written into, and a later one may overwrite what an
 * earlier one produced — so a file belongs to the page, not to the run that
 * happened to write it. Grouping by execution would put the same path under two
 * headings and make the second one a lie.
 *
 * **Files inside a subdivision collapse into one row.** A page of twelve staves
 * holds twenty-four staff-level files, and listing them individually would bury
 * the four page-level ones that a visitor is actually looking for. They also
 * behave as one thing downstream: selecting staff transcriptions shows all of
 * them at once rather than isolating a staff, so one row is what the selection
 * actually means.
 *
 * Which folders are subdivisions is not written down here, because Musibot
 * does not know either — `Staves`, `Grandstaves` and `Systems` come from the
 * Musicorpus Specification, and Musibot treats a path purely syntactically so
 * that a new subdivision level is not a change to Musibot. So the rule is
 * structural: `<folder>/<instance>/<name>` is a subdivision file, and the
 * folder names itself.
 */
export interface FileRow {
  /** Stable identity for selection. Equal to `label`. */
  key: string;
  /** What the row is called — a concrete path, or a pattern for a group. */
  label: string;
  /**
   * `label` without the section's own heading, split so that the panel can
   * shorten it from the middle.
   *
   * A 300-pixel column cannot hold `Staves/{s}/transcription.musicxml`, and
   * cutting the tail off would hide the only part that distinguishes it from
   * `Staves/{s}/transcription.lmx` beside it. Two things give way, in order:
   * the heading folder, which the section above the row already says, and then
   * the remaining folders. The file name always stays.
   */
  prefix: string;
  name: string;
  /** The concrete paths this row stands for. One, unless it is a group. */
  paths: string[];
  /** Bytes across all of them. */
  size: number;
  /** How many instances a subdivision row covers. `null` at page level. */
  instances: number | null;
  /** True for the file the visitor uploaded — the one thing they already have. */
  isSource: boolean;
  /** A running execution declares this path among its outputs. */
  willBeOverwritten: boolean;
}

export interface FileSection {
  /** `Page`, or the subdivision folder's own name. */
  heading: string;
  rows: FileRow[];
}

/**
 * Group a listing into the sections the panel renders.
 *
 * `sourcePath` is where the visitor's own upload went, which is not a constant:
 * it was decided by the *Signature* of the pipeline they chose, so it is
 * `image.jpg` for a page-level run and `Staves/1/image.jpg` for a staff-level
 * one. See `pipelines.uploadPathFor`.
 */
export function groupFiles(
  files: FileView[],
  { sourcePath, overwritten = [] }: { sourcePath: string | null; overwritten?: string[] },
): FileSection[] {
  const willOverwrite = new Set(overwritten);
  const sections = new Map<string, Map<string, FileRow>>();

  for (const file of files) {
    const segments = file.path.split("/");
    const isSubdivision = segments.length >= 3;

    const heading = isSubdivision ? segments[0] : "Page";
    // `Staves/7/image.jpg` and `Staves/8/image.jpg` are one row; the instance
    // is what varies and `{s}` is how a Signature writes "whichever".
    const label = isSubdivision ? [segments[0], "{s}", ...segments.slice(2)].join("/") : file.path;

    const rows = sections.get(heading) ?? new Map<string, FileRow>();
    sections.set(heading, rows);

    const existing = rows.get(label);
    if (existing === undefined) {
      // The heading is rendered above the row, so the row does not repeat it.
      const shown = isSubdivision ? label.slice(heading.length + 1) : label;
      rows.set(label, {
        key: label,
        label,
        prefix: shown.slice(0, shown.lastIndexOf("/") + 1),
        name: shown.slice(shown.lastIndexOf("/") + 1),
        paths: [file.path],
        size: file.size,
        instances: isSubdivision ? 1 : null,
        isSource: file.path === sourcePath,
        willBeOverwritten: willOverwrite.has(file.path),
      });
    } else {
      existing.paths.push(file.path);
      existing.size += file.size;
      existing.instances = (existing.instances ?? 0) + 1;
      existing.isSource ||= file.path === sourcePath;
      existing.willBeOverwritten ||= willOverwrite.has(file.path);
    }
  }

  // `Page` first, then subdivisions in the order storage happened to mention
  // them. Nothing in a Signature orders instances, so nothing here pretends to.
  return [...sections.entries()]
    .sort(([a], [b]) => (a === "Page" ? -1 : b === "Page" ? 1 : a.localeCompare(b)))
    .map(([heading, rows]) => ({
      heading,
      rows: [...rows.values()].sort((a, b) => a.label.localeCompare(b.label)),
    }));
}

/** `2.1 kB`, `84.7 kB`, `1.2 MB` — enough to tell empty from written. */
export function formatSize(bytes: number): string {
  if (bytes < 1000) {
    return `${bytes} B`;
  }
  if (bytes < 1000 * 1000) {
    return `${(bytes / 1000).toFixed(1)} kB`;
  }
  return `${(bytes / 1000 / 1000).toFixed(1)} MB`;
}
