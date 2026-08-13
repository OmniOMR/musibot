# Using python client

This guide explains the basics of using the Musibot python client to have music documents processed by the system.


## Installation

We assume you have your own local python project, in which you need to utilize Musibot service in some way. Let's start by installing the python client package:

```bash
pip3 install 'musibot-client @ git+https://github.com/OmniOMR/musibot.git@main#subdirectory=components/python-client'
```


## Processing a Musicorpus page folder by a pipeline

Musibot works with Musicorpus pages, we will set up an in-memory representation of one such page folder and send it to Musibot for recognition, then we'll download one file that interests us (the page-level MusicXML):

The address is where the `api` service is published — `http://localhost:8000/musibot/api` for the [local development stack](../deploy/README.md), and `https://<host>/musibot/api` for a deployment. A service you started yourself and reach directly answers on `http://localhost:8080`.

```py
from musibot.client import MusibotClient
from pathlib import Path


client = MusibotClient(
    musibot_api_url="http://localhost:8000/musibot/api",
    api_token="secret"
)

output_files = client.process_page(
    input={
        "image.jpg": Path("my-page-scan.jpg").read_bytes()

        # optionally any other Musicorpus files
        # "Staves/1/image.jpg": ...
        # "Staves/2/transcription.musicxml": ...
    },
    pipeline=("hello-model", "1.0.0"),
    output={  # a set, not a dict
        "transcription.musicxml"

        # optionally any other Musicorpus files
        # "Staves/1/transcription.musicxml"
    }
)

print(output_files)
# {
#   "transcription.musicxml": b"<?xml version="1.0" encodi..."
# }
```


## Running a single model

Every *Model* Musibot knows about is also offered as a *Pipeline* of its own, with the same name and version — an [ImplicitPipeline](domain-model.md). It runs that one *Model* and nothing else, which is how a *Model* is tested in isolation without anyone having to write a *Pipeline* that merely calls it.

There is nothing new to learn: it is requested exactly like any other pipeline.

```py
output_files = client.process_page(
    input={"image.jpg": Path("my-page-scan.jpg").read_bytes()},
    pipeline=("hello-model", "1.0.0"),  # a Model, run on its own
    output={"transcription.musicxml"}
)
```

To see what is available — pipelines and models alike — ask:

```py
listing = client.list_pipelines()

for pipeline in listing.pipelines:
    kind = "model" if pipeline.implicit else "pipeline"
    print(f"{pipeline.name} {pipeline.version} ({kind}, {pipeline.instances} running)")
```

`instances` is the number of live providers behind an entry. It is worth reading when executions time out for no apparent reason: an entry with zero instances is listed only because something announced it moments before going away.


## Finding out what was produced

`process_page` asks for `output` files by name, which works when you know what to expect. Often you do not: a page-level pipeline finds the staves itself, so how many `Staves/{n}/` folders come back is the recognition's answer rather than yours.

For that, hold the page open and ask what it holds.

```py
with MusibotClient(musibot_api_url="http://localhost:8000/musibot/api", api_token="secret") as client:
    page = client.create_page()
    client.upload_files(page.page_id, {"image.jpg": Path("my-page-scan.jpg").read_bytes()})

    execution = client.start_execution(page.page_id, "hello-model", "1.0.0", ["image.jpg"])
    client.wait_for_execution(page.page_id, execution.execution_id)

    for file in client.list_files(page.page_id):
        print(f"{file.path}  {file.size} bytes")
    # image.jpg  918273 bytes
    # layout.json  2143 bytes
    # Staves/1/transcription.musicxml  4021 bytes
    # Staves/2/transcription.musicxml  3877 bytes

    transcriptions = client.download_files(
        page.page_id,
        [file.path for file in client.list_files(page.page_id) if file.path.endswith(".musicxml")],
    )

    client.delete_page(page.page_id)
```

`list_files` answers from object storage each time rather than from a list the server keeps, so it is also what to poll while an execution runs: files appear as they are written. Note that it reports the page's folder as it is now — a second execution may overwrite a file the first produced, and what you get back is the newer one.

Delete the page when you are done. `process_page` does it for you; holding a page open yourself makes it yours to clean up.


## Batch processing of many pages

A whole collection is not a loop around `process_page`. `process_pages` keeps several pages in flight, hands results back as they finish, and treats a failed page as a result rather than as the end of the run:

