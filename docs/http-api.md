# HTTP API

This page provides a high-level overview of the HTTP API that the `api` service exposes to public.


## Authentication

Requests to the API are authorized with a bearer token, given to the *User* manually. Existing known API tokens are listed in the `api` service's configuration file. Each *User* is identified by their token and may only access *Musicorpus Pages* they created; requests touching another user's page are rejected.

Authentication for the *general public* is not yet designed or implemented. Will be added later.


## Musicorpus Page

This is the heart of the API, where a *User* may upload page scans, start *Pipeline Executions* and download generated files.

Working with *Musicorpus Pages*:

- `POST /musicorpus-pages` Creates a new and empty *MusicorpusPage*, returns that page's representation, including its ID (a 12-character NanoID — random and URL-safe, not sequential, so pages cannot be enumerated across users).
- `GET /musicorpus-pages/{id}` Fetches information about a given *MusicorpusPage*
- `DELETE /musicorpus-pages/{id}` Deletes a *MusicorpusPage* and frees all of its resources (including killing any running *Pipeline Executions*).

Working with *Files*:

- `POST /musicorpus-pages/{id}/file-urls` Issues short-lived, presigned MinIO URLs for uploading and/or downloading *Files* directly to and from object storage — this keeps the non-scaling `api` service out of the file byte-path. The request body lists the *Files* to upload (`put`) and/or download (`get`); the response maps each path to a presigned URL plus an expiry. The client then transfers the bytes straight to/from MinIO.

```
POST /musicorpus-pages/{id}/file-urls
{ "put": ["image.jpg"], "get": ["transcription.musicxml"] }

200 OK
{
  "put": { "image.jpg": "https://<minio-public>/bucket/{id}/image.jpg?X-Amz-Signature=..." },
  "get": { "transcription.musicxml": "https://<minio-public>/bucket/{id}/transcription.musicxml?X-Amz-Signature=..." },
  "expires_at": "2026-07-22T16:05:00Z"
}
```

Executing *Pipelines*:

- `POST /musicorpus-pages/{id}/pipeline-executions` Starts a new pipeline execution, with its name and version specified in the payload. Returns that pipeline's representation, including its ID (integer, autoincrementing per page).
- `GET /musicorpus-pages/{id}/pipeline-executions` Returns the list of completed and running pipeline executions for this page.
- `GET /musicorpus-pages/{id}/pipeline-executions/{id}` Returns information about a specific pipeline execution.


## Pipelines

Endpoints to inspect available *Pipelines* and their versions.

- `GET /pipelines` Returns the list of known and available *Pipelines* and their versions and *Orchestrators* they can run on.
- `GET /pipelines/{pipeline-name}` Returns the list of versions of a given *Pipeline*, used by users to check when a newer version becomes available.

This listing is not configured anywhere — it is assembled from what *Orchestrators* and *Workers* announce over RabbitMQ, and it includes an *ImplicitPipeline* for every known *Model*. Beside the `pipelines` array, the response carries a top-level `warnings` array reporting name and signature conflicts between announcing providers. See [Discovery](discovery.md) for the response shape and for why the listing may lag reality by a few seconds.


## Streaming

HTTP endpoints for Server-Sent-Events (SSE) streams for various use cases. Extracted out because, for example, *Pipeline Execution* completion events may be listened to for all the *Musicorpus Pages* a *User* currently has.

TBA
