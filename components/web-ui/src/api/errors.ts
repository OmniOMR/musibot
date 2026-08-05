/**
 * What the API can refuse with, as types rather than status codes.
 *
 * The public tier answers several refusals that mean genuinely different things
 * to a visitor, and the screens have different copy for each. Sorting them here
 * rather than at every call site keeps a `catch` from having to remember that
 * `429` means two things depending on whether a `Retry-After` came with it.
 *
 * Fields are declared and assigned rather than written as constructor
 * parameter properties: `erasableSyntaxOnly` is on in `tsconfig`, so the only
 * TypeScript allowed is the kind that vanishes when the types are stripped, and
 * a parameter property emits an assignment.
 */

/** Any refusal from the API, carrying what the service said about it. */
export class ApiError extends Error {
  readonly status: number;
  /** The service's own `detail`, when it sent one. Not for display. */
  readonly detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * The public tier is full — too many executions at once, or too many pages
 * held by this session.
 *
 * `retryAfterSeconds` is present when waiting is the answer and absent when it
 * is not: over the page cap, deleting a page helps and waiting does not, so the
 * service deliberately sends no `Retry-After`. A countdown must therefore only
 * be shown when this is set.
 *
 * Receiving this is never a reason to mint a new session. The caps are on the
 * public tier as a whole, so a fresh token buys nothing — it would only add
 * load to a service already saying it has too much.
 */
export class RateLimited extends ApiError {
  readonly retryAfterSeconds: number | null;

  constructor(message: string, retryAfterSeconds: number | null, detail?: string) {
    super(message, 429, detail);
    this.name = "RateLimited";
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

/**
 * The token is not accepted any more.
 *
 * Which means the session is over and every page created under it is gone — the
 * api service holds all state in memory and rebuilds it empty on every start,
 * so this arrives both when a session genuinely expires and when the service
 * restarts under a session that had time left. There is no way to tell the two
 * apart from here, and both have the same consequence.
 */
export class SessionExpired extends ApiError {
  constructor(message: string, detail?: string) {
    super(message, 401, detail);
    this.name = "SessionExpired";
  }
}

/**
 * This instance does not offer public access at all — the minting endpoint
 * answers `404`. A deployment decision rather than a fault, and one the UI can
 * only report.
 */
export class PublicAccessUnavailable extends ApiError {
  constructor(message: string, detail?: string) {
    super(message, 404, detail);
    this.name = "PublicAccessUnavailable";
  }
}

/** Object storage held by the public tier is full. Nothing to wait for. */
export class PublicStorageFull extends ApiError {
  constructor(message: string, detail?: string) {
    super(message, 507, detail);
    this.name = "PublicStorageFull";
  }
}
