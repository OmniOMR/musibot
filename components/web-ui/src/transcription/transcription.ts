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
 * file that happened to be clicked. `transcription.musicxml` is what gets
 * rendered as notation and `transcription.lmx` is the token sequence a model
 * developer reads underneath it; selecting either shows both, because they are
 * two views of one answer and nobody wants to click twice.
 */
export interface Reading {
  /** The folder these files live in — `` at page level, `Staves/3/` below it. */
  folder: string;
  /** "staff 3", or `null` at page level. */
  label: string | null;
  /** The rendered notation's source, if the folder holds one. */
  musicXmlPath: string | null;
  /** The token sequence, if the folder holds one. */
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
 */
export function readingsFor(selected: FileRow | null, files: FileView[]): Reading[] {
  if (!opensTranscription(selected) || selected === null) {
    return [];
  }

  const subdivision = subdivisionOf(selected.paths[0]);
  const folders = new Set<string>();
  for (const path of selected.paths) {
    folders.add(path.slice(0, path.lastIndexOf("/") + 1));
  }

  const held = new Set(files.map((file) => file.path));

  return [...folders]
    .sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    .map((folder) => ({
      folder,
      label: subdivision === null ? null : instanceLabel(`${folder}transcription.musicxml`),
      musicXmlPath: held.has(`${folder}transcription.musicxml`)
        ? `${folder}transcription.musicxml`
        : null,
      lmxPath:
        selected.name === "transcription.lmx"
          ? held.has(`${folder}transcription.lmx`)
            ? `${folder}transcription.lmx`
            : null
          : null,
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

  // repair MusicXML part by part
  for (const part of doc.querySelectorAll("part")) {
    // get the divisions value for this part
    const divisions = parseInt(part.querySelector("divisions")?.textContent || "1");

    // OSMD expects the duration element for rests.
    // But measure rests do not have it (at least those exported by MuseScore)
    // and LMX does not produce it. So we add a duration element to every
    // measure rest that does not have it with duration equal to four beats.
    for (const measureRest of doc.querySelectorAll(`rest[measure="yes"]`)) {
      if (measureRest.parentElement?.querySelector("duration")) {
        continue;
      }
      const duration = doc.createElement("duration");
      duration.innerText = String(divisions * 4);
      measureRest.after(duration);
    }
  }

  const serializer = new XMLSerializer();
  return serializer.serializeToString(doc);
}
