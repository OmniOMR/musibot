# Changelog for `web-ui`

Released as `web-ui/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

The Web UI has no outward contract of its own: nothing depends on it, and it depends on the HTTP API. So entries here describe what a *User* can see and do, not an interface anyone programs against.


## Unreleased


### Added

- **The toolchain.** Vite, React, TypeScript and MUI, built to a static bundle that nginx serves. No server-side rendering: the deployment is files behind a web server, and stays that way.
- **A landing page that link previews can read.** The title, description, canonical link, Open Graph and Twitter card tags and a `<noscript>` body are static in `index.html`, and `robots.txt` and `sitemap.xml` are generated at build time from the same public-origin constant. Googlebot runs JavaScript and would have indexed the app regardless; the scrapers behind Slack, LinkedIn and Mastodon previews do not, and a URL that gets emailed around is the whole point of the public tier.
- **The theme** — printed paper: a warm ivory page, Source Serif 4 headings over Source Sans 3 body text, flat surfaces divided by hairline rules, and Charles University's cardinal red as the one saturated colour. Fonts are bundled rather than fetched from a CDN. Colour choices and their measured contrast ratios are recorded in `src/theme/palette.ts`.


- **Upload, and the pipeline choice.** A dropped, chosen or sampled JPEG is measured in the browser, and its shape decides which of two *Pipelines* is offered first — a tall image is assumed to be a whole page, a wide one a single staff — with the assumption stated as one and overridable in a click. Underneath, *All pipelines* lists everything the instance announces, *ImplicitPipelines* included. Then the page is created, the bytes go straight to object storage over a presigned URL, and the execution starts.
- **The upload path comes from the pipeline's *Signature*.** A page-level pipeline reads `image.jpg`; a staff-level one reads `Staves/1/image.jpg`, and the api service rejects an input list that does not fit the signature. So the destination is derived per pipeline rather than assumed, and a pipeline needing more than the one file a visitor uploads is listed and disabled rather than offered and then refused.
- **The two default pipelines are named in the UI** — `mzk-page` and `mzk-staff`, both v1. When an instance does not announce them, both primary choices are disabled with a note and the full list is opened instead, so the app is usable on an instance running only a model or two.


- **Sessions, and a typed client for the HTTP API.** A visitor's bearer token is minted on demand and kept with the pages created under it, in `localStorage`, since the API has no endpoint that lists a user's pages. A token's hour is fixed at minting and never extended, so the app holds several rather than one: a new page is only ever created under a token with more than 20 minutes left, and a token with less is replaced. That makes a page's lifetime something decided before it exists rather than an accident of when the visitor arrived — and it makes a page's token a property of the page, which every call carries and by which a page's expiry is read. Being refused for load never mints; only the clock does. A `401` forgets the session and its pages, because that is what a `401` means once the service has rebuilt its state empty.
- **The floating session pill** on the landing page, once there is something in the session to go back to. Absent, not empty, on a first visit.


- **The landing page.** The pitch on the left, the way in on the right: a drop zone that takes a JPEG by drop or by file picker, four sample pages for a visitor with nothing to hand, the four steps from upload to MusicXML in notation software, and the affiliations and NAKI III funding line along the bottom. The paragraph sending libraries and archives to an email address rather than to the API is load-bearing rather than polite — the public tier is capped as one pool and sized for a conference demo, so a collection fed through it would fail slowly while occupying the tier. Nothing is uploaded yet; the drop zone and the samples hand back what was chosen and the flow that catches it is the next piece of work.

- **Routes for the screens the app will have.** The landing page at the root, one *MusicorpusPage* at `/musicorpus-pages/{id}`, the current session's pages at `/session`, and a not-found screen for anything else. The screens themselves are placeholders; what is real is that a page's address is a page's address — it can be pasted, bookmarked and reloaded for as long as the session behind it lives, which is what nginx's SPA fallback and the router's base path together make true.


- **A base path.** The app is built for `https://<host>/musibot/` rather than the root of a host, which every URL it emits has to account for. Asset and favicon URLs follow from Vite's `base`; the API's address is built from `import.meta.env.BASE_URL` in `src/api/base.ts`, and nothing in `src/` may write an absolute path — one works in every test and 404s in the deployment. The dev server serves under the same base, so it is not a production-only setting.


### Not yet implemented

The results. A page can be uploaded and a *Pipeline* started on it, but the screen it then navigates to is still a placeholder — there is no progress view, no file list, no transcription and no log. Progress will be polled rather than streamed until the API's SSE stream exists.

Two things on the landing page are stubs rather than features. The four sample pages are drawn stand-ins and clicking one reports that the sample could not be loaded, because `public/samples/` is empty; the code that fetches them is the real code, what is missing is four JPEGs. And errors in the upload flow are shown as plain text rather than as the designed cards.
