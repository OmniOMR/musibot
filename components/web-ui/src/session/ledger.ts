/**
 * What this browser has done, and under which token.
 *
 * The api service has no endpoint that lists a user's pages, so if the app does
 * not write down what it uploaded, nothing does. This module is that record,
 * and the rules it enforces about *Public Sessions* are the interesting part.
 *
 *
 * ## Why there is more than one session
 *
 * A minted token lives about an hour, fixed at minting and never extended. A
 * page created under it dies with it. So a visitor who uploads at minute 55 of
 * a token's life gets a page that lives five minutes — which is not a limit
 * anyone chose, just an accident of when they happened to arrive.
 *
 * The fix is to stop treating "the session" as one token. Before a page is
 * created, the current token is checked: if it has more than
 * `MINIMUM_PAGE_LIFETIME_MS` left, it is used; if not, a new one is minted and
 * becomes current. Every page gets at least that much life, and the visitor
 * accumulates a few tokens over a long sitting rather than one.
 *
 * The consequence to keep in mind everywhere else: **a page's token is a
 * property of the page**, not of the app. Asking about an old page with the
 * current token answers `404` — as far as the service is concerned that is
 * somebody else's page — so every request about a page carries the token it was
 * created under, and a page's expiry is its token's expiry.
 *
 *
 * ## When a token is *not* minted
 *
 * Only the rule above mints. In particular a `429` never does: the caps are on
 * the public tier as one pool, so a fresh token buys nothing and would only add
 * load to a service already saying it has too much. That refusal is shown to
 * the visitor and nothing else happens.
 *
 * A `401` is different, and is the one case beyond the clock that drops a
 * session. It is proof the token is dead however much life we recorded for it —
 * the api service keeps all state in memory and rebuilds it empty on every
 * start, so a restart invalidates live tokens without the clock moving. The
 * session and its pages are forgotten, because they are genuinely gone, and the
 * next upload mints as it would for any expired token.
 */

/** A minted *Public Session*: a bearer token and when it stops working. */
export interface PublicSession {
  token: string;
  /** ISO 8601, as the service sent it. */
  expiresAt: string;
}

/** A page this browser uploaded, and the session that owns it. */
export interface TrackedPage {
  pageId: string;
  /** The session it was created under. Its expiry is this page's expiry. */
  token: string;
  /** What the visitor called the file they uploaded. */
  fileName: string;
  /** ISO 8601. */
  createdAt: string;
  /** The pipeline started on it, once one has been. */
  pipelineName: string | null;
  pipelineVersion: string | null;
}

export interface Ledger {
  sessions: PublicSession[];
  pages: TrackedPage[];
}

/**
 * How much life a token must have left to be given another page.
 *
 * Twenty minutes is a judgement about the work, not about the clock: it is
 * long enough for a page to be recognised, looked at and downloaded without the
 * visitor watching a countdown. Raising it means minting more often; lowering
 * it means pages that expire while someone is still reading them.
 */
export const MINIMUM_PAGE_LIFETIME_MS = 20 * 60 * 1000;

const STORAGE_KEY = "musibot.ledger.v1";

export const EMPTY: Ledger = { sessions: [], pages: [] };

/**
 * Read the ledger back.
 *
 * Tolerant of anything it finds. This is `localStorage`, which survives across
 * versions of the app, is shared with whatever else the origin stores and can
 * be edited by hand — so a shape that does not parse is discarded rather than
 * thrown over, since losing the record of an ephemeral hour is a smaller harm
 * than a landing page that will not render.
 */
export function read(storage: Storage = localStorage): Ledger {
  let parsed: unknown;
  try {
    const raw = storage.getItem(STORAGE_KEY);
    if (raw === null) {
      return EMPTY;
    }
    parsed = JSON.parse(raw);
  } catch {
    return EMPTY;
  }

  if (typeof parsed !== "object" || parsed === null) {
    return EMPTY;
  }
  const candidate = parsed as Partial<Ledger>;
  return {
    sessions: (Array.isArray(candidate.sessions) ? candidate.sessions : []).filter(isSession),
    pages: (Array.isArray(candidate.pages) ? candidate.pages : []).filter(isPage),
  };
}

