# web-ui

Single-page web application for the *General public* and *Model developers*. A UI layer over the Web API.


## Responsibilities

- Upload page scans (JPEG, PNG, BMP, TIFF or a one-page PDF), pick a pipeline, and watch the reading happen — the recognition log arrives over the API's SSE stream.
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


## The upload flow

A file arrives three ways — dropped, chosen from the picker, or taken from the samples — and all three end in `LandingScreen`, which asks two questions: is it an image Musibot takes, and how should it be read. The second is `PipelineChoice`, a card that opens over the landing page. It is a step and not a route, because nothing exists on the server yet for an address to name.

The first is `isAcceptedUpload`, and its answer is JPEG, PNG, BMP, TIFF or PDF. What happens next is `prepareUpload`, the seam every chosen file passes through:

| Format | What happens | Why |
| --- | --- | --- |
| JPEG, PNG | uploaded untouched | a scan is line art, and JPEG's ringing lands on exactly the strokes recognition reads |
| BMP | re-encoded as JPEG | not compressed at all — 300 DPI A4 is ~25 MB |
| TIFF | decoded by UTIF, re-encoded as JPEG | no browser hands one to an `<img>`, so it could not even be measured as it arrived |
| PDF | first page rasterised at 300 DPI | there is no image in it to pass through |

Neither a multi-page PDF nor a multi-page TIFF is silently truncated: the page count comes back and the choice card says so before anything is uploaded. Both formats also pass through `fit` in `canvasSize.ts`, because a canvas asked for more pixels than the browser allows returns a blank rather than an error, and a blank page reads as a failed recognition rather than as a failed upload.

`pdfjs-dist` and `utif2` are reached with `await import()` from `src/upload/pdfPage.ts` and `src/upload/tiffPage.ts`, which exist to be the lazy chunks: **nothing on the eager path may import them**, or the landing page starts paying 166 kB gzipped plus a 1.3 MB worker for formats most visitors never use. `npm run build` shows whether that still holds — `pdfPage-*.js`, `tiffPage-*.js` and `pdf.worker.min-*.mjs` should be their own files, and `index-*.js` should mention none of them.

**A PNG is uploaded to `image.jpg` like everything else, which diverges from the Musicorpus Specification** — see the note on `ACCEPTED_UPLOAD_TYPES` in `src/upload/prepareUpload.ts` for why that works and what the honest fix would be. BMP, TIFF and PDF do not have this problem, because they arrive as real JPEGs.

**The two defaults are hardcoded**, in `src/pipelines.ts`: `mzk-page` v1 for a whole page and `mzk-staff` v1 for a single cropped staff (MZK is the Moravian Library, Moravská zemská knihovna). "The one we recommend" is a product decision and there is nothing in a *Pipeline's* announcement that could carry it. Nothing guarantees they are deployed — pipelines are announced over RabbitMQ by whatever is connected — so when one is missing its option is disabled, the card says so, and the *All pipelines* list is opened rather than left for the visitor to find.

**Where the upload lands is decided by the chosen pipeline's *Signature*, not by a constant.** A *Signature* declares patterns and an execution names concrete paths, and the api service rejects an input list that does not fit with a `400`. So a page-level pipeline wants `image.jpg` while a staff-level one wants the same bytes at `Staves/1/image.jpg`; `uploadPathFor` instantiates the one required input pattern, filling any slot with `1`. This is not a detail that can be skipped — the only model currently deployed for testing declares `Staves/{staff}/image.jpg`, and uploading to `image.jpg` for it fails at the edge. See [Signatures](../../docs/signatures.md).

A pipeline this app cannot drive from a single upload — one needing a *File* an earlier execution must produce, or one nothing is currently running — is listed and disabled with the reason. Hiding it would leave a visitor hunting for something they read about elsewhere.


## The MusicorpusPage screen

The workspace behind an upload: full height, panels rather than a content column. `src/page/` holds its logic and `src/screens/page/` its parts.

