# web-ui

Single-page web application for the *General public* and *Model developers*. A UI layer over the Web API.


## Responsibilities

- Upload page scans (JPEG), pick a pipeline, watch live progress via the API's SSE stream.
- View and download recognition results.


## Stack

React single-page app, written in TypeScript, using MUI (Material UI) components, built by Vite.

No server-side rendering and no SSG framework. The build produces static files that nginx serves, which is the whole of the deployment story — see [Search engines](#search-engines) for why that is enough.


## Routes

There are four, and they are declared in `src/routes.tsx` against the path constants in `src/paths.ts`:

| Route | Screen | |
| --- | --- | --- |
| `/` | `LandingScreen` | The pitch and the upload. The only screen meant to be indexed. |
| `/musicorpus-pages/:pageId` | `MusicorpusPageScreen` | One *MusicorpusPage* — the four-panel screen the recognition happens on. |
| `/session` | `SessionScreen` | Everything this browser has uploaded while its session lasts. |
| `*` | `NotFoundScreen` | An address nothing claimed. |

The names follow the domain and the HTTP API rather than being shortened, because `page` is the most overloaded word in this project — a page of sheet music, a *MusicorpusPage*, a screen of the app. For the same reason the components live in `src/screens/` rather than the usual `src/pages/`.

Three things are worth knowing before adding a route.

**Paths are written with a leading slash, and that is not a contradiction of [The base path](#the-base-path).** The rule there is about URLs the *browser* resolves, which resolve against the origin root and miss the deployment. A react-router path is resolved against the router's `basename`, which `src/App.tsx` sets from `import.meta.env.BASE_URL`. So the app is written as though it sat at the root of a host and one setting moves all of it. Navigate with `<Link to={...}>` and `useNavigate` rather than with `<a href>`, or the basename is bypassed and the browser's rule applies again.

**A deep link only survives a reload because nginx says so.** `try_files $uri $uri/ /index.html` in [deploy/nginx/musibot.conf.template](../../deploy/nginx/musibot.conf.template) is what answers `/musibot/session` with the app instead of a 404. That line and the routes above are one mechanism in two files.

**A route that is not the landing page probably belongs in `robots.txt`.** It is generated in `vite.config.ts` and lists what crawlers should leave alone: per-user pages behind an upload, and the API. A new route is either public and indexable, or it needs a line there.


## Screens

They live in `src/screens/`, one file per route, with a folder of parts beside any screen big enough to need one (`src/screens/landing/`). Anything used by more than one screen — the header, the footer, the column their content is set in — is in `src/components/`.

The page is **full-bleed**: the ivory runs edge to edge with no card or frame around it, and only the *content* is bounded, by `src/components/ContentWidth.tsx`. So a section that carries a hairline rule is a full-width band with a `ContentWidth` inside it, not the other way round — the rule spans the window while the words stop where the eye does.

`src/links.ts` holds every address pointing outside the app: the interactive HTTP API docs, the python client, the project, and the address libraries are told to write to. They name things outside this repository and go stale without anything here failing to build, so they are in one file rather than scattered through the markup.

Two placeholders are still in the landing page and both are meant to be noticed:

- **The four sample pages are drawn, not photographed.** `src/screens/landing/SampleArt.tsx` renders ruled lines standing in for a scan, exactly as the design file did. Real JPEGs go in `public/samples/`, after which that file goes away. The stand-ins are obviously not photographs on purpose — a placeholder that looked real would ship unnoticed.
- **Nothing is uploaded yet.** The drop zone and the samples both call back with what was chosen and the landing screen drops it; that callback is the seam the upload flow plugs into.


## Sessions

The public tier has no accounts. A visitor gets a bearer token from `POST /public-sessions`, it lives about an hour, and a page created under it is deleted when it expires. `src/session/` holds the app's side of that, and it is more than a variable holding a token — for one reason.

**A token's expiry is fixed at minting and is never extended.** So a visitor who uploads at minute 55 of a token's life gets a page that lives five minutes, which is not a limit anyone chose. The app therefore keeps *several* sessions rather than one: before a page is created, the current token is checked, and if it has **20 minutes or less** left a new one is minted and becomes current. Every page gets at least that much life.

The consequence reaches everywhere else in the app: **a page's token is a property of the page**. Asking about last hour's page with this hour's token answers `404` — to the service that is somebody else's page — so every call in `src/api/client.ts` takes its token as an argument rather than reading an ambient one, and `useSession().tokenForPage(pageId)` is what a screen asks. A page's expiry is its session's expiry.

Two things deliberately do **not** mint:

- **`429`.** The caps are on the public tier as one pool, and the per-session ones are courtesy caps meant to be hit rather than routed around. A fresh token buys nothing globally and would defeat the per-session ones, so the refusal is shown to the visitor and nothing else happens.
- **A timer, a page load, or anything else on a schedule.** Only an upload about to happen mints, and only when the clock says it must.

The one thing beyond the clock that *drops* a session is a **`401`**, which is proof the token is dead however much life was recorded for it — the api service keeps all state in memory and rebuilds it empty on every start, so a restart invalidates live tokens without the clock moving. That session and its pages are forgotten, since they are genuinely gone.

The ledger lives in `localStorage` under one key, because the API has no endpoint that lists a user's pages: if the app does not write down what it uploaded, nothing does. It is read tolerantly — a stored value that will not parse is discarded rather than thrown over, since losing the record of an ephemeral hour beats a landing page that will not render.

One limitation follows from all of this and is worth knowing: **a page's URL is not shareable.** Reaching a page needs the token it was created under, which lives in one browser's `localStorage` and is deliberately never in the URL.


## Development

Requires **Node 22.12+ or 24+** (Vite 8's floor; the test runner's jsdom wants 22.22+, so 24 is the comfortable choice).

```bash
cd components/web-ui
npm install
npm start
```

The dev server comes up on http://localhost:5173 and proxies `/api/*` to `127.0.0.1:8080`, which is where `musibot-api` runs with no configuration (see [../api/README.md](../api/README.md)). Point it elsewhere with `MUSIBOT_API_URL`.

**The api service needs `public_access_enabled` turned on**, or nothing in this app works past the landing page: it is off by default so that a Libraries-only deployment does not acquire a public demo by accident, and with it off `POST /public-sessions` answers `404` and the UI reports that the instance offers no public access. See [Public access](../../docs/public-access.md).

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
MUSIBOT_PUBLIC_ORIGIN=https://quest.ms.mff.cuni.cz npm run build
```

That is the origin and nothing more — where under it Musibot sits is the base path below, and the two are joined rather than written out twice. Getting it wrong means link previews and search results that point at somebody else's host.

One limitation that comes with being served under a path prefix: crawlers read `robots.txt` from the origin root and nowhere else, so while Musibot lives at `https://<host>/musibot/` the generated `robots.txt` is served but never consulted — the rules that apply are whoever owns the hostname's. It is emitted anyway, because it costs nothing and becomes correct the day Musibot gets a host of its own. The sitemap does not share the limitation: it is found by being submitted or linked, not by its location.


## Theme

The look is printed paper: a warm ivory page, a serif for headings, flat surfaces separated by hairline rules rather than drop shadows, and Charles University's cardinal red as the one saturated colour.

- `src/theme/palette.ts` — the colour tokens. The reds and the blue are CUNI's, from the official graphics manual, with the measured contrast ratios recorded alongside them. The warm neutral ramp is ours.
- `src/theme/theme.ts` — the MUI theme built from those tokens.

Two things there are load-bearing and easy to undo by accident:

**MUI's `grey` palette is replaced outright.** The stock one is cool-toned and reaches much further into component styles than it looks — dividers, disabled states, outlined-input borders, skeletons. Left alone, all of those render blue-grey against an ivory page and the paper look collapses. It is not a beige background over neutral furniture; *everything* neutral is warm.

**Red fills shapes; the darker red carries text.** `#d22d40` is 4.75:1 on the page background — AA, but with no headroom to spend on small or light text. `#ae2f3c` (the manual's own darker red) is 6.09:1, and is what `MuiLink` and any red text use.

Light only, deliberately. The paper metaphor does not survive inversion, so rather than ship a second theme that nobody checks, there is one.

Fonts are **Source Serif 4** (headings) and **Source Sans 3** (body), bundled via `@fontsource` rather than loaded from the Google Fonts CDN — a German court has found that CDN font loading, which discloses the visitor's IP to a third party, breaches the GDPR, and this is an EU university service.

`src/theme/theme.ts` also exports `mono` and `serif` as bare font stacks, because the design reaches for both well outside where MUI would apply them — monospace for file paths, page IDs, pipeline versions, log lines and image dimensions, anything a user might have to read character by character; the serif for the wordmark and the affiliation line, which are not headings. A MUI component needs the stack named, since the class it generates outranks the element rule `CssBaseline` sets.


## Testing

Component / unit tests with Vitest and Testing Library; optionally end-to-end (Playwright) against a compose server. `src/theme/theme.test.tsx` guards the two theme decisions above, since both are invisible until they break.


## The base path

Musibot is published at `https://<host>/musibot/`, not at the root of a host, and every URL this bundle emits has to account for it. That is one setting — `base` in `vite.config.ts` — from which Vite rewrites the asset and favicon URLs and which it hands to the app as `import.meta.env.BASE_URL`.

**Nothing in `src/` may write an absolute path.** A literal `/api/pipelines` resolves against the origin root and misses the deployment entirely, while working perfectly in every test. `src/api/base.ts` builds the API's address from `BASE_URL` instead, and everything that talks to the API must go through it.

The dev server serves under the same base, so the development address is http://localhost:5173/musibot/ and the proxy strips the same prefix nginx does. That is deliberate: a base path that only applies to production is a base path that is only tested in production.


## Deployment

Built to a static bundle and served by nginx, which also reverse-proxies the Web API behind the same origin — see [deploy/nginx/musibot.conf.template](../../deploy/nginx/musibot.conf.template) and [docs/deployment.md](../../docs/deployment.md).

The local stack can serve the built bundle under the real prefix, behind a stand-in for the university proxy: `npm run build`, then `docker compose up -d` in `deploy/`, then browse http://localhost:8000/musibot/. See [deploy/README.md](../../deploy/README.md).


## Versioning

Own version, decoupled from the API version it targets (negotiated over HTTP). Released as `web-ui/vX.Y.Z` git tags; the `version` field in `package.json` stays at `0.0.0` because the package is never published to npm and the tags are the record. See [Versioning and releases](../../docs/versioning-and-releases.md).
