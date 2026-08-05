# Changelog for `web-ui`

Released as `web-ui/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

The Web UI has no outward contract of its own: nothing depends on it, and it depends on the HTTP API. So entries here describe what a *User* can see and do, not an interface anyone programs against.


## Unreleased


### Fixed

- **Two pages in five were being taken for a single staff.** The guess that picks a default *Pipeline* asked whether an image was wider than it was tall, and 41 of the 100 pages in the `UFAL.OmniOMR` corpus are landscape — so a page was handed to a model that reads one line of music, which transcribes the whole sheet as though it were one. The threshold is now a width-to-height ratio of 3.0, measured across those 100 pages and 1184 staff crops: the two populations are separated by an empty band, nothing in the corpus falling between 1.5 and 4.6. The histogram is in the source beside the number. The explanation shown to the visitor no longer claims a page is "tall and narrow" either, which was untrue of it in plain sight.


### Added

- **The toolchain.** Vite, React, TypeScript and MUI, built to a static bundle that nginx serves. No server-side rendering: the deployment is files behind a web server, and stays that way.
- **A landing page that link previews can read.** The title, description, canonical link, Open Graph and Twitter card tags and a `<noscript>` body are static in `index.html`, and `robots.txt` and `sitemap.xml` are generated at build time from the same public-origin constant. Googlebot runs JavaScript and would have indexed the app regardless; the scrapers behind Slack, LinkedIn and Mastodon previews do not, and a URL that gets emailed around is the whole point of the public tier.
- **The theme** — printed paper: a warm ivory page, Source Serif 4 headings over Source Sans 3 body text, flat surfaces divided by hairline rules, and Charles University's cardinal red as the one saturated colour. Fonts are bundled rather than fetched from a CDN. Colour choices and their measured contrast ratios are recorded in `src/theme/palette.ts`.


- **The transcription, beside the scan.** Selecting a transcription opens a panel showing what Musibot read: the notation engraved from MusicXML, and the LMX token sequence underneath it. One reading per staff for a staff-level file, matching what the canvas is showing, since comparing the reading against the crop is the point of having both. The renderer is loaded only when somebody actually opens a transcription — it is larger than the whole of the rest of the app, and the landing page should not pay for it.
- **Third-party notices.** The bundle redistributes every library compiled into it, and their licences require their notices to travel with it — which nothing did, since the build strips comments. `THIRD-PARTY-NOTICES.md` now carries them, generated from the dependency tree rather than maintained by hand. It also records that Musibot elects MIT for the one dual-licensed dependency, and carries the Open Font License for the two bundled typefaces.


- **The canvas.** The scan, pannable and zoomable, with whatever has been found on it drawn over the top: staff regions from `layout.json` in the university red, symbol detections from `coco-object-detection.json` in the blue, and a class name on hover. Selecting a staff-level layer shows *every* staff at once, stacked and labelled, because what a reader is checking is whether the reading holds across the page. Rulers down two edges say how big a thing actually is, which the zoom percentage cannot. A transcription gets no boxes: there is no coordinate in a MusicXML file.
- **Layers are read into memory rather than linked.** A presigned URL outlives neither the page nor a long look at it, so files are fetched once and shown from memory — which also means a *File* a later execution rewrote is re-read, while one that has not changed is free to return to.


- **The MusicorpusPage screen, and what a page holds.** The workspace an upload lands on: the page's identity and how long it has left, every *Pipeline Execution* it has had with its state, and the *Files* it now contains — grouped under `Page` and each subdivision, with the files inside a subdivision collapsed into one row per name rather than one per staff. Each row can be downloaded, and *Download results* takes everything except the file the visitor uploaded. A *File* a running execution is about to overwrite says so before it is downloaded, read from that pipeline's declared outputs.
- **Progress is polled while something is running, and not otherwise.** The SSE stream the API documents does not exist yet, so a finished execution's outputs appear together rather than one at a time — a running execution shows that it is running and never a percentage, which an image-to-sequence model could not honestly report anyway. Polling stops as soon as nothing is running, so an open tab is not a standing load on a public tier shared by everyone.
- **A page that is not this browser's says so.** Reaching a page needs the token it was created under, so a pasted link, or the same link on another machine, gets an explanation rather than an empty workspace. An expired page gets its own.


- **Upload, and the pipeline choice.** A dropped, chosen or sampled JPEG is measured in the browser, and its shape decides which of two *Pipelines* is offered first — a page-shaped image is assumed to be a whole page, a long strip a single staff — with the assumption stated as one and overridable in a click. Underneath, *All pipelines* lists everything the instance announces, *ImplicitPipelines* included. Then the page is created, the bytes go straight to object storage over a presigned URL, and the execution starts.
- **The upload path comes from the pipeline's *Signature*.** A page-level pipeline reads `image.jpg`; a staff-level one reads `Staves/1/image.jpg`, and the api service rejects an input list that does not fit the signature. So the destination is derived per pipeline rather than assumed, and a pipeline needing more than the one file a visitor uploads is listed and disabled rather than offered and then refused.
- **The two default pipelines are named in the UI** — `mzk-page` and `mzk-staff`, both v1. When an instance does not announce them, both primary choices are disabled with a note and the full list is opened instead, so the app is usable on an instance running only a model or two.


- **Sessions, and a typed client for the HTTP API.** A visitor's bearer token is minted on demand and kept with the pages created under it, in `localStorage`, since the API has no endpoint that lists a user's pages. A token's hour is fixed at minting and never extended, so the app holds several rather than one: a new page is only ever created under a token with more than 20 minutes left, and a token with less is replaced. That makes a page's lifetime something decided before it exists rather than an accident of when the visitor arrived — and it makes a page's token a property of the page, which every call carries and by which a page's expiry is read. Being refused for load never mints; only the clock does. A `401` forgets the session and its pages, because that is what a `401` means once the service has rebuilt its state empty.
- **The floating session pill** on the landing page, once there is something in the session to go back to. Absent, not empty, on a first visit.


- **The landing page.** The pitch on the left, the way in on the right: a drop zone that takes a JPEG by drop or by file picker, four sample pages for a visitor with nothing to hand, the four steps from upload to MusicXML in notation software, and the affiliations and NAKI III funding line along the bottom. The paragraph sending libraries and archives to an email address rather than to the API is load-bearing rather than polite — the public tier is capped as one pool and sized for a conference demo, so a collection fed through it would fail slowly while occupying the tier. Nothing is uploaded yet; the drop zone and the samples hand back what was chosen and the flow that catches it is the next piece of work.

- **Routes for the screens the app will have.** The landing page at the root, one *MusicorpusPage* at `/musicorpus-pages/{id}`, the current session's pages at `/session`, and a not-found screen for anything else. The screens themselves are placeholders; what is real is that a page's address is a page's address — it can be pasted, bookmarked and reloaded for as long as the session behind it lives, which is what nginx's SPA fallback and the router's base path together make true.


- **A base path.** The app is built for `https://<host>/musibot/` rather than the root of a host, which every URL it emits has to account for. Asset and favicon URLs follow from Vite's `base`; the API's address is built from `import.meta.env.BASE_URL` in `src/api/base.ts`, and nothing in `src/` may write an absolute path — one works in every test and 404s in the deployment. The dev server serves under the same base, so it is not a production-only setting.


### Not yet implemented

The recognition log — the pill opens nothing, and the API has no log endpoint to open it onto. A page also cannot yet have a further *Pipeline* run on it from the screen, so the *+ Run pipeline* button is absent rather than dead, and the session overview at `/session` is still a placeholder.

Two things on the landing page are stubs rather than features. The four sample pages are drawn stand-ins and clicking one reports that the sample could not be loaded, because `public/samples/` is empty; the code that fetches them is the real code, what is missing is four JPEGs. And errors in the upload flow are shown as plain text rather than as the designed cards.