export function write(ledger: Ledger, storage: Storage = localStorage): void {
  try {
    storage.setItem(STORAGE_KEY, JSON.stringify(ledger));
  } catch {
    // A full or disabled store is not a reason to fail an upload. The visitor
    // loses the list when the tab closes, and nothing else changes — the pages
    // themselves live on the server either way.
  }
}

function isSession(value: unknown): value is PublicSession {
  const session = value as Partial<PublicSession> | null;
  return (
    typeof session === "object" &&
    session !== null &&
    typeof session.token === "string" &&
    typeof session.expiresAt === "string"
  );
}

function isPage(value: unknown): value is TrackedPage {
  const page = value as Partial<TrackedPage> | null;
  return (
    typeof page === "object" &&
    page !== null &&
    typeof page.pageId === "string" &&
    typeof page.token === "string"
  );
}

/**
 * Drop what has expired.
 *
 * A page dies with its session, so both go together, and a page whose session
 * is not in the ledger at all is dropped too — without the token there is no
 * way to ask about it, which makes it unreachable rather than merely old.
 */
export function prune(ledger: Ledger, now: Date): Ledger {
  const alive = ledger.sessions.filter((session) => expiryOf(session) > now);
  const tokens = new Set(alive.map((session) => session.token));
  return {
    sessions: alive,
    pages: ledger.pages.filter((page) => tokens.has(page.token)),
  };
}

/** Forget a session and everything created under it. For a `401`. */
export function forgetSession(ledger: Ledger, token: string): Ledger {
  return {
    sessions: ledger.sessions.filter((session) => session.token !== token),
    pages: ledger.pages.filter((page) => page.token !== token),
  };
}

function expiryOf(session: PublicSession): Date {
  return new Date(session.expiresAt);
}

/**
 * The session a new page may be created under, or `null` if one must be minted.
 *
 * The newest session wins, and only if it has more than
 * `MINIMUM_PAGE_LIFETIME_MS` left. Anything shorter is refused rather than
 * stretched: the point is that a page's life is decided before it is created,
 * not discovered afterwards.
 */
export function sessionForNewPage(ledger: Ledger, now: Date): PublicSession | null {
  const threshold = now.getTime() + MINIMUM_PAGE_LIFETIME_MS;
  const usable = ledger.sessions.filter((session) => expiryOf(session).getTime() > threshold);
  if (usable.length === 0) {
    return null;
  }
  return usable.reduce((latest, session) =>
    expiryOf(session) > expiryOf(latest) ? session : latest,
  );
}

/** When a page will be deleted, which is when its session expires. */
export function pageExpiry(ledger: Ledger, page: TrackedPage): Date | null {
  const session = ledger.sessions.find((candidate) => candidate.token === page.token);
  return session === undefined ? null : expiryOf(session);
}

/** The token to send when asking about a page. Never the current one. */
export function tokenForPage(ledger: Ledger, pageId: string): string | null {
  return ledger.pages.find((page) => page.pageId === pageId)?.token ?? null;
}

export function addSession(ledger: Ledger, session: PublicSession): Ledger {
  return { ...ledger, sessions: [...ledger.sessions, session] };
}

/** Record a page, or replace what is known about one already recorded. */
export function addPage(ledger: Ledger, page: TrackedPage): Ledger {
  const others = ledger.pages.filter((candidate) => candidate.pageId !== page.pageId);
  return { ...ledger, pages: [...others, page] };
}

/** Pages newest first, which is the order every screen shows them in. */
export function pagesNewestFirst(ledger: Ledger): TrackedPage[] {
  return [...ledger.pages].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}
