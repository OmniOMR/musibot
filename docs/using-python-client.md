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


## Batch processing of many pages

TODO
