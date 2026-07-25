# Using python client

This guide explains the basics of using the Musibot python client to have music documents processed by the system.


## Installation

We assume you have your own local python project, in which you need to utilize Musibot service in some way. Let's start by installing the python client package:

```bash
pip3 install 'musibot-client @ git+https://github.com/OmniOMR/musibot.git@main#subdirectory=components/python-client'
```


## Processing a Musicorpus page folder by a pipeline

Musibot works with Musicorpus pages, we will set up an in-memory representation of one such page folder and send it to Musibot for recognition, then we'll download one file that interests us (the page-level MusicXML):

```py
from musibot.client import MusibotClient
from pathlib import Path


client = MusibotClient(
    musibot_api_url="http://localhost:8080/api",
    api_token="secret"
)

output_files = client.process_page(
    input={
        "image.jpg": Path("my-page-scan.jpg").read_bytes()

        # optionally any other Musicorpus files
        # "Staves/1/image.jpg": ...
        # "Staves/2/transcription.musicxml": ...
    },
    pipeline=("hello-world", "1.0.0"),
    output = {  # a set, not a dict
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


## Batch processing of many pages

TODO
