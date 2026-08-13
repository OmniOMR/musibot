import { apiUrl } from "./base";
import {
  ApiError,
  PublicAccessUnavailable,
  PublicStorageFull,
  RateLimited,
  SessionExpired,
} from "./errors";
import type {
  FileListingResponse,
  FileUrlsResponse,
  MusicorpusPageView,
  PipelineExecutionView,
  PipelineListingResponse,
  PublicSessionView,
  StartExecutionRequest,
} from "./types";

/**
 * The HTTP API, as functions.
 *
 * Every call but the first takes a `token` explicitly rather than reading an
 * ambient one, and that is the important decision in this file. A visitor
 * accumulates several *Public Sessions* over an hour of use, and a page belongs
 * to the one it was created under — asking about a page with the *current*
 * token answers `404`, because as far as the service is concerned that is
 * somebody else's page. Making the token a parameter means a call site cannot
 * forget which one it needs; see `session/ledger.ts` for why there is more than
 * one.
 *
 * Nothing here touches storage or the ledger. The bytes of a *File* never pass
 * through the api service at all — `createFileUrls` gets a presigned URL and
 * the transfer goes straight to MinIO, which is what keeps the one
 * non-horizontally-scaling service out of the byte path.
 */

interface RequestOptions {
  token?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Extra headers — `Accept`, for the one endpoint that answers a stream. */
  headers?: Record<string, string>;
}

/** The service's `detail` string, if the body was the shape it usually is. */
async function detailOf(response: Response): Promise<string | undefined> {
  try {
    const body: unknown = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      const detail = (body as { detail: unknown }).detail;
      return typeof detail === "string" ? detail : JSON.stringify(detail);
    }
  } catch {
    // A non-JSON error body is not itself an error worth reporting; the status
    // is what the caller branches on.
  }
  return undefined;
}

function errorFor(response: Response, detail: string | undefined): ApiError {
  switch (response.status) {
    case 401:
      return new SessionExpired("This session has ended.", detail);
    case 404:
      // Only the minting endpoint answers 404 as a statement about the
      // instance; everywhere else it means the page is not this caller's, which
      // the caller has to interpret in context.
      return new ApiError("Not found.", 404, detail);
    case 429: {
      const header = response.headers.get("Retry-After");
      const seconds = header === null ? null : Number.parseInt(header, 10);
      return new RateLimited(
        "Musibot is at its public limit just now.",
        seconds !== null && Number.isFinite(seconds) ? seconds : null,
        detail,
      );
    }
    case 507:
      return new PublicStorageFull("There is no room for another page just now.", detail);
    default:
      return new ApiError(`The service answered ${response.status}.`, response.status, detail);
  }
}

/**
 * One call to the API, answered or thrown.
 *
 * The raw `Response` rather than a parsed body, because one endpoint — the log
 * stream — answers with a body that never ends and must be read as it arrives.
 * Everything else goes through `request` below.
 */
export async function apiFetch(
  method: string,
  path: string,
  { token, body, signal, headers: extra }: RequestOptions = {},
): Promise<Response> {
  const headers: Record<string, string> = { ...extra };
  if (token !== undefined) {
    headers.Authorization = `Bearer ${token}`;
  }
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(apiUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    throw errorFor(response, await detailOf(response));
  }
  return response;
}

async function request<T>(method: string, path: string, options: RequestOptions = {}): Promise<T> {
  const response = await apiFetch(method, path, options);

  // 204 on DELETE, and nothing to parse.
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

// --- public sessions -------------------------------------------------------

/**
 * Mint a *Public Session*.
 *
 * Free, unlimited and unguarded — the token is worth nothing as a defence and
 * exists only so two members of the public do not see each other's pages. What
 * protects the instance is a set of caps on the public tier as one pool, which
 * is the service's business and not this app's. See `docs/public-access.md`.
 *
 * That it is free is not licence to call it freely. A token is what fixes a
 * page's lifetime, so minting one per page would be both pointless and rude;
 * `session/ledger.ts` holds the rule for when a new one is actually needed.
 */
export async function mintPublicSession(signal?: AbortSignal): Promise<PublicSessionView> {
  try {
    return await request<PublicSessionView>("POST", "/public-sessions", { signal });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) {
      throw new PublicAccessUnavailable(
        "This Musibot instance does not offer public access.",
        error.detail,
      );
    }
    throw error;
  }
}

// --- pages -----------------------------------------------------------------

export function createPage(token: string, signal?: AbortSignal): Promise<MusicorpusPageView> {
  return request<MusicorpusPageView>("POST", "/musicorpus-pages", { token, signal });
}

export function getPage(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<MusicorpusPageView> {
  return request<MusicorpusPageView>("GET", `/musicorpus-pages/${pageId}`, { token, signal });
}

export function deletePage(token: string, pageId: string, signal?: AbortSignal): Promise<void> {
  return request<void>("DELETE", `/musicorpus-pages/${pageId}`, { token, signal });
}

// --- files -----------------------------------------------------------------

/**
 * What the page holds right now.
 *
 * Polled while an execution runs, which is the whole of the progress mechanism
 * until the SSE stream exists — so a finished execution's outputs appear
 * together rather than one at a time. Answered from object storage, so it is
 * true across a *File* a later execution overwrote.
 */
export function listFiles(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<FileListingResponse> {
  return request<FileListingResponse>("GET", `/musicorpus-pages/${pageId}/files`, {
    token,
    signal,
  });
}

export function createFileUrls(
  token: string,
  pageId: string,
  paths: { put?: string[]; get?: string[] },
  signal?: AbortSignal,
): Promise<FileUrlsResponse> {
  return request<FileUrlsResponse>("POST", `/musicorpus-pages/${pageId}/file-urls`, {
    token,
    signal,
    body: { put: paths.put ?? [], get: paths.get ?? [] },
  });
}

// --- executions ------------------------------------------------------------

export function startExecution(
  token: string,
  pageId: string,
  body: StartExecutionRequest,
  signal?: AbortSignal,
): Promise<PipelineExecutionView> {
  return request<PipelineExecutionView>("POST", `/musicorpus-pages/${pageId}/pipeline-executions`, {
    token,
    signal,
    body,
  });
}

export function listExecutions(
  token: string,
  pageId: string,
  signal?: AbortSignal,
): Promise<PipelineExecutionView[]> {
  return request<PipelineExecutionView[]>(
    "GET",
    `/musicorpus-pages/${pageId}/pipeline-executions`,
    {
      token,
      signal,
    },
  );
}

// --- pipelines -------------------------------------------------------------

/**
 * Everything currently available, *ImplicitPipelines* included.
 *
 * Assembled from what *Orchestrators* and *Workers* announce over RabbitMQ
 * rather than configured anywhere, so it can lag reality by a few seconds and
 * an entry with zero `instances` is one whose announcer has just gone away.
 */
export function listPipelines(
  token: string,
  signal?: AbortSignal,
): Promise<PipelineListingResponse> {
  return request<PipelineListingResponse>("GET", "/pipelines", { token, signal });
}
