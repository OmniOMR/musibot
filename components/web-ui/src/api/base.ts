/**
 * Where the Web API is, as this bundle must address it.
 *
 * Musibot is published under a path prefix — `https://<host>/musibot/` — so
 * an absolute `/api/pipelines` would resolve against the origin root and miss
 * the deployment entirely. It has to be relative to wherever the bundle is
 * served from, which Vite knows and hands over as `import.meta.env.BASE_URL`
 * (the `base` setting in `vite.config.ts`, always with a trailing slash).
 *
 * The dev server serves under the same base and proxies the same prefix, so
 * this one value is correct in development and in production without a branch
 * between them.
 *
 * Everything that talks to the API must build its URLs from here. A literal
 * path written anywhere else works locally at the root, works in the dev
 * server, and 404s in the deployment.
 */
export const API_BASE_URL = `${import.meta.env.BASE_URL}api`;

/** The URL of one API endpoint, given its path as the service declares it. */
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path.startsWith("/") ? path : `/${path}`}`;
}
