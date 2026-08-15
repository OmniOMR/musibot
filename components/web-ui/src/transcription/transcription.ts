import type { FileView } from "../api/types";
import type { FileRow } from "../page/files";
import { fileNameOf, instanceLabel, subdivisionOf } from "../scene/scene";

/**
 * Which *Files* the transcription panel is about.
 *
 * The panel opens when a transcription is selected, and shows one reading per
 * instance: one for a page-level file, one per staff for a staff-level one —
 * the same rule the canvas follows, and for the same reason. A reader checking
 * whether the recognition is right wants to see the notation beside the crop it
 * came from, and both panels showing the same set at the same time is what makes
 * that comparison possible.
 *
 * A reading is assembled from whatever the folder holds rather than from the
 * file that happened to be clicked, so the notation is always engraved when the
 * folder has MusicXML to engrave it from.
 */
export interface Reading {
  /** The folder these files live in — `` at page level, `Staves/3/` below it. */
  folder: string;
  /** "staff 3", or `null` at page level. */
  label: string | null;
  /** The rendered notation's source, if the folder holds one. */
  musicXmlPath: string | null;
  /** The token sequence, if the folder holds one and the tokens were asked for. */
  lmxPath: string | null;
}

/** Everything Musibot calls a transcription. */
const TRANSCRIPTION = /^transcription\./;

export function isTranscription(path: string): boolean {
  return TRANSCRIPTION.test(fileNameOf(path));
}

/** Whether selecting this row should open the panel at all. */
export function opensTranscription(selected: FileRow | null): boolean {
  return selected !== null && selected.paths.some(isTranscription);
}

/**
 * The readings a selection asks for, in instance order.
 *
 * Only the two formats the panel can do something with are collected. A
 * `transcription.mscz` sitting beside them is a *File* the page holds and the
 * overview lists, but it is a MuseScore document and there is nothing this
 * panel could show of it.
 *
 * The two are not symmetric. Notation is what a reading looks like to anybody,
 * so MusicXML is engraved whenever the folder holds it; the LMX underneath is a
 * model developer's view of the same answer, and a visitor who came to see
 * whether Musibot read their music correctly only scrolls past a wall of tokens
 * to get to the next staff. So the tokens are shown when they are what was
 * selected, and left out when the notation was.
 */
export function readingsFor(selected: FileRow | null, files: FileView[]): Reading[] {
  if (!opensTranscription(selected) || selected === null) {
    return [];
  }

  const wantsTokens = selected.name === "transcription.lmx";
  const subdivision = subdivisionOf(selected.paths[0]);
  const folders = new Set<string>();
  for (const path of selected.paths) {
    folders.add(path.slice(0, path.lastIndexOf("/") + 1));
  }

  const held = new Set(files.map((file) => file.path));
  const heldIn = (folder: string, name: string): string | null =>
    held.has(`${folder}${name}`) ? `${folder}${name}` : null;

  return [...folders]
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .map((folder) => ({
      folder,
      label: subdivision === null ? null : instanceLabel(`${folder}transcription.musicxml`),
      musicXmlPath: heldIn(folder, "transcription.musicxml"),
      lmxPath: wantsTokens ? heldIn(folder, "transcription.lmx") : null,
    }));
}

/** Every *File* the panel needs fetched. */
export function pathsOf(readings: Reading[]): string[] {
  return readings.flatMap((reading) =>
    [reading.musicXmlPath, reading.lmxPath].filter((path): path is string => path !== null),
  );
}

/**
 * Split an LMX document into tokens.
 *
 * LMX is Linearized MusicXML — the same content as the MusicXML beside it,
 * written as a flat sequence so that a sequence model can emit it. What a model
 * developer wants from it is to read what the model actually produced, token by
 * token, which means the split has to be the obvious one and not a parse:
 * whitespace, and nothing else. Anything cleverer would be this app's opinion
 * about a format it does not own.
 */
export function tokensOf(lmx: string): string[] {
  return lmx.trim().split(/\s+/).filter(Boolean);
}

/**
 * Adjusts given MusicXML string so that OSMD does not crash
 * on edgecases.
 */
export function preprocessMusicXmlForOSMD(musicXml: string): string {
  const parser = new DOMParser();
  const doc = parser.parseFromString(musicXml, "application/xml");

  // repair MusicXML part by part, because divisions is a per-part value
  for (const part of doc.querySelectorAll("part")) {
    // get the divisions value for this part
    const divisions = parseInt(part.querySelector("divisions")?.textContent || "1");

    // OSMD expects the duration element for rests.
    // But measure rests do not have it (at least those exported by MuseScore)
    // and LMX does not produce it. So we add a duration element to every
    // measure rest that does not have it with duration equal to four beats.
    for (const measureRest of part.querySelectorAll(`rest[measure="yes"]`)) {
      if (measureRest.parentElement?.querySelector("duration")) {
        continue;
      }
      const duration = doc.createElement("duration");
      // textContent, not innerText: this is an XML document, so createElement
      // gives a plain Element and innerText would be an expando property that
      // the serializer never sees — an empty <duration/> is no duration at all.
      duration.textContent = String(divisions * 4);
      measureRest.after(duration);
    }
  }

  const serializer = new XMLSerializer();
  return serializer.serializeToString(doc);
}
