# Musibot

Musibot is a web service for reading sheet music (scans and photos). By reading we mean producing a machine-readable file format, such as MusicXML.

Musibot comes from the research field of Optical Music Recognition (OMR) and serves as a place of deployment and production-level use of trained OMR models. To represent the music notation-related data, it uses the [Musicorpus Specification](https://github.com/OmniOMR/musicorpus/blob/main/docs/musicorpus-specification/musicorpus-specification.md), which describes in detail how page-level OMR data should be annotated.

Musibot consists of:

- **Web UI** where users can upload scans of individual pages (JPEG) and have them read.
- **Web HTTP API** that advanced users may use to send pages for recognition.
- **Python Client** that advanced users may choose over the low-level HTTP API for easier consumption.
- **Recognition pipelines** that string together specific versions of OMR models to perform useful work for the user (e.g. first find all staves, then run each staff through an end-to-end CRNN model and then concatenate results into one MusicXML file).
- **Models** that preform the actual recognition (usually deep learning models)
- **Workers** create separated runtime environments for specific models and allow for their horizontal scalability


## Documentation

User documentation:

- Using Web UI
- [Using python client](docs/using-python-client.md) TODO
- [Adding models](docs/adding-models.md)
- [Writing pipelines](docs/writing-pipelines.md)

Design:

- [Who are the users](docs/who-are-the-users.md)
- [Domain model](docs/domain-model.md)
- [Architecture](docs/architecture.md)
- [Repository layout](docs/repository-layout.md)
- [User request dataflow](docs/user-request-dataflow.md)

Interfaces:

- Python Client (TBA, see `docs/using-python-client.md` for now)
- [HTTP API](docs/http-api.md)
- Orchestrator Head API (TBA, see `docs/writing-pipelines.md` for now)
- RabbitMQ queues and messages
- Worker IPC (TBA, see `docs/adding-models.md` and `docs/user-request-dataflow.md` for now)

Technical documentation:

- [Service configuration](docs/service-configuration.md)
- [Deployment](docs/deployment.md)
