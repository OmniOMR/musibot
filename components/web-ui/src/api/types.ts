/**
 * The API's response bodies, as this app reads them.
 *
 * Field names are the wire's — `page_id`, `last_modified` — rather than
 * camel-cased on the way in. Renaming would mean a translation layer for every
 * shape and a second vocabulary to hold in your head while reading
 * `docs/http-api.md` beside the code; the cost of the inconsistency is one
 * underscore.
 *
 * These are declarations, not validators. The service is the one that built
 * them and the two ship from the same repository.
 */

/** A freshly minted *Public Session*. `expires_at` is ISO 8601. */
export interface PublicSessionView {
  token: string;
  expires_at: string;
}

/** One execution of a *Pipeline* against a page. */
export interface PipelineExecutionView {
  execution_id: number;
  pipeline_name: string;
  pipeline_version: string;
  input: string[];
  /** `queued`, `running`, `completed`, `failed` — the service's word for it. */
  state: string;
  error: string | null;
}

/** A *MusicorpusPage*. Its *Files* are not here; ask `listFiles`. */
export interface MusicorpusPageView {
  page_id: string;
  executions: PipelineExecutionView[];
}

/** One *File* the page currently holds. */
export interface FileView {
  path: string;
  size: number;
  last_modified: string;
}

export interface FileListingResponse {
  files: FileView[];
}

/** Presigned URLs, keyed by the *File* path they were asked for. */
export interface FileUrlsResponse {
  put: Record<string, string>;
  get: Record<string, string>;
  expires_at: string;
}

export interface SignatureView {
  input: string[];
  output: string[];
}

export interface PipelineView {
  name: string;
  version: string;
  signature: SignatureView;
  /** True for the single-*Model* pipeline Musibot offers for every *Model*. */
  implicit: boolean;
  orchestrators: string[];
  /** Live announcers behind this entry. A diagnostic, not a capacity figure. */
  instances: number;
}

export interface PipelineWarningView {
  type: string;
  message: string;
  pipeline: { name: string; version: string };
}

export interface PipelineListingResponse {
  pipelines: PipelineView[];
  warnings: PipelineWarningView[];
}

/**
 * One line of a page's log, as one event of the SSE stream carries it.
 *
 * `seconds` is time since its *Pipeline Execution* started rather than a
 * timestamp — what a reader is judging is how long a step took — and it is
 * measured on the service's clock, the one clock every line passes through.
 */
export interface LogLineView {
  execution_id: number;
  seconds: number;
  /** `worker` and `orchestrator` lines were printed by a *Model* or a
   * *Pipeline*; `api` is the service saying what it did with the execution. */
  kind: "worker" | "orchestrator" | "api";
  /** The *Model* or *Pipeline* that printed it, or `api` for the service. */
  source: string;
  level: "debug" | "info" | "warning" | "error";
  message: string;
}

/**
 * *Files* one *Pipeline Execution* has just written, as one SSE event carries
 * it.
 *
 * An invitation to look rather than a description of the page: the paths are
 * what changed, and what the page now holds — with sizes and times — comes from
 * `listFiles`. Deletions never appear; they do not propagate out of a *Model*.
 */
export interface FileChangeView {
  execution_id: number;
  paths: string[];
}

/**
 * One ended *Pipeline Execution*, as one event of the result stream carries it.
 *
 * It names its page because that stream is scoped to a *User*: it carries every
 * page of the identity, so a watcher of one page filters on `page_id`.
 */
export interface ExecutionResultView {
  page_id: string;
  execution: PipelineExecutionView;
}

/** What starting a *Pipeline Execution* asks for. */
export interface StartExecutionRequest {
  pipeline_name: string;
  pipeline_version: string;
  /**
   * The *Files* to run over. Required, and the service will not invent it: it
   * holds no list of a page's *Files* and never learns which presigned upload
   * URLs were used. See `docs/signatures.md`.
   */
  input: string[];
  parameters?: Record<string, unknown>;
}
