# Public access

How the *General public* — the third and lowest-priority [class of user](who-are-the-users.md) — is let onto a running Musibot instance without endangering the first two. Not yet implemented; this page is the design.

*Libraries* and *Model developers* hold API tokens issued to them by hand (see [HTTP API](http-api.md)). The public holds nothing: they follow a link to the *Web UI*, upload a scan and expect it to work. That is the whole point of the public tier — it exists so the team can demo the pipeline at a conference and email a URL to a prospective partner.


## What is being defended

Exactly one thing: **the public must not starve the *Libraries***. A conference demo and a hobby musician are welcome to consume the instance's spare capacity; they are not welcome to sit in front of a library's week-long batch run and delay it.

That is a narrower goal than "prevent abuse", and the narrowness is deliberate. Musibot is not defending against a determined attacker, is not protecting the public from each other, and is not trying to keep any individual member of the public within a fair share. Everything below follows from that one sentence, and features that would only make sense under a broader threat model are deliberately absent.


## No identification of public users

The obvious design — issue a token per client IP address and rate-limit each one — was considered and rejected. Three reasons, any one of which is sufficient:

- **The IP address is not reliably knowable.** Musibot's nginx sits behind the university's own reverse proxy, so the client address would have to arrive through an `X-Forwarded-For` chain that Musibot neither controls nor can trust without coordinating trusted-proxy configuration with the university IT department. That is real, recurring work in exchange for a defense we do not need.
- **The primary use case defeats it.** The public tier exists for conference demos, and a conference room is a single NAT address. The traffic pattern that most looks like an attacker is the exact pattern we built the tier to serve.
- **It is unnecessary.** A limit on the public *as a whole* protects the *Libraries* just as well and needs no identity at all. See below.

So Musibot does not identify public users, does not rate-limit per client, and does not care how many distinct humans are behind the public tier.


## Public sessions

The public still gets a bearer token, minted on demand:

```
POST /public-sessions

201 Created
{ "token": "...", "expires_at": "2026-07-31T15:04:00Z" }
```

The token behaves exactly like a *Library* API token — same `Authorization: Bearer` header, same security scheme, same `401`s. It identifies a *Public Session*, whose user identity is namespaced (`public:<nanoid>`) so it cannot collide with a name from `api_tokens_file`.

**Minting is free, unlimited, and unguarded**, and the token is therefore worth nothing as a defense: anyone can hold a thousand of them. It exists for one purpose only — so that two members of the public do not see each other's *Musicorpus Pages*. Page ownership already works this way (`get_owned_page` answers `404` for a page owned by someone else), and a public session slots into it with no second code path.

Everything downstream is unchanged. What is new is that the service must know whether the caller is public, which is what all the limits below key off.


## The limits

Two kinds, doing two different jobs.


### Global caps — the actual defense

These apply to the public tier as one pool. They are what keeps the *Libraries* safe, and they are the only limits here that survive contact with someone acting in bad faith:

| Cap | Purpose |
| --- | --- |
| Concurrent *Pipeline Executions* across all public sessions | Bounds how much of the worker fleet the public can hold at once. |
| Total storage held by public sessions | Bounds MinIO consumption. |

The execution cap is the important number. With `N` *Workers* for a given *Model* and a cap of `K`, the public can occupy at most `K` of them, so a *Library* batch run proceeds at no worse than `(N-K)/N` throughput and is never delayed by more than `K` jobs' worth of queueing. Combined with a shorter public execution timeout, the worst case is fully quantified: **public work can occupy at most `K` workers for at most one public timeout each**. That product is the guarantee the *Libraries* get, and it holds no matter how many public users show up or how they behave.

`K` should be at least 2, so that one public user cannot hold the entire public tier by keeping the single slot occupied.

When a cap is reached the request is **rejected, not queued** — a `429` with `Retry-After` for the execution cap, and the *Web UI* says the demo is busy and offers to retry. Queuing would mean holding requests open inside a single-process service with no backpressure, which trades a clear rejection for an unbounded internal one.


### Per-session caps — courtesy, not protection

| Cap | Value | Purpose |
| --- | --- | --- |
| Concurrent *Pipeline Executions* per session | 1 | One page at a time per browser tab. |
| *Musicorpus Pages* per session | 5 | Keeps an abandoned session from hoarding the pool. |

