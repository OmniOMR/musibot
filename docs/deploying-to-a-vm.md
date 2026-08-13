# Deploying onto a VM

The runbook: how to bring a Musibot instance up on a blank Ubuntu VM, and how to update it afterwards. [Deployment](deployment.md) is the companion to this page — it explains *why* the arrangement is what it is, and this page assumes it rather than repeating it. When something here looks arbitrary (the bucket named after the URL, the prefix that is stripped and then written back on), that is where the reason lives.

Everything below installs onto one machine. Splitting *Workers* onto their own VMs changes only which addresses go into which configuration file, and is noted where it does.


## What ends up on the machine

Six things run, and nginx is the only one the world can reach:

| | Runs as | Listens on | Started by |
| --- | --- | --- | --- |
| nginx | `www-data` | `:80` | `nginx.service` (from apt) |
| MinIO | `minio-user` | `:9000`, `:9001` | `minio.service` (from the .deb) |
| RabbitMQ | `rabbitmq` | `:5672`, `:15672` | `rabbitmq-server.service` (from apt) |
| Web API | `musibot` | `127.0.0.1:8080` | `musibot-api.service` (this repo) |
| Workers | `musibot` | nothing | `musibot-worker@<instance>.service` (this repo) |
| Web UI | — | — | static files, served by nginx |

The university proxy publishes the instance at `https://quest.ms.mff.cuni.cz/musibot/` and forwards to port 80 on this VM, **stripping the `/musibot` prefix on the way**. Nothing on the VM terminates TLS.


### The network this sits on

The VM is not reachable from the internet. It sits on the university's internal network, and the university's proxy is the only thing that publishes any of it — which is why that proxy exists in the first place, and is what makes the rest of this simple.

So the services bind normally rather than being restricted to the loopback, and there is no firewall to configure. RabbitMQ and MinIO answer on every interface because a *Worker* on a second VM has to reach both directly: it consumes its work from the broker and moves a page's *Files* to and from object storage itself, never through the `api` service. Moving a worker off this machine is then a matter of putting this VM's hostname into that worker's environment file, and nothing else.

Two things follow that are worth being deliberate about rather than surprised by. The RabbitMQ management UI and the MinIO Console are reachable from anywhere on the university network, and published to the internet besides — nginx serves both under the public prefix, deliberately, because being able to look at a queue is worth more here than the exposure costs. The only thing in front of either is its own login, so those two passwords are the ones to actually choose well. And the `api` service still binds the loopback, not because it is more sensitive but because nothing except nginx has any reason to call it.

What makes this an easy trade is that the VM holds nothing worth taking. All state is ephemeral — a page arrives, is processed within minutes, is downloaded and is forgotten — so the blast radius of a compromise is the machine itself, which is precisely what isolating it was for.

On disk:

```
/opt/musibot/
    repo/                        this repository, for its unit files and templates
    api/venv/                    the Web API
    workers/<instance>/venv/     one Worker Head, per systemd instance
    models/<codebase>/venv/      a Model's own environment, when it needs one
    models/<codebase>/snapshots/ its weights — several of them
/etc/musibot/
    api.env                      the Web API's configuration
    api-tokens.json              the Library API tokens
    worker-<instance>.env        one per worker instance
    nginx.env                    the addresses nginx's config is rendered from
/var/lib/musibot/<instance>/     a Worker's scratch mirror of the pages it is working on
/var/lib/minio/                  the objects
/var/www/musibot/
    releases/<stamp>/            an unpacked Web UI bundle
    current -> releases/<stamp>  the one nginx serves
```


**`workers/` and `models/` are indexed by different things**, which is the part of that layout most likely to be misread. A *Worker* is one running process and gets a directory per systemd instance; a *Model* is an installed codebase and gets a directory per codebase, shared by every worker running it. So Zeus is installed once, at `models/zeus/`, while `workers/` holds one entry per snapshot being served — and the two directory names deliberately do not match:

```
/opt/musibot/
    models/zeus/venv/                                Zeus, installed once, on python 3.10
    models/zeus/snapshots/zod-bw-auth-ft-2026-07-20.model/
    models/zeus/snapshots/zod-bw-auth-2026-07-13.model/
    workers/solo26-zod-bw-auth-ft-2026-07-20/venv/   a head serving the first
    workers/solo26-zod-bw-auth-2026-07-13/venv/      a head serving the second
```

