# Changelog for `web-ui`

Released as `web-ui/vX.Y.Z` git tags — see [Versioning and releases](../../docs/versioning-and-releases.md).

The Web UI has no outward contract of its own: nothing depends on it, and it depends on the HTTP API. So entries here describe what a *User* can see and do, not an interface anyone programs against.


## Unreleased


### Added

- **The four sample pages are real scans.** "Nothing to hand? Take one of ours" offered four thumbnails drawn out of ruled lines — deliberately not photographs of anything, so that a placeholder could not ship unnoticed. The scans are here now: an engraved Lied of 1893, a nineteenth-century manuscript trombone part, a cropped staff in handwriting, and a photograph of a printed sheet lying on a carpet. Clicking one puts it through the upload flow exactly as though it had come off your own disk, so the samples demonstrate what Musibot is and is not good at rather than only what it looks like.

  All four are public domain, which is a requirement on any replacement rather than a happy accident: a sample is the one image on the site that Musibot redistributes rather than merely reads.

  **Dragging one up works too**, which is what the row has always invited and never done. A drag now carries which sample it is rather than the picture on screen: that picture is a thumbnail a few kilobytes wide, and a browser will hand a dragged image over as a file, so the alternative was uploading the thumbnail and having Musibot read it back to you.

- **A scanner's PDF can be uploaded directly.** Somebody scans a sheet of music and their scanner hands them a one-page PDF, which Musibot refused — so the file had to be opened, exported as an image and uploaded again, for a document that already holds nothing but the scan. Drop the PDF now and Musibot rasterises its first page at 300 DPI, which is the resolution OMR is written for and the one flatbed scanners default to: for a scan wrapped in a PDF this substantially recovers the image already inside the file rather than approximating it. A score exported from notation software has no native resolution and simply renders cleanly, which makes it about the best page Musibot can be given.

  **Only the first page, and it says so.** A PDF of several pages has the rest left unread, and the choice card tells you how many there were before you start the reading — one page at a time is what this app is, and losing the others quietly is the one way the flow could lie to you.

- **TIFF scans are read too.** The format an archive or a flatbed scanner reaches for first, and the one Musibot could not take, because no browser decodes a TIFF: Safari manages it through macOS, Chrome and Firefox have never done it at all. Musibot now decodes it itself, covering the compressions a scanner actually produces — CCITT Group 4 among them, which is what a bilevel scan is nearly always stored as. The tail the decoder does not cover, such as 16-bit samples or CMYK, is reported as a file that could not be read rather than left to fail later.

  A multi-page TIFF is treated exactly as a multi-page PDF: the first page is read, and the choice card says how many there were. A page held in the file as a reduced-resolution thumbnail is skipped rather than mistaken for the scan.


### Changed

- **PNG and BMP scans are accepted, not only JPEG.** The upload form was the only thing in Musibot that cared what format a page was in: every *Model* opens a page's image with `cv.imread`, which decides on the file's magic bytes and never looks at its name, so a PNG has always read perfectly well once renamed to `.jpg`. The form takes both without the rename, and the drop zone says so.

  A PNG is uploaded as it arrived, because a scan is line art and JPEG's ringing lands exactly on the thin dark strokes that recognition reads — re-encoding a lossless file to gain a file extension would be paying in the one currency that matters here. A BMP is re-encoded, because it is not compressed at all: a 300 DPI A4 bitmap is around 25 MB of the same page a JPEG carries in one, and nothing limits an upload's size, so it would have gone through slowly rather than failed.

  That passing-through is a hack, and it is marked as one in the source. A PNG lands at `image.jpg`, because that is the path a *Signature* names — so a page whose `image.jpg` is a PNG is not a conforming *MusicorpusPage*, and anything reading such a corpus by the standard rather than by sniffing is entitled to be wrong about it. BMP, TIFF and PDF do not have this problem, since they arrive as real JPEGs. The fix for PNG belongs in the specification, not in this app.

- **An outsized page is scaled down rather than lost.** Everything that gets re-encoded passes over a canvas, and a browser asked for a larger one than it allows does not fail — it hands back a blank, which would have reached the visitor as a page that read as empty. Anything over 25 megapixels is now drawn smaller: a 600 DPI archival scan, or the page of a PDF whose sheet was never a sheet of paper. Every ordinary size, up to A3 and tabloid at 300 DPI, is untouched.