**Nothing is polled.** `usePageState` asks about the page once when the screen opens and is told what changed after that: the file-change stream when an execution writes a *File*, the result stream when one ends. An idle page costs no requests, which matters because the public tier is one shared pool and every open tab used to be a standing load on it.

Two things make that safe rather than optimistic, and both must survive any rewrite of this hook. **Every reconnection re-asks**, since neither stream replays and a connection can drop across an ending. And **a stream silent for 45 seconds is presumed dead** and reopened — three missed keepalives — because a connection killed by something in the middle can otherwise leave a page that has simply stopped updating, and with no poll behind it nothing would ever notice.

The result stream is scoped to the *User*, not the page, so this filters it by `page_id`. That is what lets one connection serve a client holding many pages — the session screen, and the python client's planned batch API. **Nothing here may show a percentage** — an image-to-sequence model does not know how long its own output will be, so there is no figure to report, which is why Musibot has no progress reporting at all.

**A *File* appears as it is written.** `usePageState` holds the page's file-change stream open and treats a notice as "ask again now", listing the page again rather than building a listing out of the paths it was told about — object storage already knows what the page holds, with sizes and times, and a second copy assembled here would go stale the moment an execution overwrote a *File*. A missed notice therefore costs the wait until the next poll and nothing else.

**The log is a real stream, and it is not replayed.** `usePageLog` opens `POST /musicorpus-pages/{id}/logs` with `fetch` — not `EventSource`, which cannot send the bearer header every other call uses — and holds it open for as long as the screen is, not only while something runs: the service keeps no buffer, so a stream opened after an execution had started would miss its beginning. Lines accumulate in the hook rather than in `LogPanel`, so collapsing the panel and opening it again shows the whole log; a browser reload loses it, which is what "no buffer" means. A dropped connection is retried, and the panel says so rather than letting a stopped log look like a quiet reading.

**The file list is the page's contents, not any execution's outputs.** A page's folder is flat storage that several executions have written into, and a later one may overwrite what an earlier one produced — so grouping files under the run that wrote them would put one path under two headings and make one of them wrong. Executions are the page's history; files are its present. A file a *running* execution declares among its outputs is flagged *will be replaced*, read from the pipeline's *Signature* rather than guessed.

**Something is always selected, until the visitor selects something else.** A page used to open with nothing chosen and an empty canvas beside a running recognition, which reads as a broken service rather than as a page nobody has clicked on yet. So `page/interest.ts` picks the row most worth looking at and keeps picking as the reading produces better answers — the scan, then the boxes over it, then the crops, then the transcription — and stops the moment the visitor chooses a row themselves. The order is a plain list meant to be edited as models start writing new kinds of *File*; a *File* it does not name is never chosen for somebody, since guessing at what a `debug.txt` means is worse than showing the scan, unless it is the only thing the page holds.

**Files inside a subdivision collapse into one row.** Twelve staves is twenty-four files, which would bury the page-level ones. They also behave as one thing downstream — selecting staff transcriptions shows all of them at once rather than isolating a staff — so one row is what the selection means. Which folders are subdivisions is not written down: `<folder>/<instance>/<name>` is the rule, and the folder names its own section, because Musibot treats paths purely syntactically so that a new subdivision level is not a change to Musibot.

**A page is only reachable in the browser that uploaded it**, since it is fetched with the token it was created under. The screen says so rather than showing an empty workspace.

**A page can be read more than once.** *+ Run pipeline* offers whatever can be run on the *Files* the page already holds, worked out by matching each announced *Signature* against them — the api service passes an input list through and expands nothing, so deciding which files to name is this app's job. Three shapes are handled, which cover every example in [Signatures](../../docs/signatures.md): patterns with no slots (one way to run it, if the files are there), one pattern with a single-instance slot (one way *per* matching file, since that is what `{s}` means), and one pattern with a set slot (one way, over the whole set). Anything needing slots bound across several patterns is refused with a reason rather than guessed at — that is the fan-out the api service deliberately does not do, and doing it here would mean inventing a partial-failure policy nothing else in Musibot has.


### The canvas

