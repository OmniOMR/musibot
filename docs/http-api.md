# HTTP API

This page provides a high-level overview of the HTTP API that the `api` service exposes to public.


## Authentication

Requests to the API are authorized with a bearer token, given to the *User* manually. Existing known API tokens are listed in the `api` service's configuration file.

Authentication for the *general public* is not yet designed or implemented. Will be added later.


## Musicorpus Page

This is the heart of the API, where a *User* may upload page scans, start *Pipeline Executions* and download generated files.

Working with *Musicorpus Pages*:

- `POST /musicorpus-pages` Creates a new and empty *MusicorpusPage*, returns that page's representation, including its ID (integer, autoincrementing).
- `GET /musicorpus-pages/{id}` Fetches information about a given *MusicorpusPage*

Working with *Files*:

- `PUT /musicorpus-pages/{id}/files/{path}` Creates or replaces a *File* at the given path within the *MusicorpusPage*
- `GET /musicorpus-pages/{id}/files/{path}` Downloads a *File* at the given path within the *MusicorpusPage*

Executing *Pipelines*:

- `POST /musicorpus-pages/{id}/pipeline-executions` Starts a new pipeline execution, with its name and version specified in the payload. Returns that pipeline's representation, including its ID (integer, autoincrementing).
- `GET /musicorpus-pages/{id}/pipeline-executions` Returns the list of completed and running pipeline executions for this page.
- `GET /musicorpus-pages/{id}/pipeline-executions/{id}` Returns information about a specific pipeline execution.


## Pipelines

Endpoints to inspect available *Pipelines* and their versions.

- `GET /pipelines` Returns the list of known and available *Pipelines* and their versions and *Orchestrators* they can run on.
- `GET /pipelines/{pipeline-name}` Returns the list of versions of a given *Pipeline*, used by users to check when a newer version becomes available.


## Streaming

HTTP endpoints for of Server-Sent-Events (SSE) streams for various usecases. Extracted out because, for example, *Pipeline Execution* completion events may be listened for for all the *Musicorpus Pages* a *User* currently has.

TBA
