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
 * One consequence to be aware of: FastAPI generates the URLs in its
 * interactive docs from where it thinks it is mounted, so `/api/docs` will
 * not work until the service is told its prefix (`root_path`). That is a
 * change to the api service, not to this file.
 */
const API_PREFIX = "/api";

const API_TARGET = process.env.MUSIBOT_API_URL ?? "http://127.0.0.1:8080";

/**
 * The public origin the built bundle will be served from.
 *
 * index.html hardcodes its SEO tags — canonical link, Open Graph, Twitter
 * card — and they have to carry absolute URLs, so the origin has to be known
 * at build time. Override it for a real deployment:
 *
 *     MUSIBOT_PUBLIC_URL=https://musibot.example.cz npm run build
 *
 * Getting it wrong means link previews and search results that point at
 * somebody else's host, which is why it is a loud placeholder rather than a
 * plausible-looking guess.
 */
const PUBLIC_URL = (process.env.MUSIBOT_PUBLIC_URL ?? "https://musibot.example.org").replace(
  /\/$/,
  "",
);

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
      this.emitFile({
        type: "asset",
        fileName: "robots.txt",
        source: [
          "User-agent: *",
          "Allow: /$",
          "Disallow: /app/",
          "Disallow: /musicorpus-pages/",
          "Disallow: /docs",
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