- **"Download results" is now "Download MusicXML", and saves the one file.** The button in the page header fetched everything a reading had produced, which for a page read staff by staff is the crops, the layout, a MusicXML and an LMX per staff — dozens of saves, from one click, in a browser that asks about each. Almost nobody wanted any of it: a visitor comes to Musibot to turn a scan into MusicXML, and that is the page's own `transcription.musicxml`. So that is what the button saves, and it is disabled until the reading has written one. Everything else is still downloadable a row at a time from the file list, which is where somebody who wants a single staff's tokens is already looking.

  A page uploaded as a single staff crop has no page-level MusicXML, only a `Staves/1/transcription.musicxml` — and that one file is nonetheless all of that page's music, so the button offers it. It is when a page holds *several* staff readings and no page-level one that there is nothing to offer, because thirty fragments of somebody's music is not somebody's music.

  The saved file is named after the scan it was read from: `nocturne-op9.jpg` comes back as `nocturne-op9.musicxml`, rather than as `transcription.musicxml` like every other page's. A visitor who reads three scans could not otherwise tell the three files apart, and a browser handed the same name three times does not ask — it appends a number.

- **The token sequence is shown only when it is what was selected.** Selecting either transcription format used to show both, on the reasoning that they are two views of one answer and nobody wants to click twice. But they are for two different readers, and most visitors are the first kind: they came to see whether Musibot read their music correctly, and a wall of LMX under every staff was one more thing to scroll past to reach the next one. Selecting `transcription.musicxml` now shows the notation alone; the tokens appear when `transcription.lmx` is what was selected, and the panel no longer fetches a file it was not going to show. The other direction is unchanged — selecting the tokens still shows the notation above them, because that is what the same answer looks like to everybody.


### Fixed

- **A page transcription was engraved as one endless line.** Every reading was drawn as a single unbroken staff. That is right for a staff crop, which is one line of music and has no systems of its own to honour, and wrong for a whole page: a page's systems are written in its MusicXML, and running them together turned a sheet of music into one line disappearing off the side of the panel. Page-level readings now break where the file says they break, and staff-level ones are drawn as before.

- **Measure rests were dropping out of the engraving.** OSMD wants a `<duration>` on every rest, and a measure rest carries none — neither the ones MuseScore exports nor the ones LMX produces. Musibot repairs the document on the way in, but the repair had never taken effect: it wrote the number into a property that exists only on HTML elements, so what OSMD received was an empty `<duration/>`, and the repaired document reached it having lost the `<?xml` declaration by which OSMD tells a score from a URL to fetch one from. A score with a full-bar rest in it renders now.


## 0.1.1 — 2026-08-14

A page screen that shows something the moment it opens, and stops polling: what it displays now arrives on the streams the `api` service grew in 0.3.0. Needs an `api` service of that version or newer.


### Added

- **A page opens showing something.** Nothing was selected when a page screen opened, so a visitor who had just dropped a scan in watched an empty canvas while the recognition ran, and an empty one afterwards until they thought to click a row. Musibot now selects the *File* most worth looking at and re-selects as better ones appear — the scan, then the boxes over it, then the staff crops, then the transcription — and leaves the choice alone the moment the visitor makes one of their own. A *File* the order does not name is never chosen for somebody unless it is the only thing the page holds: a model may write anything, and showing an arbitrary file is worse than showing the scan.

- **The page screen no longer polls.** It asked the service about a running page every 1.5 seconds; now it asks once when the screen opens and is told what changed — the file-change stream when an execution writes a *File*, the result stream when one ends. An idle page costs no requests at all, which matters most on the public tier, where every open tab used to be a standing load on one shared pool.

  Two things make dropping the poll safe rather than optimistic. Every reconnection re-asks, because neither stream replays and a connection can drop across an ending. And a stream that says nothing for 45 seconds — three missed keepalives — is presumed dead and reopened, since a connection killed by something in the middle can otherwise leave a page that has simply stopped updating.

- **A result appears the moment it is written.** The file list no longer waits for the next poll: the app watches the page's file-change stream, and a notice that an execution has written something sends it to list the page again. What it shows still comes from object storage — the notice is only a reason to ask — so a *File* it names carries its real size and time, and a missed notice costs the wait until the next poll and nothing more.

- **The recognition log shows a real reading.** The panel across the bottom of a page now streams what actually happened — what each *Model* printed as it printed it, alongside the service's own account of the execution: what was started, what it wrote, how long it took, and why it failed. It had been a convincing stand-in that played back a scripted reading on a timer, labelled as a sample so nobody took it for one; that is gone, and with it the label.

  A line is stamped with seconds into its execution rather than a time of day, since what a reader is judging is how long a step took. Lines are kept for as long as the page is open, so collapsing the panel and opening it again shows the whole log — but nothing is replayed after a browser reload, because the service holds no buffer and a log is a *User* watching a page being read rather than a record kept for later.