```py
from musibot.client import BatchJob, MusibotClient


def jobs():
    """Pulled lazily, one page at a time as a worker frees up — so this fetches
    a scan only when there is something ready to read it."""
    for uuid in database.page_uuids():
        yield BatchJob(key=uuid, input={"image.jpg": image_server.fetch(uuid)})


with MusibotClient(musibot_api_url=..., api_token=...) as client:
    for result in client.process_pages(
        jobs(),
        pipeline=("page-to-musicxml", "1.2.0"),
        output={"transcription.musicxml"},
        concurrency=8,
    ):
        if result.failed:
            failures.record(result.key, str(result.error))
            continue
        storage.put(result.key, result.files["transcription.musicxml"])
```

Four things about that loop are the whole design:

**`key` is yours.** Whatever you put on the job comes back on the result untouched — a database UUID here, a folder in the next example, a row object if that suits you. It is how a result is matched back to what it came from, because **results arrive as pages finish rather than in the order you gave them**.

**A failure is a result.** One unreadable scan among a million is not a reason to stop, so `result.error` carries what went wrong and the loop goes on. Exceptions are kept for what ends the whole run — a token the server does not accept, a server that is not there at all.

**The jobs are pulled lazily.** A million-page run never holds a million scans: the generator is asked for a page only when a worker is free, and it runs on that worker, so fetching the next scan overlaps with Musibot reading the last one.

**`concurrency` is how many pages are in flight**, and it should be sized against the *Worker* fleet rather than against your patience. More pages in flight than there are *Workers* to read them only lengthens a queue.

Stopping early — a `break`, a Ctrl+C — shuts the run down and deletes the pages still in flight.


### When the network goes away

Infrastructure trouble is waited out rather than reported: a connection that dropped, a service restarting behind a proxy, a `429` from a shared instance. Each is retried with a doubling backoff and a warning in the log, so a run that met a ten-minute outage at three in the morning is finished by breakfast instead of 98% finished.

What is *not* retried is a *Pipeline* that ran and failed. The *Model* answered — "No staves found in the image" — and asking it the same question again gives the same answer.

The defaults ride out about a quarter of an hour. For an overnight run over a collection, buy more:

```py
from musibot.client import RetryPolicy

client.process_pages(..., retry=RetryPolicy(give_up_after_seconds=3600))
```

`result.attempts` says how many tries a page took, which is worth recording: a run that quietly needed three attempts a page is a run with something wrong under it.


### A benchmark over a local dataset

The other shape this is built for: a folder of Musicorpus pages on disk, a pipeline to measure, and outputs to write back beside the originals. Here the outputs cannot be named in advance — how many staves a page has is what the recognition found out — so `output` takes a predicate over the page's *Files* instead of a set of names:

```py
def jobs(dataset: Path):
    for page_dir in sorted(dataset.iterdir()):
        yield BatchJob(key=page_dir, input={"image.jpg": (page_dir / "image.jpg").read_bytes()})


for result in client.process_pages(
    jobs(Path("benchmarks/UFAL.OmniOMR")),
    pipeline=("ayce-long", "2026-08-03-192253-e440"),
    output=lambda file: file.path.endswith((".musicxml", ".lmx")),
    concurrency=4,
):
    for path, content in result.files.items():
        target = result.key / "predicted" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    metrics.add(page=result.key, seconds=result.seconds, error=result.error)
```

There is deliberately no `process_dataset` helper. Where predictions land, whether an existing one is overwritten, and which *Files* a page should upload for a given *Signature* are decisions a benchmark rig should own rather than inherit — and the generator above is the whole of what a helper would have saved.


## Watching executions finish

`wait_for_execution` and the batch both wait on one stream of endings that the client holds open for all of its pages — nothing polls. That stream is available raw for a caller that wants to watch rather than to wait:

```py
for ended in client.watch_execution_results():
    print(ended.page_id, ended.execution.state, ended.execution.error or "")
```

It carries **every page of your token's identity**, including pages another script sharing that token created: Musibot has no sessions, so a script that cares about its own pages filters on `page_id` — which it can, since it created them. Two things that must not see each other want two tokens mapping to two *identities*; see [the HTTP API](http-api.md#there-are-no-sessions-only-identities).

Nothing is replayed. An execution that ended before this was called is not announced on it, which is why `wait_for_execution` also asks about its execution once as it starts waiting.


## Everything else

[The reference](python-client-reference.md) lists every method, model and error, along with what each costs.
