import { useCallback, useMemo, useRef, useState, type ReactNode } from "react";

import { mintPublicSession } from "../api/client";
import * as ledger from "./ledger";
import { SessionContext, type NewPage, type SessionState } from "./SessionContext";

/**
 * Holds the ledger, and is the only place that mints.
 *
 * The rules it enforces are `ledger.ts`'s; what this adds is React state, one
 * copy of the truth, and a guard against minting twice at once — a visitor who
 * drops three files in quick succession would otherwise open three minting
 * requests and end up with three sessions where one was needed, which is
 * exactly the spamming the rule exists to prevent.
 */
export default function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<ledger.Ledger>(() => ledger.prune(ledger.read(), new Date()));

  /**
   * The mint in flight, if there is one. Concurrent callers await the same
   * promise rather than starting their own; a ref rather than state because
   * nothing renders differently while it is pending and a re-render here would
   * be one more chance to start a second request.
   */
  const minting = useRef<Promise<ledger.PublicSession> | null>(null);

  const commit = useCallback((next: ledger.Ledger) => {
    ledger.write(next);
    setState(next);
    return next;
  }, []);

  const tokenForNewPage = useCallback(async (): Promise<ledger.PublicSession> => {
    const pruned = ledger.prune(ledger.read(), new Date());
    const usable = ledger.sessionForNewPage(pruned, new Date());
    if (usable !== null) {
      // The clock may have moved since the last render, so the pruning above is
      // worth keeping even when nothing has to be minted.
      commit(pruned);
      return usable;
    }

    minting.current ??= (async () => {
      try {
        const minted = await mintPublicSession();
        const session: ledger.PublicSession = {
          token: minted.token,
          expiresAt: minted.expires_at,
        };
        commit(ledger.addSession(ledger.prune(ledger.read(), new Date()), session));
        return session;
      } finally {
        minting.current = null;
      }
    })();

    return minting.current;
  }, [commit]);

  const rememberPage = useCallback(
    (page: NewPage) => {
      commit(
        ledger.addPage(ledger.read(), {
          pageId: page.pageId,
          token: page.token,
          fileName: page.fileName,
          createdAt: new Date().toISOString(),
          pipelineName: null,
          pipelineVersion: null,
        }),
      );
    },
    [commit],
  );

  const notePipeline = useCallback(
    (pageId: string, name: string, version: string) => {
      const current = ledger.read();
      const page = current.pages.find((candidate) => candidate.pageId === pageId);
      if (page === undefined) {
        return;
      }
      commit(ledger.addPage(current, { ...page, pipelineName: name, pipelineVersion: version }));
    },
    [commit],
  );

  const forget = useCallback(
    (token: string) => {
      commit(ledger.forgetSession(ledger.read(), token));
    },
    [commit],
  );

  const value = useMemo<SessionState>(
    () => ({
      pages: ledger.pagesNewestFirst(state),
      tokenForNewPage,
      tokenForPage: (pageId) => ledger.tokenForPage(state, pageId),
      expiryOf: (pageId) => {
        const page = state.pages.find((candidate) => candidate.pageId === pageId);
        return page === undefined ? null : ledger.pageExpiry(state, page);
      },
      rememberPage,
      notePipeline,
      forget,
    }),
    [state, tokenForNewPage, rememberPage, notePipeline, forget],
  );

  return <SessionContext value={value}>{children}</SessionContext>;
}