SVG, with React rendering its contents and d3 supplying only behaviour. `src/scene/` holds it. Two coordinate spaces meet there and the whole design is about keeping them apart.

**The transform is never React state.** Put it there and every frame of a pan re-renders the panel and walks a thousand memoised boxes to confirm they have not moved. Instead `useZoom` writes it straight onto the world `<g>` through a ref, so a gesture reaches no component at all — the boxes re-render only when the selected layer changes.

**Screen-space things follow from that.** The rulers and the crop labels have to be recomputed every frame, and since there is no per-frame state change for them to react to, they are updated from the same callback. That is why they are imperative — not because React is too slow for a dozen ticks. A box's stroke is screen-space too, and SVG solves that one natively with `vector-effect="non-scaling-stroke"`. Crop labels sit at world coordinates inside the world group and carry the inverse scale, so the transform places them and they keep their type size.

`src/scene/ruler.ts` is the one place d3 renders DOM itself, into a `<g>` React creates empty. **That `<g>` must never gain a React child** — React has nothing to diff there and leaves it alone, which is exactly what makes it safe.

**Files are fetched into memory, not linked.** Presigned URLs live fifteen minutes and a page lives about an hour, so an `<image href>` pointing at one turns into a 403 while somebody is looking at it. Fetching into a blob removes the problem rather than scheduling a repair for it; the cache is keyed by path *and* `last_modified`, so a *File* a later execution rewrote is re-read while an untouched one is free to return to; and streaming will need an in-memory buffer anyway, since object storage only holds a *File* once it is complete. Only the selected layer is fetched, and object URLs are revoked when it changes.

**Boxes come from `bbox` and nothing else.** Both spatial layers are COCO — `layout.json` for staff regions in the university red, `coco-object-detection.json` for symbols in the blue — so one reader serves both. Every annotation also carries `segmentation`, as polygon arrays in one file and run-length encoding in another; drawing it would mean an RLE decoder for shapes the boxes already locate, and polygons are the one thing that makes an SVG scene slow where thousands of rectangles do not.


### The transcription

Beside the canvas, and only while a transcription is selected — the panel would have nothing to say about a `layout.json`, and half a canvas is worth more than a column explaining that it is empty. It shows one reading per instance, the same set the canvas is showing, because comparing the reading against the crop it came from is the point of having both.

Each reading is the notation engraved from `transcription.musicxml`, with the `transcription.lmx` tokens underneath. The second is not a fallback for the first: a musician checks whether the notation looks right, while somebody working on the model reads the token sequence, where a wrong duration is a wrong token rather than a subtly wrong stem. Selecting either file shows both, since they are two views of one answer.

**OpenSheetMusicDisplay is loaded on demand.** It ships as a single prebuilt file of about 1.3 MB with VexFlow and JSZip already inside it, so it cannot be tree-shaken, and bundling it would charge every visitor to the landing page for a renderer most of them never open. A dynamic `import()` puts it in a chunk of its own — the main bundle is ~580 kB, the renderer ~1.3 MB (335 kB gzipped) and separate.

Like the ruler on the canvas, OSMD writes its own DOM into a container React renders empty and never gives a child to. It is re-rendered on width changes, since engraving decides line breaks and is a layout decision rather than a style.

LMX is split on whitespace and nothing else. It is Linearized MusicXML — a flat token sequence a model can emit — and anything cleverer than a whitespace split would be this app's opinion about a format it does not own.


## Third-party notices

The bundle is a redistribution of every library compiled into it, and permissive licences — BSD, MIT, the SIL Open Font License — require their notices to accompany it. Nothing does that by itself: Vite strips comments, so a licence header in a dependency's source does not survive into `dist/`.

[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md) is that file, and it is **generated**:

```bash
npm run notices       # after adding or upgrading any dependency
```

It is committed, so a diff shows what changed. A hand-maintained list is accurate exactly once.

Two things it settles that would otherwise be left ambiguous. **JSZip** is offered as `MIT OR GPL-3.0-or-later` and Musibot elects MIT — an unstated election is how a dual-licensed dependency comes to be read as putting GPL in a web UI. And the **fonts** are bundled rather than fetched from a CDN, so the Open Font License travels with them rather than staying on somebody else's server.

