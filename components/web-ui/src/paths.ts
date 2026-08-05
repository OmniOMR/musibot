/**
 * The app's own routes, written down once.
 *
 * These are *router* paths, not URLs, and the leading slash is correct here —
 * which is worth saying out loud, because `src/api/base.ts` forbids exactly
 * that shape. The difference is who resolves the path. A `fetch("/api/...")`
 * is resolved by the browser against the origin root and misses the `/musibot/`
 * deployment; a react-router path is resolved against the router's `basename`,
 * which `App.tsx` sets from `import.meta.env.BASE_URL`. So the app writes its
 * routes as if it lived at the root, and one setting moves all of them.
 *
 * The names follow the domain and the HTTP API rather than being shortened:
 * a *MusicorpusPage* is what the API calls it, what the docs call it, and what
 * the URL should call it too.
 */

/** Landing page: the pitch, and the upload that starts everything. */
export const LANDING = "/";

/** One *MusicorpusPage* — the four-panel screen the recognition happens on. */
export const MUSICORPUS_PAGE = "/musicorpus-pages/:pageId";

/** Everything this browser has uploaded while its session lasts. */
export const SESSION = "/session";

/** The address of one *MusicorpusPage*, given its ID. */
export function musicorpusPagePath(pageId: string): string {
  return `/musicorpus-pages/${encodeURIComponent(pageId)}`;
}
