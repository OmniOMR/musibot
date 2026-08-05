import { createFileUrls } from "./client";

/**
 * Fetch *Files* out of a page and hand them to the browser to save.
 *
 * The bytes come straight from object storage over a presigned URL and never
 * through the api service, exactly as they went in. The `download` attribute
 * would normally be ignored on a cross-origin link, so the blob is fetched and
 * saved from an object URL instead — which also means the browser saves it
 * under the *File's* own name rather than the signed URL's.
 */
export async function downloadFiles(token: string, pageId: string, paths: string[]): Promise<void> {
  if (paths.length === 0) {
    return;
  }

  const urls = await createFileUrls(token, pageId, { get: paths });

  for (const path of paths) {
    const url = urls.get[path];
    if (url === undefined) {
      continue;
    }
    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`${path} could not be downloaded (${response.status}).`);
    }
    save(await response.blob(), saveNameOf(path));
  }
}

/**
 * A flat name for a *File* that lives in a folder.
 *
 * `Staves/7/transcription.musicxml` saved as `transcription.musicxml` would
 * collide with staff 8's the moment two are saved together, and a browser
 * silently renames rather than asking. The folder is folded into the name.
 */
function saveNameOf(path: string): string {
  return path.replaceAll("/", "-");
}

function save(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
