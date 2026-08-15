import { createFileUrls, createPage, startExecution } from "../api/client";
import { ApiError } from "../api/errors";
import type { PipelineRef } from "../pipelines";

/**
 * Everything between "Start reading" and a page with a *Pipeline* running on it.
 *
 * Four calls, and the order matters: the page has to exist before a URL can be
 * signed for it, the bytes have to be in storage before an execution is told to
 * read them, and the execution has to name the *File* by the path it was
 * actually uploaded to.
 *
 * The bytes go straight to MinIO over a presigned URL and never through the api
 * service, which is what keeps the one non-horizontally-scaling service out of
 * the byte path. That request carries no `Authorization` header: the signature
 * is in the query string, and real object storage refuses a request that
 * presents both.
 */
export async function startRecognition({
  token,
  file,
  uploadPath,
  pipeline,
}: {
  token: string;
  file: File;
  /** Where the bytes must land for this pipeline — see `pipelines.uploadPathFor`. */
  uploadPath: string;
  pipeline: PipelineRef;
}): Promise<string> {
  const page = await createPage(token);

  const urls = await createFileUrls(token, page.page_id, { put: [uploadPath] });
  const url = urls.put[uploadPath];
  if (url === undefined) {
    throw new ApiError(`The service issued no upload URL for ${uploadPath}.`, 500);
  }

  const stored = await fetch(url, {
    method: "PUT",
    body: file,
    // What the bytes actually are, which is not what `uploadPath` calls them —
    // a PNG goes to `image.jpg` like everything else. See the note on
    // `ACCEPTED_IMAGE_TYPES`. Safe to send: the presigned signature covers the
    // bucket and key and does not sign this header, so storage records it
    // without checking it against anything.
    headers: { "Content-Type": file.type === "" ? "image/jpeg" : file.type },
  });
  if (!stored.ok) {
    throw new ApiError(`The page could not be uploaded (${stored.status}).`, stored.status);
  }

  // `input` has no default and the service will not invent one: it holds no
  // list of a page's Files and never learns which presigned URLs were used.
  // See docs/signatures.md.
  await startExecution(token, page.page_id, {
    pipeline_name: pipeline.name,
    pipeline_version: pipeline.version,
    input: [uploadPath],
  });

  return page.page_id;
}