That is also why `snapshots/` is plural. One codebase serves as many as you have deployed, and [replacing one](#naming-a-worker-instance) puts the new beside the old rather than over it, so two live at once for as long as the changeover takes. A `models/<codebase>/` directory exists only when the *Model* cannot share its head's environment — `hello-model` has none, because it lives in `workers/hello/venv` alongside the head.

If two snapshots ever need different *versions* of the same codebase, version the codebase directory too — `models/zeus-1.2/` — and point each worker's model command at the one it needs. Nothing prevents it; it simply has not been necessary.

Two further things about that layout are decisions rather than convention.

**`venv`, not `.venv`.** The leading dot belongs in a source checkout, where it keeps the environment out of the way of the code; every component in this repository uses it for exactly that. Here there is no code to get out of the way of, and the dot only hides the single thing the directory contains — `ls /opt/musibot/api` showing nothing is not a helpful start to an incident.

**One virtual environment per service, not one shared by all of them.** They all depend on `core`, and `core` is the wire contract, so a single shared environment looks like it would usefully force one version of it on everything. It would not, and the reason is worth knowing before someone consolidates them:

- It cannot cover everything anyway. An *Orchestrator* needs an environment of its own because its *Pipelines*' dependencies are arbitrary and may conflict with each other, and a *Worker Head* is often installed into its *Model*'s environment on purpose ([the one-venv case](deployment.md#one-venv-or-two), which `hello-model` uses below). What is left to share is the `api` service and those heads that live apart from their model.
- What it would enforce is the wrong thing: one *installed* `core`, not one *running* `core`. Upgrade the shared environment to update a worker, restart only that worker, and the `api` service goes on serving the `core` it imported at boot — from an environment that now holds a different one. The mismatch is not prevented, it is hidden, and it appears at the next unrelated restart.
- It would not generalise. A *Worker* on a second VM has its own environment regardless, so the invariant would hold only on this machine — which is worse than not holding at all, because it invites relying on it.
- It costs operability. The `api` service and the worker heads could no longer be rolled back independently, and since restarting the `api` service discards all state, every worker-head update would become a full outage.

Keeping them separate makes "which `core` is the `api` service running" a fact readable off the disk. What actually keeps the versions together is the update procedure — [core is a fleet-wide change](#updating-when-the-source-changes), and nothing on the wire checks it today.


### The accounts

Three separate systems have their own idea of a user — the operating system, RabbitMQ, and MinIO — and this deployment creates accounts in all three. They are unrelated namespaces, so the same name in two of them is two accounts.

| Account | Lives in | Created by | Who uses it |
| --- | --- | --- | --- |
| `musibot` | unix | `useradd`, section 1 | the `musibot-api` and `musibot-worker@*` units |
| `minio-user` | unix | `useradd`, section 3 | the `minio` unit |
| `rabbitmq` | unix | the `rabbitmq-server` package | the broker |
| `www-data` | unix | Ubuntu itself | nginx |
| `musibot` | RabbitMQ | `rabbitmqctl add_user`, section 2 | the `api` service and every *Worker Head* |
| `admin` | RabbitMQ | `rabbitmqctl add_user`, section 2 | a human, at `/musibot/rabbitmq/` |
| `guest` | RabbitMQ | the package, by default | nobody — it is deleted |
| `musibot-admin` | MinIO | `MINIO_ROOT_USER`, section 3 | a human, with `mc` and at `/musibot/minio/` |
| *a generated access key* | MinIO | `mc admin user svcacct add`, section 3 | the `api` service and every *Worker Head* |
| `alice`, … | `api-tokens.json` | you, section 4 | *Library* users of the HTTP API |

Two of those are worth pointing at directly.

**The two `musibot`s are different accounts.** One is a unix system user that owns `/opt/musibot` and runs the services; the other is a RabbitMQ user that those services authenticate to the broker as. They share a name because it reads well in both places, and nothing connects them.

**The MinIO service account has no name.** MinIO calls it a service account rather than a user, and its identity *is* its access key — a generated string, not something you choose (unless you pass `--access-key`). So the row above cannot name it, and neither can the command that creates it: `mc admin user svcacct add musibot-local musibot-admin` names the alias and the parent user, and prints the new identity rather than taking one.

The last row is not really an account: *Library* users are entries in a JSON file the `api` service reads, with no presence anywhere else on the machine. The *General public* has nothing at all — a public session is a token minted on demand, and it is not in this table because it is not created by anybody.


## Before you start

**Ubuntu 26.04 LTS** ("Resolute Raccoon") is assumed.

Decide the public address before configuring anything, because three separate places are told it and they have to agree: nginx (`MUSIBOT_PUBLIC_HOST`), the `api` service (`MUSIBOT_S3_PUBLIC_URL`), and the Web UI bundle (`MUSIBOT_PUBLIC_ORIGIN` at build time). This page uses `quest.ms.mff.cuni.cz` throughout.

```bash
sudo apt update
sudo apt install -y nginx git curl rsync gettext-base software-properties-common nano
```

`gettext-base` is there for `envsubst`, which renders the nginx configuration; `software-properties-common` provides `add-apt-repository`, which the next section needs. `nano` is normally already present, and is installed here so that the `sudo nano` steps below cannot be the first thing that fails — every configuration file on this page is edited with it rather than with `sudo -e`, which would open whatever `$EDITOR` happens to be on a machine nobody has configured yet. Use another editor freely; nano is named only so that the instruction is unambiguous.

Then put this repository on the machine. It is not what the python services are installed *from* — those come from git links at explicit tags, so that what is installed is a version rather than a working copy — but the unit files, the nginx template and the example configurations live here, and `git pull` is how the VM gets new ones:

```bash
sudo mkdir -p /opt/musibot
sudo git clone https://github.com/OmniOMR/musibot.git /opt/musibot/repo
```


### Python versions on this machine

This VM will end up with several pythons on it, and that is the design working rather than a mess accumulating. A *Model* is reached only over [the worker IPC](worker-ipc.md) — pipes and the filesystem, no shared imports and no shared interpreter — precisely so that it may pin whatever python its dependencies need. [Zeus](../components/models/zeus/README.md) needs **3.10**, because TensorFlow 2.12 has no wheels for anything newer. The next model will need something else. Installing a python version is therefore a routine deployment step here, and this is the recipe for it.

Two versions are needed before anything else is installed:

| | Version | Why |
| --- | --- | --- |
| The system's | 3.14 | Ubuntu's own. Left alone; nothing of Musibot's runs on it. |
| The core services | **3.12** | The `api` service and every *Worker Head*. |
| Zeus | 3.10 | Installed later, in [its own section](../components/models/zeus/README.md). |

3.14 would very likely work — it satisfies the 3.11 floor `core` sets — but every component here is developed and tested on 3.12, and a first deployment is not the place to also find out what a two-version jump costs. Moving up later is a venv rebuilt and a service restarted, per component and independently. Every `python3.12` below is that decision and nothing more.


#### From deadsnakes, which is where these come from

[deadsnakes](https://launchpad.net/~deadsnakes/+archive/ubuntu/ppa) packages the python versions Ubuntu does not ship, for the release you are on. It carries 26.04 ("resolute"), and on it provides **3.7 through 3.13**, plus pre-release series. It does *not* carry 3.14 — that is the one Ubuntu itself ships, and the PPA never duplicates it.

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update

# what this deployment needs today
sudo apt install -y python3.12 python3.12-venv
```

**`python3.X-venv` is a separate package and is the one that gets forgotten.** Without it, `python3.12 -m venv` fails with a message telling you to install exactly that, which is at least a good failure.

A third package is sometimes needed: **`python3.X-dev`**, the headers. Reach for it when a `pip install` starts compiling — that happens when a dependency has no wheel for the interpreter version or platform, and the error is a compiler one about a missing `Python.h` rather than anything that names the package. Neither Musibot nor Zeus needs it today.

Check what a version's availability actually is before promising a model that it can have it:

```bash
apt-cache policy python3.11          # candidate version, and where it comes from
python3.11 --version                 # after installing
ls /usr/bin/python3.*                # what this machine has now
```


#### Why deadsnakes, and what the alternatives cost

There are four ways to get a python that Ubuntu does not ship, and researchers arrive here with strong habits about which one is obvious. It is worth writing down why this deployment picked the one it did, so that changing it later is a decision rather than a reflex.

| | Install cost | Who ships the security fix | Portability | Exact patch pinning |
| --- | --- | --- | --- | --- |
| **deadsnakes** | seconds, `apt` | `apt`, against the system OpenSSL | Ubuntu only, and only series they build | no — you get their build of the series |
| Standalone build | seconds, a tarball | upstream rebuilds, bundled OpenSSL | any Linux, no root needed | yes |
| Source build | 10–30 min per version per machine | you, by rebuilding | any Unix, no root needed | yes |
| conda | minutes, and gigabytes | the channel's bundled stack | any OS, no root needed | yes |

The axis that actually separates them is the second column: **who hands you an OpenSSL fix, and whether you have to remember to ask.** deadsnakes links against the system OpenSSL, so the same `apt upgrade` that patches nginx patches python's TLS. Everything else bundles its own, which means a CVE is fixed when you notice it and re-run an install. This machine is published to the internet, is meant to be low-touch, and is otherwise entirely apt-managed — nginx, RabbitMQ, the MinIO `.deb`. One update mechanism covering the interpreter too is what deadsnakes is being bought for, and it is the whole of the argument.

The counter-argument, which is real: deadsnakes is a volunteer PPA that states plainly it makes no guarantee of timely security updates, and it is useless anywhere that is not Ubuntu. If this deployment ever needs one recipe that also works on a compute cluster or a non-Ubuntu host, that is the point at which to switch everything to standalone builds and accept watching for rebuilds yourself.

**Do not reach for source builds.** They cost half an hour each and are the only option here that can fail silently: if `libssl-dev`, `libffi-dev`, `libsqlite3-dev`, `liblzma-dev` and friends are not installed first, `make` *succeeds* and produces a python with no `ssl`, no `ctypes`, no `sqlite3`. That surfaces weeks later as a `pip` that cannot do TLS. CPython 3.12 and newer print a missing-module summary at the end of the build, which helps only if it is read. A plain `./configure && make` also skips profile-guided optimization, so the interpreter it produces is measurably *slower* than the prebuilt tarball you could have downloaded in a second — matching it means `--enable-optimizations` and roughly triple the build time. pyenv is this same approach with nicer ergonomics and the same two problems.

**Do not bring conda.** It is the habit most likely to walk in with whoever inherits this, and it earns its weight for a real problem this deployment does not have: pinning *non-python* dependencies — CUDA toolkits, GDAL, ffmpeg — as part of an environment. Musibot's contract with a *Model* is that the model is pip-installable, and Zeus gets its CUDA from TensorFlow's own wheels. Conda here buys a second package ecosystem to reason about, gigabytes per environment, a second place for CVEs to live, and the well-known sharp edge of mixing `conda install` and `pip install` in one environment. It buys nothing back.

Its licensing is *not* the reason to avoid it, and it is worth saying so rather than leaving a rumour in place: Anaconda's [academic policy](https://www.anaconda.com/legal/terms/academic) exempts accredited universities from the 200-employee threshold for teaching, learning and research, so a university lab using it is fine. The clause worth knowing is the other one — a paid licence *is* required for embedding, mirroring, or providing third parties access to their products, which is a question a publicly published service can eventually raise in a way a research workstation never does. Miniforge with conda-forge avoids it entirely. Neither is a reason to introduce conda where nothing needs it.


#### When deadsnakes cannot supply it

For anything outside 3.7–3.13, or when a model pins an exact patch release rather than whatever the PPA's series is at, install a **prebuilt standalone CPython** rather than compiling one. These are the same artifacts `uv` downloads, and they are ordinary tarballs — reaching for them costs no new tooling:

```bash
# from https://github.com/astral-sh/python-build-standalone/releases
sudo mkdir -p /opt/python/3.9.18
sudo tar xzf cpython-3.9.18+*-x86_64-unknown-linux-gnu-install_only.tar.gz \
    -C /opt/python/3.9.18 --strip-components=1

/opt/python/3.9.18/bin/python3.9 --version
```

That leaves `/opt/python/<version>/bin/python3.X`, which a venv or a `MUSIBOT_MODEL_COMMAND` names by absolute path like any other interpreter. They are profile-optimized and cannot have missing modules, so this is strictly better than building the same version by hand.

[uv](https://docs.astral.sh/uv/) will manage the same builds for you if you would rather it did. Give it a directory the service account can actually read — the units set `ProtectHome=yes`, so an interpreter left under someone's home is unusable by `musibot`:

```bash
sudo UV_PYTHON_INSTALL_DIR=/opt/python uv python install 3.9.18
```

If you nonetheless build from source, use **`make altinstall`** and never `make install`: the latter installs a bare `python3` into `/usr/local/bin` and shadows the system one for every user on the machine.


#### Two ways to break the machine

Unlike the choices above, these are not trade-offs.

**Do not repoint `python3`.** No `update-alternatives`, no symlink into `/usr/bin`. Ubuntu's own tooling — `apt` itself included — runs on the system python, and repointing it to satisfy a model is how a machine becomes unrecoverable. Every venv here names its interpreter explicitly for this reason, and a *Worker Head* launches its *Model* by absolute path for the same one.

**Do not `pip install` into an interpreter, only into a venv.** Ubuntu marks its pythons externally-managed and pip refuses, which is correct and worth not working around. Every python package in this deployment lives in a virtual environment that belongs to exactly one service.

When the last model needing a version is gone, `sudo apt remove python3.X` is safe — but note that a venv holds a symlink to its interpreter rather than a copy, so removing a version breaks every venv built on it. That failure appears at the next restart, not at the moment of removal.


## 1. The machine account

One unprivileged system account owns everything Musibot runs. It has no shell and no password: nothing about this deployment involves logging in as it.

```bash
sudo useradd --system --home-dir /opt/musibot --shell /usr/sbin/nologin musibot

sudo mkdir -p /opt/musibot/{api,workers,models}
sudo chown musibot:musibot /opt/musibot
sudo chown -R musibot:musibot /opt/musibot/{api,workers,models}

# Configuration is readable by the service and writable only by root. It holds
# credentials, so it is not world-readable.
sudo mkdir -p /etc/musibot
sudo chown root:musibot /etc/musibot
sudo chmod 0750 /etc/musibot
```


## 2. RabbitMQ

Straight from the archive:

```bash
sudo apt install -y rabbitmq-server
```

26.04 ships RabbitMQ **4.0.5**, which is the major version Musibot is developed against and the one the [local stack](../deploy/README.md) runs — so no third-party apt repository is needed here, and the deployment is not the place a different broker version first appears. That matters more than it sounds: RabbitMQ 4 refuses to declare a transient non-exclusive queue at all, which is why Musibot's shared work queues are declared `durable` (see [RabbitMQ exchanges and messages](rabbitmq-exchanges-and-messages.md)). Durable queues, not durable messages — everything is still published non-persistent, so a broker restart discards in-flight work exactly as the design intends.

Should a future release lag behind, Team RabbitMQ's [installation page](https://www.rabbitmq.com/docs/install-debian) has the apt repository to add. Nothing else in this section changes.

One configuration drop-in, the same file the local stack uses: it publishes the management UI under the deployment's path prefix, which is the path the UI builds its own links from and therefore the path it expects to be asked for. Everything else about the broker is left at its defaults.

```bash
sudo mkdir -p /etc/rabbitmq/conf.d
sudo cp /opt/musibot/repo/deploy/rabbitmq/20-musibot.conf /etc/rabbitmq/conf.d/

sudo rabbitmq-plugins enable rabbitmq_management
sudo systemctl restart rabbitmq-server
```

Then the accounts. Two of them, because the service and the human need different things — the service needs to publish and consume and nothing else, and separating them means a rotated service credential does not lock an operator out of the UI:

```bash
# The service account every Musibot process connects as. The password is
# omitted deliberately — rabbitmqctl then prompts for it.
sudo rabbitmqctl add_user musibot
sudo rabbitmqctl set_permissions -p / musibot '.*' '.*' '.*'

# An operator, for the management UI at /musibot/rabbitmq/.
sudo rabbitmqctl add_user admin
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl set_permissions -p / admin '.*' '.*' '.*'

sudo rabbitmqctl delete_user guest
```

This is the first place a secret is typed, so it is worth setting the habit here: **passwords are not passed as command line arguments.** A password in `argv` is written to `~/.bash_history` and is readable in `/proc/<pid>/cmdline` by any other user for as long as the command runs. Neither is dramatic on a single-administrator VM, but the history file persists indefinitely, and both tools used on this page — `rabbitmqctl` and `mc` — prompt when the credential is simply left off, so avoiding it costs nothing. When something genuinely has to take a secret inline, `set +o history` before it and `set -o history` after is the fallback.

Choose these passwords with a generator rather than by hand, and keep them to letters and digits. Not for entropy — a generated password has plenty — but because both end up inside URLs and dotenv files later, where a `@`, `#` or `%` becomes a parsing problem at the least convenient moment.

The `admin` password is one to choose properly: that UI is published under the public prefix and its login is the only thing in front of it. `guest` cannot connect from anywhere but the machine itself, which RabbitMQ enforces by default, so deleting it changes little — it is gone because a default credential on a machine is one fewer thing to think about, not because it was a way in.


## 3. MinIO

**Read this before installing it.** The MinIO project archived its repository in April 2026 and no longer maintains the community server; the last community binary is `RELEASE.2025-09-07T16-13-09Z`, and the administrative Console was already stripped down to a bare object browser in mid-2025. Nothing about that blocks this deployment — it is a working S3 server and `mc` does everything the Console used to — but it does mean the version below is the last one there will be, and that replacing MinIO is a decision this deployment will have to make rather than one it can defer forever. It is recorded in [Rough edges](rough-edges.md).

```bash
curl -fLO https://dl.min.io/server/minio/release/linux-amd64/archive/minio_20250907161309.0.0_amd64.deb
sudo dpkg -i minio_20250907161309.0.0_amd64.deb

sudo useradd --system --no-create-home --shell /usr/sbin/nologin minio-user 2>/dev/null || true
sudo mkdir -p /var/lib/minio
sudo chown minio-user:minio-user /var/lib/minio

sudo install -m 0600 /opt/musibot/repo/deploy/minio/minio.env.example /etc/default/minio
sudo nano /etc/default/minio          # fill in the root credentials and the public host

sudo systemctl enable --now minio
```

Now the bucket and the credential Musibot uses. The bucket is named `musibot` and every key lives under `s3/` — the arrangement that lets a presigned URL survive being served from a path prefix, and the one thing here that is not a free choice ([Deployment](deployment.md) sets out why there is no alternative):

```bash
curl -fLo mc https://dl.min.io/client/mc/release/linux-amd64/mc
chmod +x mc && sudo mv mc /usr/local/bin/

# Keys omitted, so mc prompts for them rather than taking them from argv.
# These are MinIO's own superuser credentials — MINIO_ROOT_USER and
# MINIO_ROOT_PASSWORD out of /etc/default/minio, which have nothing to do with
# the unix root account despite the name.
mc alias set musibot-local http://127.0.0.1:9000
#   Enter Access Key: musibot-admin
#   Enter Secret Key: ***

mc mb musibot-local/musibot

# A service account, so that the services do not hold the superuser
# credentials. Neither argument is its name: `musibot-local` is the alias set
# above, and `musibot-admin` is the existing user it is created *under*.
mc admin user svcacct add musibot-local musibot-admin
#   Access Key: 5HQ2M8TF1PGKX0WBNZ7A
#   Secret Key: n4Kd...
```

A service account has no name of its own — **its identity is the generated access key**, and that is what the two lines it prints are. Keep the pair: it goes into `api.env` and into every worker's environment file, as `MUSIBOT_S3_ACCESS_KEY` and `MUSIBOT_S3_SECRET_KEY`. Pass `--access-key` if you would rather it were something recognisable than a random string.

`mc alias set` writes the superuser credentials to `~/.mc/config.json` in plaintext — a root-owned file, which is fine here, but worth knowing exists.

The `api` service refuses to start if the bucket does not exist, since it wipes its key prefix clean at startup and cannot do that to a bucket that is not there.

Note that a password with `@`, `:` or `/` in it has to be percent-encoded there, which is the second reason the section above suggests keeping generated passwords alphanumeric.


## 4. The Web API

```bash
sudo -u musibot python3.12 -m venv /opt/musibot/api/venv
sudo -u musibot /opt/musibot/api/venv/bin/pip install \
    'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
    'musibot-api @ git+https://github.com/OmniOMR/musibot.git@api/v0.1.0#subdirectory=components/api'
```

**`musibot-core` has to be named explicitly**, every time, in the same command. It is a dependency of `musibot-api` but is on no package index, so pip cannot resolve it on its own; given both, pip uses the one you supplied. Omitting it fails clearly rather than subtly — `Could not find a version that satisfies the requirement musibot-core>=0.1.0` — which is the good outcome. See [Versioning and releases](versioning-and-releases.md).

The tokens the *Library* users authenticate with, as a JSON object mapping token to the user it identifies:

```bash
printf '{\n  "%s": "alice"\n}\n' "$(openssl rand -hex 24)" | sudo tee /etc/musibot/api-tokens.json
sudo chown root:musibot /etc/musibot/api-tokens.json
sudo chmod 0640 /etc/musibot/api-tokens.json
```

Without this file the service comes up accepting the built-in development token `secret` and warns loudly that it is doing so. That warning is the one line worth grepping for after any configuration change.

Then the configuration and the unit:

```bash
sudo install -o root -g musibot -m 0640 \
    /opt/musibot/repo/deploy/systemd/api.env.example /etc/musibot/api.env
sudo nano /etc/musibot/api.env        # RabbitMQ and MinIO credentials, the public URL

sudo cp /opt/musibot/repo/deploy/systemd/musibot-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now musibot-api

sudo journalctl -u musibot-api -f
```

The first thing it logs is its effective configuration with the secrets masked, which is the single most useful line in this log when a service turns out to be talking to the wrong host. The second is that it wiped its MinIO prefix, which it does on every start.

```bash
curl -s -H "Authorization: Bearer {aliceToken}" http://127.0.0.1:8080/pipelines
# {"pipelines":[]}   ← no Workers yet; that comes in section 7
```


## 5. The Web UI

The bundle is built on your workstation and copied here. Nothing about building it needs to happen on the VM, and keeping the Node toolchain off the VM is worth the copy.

The public origin is baked into the bundle at build time — `index.html` carries absolute canonical, Open Graph and Twitter URLs, and the default is a deliberately obvious placeholder so that a forgotten variable does not quietly publish link previews pointing at `musibot.example.org`:

```bash
# on your workstation, in components/web-ui
npm ci
MUSIBOT_PUBLIC_ORIGIN=https://quest.ms.mff.cuni.cz npm run build
```

`MUSIBOT_BASE_PATH` defaults to `/musibot/`, which is right here; it is the other half of the same address and only needs setting if the prefix ever changes.

Publish by unpacking beside the current release and swapping a symlink, rather than by copying over the files nginx is serving. A bundle half-replaced in place serves an `index.html` naming asset hashes that are not there yet, and the symlink swap is atomic:

```bash
stamp=$(date +%Y%m%d-%H%M%S)
rsync -a --delete dist/ deploy-host:/tmp/web-ui-$stamp/

# on the VM
sudo mkdir -p /var/www/musibot/releases
sudo mv /tmp/web-ui-$stamp /var/www/musibot/releases/$stamp
sudo chown -R www-data:www-data /var/www/musibot/releases/$stamp
sudo ln -sfn /var/www/musibot/releases/$stamp /var/www/musibot/current
```

No service restarts. nginx follows the symlink per request, `index.html` is served `no-cache` so a browser picks up the new bundle on its next load, and the fingerprinted assets under `assets/` are immutable, so the old release keeps serving anyone mid-session. Keep a few releases around — rolling back is re-pointing the symlink.


## 6. nginx

The configuration is a template, because the deployment addresses differ between this VM and the local stack and nothing else does. Render it, do not copy it:

```bash
sudo install -o root -g root -m 0644 \
    /opt/musibot/repo/deploy/nginx/nginx.env.example /etc/musibot/nginx.env
sudo nano /etc/musibot/nginx.env      # the public host, if it is not quest.ms.mff.cuni.cz

sudo /opt/musibot/repo/deploy/nginx/render-config.sh /etc/musibot/nginx.env \
    | sudo tee /etc/nginx/sites-available/musibot.conf > /dev/null

sudo ln -sfn /etc/nginx/sites-available/musibot.conf /etc/nginx/sites-enabled/musibot.conf
sudo rm -f /etc/nginx/sites-enabled/default        # or it also answers on :80

sudo nginx -t && sudo systemctl reload nginx
```

`render-config.sh` exists because `envsubst` on its own would eat nginx's variables too — `$host`, `$remote_addr`, `$connection_upgrade` — and the result is a configuration nginx still accepts, which then forwards an empty `Host` header. The script substitutes only the names the template actually mentions, and refuses to render if any of them is unset. Its header explains the trap in full; it is worth reading once before editing the template.

The instance should now answer, and this is the first point at which the whole public topology is exercised:

```bash
curl -sI http://127.0.0.1/                    # the Web UI
curl -s -H "Authorization: Bearer {aliceToken}" http://127.0.0.1/api/pipelines       # the Web API, prefix stripped by the proxy
```

Browse `https://quest.ms.mff.cuni.cz/musibot/` and check all five addresses from [Deployment](deployment.md): the UI, `api/docs`, the MinIO Console at `minio/` (styled, not a wall of unstyled text), and the RabbitMQ UI at `rabbitmq/`.


## 7. A worker

A *Worker* is a *Worker Head* plus exactly one *Model*. One templated unit serves all of them — `musibot-worker@<instance>` — and everything that differs between models is in `/etc/musibot/worker-<instance>.env`, including which model it runs.

```bash
sudo cp /opt/musibot/repo/deploy/systemd/musibot-worker@.service /etc/systemd/system/
sudo systemctl daemon-reload
```


### Naming a worker instance

The instance name is a label for whoever operates this machine, and nothing else. **It is not the model's identity**: what a *Pipeline* pins is the name and version the *Model* announces out of its own weights, so renaming an instance changes nothing any *User* can see. It does, however, become a filename (`/etc/musibot/worker-<instance>.env`), a directory (`/var/lib/musibot/<instance>/`) and a venv path, so it has to be unique on the machine and stick to letters, digits, `-`, `_` and `.`.

**Name it after the snapshot it serves, not after the model's code.** `zeus` names a repository, and a repository can serve any number of snapshots that are, to Musibot, entirely different models. The snapshot is the thing that actually varies between one worker and the next, and it is the one line of the environment file that matters. Prefix the architecture when the snapshot's own name does not already imply it, since that is what tells you at a glance which subdivision the worker reads:

```
musibot-worker@solo26-zod-bw-auth-ft-2026-07-20
                └────┘ └───────────────────────┘
           architecture          snapshot
```

Long, and worth it. These names are typed rarely, tab-complete, and glob usefully — `systemctl list-units 'musibot-worker@solo26-*'` is a question you will want to ask.

The payoff is in how a snapshot is replaced. Because the new snapshot is a *different instance* rather than an edit to an existing one, a changeover is:

```bash
systemctl enable --now musibot-worker@solo26-<new-snapshot>   # both now running
journalctl -u musibot-worker@solo26-<new-snapshot> -f         # watch it announce
systemctl disable --now musibot-worker@solo26-<old-snapshot>  # then retire the old
```

No window in which nothing serves, and rolling back is starting the old instance again — it is still installed, still configured, and its snapshot is still on disk. An instance named `zeus` cannot do this: swapping its snapshot is an edit-and-restart, with a gap, and the rollback is editing the file back from memory.

Each instance gets its own head virtual environment under `/opt/musibot/workers/<instance>/`, which costs about twenty seconds and fifty megabytes and makes each deployment self-contained. Symlink that directory to a shared one if you would rather two instances share a head installation.

A model with no snapshot to speak of is named after itself — `hello` below, since there is only ever one `hello-model`.

**Deploy `hello-model` first.** It transcribes nothing, has no dependencies and starts instantly, so it separates "the messaging, storage and discovery all work" from "the model works" — which are otherwise diagnosed together, through a TensorFlow log:

```bash
sudo -u musibot python3.12 -m venv /opt/musibot/workers/hello/venv
sudo -u musibot /opt/musibot/workers/hello/venv/bin/pip install \
    'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
    'musibot-worker-head @ git+https://github.com/OmniOMR/musibot.git@worker-head/v0.1.0#subdirectory=components/worker-head' \
    'musibot-hello-model @ git+https://github.com/OmniOMR/musibot.git@main#subdirectory=components/models/hello-model'

sudo install -o root -g musibot -m 0640 \
    /opt/musibot/repo/deploy/systemd/worker.env.example /etc/musibot/worker-hello.env
sudo nano /etc/musibot/worker-hello.env
```

Two lines in that file are the worker's own, and the rest is the same RabbitMQ and MinIO configuration the `api` service has:

```ini
MUSIBOT_MODEL_COMMAND="/opt/musibot/workers/hello/venv/bin/python -m hello_model"
MUSIBOT_MODEL_READY_TIMEOUT_SECONDS=300
```

Note what is *not* there: the pages directory. The unit derives it from the instance name, so it cannot end up pointing into another worker's state. Setting it here would silently override the unit — `EnvironmentFile=` beats `Environment=` whichever order they appear in — and `systemctl show -p Environment` would not reveal it, since that reports only the unit's own line and never the file's contents. The service logs its effective configuration at startup; that is what to read.

This is the **one-venv** case: `hello-model` has no dependencies and runs on any modern python, so it shares the head's virtual environment. A model that cannot — one pinned to an older python, or with conflicting pins — gets a venv of its own and is launched by absolute path across the IPC boundary. That is [Zeus](../components/models/zeus/README.md), and it is the case that justifies the boundary being IPC at all.

```bash
sudo systemctl enable --now musibot-worker@hello
journalctl -u musibot-worker@hello -f

curl -s http://127.0.0.1:8080/pipelines
# hello-model 1.0.0, 1 instance
```

A model appearing in that listing is the *Worker* announcing itself; a model disappearing from it is a heartbeat that stopped. Both are [discovery](discovery.md), and neither involves any configuration on the `api` service's side.

**Then the real model.** [components/models/zeus](../components/models/zeus/README.md) is the worked case: two virtual environments, a snapshot to download, and an identity that comes out of the snapshot rather than out of the configuration.


## 8. Checking the whole thing

From a machine that is not the VM, against the public URL, with a token from `api-tokens.json`:

```python
from pathlib import Path
from musibot.client import MusibotClient

with MusibotClient(
    musibot_api_url="https://quest.ms.mff.cuni.cz/musibot/api",
    api_token="THE-TOKEN",
) as client:
    for pipeline in client.list_pipelines().pipelines:
        print(pipeline.name, pipeline.version, pipeline.instances)

    output = client.process_page(
        input={"image.jpg": Path("scan.jpg").read_bytes()},
        pipeline=("hello-model", "1.0.0"),
        output={"transcription.musicxml"},
    )
    print(output["transcription.musicxml"][:200])
```

`hello-model` writes a one-measure MusicXML whose lyric reads `Hello World! (N bytes)`, and that byte count is the point of running it: it is proof the *File* travelled from here through MinIO into the *Worker's* local mirror before the model ran. If it comes back with the right number, then presigned URLs, the bucket layout, the prefix reconstruction and the whole message path are all correct, and any remaining problem is a model's.

Zeus is the same call with different names on everything, because its *Signature* reads a staff rather than a page — the file has to be named where a staff lives, and the transcription comes back beside it:

```python
output = client.process_page(
    input={"Staves/1/image.jpg": Path("staff-crop.jpg").read_bytes()},
    pipeline=("zod-bw-auth-ft", "2026-07-20-153411-e40"),
    output={"Staves/1/transcription.musicxml"},
)
```

Naming that input `image.jpg` instead is refused by the `api` service before it reaches a *Worker*, with a message saying so — which is the check that stops someone running Zeus over a whole page and believing the result.

Then the Web UI, in a browser, at `https://quest.ms.mff.cuni.cz/musibot/` — which exercises the one thing the client does not: the public session tier. If the landing page reports that the instance offers no public access, `public_access_enabled` is still false.


## Updating when the source changes

Each component updates on its own, which is what the per-component versioning is for. Nothing here requires stopping anything else.

| Changed | Do | Costs |
| --- | --- | --- |
| `api` or `core` | reinstall in `/opt/musibot/api/venv`, `systemctl restart musibot-api` | **all state**, see below |
| `worker-head` or `core` | reinstall in that worker's venv, `systemctl restart musibot-worker@<instance>` | executions that worker is running |
| a *Model* | reinstall in the model's venv, restart its worker | as above |
| a *Model*'s weights | edit `MUSIBOT_MODEL_COMMAND`, restart its worker | the old model version disappears from the registry |
| `web-ui` | build, rsync, swap the symlink | nothing |
| nginx config, unit files | `git pull` in `/opt/musibot/repo`, re-render or re-copy, reload | nothing |

**A change to `core` is the one that is not per-component.** `core` is the wire contract — the message protocol and the page model — so the `api` service and every *Worker Head*, on this VM and on any other, have to be moved together. Each lives in its own virtual environment, so "together" is a thing you do rather than a thing the machine does for you: update every environment in one pass, then restart everything, `api` last.

Nothing enforces this today. A *Worker Head* announces its own version and the `api` service does not even read it, and `core`'s version is not announced at all, so a *Worker* left behind on an older `core` is not refused and not reported — it simply misbehaves in whatever way the protocol change implies. It is recorded in [Rough edges](rough-edges.md); until it is closed, the discipline above is the whole of the mechanism, which is a reason to update `core` deliberately and never incidentally.

Reinstalling is a plain `pip install` of the newer ref — no `--force-reinstall`, no `-U`:

```bash
sudo -u musibot /opt/musibot/api/venv/bin/pip install \
    'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.2.0#subdirectory=components/core' \
    'musibot-api @ git+https://github.com/OmniOMR/musibot.git@api/v0.2.0#subdirectory=components/api'

sudo -u musibot /opt/musibot/api/venv/bin/pip show musibot-api | grep Version
sudo systemctl restart musibot-api
```

That works because every component's version is derived from the git tags, so every commit builds as a distinct version and pip sees a version change. Were the version written down by hand and left unchanged during a development cycle, pip would do **nothing, silently** — including under `-U` — and you would restart the service into the code you already had. That trap is the whole reason for the versioning scheme; [Versioning and releases](versioning-and-releases.md) has the table. The `pip show` line above is how you confirm which side of it you are on.

Rolling back is the same command with the older tag. pip syncs to whatever the URL builds, downgrade included.

To follow `main` rather than a release, put a branch name or a commit SHA where the tag goes. Distinct versions still fall out, so the update behaviour is unchanged.


### What restarting the Web API costs

All of it. The service holds every *MusicorpusPage*, *Public Session* and *Pipeline Execution* in memory, and it wipes its MinIO key prefix on startup — deliberately, because the state is ephemeral by design and stale objects must not be mistaken for a live page's *Files* (see [User request dataflow](user-request-dataflow.md)). After a restart:

- every page is gone, and *Users* holding one get `404`
- every public session is gone; the Web UI says the session expired and offers a reload
- executions in flight are abandoned, and a *Worker* still running one writes into a folder nothing tracks any more

So restarting this unit is an announced act. Update it during a quiet period, and when updating several things at once do them in this order — Web UI first (it costs nothing), then the workers, then the `api` service last, so that its startup wipe also clears whatever the restarted workers left behind.

Restarting a *Worker* is much cheaper: it says goodbye to the registry, shuts its model down through the IPC protocol rather than being killed, and disappears from `GET /pipelines` within a heartbeat. Only the executions it was actually running are lost, and those fail as timeouts on the `api` service's side. With several workers behind one model, restarting them one at a time is invisible to *Users*.


### When the configuration changes

Editing `/etc/musibot/*.env` needs a restart of whatever reads it, and nothing else — systemd re-reads `EnvironmentFile` on start. The nginx template is the exception, because the rendered file is what nginx has:

```bash
cd /opt/musibot/repo && sudo git pull
sudo /opt/musibot/repo/deploy/nginx/render-config.sh /etc/musibot/nginx.env \
    | sudo tee /etc/nginx/sites-available/musibot.conf > /dev/null
sudo nginx -t && sudo systemctl reload nginx
```

Never edit `/etc/nginx/sites-available/musibot.conf` directly — it is generated, it says so in its first line, and the next render silently discards the change. Edit `deploy/nginx/musibot.conf.template` in the repository, where the local stack will also exercise it.

Unit files changed in the repository need copying and a `daemon-reload`:

```bash
sudo cp /opt/musibot/repo/deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart musibot-api                 # only if that unit changed
```


## Operating it

Everything logs to the journal, and every Musibot process logs its effective configuration at startup with the secrets masked:

```bash
journalctl -u musibot-api -f
journalctl -u musibot-worker@solo26-zod-bw-auth-ft-2026-07-20 -f
journalctl -u minio -u rabbitmq-server --since '10 min ago'
```

A *Model*'s own stdout and stderr are captured by its *Worker Head*, appear in that worker's journal, and are published onto `musibot.logs` for the `api` service to stream to whoever is watching that page. So a failed transcription explains itself in the *Web UI*; the journal is where to look for what was printed while nobody had the page open, a model loading its weights included.


### When something is wrong

| What you see | Almost always |
| --- | --- |
| `SignatureDoesNotMatch` on every download | `MUSIBOT_PUBLIC_HOST` in `nginx.env` is not byte-for-byte the `Host` a browser sends, or `MUSIBOT_S3_PUBLIC_URL` carries a path instead of just the origin. The signature covers both. |
| `GET /pipelines` is empty | No *Worker* has announced. Check its journal: a model still loading its weights has not announced yet, and one that failed to start says so there. |
| A pipeline is listed with `instances: 0` | Something announced moments before going away. Its worker is crash-looping — `systemctl status musibot-worker@<instance>`. |
| Executions time out with a worker running | The worker is announcing a *different* model version from the one being requested. The version comes from the model, so read it out of the worker's journal rather than assuming. |
| The MinIO Console renders unstyled | The `/minio/` location is forwarding the prefix instead of stripping it, or `MINIO_BROWSER_REDIRECT_URL` is wrong. The Console answers unknown paths with its SPA fallback, so its assets come back as `200 text/html`. |
| The RabbitMQ UI is a 404 | The opposite mistake: it expects the *whole* public path, which nginx reconstructs and `management.path_prefix` must agree with. |
| `413` on upload | `client_max_body_size` in the template — and the university proxy has one of its own, which we do not control and which is the lower of the two when it is. |
| `502` from nginx | `musibot-api` is not running, or is bound somewhere other than `MUSIBOT_API_UPSTREAM`. |
| A deep Web UI link 404s on reload | The bundle is not where `MUSIBOT_WEB_ROOT` points — check the `current` symlink. The SPA fallback in the template handles the routing itself. |
| `Could not find a version that satisfies musibot-core` | The explicit `musibot-core @ git+...` was left out of a `pip install`. It is required in every one of them. |
| The log warns about the token `secret` | `MUSIBOT_API_TOKENS_FILE` is unset or the file is unreadable by the `musibot` user. The instance is accepting a publicly known token. |
