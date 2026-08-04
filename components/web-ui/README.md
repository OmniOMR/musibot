# web-ui

Single-page web application for the *General public* and *Model developers*. A UI layer over the Web API.


## Responsibilities

- Upload page scans (JPEG), pick a pipeline, watch live progress via the API's SSE stream.
- View and download recognition results.


## Stack

React single-page app, written in TypeScript, using MUI (Material UI) components, built by Vite.

No server-side rendering and no SSG framework. The build produces static files that nginx serves, which is the whole of the deployment story — see [Search engines](#search-engines) for why that is enough.


## Development

Requires **Node 22.12+ or 24+** (Vite 8's floor; the test runner's jsdom wants 22.22+, so 24 is the comfortable choice).

```bash
cd components/web-ui
npm install
npm start
```

The dev server comes up on http://localhost:5173 and proxies `/api/*` to `127.0.0.1:8080`, which is where `musibot-api` runs with no configuration (see [../api/README.md](../api/README.md)). Point it elsewhere with `MUSIBOT_API_URL`.

Proxying rather than calling an absolute URL keeps the browser on a single origin, which is what production is too — nginx serves this bundle and reverse-proxies the API behind the same host — so no CORS handling is needed in either place and no code differs between them.

The app addresses the API under a single `/api` prefix, which is where it sits in the deployment. The service itself mounts its routes at the root, so the prefix is stripped on the way through and nginx does the same. The app therefore never names an individual API route, and a route added to the service needs no change here.

```bash
npm run build       # type-check, then bundle to dist/
npm run lint
npm run format      # prettier; npm run format:check in CI
npm test
npm run preview     # serve dist/ as nginx would
```

`start` and `test` are npm's own lifecycle names, so they run without `run`. Everything else needs `npm run`.


### Editor

`.vscode/` configures this component the way each python component configures itself, which `musibot.code-workspace` at the repository root is what makes work — every component is a workspace folder with its own tooling. Here that means eslint and prettier resolved from `node_modules` rather than from whatever the extensions bundle, so the editor and the command line agree, and the workspace TypeScript rather than the one VS Code ships.

Formatting is prettier's job and linting is eslint's — together they cover what ruff does alone on the python side. Markdown is excluded from both: this repository's markdown conventions (two blank lines before a heading, paragraphs left unwrapped) are not prettier's.


## Search engines

Only the landing page is meant to be indexed, and everything that makes that work is static in `index.html`: the title, description, canonical link, Open Graph and Twitter card tags, and a `<noscript>` body carrying the real pitch text.

That is deliberate, and it is worth knowing why, because "it is an SPA, so it cannot be indexed" is not the reason. Googlebot does execute JavaScript and would index the rendered app. What does *not* execute JavaScript is every link-preview scraper — Slack, LinkedIn, X, Mastodon, Facebook. Since the point of the public tier is a URL that gets emailed around and shown at conferences (see [Who are the users](../../docs/who-are-the-users.md)), those previews matter at least as much as ranking, and they are built only from static tags.

So the rule is: **keep the meta tags and the `<noscript>` body truthful and in sync with what the app actually says.** They are the only version of this page that some clients will ever see.

`robots.txt` and `sitemap.xml` are generated at build time by a small plugin in `vite.config.ts`, from the same constant that fills in the tags, so the public origin is written down once.

If more pages ever need indexing, the upgrade path is build-time prerendering (`vite-react-ssg`, or React Router's `prerender` with `ssr: false`) rather than a server. It is not free with MUI, though: emotion styles at runtime, so prerendered HTML needs critical-CSS extraction or it arrives unstyled and flashes.


### The public URL

`index.html` needs absolute URLs, so the origin is baked in at build time. The default is a deliberately obvious placeholder:

```bash
MUSIBOT_PUBLIC_URL=https://musibot.example.cz npm run build
```

Getting this wrong means link previews and search results that point at somebody else's host.


## Theme

The look is printed paper: a warm ivory page, a serif for headings, flat surfaces separated by hairline rules rather than drop shadows, and Charles University's cardinal red as the one saturated colour.

- `src/theme/palette.ts` — the colour tokens. The reds and the blue are CUNI's, from the official graphics manual, with the measured contrast ratios recorded alongside them. The warm neutral ramp is ours.
- `src/theme/theme.ts` — the MUI theme built from those tokens.

Two things there are load-bearing and easy to undo by accident:

**MUI's `grey` palette is replaced outright.** The stock one is cool-toned and reaches much further into component styles than it looks — dividers, disabled states, outlined-input borders, skeletons. Left alone, all of those render blue-grey against an ivory page and the paper look collapses. It is not a beige background over neutral furniture; *everything* neutral is warm.

**Red fills shapes; the darker red carries text.** `#d22d40` is 4.75:1 on the page background — AA, but with no headroom to spend on small or light text. `#ae2f3c` (the manual's own darker red) is 6.09:1, and is what `MuiLink` and any red text use.

Light only, deliberately. The paper metaphor does not survive inversion, so rather than ship a second theme that nobody checks, there is one.

Fonts are **Source Serif 4** (headings) and **Source Sans 3** (body), bundled via `@fontsource` rather than loaded from the Google Fonts CDN — a German court has found that CDN font loading, which discloses the visitor's IP to a third party, breaches the GDPR, and this is an EU university service.

`src/App.tsx` is a placeholder swatch, not the landing page. It exists so the theme can be looked at rather than read; replace it when the real layout is built.


## Testing

Component / unit tests with Vitest and Testing Library; optionally end-to-end (Playwright) against a compose server. `src/theme/theme.test.tsx` guards the two theme decisions above, since both are invisible until they break.


## Deployment

Built to a static bundle and served by nginx, which also reverse-proxies the Web API behind the same origin — see [docs/deployment.md](../../docs/deployment.md).

The instance is reached under a path prefix (`/musibot/`), not at the root of a host, which the build has to know about: asset URLs, the SPA fallback and the router all need it. That is not settled here yet — see the nginx configuration work in `deploy/`.


## Versioning

Own version, decoupled from the API version it targets (negotiated over HTTP). Released as `web-ui/vX.Y.Z` git tags; the `version` field in `package.json` stays at `0.0.0` because the package is never published to npm and the tags are the record. See [Versioning and releases](../../docs/versioning-and-releases.md).