The generator excludes what demonstrably never reaches the bundle: `@types/*`, and optional dependencies — OpenSheetMusicDisplay's `gl`, which it uses only to render headlessly under Node, and the native toolchain beneath it. Everything else is listed even where it is arguably build-time only, because over-attributing costs a paragraph and under-attributing breaches a licence.


### When it goes wrong

`src/components/NoticeCard.tsx` is the one shape for all of them — say what happened, say what caused it if that is knowable, offer what to do next. No icon, no red panel: a refused upload is not an emergency, and the red in this app fills the button somebody is meant to press.

Two of these carry a decision rather than just wording.

**A refusal for load says whether waiting will help.** Over the concurrency cap it will, and the service says for how long; over the per-session page cap it will not, and the service sends no `Retry-After` precisely because deleting a page is the thing that helps. Telling somebody to wait when waiting cannot work is worse than saying nothing.

**A reading can finish, succeed, and produce nothing.** That is the unhappiest outcome Musibot has, because none of it looks like a failure: `completed`, no error, and a file list that has not changed — which reads as a broken service rather than as a page with no music on it. `src/page/outcome.ts` detects it by comparing what the *Pipeline* declared it would write against what the page now holds, ignoring optional outputs, and says nothing whenever the question cannot be answered. A false "nothing was found" on a page that has results would be worse than no message at all.


## Sessions

The public tier has no accounts. A visitor gets a bearer token from `POST /public-sessions`, it lives about an hour, and a page created under it is deleted when it expires. `src/session/` holds the app's side of that, and it is more than a variable holding a token — for one reason.

**A token's expiry is fixed at minting and is never extended.** So a visitor who uploads at minute 55 of a token's life gets a page that lives five minutes, which is not a limit anyone chose. The app therefore keeps *several* sessions rather than one: before a page is created, the current token is checked, and if it has **20 minutes or less** left a new one is minted and becomes current. Every page gets at least that much life.

The consequence reaches everywhere else in the app: **a page's token is a property of the page**. Asking about last hour's page with this hour's token answers `404` — to the service that is somebody else's page — so every call in `src/api/client.ts` takes its token as an argument rather than reading an ambient one, and `useSession().tokenForPage(pageId)` is what a screen asks. A page's expiry is its session's expiry.

Two things deliberately do **not** mint:

- **`429`.** The caps are on the public tier as one pool, and the per-session ones are courtesy caps meant to be hit rather than routed around. A fresh token buys nothing globally and would defeat the per-session ones, so the refusal is shown to the visitor and nothing else happens.
- **A timer, a page load, or anything else on a schedule.** Only an upload about to happen mints, and only when the clock says it must.

The one thing beyond the clock that *drops* a session is a **`401`**, which is proof the token is dead however much life was recorded for it — the api service keeps all state in memory and rebuilds it empty on every start, so a restart invalidates live tokens without the clock moving. That session and its pages are forgotten, since they are genuinely gone.

The ledger lives in `localStorage` under one key, because the API has no endpoint that lists a user's pages: if the app does not write down what it uploaded, nothing does. It is read tolerantly — a stored value that will not parse is discarded rather than thrown over, since losing the record of an ephemeral hour beats a landing page that will not render.

It also holds a **thumbnail per page**, a two-kilobyte data URL made in the browser at upload time from bytes already in memory. That is what lets `/session` draw its list with no network at all; the alternative is fetching several megabytes of scan per row to render it forty pixels wide. The thumbnail is centre-cropped to the list's own shape rather than fitted to it, because a staff crop is nineteen times wider than it is tall and fitted becomes a two-pixel line in an empty box — which reads as a broken image rather than as a wide one.

`/session` asks the server once per page for how the reading went, since that is the part the ledger cannot know. Once, not polled: it is a list somebody glances at on the way back to a page, and watching a recognition finish is what the page's own screen is for.

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
