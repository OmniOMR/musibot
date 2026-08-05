import { useEffect, useRef, useState } from "react";

import { createFileUrls } from "../api/client";
import type { FileView } from "../api/types";
import { readCoco, type CocoLayer } from "./coco";
import { fileNameOf } from "./scene";

/**
 * The bytes the canvas needs, held in memory.
 *
 * Files are fetched into blobs and images are shown from object URLs rather
 * than from the presigned URL itself. Three reasons, and only the first is
 * about signatures:
 *
 * **Presigned URLs expire long before a page does** — fifteen minutes against
 * about an hour — so an `<image href>` pointing at one turns into a 403 while
 * somebody is still looking at it. Fetching once removes the problem instead of
 * scheduling a repair for it.
 *
 * **A fetch is when the latest bytes are read.** A second execution may
 * overwrite a *File* the canvas is already showing, and the cache is keyed by
 * path *and* last-modified time, so a rewritten file misses the cache and is
 * re-read while an untouched one is free to return to.
 *
 * **Streaming will need this anyway.** Object storage only holds a *File* once
 * it is complete, so watching one arrive means accumulating it in memory —
 * which makes streaming a change to how this buffer fills rather than a change
 * to anything that renders.
 *
 * Only the selected layer is fetched. A page can hold several megabytes of
 * staff crops and nothing should pull them all because one of them was asked
 * for.
 */
/** An image, held in memory and measured. */
export interface SceneImage {
  /** An object URL. Valid until the selection changes or the panel unmounts. */
  url: string;
  width: number;
  height: number;
}

export interface SceneData {
  images: Map<string, SceneImage>;
  /** Parsed COCO layers, by path. */
  overlays: Map<string, CocoLayer>;
  /** Anything textual — MusicXML, LMX — as it came off the wire. */
  texts: Map<string, string>;
  loading: boolean;
  error: string | null;
}

interface CacheEntry {
  /** The `last_modified` the bytes were read at. */
  version: string;
  image?: SceneImage;
  coco?: CocoLayer;
  text?: string;
}

const EMPTY: SceneData = {
  images: new Map(),
  overlays: new Map(),
  texts: new Map(),
  loading: false,
  error: null,
};

/**
 * What to make of a *File*, decided by its name.
 *
 * Musibot itself never parses a *File* — it moves opaque bytes with a path —
 * so this is the app's own reading of the Musicorpus Specification's
 * vocabulary, and it is deliberately shallow: an image to draw, a COCO
 * document to take boxes from, or text to show. Anything else is text too,
 * which is wrong for a `.mscz` but is never asked for.
 */
function kindOf(path: string): "image" | "coco" | "text" {
  const name = fileNameOf(path);
  if (name.endsWith(".json")) {
    return "coco";
  }
  return /\.(jpe?g|png|webp|gif)$/i.test(name) ? "image" : "text";
}

export function useSceneData(
  pageId: string,
  token: string | null,
  paths: string[],
  files: FileView[],
): SceneData {
  const [data, setData] = useState<SceneData>(EMPTY);

  /**
   * What has already been read, so that clicking between two layers does not
   * fetch either of them twice. Object URLs live here rather than in state,
   * because they have to be revoked by hand and a ref is what survives to the
   * unmount that has to do it.
   */
  const cache = useRef(new Map<string, CacheEntry>());

  // The paths and their versions as one string, so the effect re-runs when the
  // selection changes or when a file it is showing has been rewritten.
  const versions = paths
    .map((path) => `${path}@${files.find((file) => file.path === path)?.last_modified ?? ""}`)
    .join("|");

  useEffect(() => {
    if (token === null || paths.length === 0) {
      setData(EMPTY);
      return;
    }

    let cancelled = false;
    setData((previous) => ({ ...previous, loading: true, error: null }));

    void (async () => {
      try {
        const wanted = versions.split("|").map((entry) => {
          const at = entry.lastIndexOf("@");
          return { path: entry.slice(0, at), version: entry.slice(at + 1) };
        });

        const stale = wanted.filter(
          ({ path, version }) => cache.current.get(path)?.version !== version,
        );

        if (stale.length > 0) {
          // One signing call for the whole selection, then straight to storage
          // for each — the api service is never in the byte path.
          const urls = await createFileUrls(token, pageId, {
            get: stale.map(({ path }) => path),
          });

          await Promise.all(
            stale.map(async ({ path, version }) => {
              const url = urls.get[path];
              if (url === undefined) {
                throw new Error(`No download URL was issued for ${path}.`);
              }
              const response = await fetch(url);
              if (!response.ok) {
                throw new Error(`${path} could not be read (${response.status}).`);
              }

              // Replacing an entry means the old object URL is about to become
              // unreachable, so it is released here rather than leaked.
              revoke(cache.current.get(path));

              switch (kindOf(path)) {
                case "coco":
                  cache.current.set(path, { version, coco: readCoco(await response.json()) });
                  break;
                case "image":
                  cache.current.set(path, { version, image: await measure(await response.blob()) });
                  break;
                default:
                  cache.current.set(path, { version, text: await response.text() });
              }
            }),
          );
        }

        if (cancelled) {
          return;
        }

        const images = new Map<string, SceneImage>();
        const overlays = new Map<string, CocoLayer>();
        const texts = new Map<string, string>();
        for (const { path } of wanted) {
          const entry = cache.current.get(path);
          if (entry?.image !== undefined) {
            images.set(path, entry.image);
          }
          if (entry?.coco !== undefined) {
            overlays.set(path, entry.coco);
          }
          if (entry?.text !== undefined) {
            texts.set(path, entry.text);
          }
        }
        setData({ images, overlays, texts, loading: false, error: null });
      } catch (error) {
        if (!cancelled) {
          setData({
            images: new Map(),
            overlays: new Map(),
            texts: new Map(),
            loading: false,
            error: error instanceof Error ? error.message : "That layer could not be read.",
          });
        }
      }
    })();

    return () => {
      cancelled = true;
    };
    // `versions` carries both the paths and their modification times.
  }, [pageId, token, versions]);

  // Every object URL this component made, released when it goes away.
  useEffect(() => {
    const held = cache.current;
    return () => {
      for (const entry of held.values()) {
        revoke(entry);
      }
      held.clear();
    };
  }, []);

  return data;
}

/**
 * Decode far enough to know how big the image is.
 *
 * SVG's `<image>` has no `naturalWidth` to read after the fact — that belongs
 * to the HTML element — and the size is needed before rendering anyway: it is
 * what stacks the staff crops without overlapping them, and what "Fit" frames.
 * So it is measured once here, beside the bytes it describes.
 */
async function measure(blob: Blob): Promise<SceneImage> {
  const url = URL.createObjectURL(blob);
  try {
    const bitmap = await createImageBitmap(blob);
    const size = { width: bitmap.width, height: bitmap.height };
    bitmap.close();
    return { url, ...size };
  } catch {
    // `createImageBitmap` refuses a format the canvas cannot decode. The
    // browser may still render it, so fall back to loading it as an image.
    return await new Promise<SceneImage>((resolve) => {
      const image = new Image();
      image.onload = () => resolve({ url, width: image.naturalWidth, height: image.naturalHeight });
      image.onerror = () => resolve({ url, width: 0, height: 0 });
      image.src = url;
    });
  }
}

function revoke(entry: CacheEntry | undefined): void {
  if (entry?.image !== undefined) {
    URL.revokeObjectURL(entry.image.url);
  }
}