## 0.1.0 — 2026-08-07

First release: the whole visitor-facing app, from the landing page to a transcription beside the scan. Everything below is new.


### Fixed

- **Two pages in five were being taken for a single staff.** The guess that picks a default *Pipeline* asked whether an image was wider than it was tall, and 41 of the 100 pages in the `UFAL.OmniOMR` corpus are landscape — so a page was handed to a model that reads one line of music, which transcribes the whole sheet as though it were one. The threshold is now a width-to-height ratio of 3.0, measured across those 100 pages and 1184 staff crops: the two populations are separated by an empty band, nothing in the corpus falling between 1.5 and 4.6. The histogram is in the source beside the number. The explanation shown to the visitor no longer claims a page is "tall and narrow" either, which was untrue of it in plain sight.


### Added

- **The toolchain.** Vite, React, TypeScript and MUI, built to a static bundle that nginx serves. No server-side rendering: the deployment is files behind a web server, and stays that way.
- **A landing page that link previews can read.** The title, description, canonical link, Open Graph and Twitter card tags and a `<noscript>` body are static in `index.html`, and `robots.txt` and `sitemap.xml` are generated at build time from the same public-origin constant. Googlebot runs JavaScript and would have indexed the app regardless; the scrapers behind Slack, LinkedIn and Mastodon previews do not, and a URL that gets emailed around is the whole point of the public tier.
- **The theme** — printed paper: a warm ivory page, Source Serif 4 headings over Source Sans 3 body text, flat surfaces divided by hairline rules, and Charles University's cardinal red as the one saturated colour. Fonts are bundled rather than fetched from a CDN. Colour choices and their measured contrast ratios are recorded in `src/theme/palette.ts`.


- **The error and edge states**, as cards rather than as a line of text: a file that is not a JPEG, an allowance that is spent, an instance that offers no public access, and a reading that finished without error having produced nothing. The last of those had no handling at all, and is the unhappiest outcome Musibot has — the execution says `completed`, nothing is reported wrong, and the file list has not changed, which a visitor reads as a broken service rather than as a page with no music on it. It is detected from what the *Pipeline* declared it would write, and offers the two things worth doing next: another pipeline, or the log.
- **A refusal for load says whether waiting will help.** Over the concurrency cap it will, and the card counts down; over the per-session page cap it will not, and the card says to delete a page instead — which is why the service deliberately sends no `Retry-After` there.


- **Running another *Pipeline* on a page that already has one.** Mostly for somebody developing a model — try a second pipeline against the same scan, or run one model alone on a staff the first pipeline cut out — and the reason the file list is not grouped by execution. What can be offered is worked out by matching each announced *Signature* against the *Files* the page actually holds, so a pipeline that reads one staff at a time is listed once per staff, and one that needs a *File* the page does not have says which.


- **The session overview** at `/session`, which the floating pill has been pointing at since it existed. Every page this browser has uploaded and can still reach: a thumbnail, the filename, which *Pipeline* ran and how it went, and how long is left. It says plainly that nothing is stored under an account and that closing the tab does not extend the hour — a visitor who takes this for a library of their work is going to lose it, and saying so once at the top is cheaper than explaining afterwards. The list is drawn from the ledger with no network; only the reading's outcome is asked of the server, once per page.
- **A thumbnail is kept for each uploaded page**, made in the browser from bytes already in hand rather than fetched back — a few kilobytes against several megabytes of scan per row.


- **The recognition log panel**, collapsed by default and opened from the pill at the foot of the overview. One log for the whole page rather than one per *Pipeline Execution*, since a page can be read twice and the story is easier to follow in the order it happened. It is empty — the API has no log endpoint yet — so it says so; what is built is the paper it will be printed on: continuous-feed dot-matrix stock with sprocket holes down both edges that scroll with the lines rather than framing them.


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

A real recognition log. The panel is built and its lines are a stand-in played back on a timer, labelled as one, because the API has no log endpoint and the SSE protocol behind it is not designed yet.

Live progress. Until the API streams, a running execution is polled and its outputs appear together when it finishes rather than one at a time.

The four sample pages on the landing page, which are drawn stand-ins until real scans exist in `public/samples/`.

Two things on the landing page are stubs rather than features. The four sample pages are drawn stand-ins and clicking one reports that the sample could not be loaded, because `public/samples/` is empty; the code that fetches them is the real code, what is missing is four JPEGs. And errors in the upload flow are shown as plain text rather than as the designed cards.
