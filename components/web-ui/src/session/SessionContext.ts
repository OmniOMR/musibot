import { createContext } from "react";

import type { PublicSession, TrackedPage } from "./ledger";

/** What a page needs recorded about it when it is first created. */
export interface NewPage {
  pageId: string;
  token: string;
  fileName: string;
}

export interface SessionState {
  /** Every page this browser still has, newest first. */
  pages: TrackedPage[];

  /**
   * A token a new page may be created under, minting one if the current
   * session has too little life left. This is the only thing that mints.
   *
   * Awaiting it is the first step of an upload, and the token it returns has to
   * be the one the page is then created with — asking again could return a
   * different session.
   */
  tokenForNewPage: () => Promise<PublicSession>;

  /** The token to send when asking about a page, or `null` if it is not ours. */
  tokenForPage: (pageId: string) => string | null;

  /** When a page will be deleted, which is when its session expires. */
  expiryOf: (pageId: string) => Date | null;

  /** Record a page just created. */
  rememberPage: (page: NewPage) => void;

  /** Note which pipeline was started on a page, for the session overview. */
  notePipeline: (pageId: string, name: string, version: string) => void;

  /**
   * Forget a session and its pages, after a `401` proved the token dead.
   * Never called for a `429`, which says nothing about the token.
   */
  forget: (token: string) => void;
}

/**
 * Undefined outside a provider, so that `useSession` can say which mistake was
 * made rather than handing back an empty session that silently does nothing.
 */
export const SessionContext = createContext<SessionState | undefined>(undefined);
