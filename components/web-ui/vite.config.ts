import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

/**
 * In development the app is served by Vite and the API runs as a separate
 * process on 127.0.0.1:8080 (see `components/api/README.md`). Proxying rather
 * than pointing the app at an absolute URL keeps the browser on one origin,
 * which is what it will be in production too — nginx serves this bundle and
 * reverse-proxies the API behind the same host — so no CORS handling is
 * needed in either place, and no code differs between the two.
 *
 * The app addresses the API under a single `/api` prefix, which is where it
 * sits in the deployment. The service itself still mounts its routes at the
 * root, so the prefix is stripped on the way through; nginx will do the same.
 * That the app never names an individual route here is the point — a route
 * added to the service needs no change on this side.
 *
 * FastAPI generates the URLs in its interactive docs from where it thinks it
 * is mounted, so `<base>api/docs` needs the service's `root_path` set to
 * match. That is a change to the api service, not to this file.
 */

/**
 * The path this app is served under.
 *
 * Musibot is published at `https://<host>/musibot/`, not at the root of a
 * host, and every URL the bundle emits has to account for that: script and
 * style tags, the favicon, and the app's own calls to the API. Vite handles
 * the assets from this one setting and exposes it to the app as
 * `import.meta.env.BASE_URL` — which is what `src/api/base.ts` builds on, and
 * why nothing in `src/` writes an absolute `/api/...`.
 *
 * The dev server serves under it too, so http://localhost:5173/musibot/ is
 * the development address. That is deliberate: a base path that only applies
 * to production is a base path that is only tested in production.
 */
const BASE = process.env.MUSIBOT_BASE_PATH ?? "/musibot/";

/**
 * Where the app addresses the API, and what the dev server proxies.
 *
 * The service itself mounts its routes at the root, so this prefix is
 * stripped on the way through — by the dev server here, and by nginx in the
 * deployment. That the app never names an individual API route is the point:
 * a route added to the service needs no change on this side.
 */
const API_PREFIX = `${BASE}api`;

const API_TARGET = process.env.MUSIBOT_API_URL ?? "http://127.0.0.1:8080";

/**
 * The scheme and host the deployment answers on — the origin, and nothing
 * more. Where under it Musibot sits is `BASE` above, and the two are joined
 * below rather than written out twice.
 *
 *     MUSIBOT_PUBLIC_ORIGIN=https://quest.ms.mff.cuni.cz npm run build
 */
const PUBLIC_ORIGIN = (process.env.MUSIBOT_PUBLIC_ORIGIN ?? "https://musibot.example.org").replace(
  /\/+$/,
  "",
);

/**
 * The absolute URL of this deployment, without a trailing slash.
 *
 * index.html hardcodes its SEO tags — canonical link, Open Graph, Twitter
 * card — and they have to carry absolute URLs, so this has to be known at
 * build time. Getting it wrong means link previews and search results that
 * point at somebody else's host, which is why the default is a loud
 * placeholder rather than a plausible-looking guess.
 */
const PUBLIC_URL = PUBLIC_ORIGIN + BASE.replace(/\/+$/, "");

/**
 * Everything that has to name the public origin: the tags in index.html, and
 * the two crawler files.
 *
 * Vite has its own `%VITE_*%` substitution for index.html, but it draws only
 * from `.env` files and this repository's root `.gitignore` excludes `*.env`
 * — a committed default would be invisible to git. And robots.txt and
 * sitemap.xml would not be substituted at all: `public/` is copied verbatim.
 * So all three are handled here, from the one constant above, because three
 * hardcoded copies of a domain is three chances to update two of them.
 *
 * The placeholder is `__MUSIBOT_PUBLIC_URL__` rather than `%VITE_PUBLIC_URL%`
 * so that Vite's own env scanner does not claim it and warn, on every build,
 * about a variable it was never meant to resolve.
 */
function publicUrlPlugin(): Plugin {
  return {
    name: "musibot:public-url",
    enforce: "pre",

    transformIndexHtml(html) {
      return html.replaceAll("__MUSIBOT_PUBLIC_URL__", PUBLIC_URL);
    },

    generateBundle() {
      // Only the landing page is worth indexing. The rest of the app is an
      // interactive tool behind an upload — nothing for a crawler to read,
      // and per-user pages it must not reach.
      //
      // A caveat that comes with being published under a path prefix: a
      // crawler reads robots.txt from the ORIGIN root and nowhere else, so
      // while Musibot lives at https://<host>/musibot/ this file is served
      // but never consulted — the rules that apply are whoever owns the
      // hostname's. It is emitted anyway because it costs nothing, because it
      // becomes correct the day Musibot gets a host of its own, and because
      // its contents are the honest description of what to crawl either way.
      // The sitemap does not share the limitation: it is found by being
      // submitted or linked, not by its location.
      this.emitFile({
        type: "asset",
        fileName: "robots.txt",
        source: [
          "User-agent: *",
          `Allow: ${BASE}$`,
          `Disallow: ${BASE}musicorpus-pages/`,
          `Disallow: ${BASE}session`,
          `Disallow: ${BASE}api/`,
          "",
          `Sitemap: ${PUBLIC_URL}/sitemap.xml`,
          "",
        ].join("\n"),
      });

      this.emitFile({
        type: "asset",
        fileName: "sitemap.xml",
        source: [
          '<?xml version="1.0" encoding="UTF-8"?>',
          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
          "  <url>",
          `    <loc>${PUBLIC_URL}/</loc>`,
          "    <changefreq>monthly</changefreq>",
          "    <priority>1.0</priority>",
          "  </url>",
          "</urlset>",
          "",
        ].join("\n"),
      });
    },
  };
}

export default defineConfig({
  base: BASE,

  plugins: [react(), publicUrlPlugin()],

  server: {
    port: 5173,
    proxy: {
      [API_PREFIX]: {
        target: API_TARGET,
        changeOrigin: true,
        rewrite: (path) => path.slice(API_PREFIX.length) || "/",
      },
    },
  },

  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