Because minting sessions is free, these are bypassed by minting another token, and nothing here pretends otherwise. **They guard against carelessness, not against malice** — a script with a bug in its retry loop, a user who opens twenty tabs — and they keep one ordinary public user from crowding out the next one before the global cap even comes into play. The global caps are what hold when someone actually tries.

The page cap answers `429` without a `Retry-After`: waiting does not help, deleting a page does.


## Session lifetime

A *Public Session* expires. When it does, its *Musicorpus Pages* are deleted and their MinIO folders freed, along the same path as an explicit `DELETE /musicorpus-pages/{id}`.

This is load-bearing, not housekeeping. A public user closes the browser tab and never deletes anything, so without expiry the public storage pool fills once and never drains — and a public tier that is permanently full is a worse outcome than the starvation being defended against, since it is permanent rather than transient and costs an attacker nothing to maintain. Expiry is what makes a global storage cap a limit rather than a countdown.

A sweep runs periodically and drops sessions past their deadline. A page with a running *Pipeline Execution* is left for the next sweep rather than being deleted underneath its execution; with a public execution timeout far shorter than the session lifetime, this only ever defers a page by one sweep. Requests bearing an expired token get the same `401` as an unknown one. The *Web UI* surfaces that rather than papering over it — it says the session expired and asks the user to reload, which mints a fresh one. Re-minting silently would be worse: the pages went with the session, so the app would quietly appear to have lost the user's work instead of explaining why the page list is empty.


## Measuring storage

The `api` service never sees *File* bytes — they travel over presigned URLs straight to MinIO (see [HTTP API](http-api.md)), which is exactly what keeps the non-scaling service out of the byte path. So it cannot count bytes as they arrive, and the storage cap is necessarily **measured after the fact**: the session sweep totals the sizes of objects under public pages and refuses new public pages while that total is over quota.

Enforcement therefore lags by up to one sweep interval, and the quota can be overshot by whatever the public manages to upload within it. Two things keep the overshoot survivable: nginx caps a single upload (below), and the quota is set well under MinIO's actual capacity precisely so that the slop has somewhere to go. The service logs public storage usage on each sweep, which is also how the deployment learns what a given quota yields in practice — the number of pages 5 GB buys depends entirely on how large the scans people bring turn out to be.

There is no cap on the number of *Files* per page, so per-session storage is not bounded by the page cap alone. The byte quota is the only real bound on public disk, which is why the sweep matters. See [Rough edges](rough-edges.md).


## Upload size, at nginx

nginx caps the body of a single upload (`client_max_body_size`) on the location that reverse-proxies MinIO. A 300 DPI A4 scan is a few megabytes as JPEG, so a limit around 30 MB is generous for the public tier.

Note that this cap **applies to everyone**. nginx cannot tell a *Library* from a member of the public: it does not hold the token map, and a client can put any string in an `Authorization` header. It is the same blindness that ruled out doing per-IP limits at the proxy. So the number must be chosen for the *Library* case — the users who actually have "300 DPI and above" material — and the public tier simply inherits it. A rejected upload surfaces as a `413` from nginx, which `python-client` should report intelligibly rather than passing through as a raw error page.


## Configuration

All of it is configuration on the `api` service ([Service configuration](service-configuration.md)), because none of it is a value two Musibot processes have to agree on — it is a policy of one deployment, and the right numbers are not knowable in advance. An instance with no public tier at all is a normal deployment, so the feature is off unless switched on.

| Field | Suggested | Meaning |
| --- | --- | --- |
| `public_access_enabled` | `false` | Whether `POST /public-sessions` mints anything at all. |
| `public_max_concurrent_executions` | `2` | The global cap `K`. Size it against the *Worker* fleet. |
| `public_storage_quota_bytes` | `5 GiB` | Global public storage, out of MinIO's ~20 GiB. |
| `public_session_ttl_seconds` | `3600` | How long a *Public Session* and its pages live. |
| `public_execution_timeout_seconds` | `60` | Public ceiling, below the general `pipeline_execution_timeout_seconds`. |
| `public_max_pages_per_session` | `5` | Courtesy cap. |
| `public_max_concurrent_executions_per_session` | `1` | Courtesy cap. |

The defaults are a starting point to be revised once there is traffic to look at, not a tuned configuration.
