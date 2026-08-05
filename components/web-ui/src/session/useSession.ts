import { use } from "react";

import { SessionContext, type SessionState } from "./SessionContext";

/** The visitor's pages and tokens. Throws outside a `SessionProvider`. */
export function useSession(): SessionState {
  const session = use(SessionContext);
  if (session === undefined) {
    throw new Error("useSession was called outside a SessionProvider.");
  }
  return session;
}
