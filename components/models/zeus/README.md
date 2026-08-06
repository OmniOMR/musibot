# zeus

Zeus is deployed here but does not live here. Its code, its training and its own Musibot documentation are at [github.com/OmniOMR/zeus](https://github.com/OmniOMR/zeus); this folder holds how *our* instance runs it — the environment file the systemd unit reads, and the steps that produce it.


## Why a folder with no code in it

Musibot is designed so that deploying a *Model* never touches this repository, and that stays true: Zeus is `pip install`ed from a git link and reached only over the [worker IPC](../../../docs/worker-ipc.md), so nothing here is required for it to run. What is here is the other half — the deployment of the one instance we operate, which has to be written down somewhere and is more useful in one place than scattered across each model's repository.

The division that makes both true: **Zeus's repository documents deploying Zeus in general** (`docs/musibot-model.md` there — read it, it is the reference for what Zeus announces and why), while **this folder documents deploying it onto our VM under systemd**. Someone running Musibot under Kubernetes uses the former and none of the latter.


## What Zeus is, from Musibot's side

| | |
| --- | --- |
| Announces | `zod-bw-auth-ft` `2026-07-20-153411-e40` — from the snapshot, not from this configuration |
| Reads | `Staves/{staff}/image.jpg` — one staff crop per execution |
| Writes | `Staves/{staff}/transcription.musicxml` and `Staves/{staff}/transcription.lmx` |
| Batching | Announced, and not yet exercised — see below |
| Python | **3.10 only**, which is why this is the two-virtual-environment case |

The name, the version and what it reads all come out of the snapshot's `model_options.yaml` rather than from a command line flag, because each is a contract that fails silently when it is wrong: a wrong subdivision transcribes staff crops as grandstaves and returns confident nonsense, and a wrong identity merges two different models into one registry entry. Which snapshot is deployed is therefore the whole of what this deployment decides. See [Model snapshots](https://github.com/OmniOMR/zeus/blob/main/docs/model-snapshots.md).

**Zeus reads staff crops, not pages.** Its *ImplicitPipeline* is exactly its signature, so a *User* runs it by uploading a single staff — which the Web UI does correctly, uploading to `Staves/1/image.jpg` for a pipeline that asks for one. Handing it a whole page scan is not refused, because a page image satisfies the signature just as well; Zeus transcribes it as though it were one staff. Turning a page into staff crops is a staff detector's job, and running the two in sequence is an *Orchestrator*'s — neither of which is deployed yet.


## Deploying it

The steps that surround this — the VM, RabbitMQ, MinIO, the `musibot-worker@.service` template — are in [Deploying onto a VM](../../../docs/deploying-to-a-vm.md). This is the Zeus-specific part of section *A worker*.

Two virtual environments, because Zeus needs python 3.10 (TensorFlow 2.12 has no wheels for anything newer) and a *Worker Head* depends on `musibot-core`, which needs 3.11 or newer. They cannot share an environment even in principle, which is the case the IPC boundary exists for.

Ubuntu 26.04's own python is 3.14, so *neither* half of this uses it: Zeus needs 3.10, and the worker head runs on the 3.12 the rest of Musibot is developed on. Both come from deadsnakes — see [Python versions on this machine](../../../docs/deploying-to-a-vm.md#python-versions-on-this-machine), which is also where to start when the *next* model needs a version neither of these is.

The two halves also land in differently-indexed places, and it is worth knowing which is which before reading the paths below. **Zeus is installed once**, at `/opt/musibot/models/zeus/`, and every worker running Zeus shares it — that directory is named after the codebase, so it does not carry an instance name and does not change when a snapshot does. **The head is per instance**, at `/opt/musibot/workers/<instance>/`, named after the snapshot it serves. Two workers on two snapshots therefore have two head directories and one Zeus.

```bash
# the PPA is already added if the VM guide was followed; adding it twice is fine
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv

# Zeus, on python 3.10
sudo -u musibot python3.10 -m venv /opt/musibot/models/zeus/venv
sudo -u musibot /opt/musibot/models/zeus/venv/bin/pip install \
    'zeus @ git+https://github.com/OmniOMR/zeus.git@main'

# the worker head, on 3.12
sudo -u musibot python3.12 -m venv /opt/musibot/workers/solo26-zod-bw-auth-ft-2026-07-20/venv
sudo -u musibot /opt/musibot/workers/solo26-zod-bw-auth-ft-2026-07-20/venv/bin/pip install \
    'musibot-core @ git+https://github.com/OmniOMR/musibot.git@core/v0.1.0#subdirectory=components/core' \
    'musibot-worker-head @ git+https://github.com/OmniOMR/musibot.git@worker-head/v0.1.0#subdirectory=components/worker-head'
```

Replace `@main` with a release tag to pin one. Every Zeus commit builds as a distinct version, so a plain `pip install` of a newer commit replaces what is there.


### The snapshot

Weights are the model repository's business and are never committed here. The current solo-staff snapshots are published on the [ijdar releases page](https://github.com/Jirka-Mayer/ijdar/releases/tag/model-snapshots); the one this deployment runs is `zod-bw-auth-ft-2026-07-20` (trained on Dolores, fine-tuned on OmniOMR).

The snapshot is downloaded now, by hand, and not by the model when it starts — the unit gives a *Model* nothing writable but its pages directory precisely so that a model which tries to fetch something at runtime fails on its first execution rather than on the day the download is slow.

```bash
sudo -u musibot mkdir -p /opt/musibot/models/zeus/snapshots
cd /opt/musibot/models/zeus/snapshots
sudo -u musibot curl -LO https://github.com/Jirka-Mayer/ijdar/releases/download/model-snapshots/zod-bw-auth-ft-2026-07-20.model.model.tar.gz
sudo -u musibot tar xzf zod-bw-auth-ft-2026-07-20.model.model.tar.gz
sudo -u musibot mv zod-bw-auth-ft-2026-07-20.model.model zod-bw-auth-ft-2026-07-20.model
```

That last line is tidying up a doubled suffix in the published archive, and it is safe to do: the identity Zeus announces is read from `model_options.yaml` inside the folder, not from the folder's name.

This unpacks *beside* whatever is already in `snapshots/` rather than replacing it, which is the arrangement the whole naming scheme rests on: the new snapshot gets a worker of its own, both run for as long as the changeover takes, and the old one stays on disk to roll back to. Delete a snapshot when no worker has served it for a while, not when it is superseded.

**Check that file before serving a snapshot**, because it is the one thing that can be wrong without anything failing:

```bash
cat /opt/musibot/models/zeus/snapshots/zod-bw-auth-ft-2026-07-20.model/model_options.yaml
```

```yaml
input_subdivisions:
- Staves
musibot_model_name: zod-bw-auth-ft
musibot_model_version: 2026-07-20-153411-e40
```

Snapshots from before that file existed — the 2024 grandstaff models, for instance — do not have it, and every field then falls back: `Grandstaves`, `zeus`, and the folder's own name. The subdivision fallback is the dangerous one, since it is right for those 2024 models and wrong for any solo-staff snapshot that predates the file. Write the file in by hand rather than retraining.


### Configuration and the unit

The instance is named after the snapshot rather than after Zeus, for the reasons in [Naming a worker instance](../../../docs/deploying-to-a-vm.md#naming-a-worker-instance). It is long, so hold it in a variable:

```bash
instance=solo26-zod-bw-auth-ft-2026-07-20

sudo install -o root -g musibot -m 0640 \
    components/models/zeus/worker-zeus.env.example "/etc/musibot/worker-$instance.env"
sudo nano "/etc/musibot/worker-$instance.env"        # fill in the credentials

sudo systemctl enable --now "musibot-worker@$instance"
journalctl -u "musibot-worker@$instance" -f
```

A healthy start logs the configuration, then Zeus's own `zeus musibot: serving zod-bw-auth-ft 2026-07-20-153411-e40` and `zeus musibot: reads Staves` (the model's stdout is captured as its log), and then the head announcing itself to the registry. `GET /musibot/api/pipelines` should list the implicit pipeline within a heartbeat.

TensorFlow takes a while to load its weights, and the head announces nothing until the model has said `ready` — so a Worker that has not appeared yet is normal for the first half-minute and is exactly what `model_ready_timeout_seconds` bounds.


### Scaling it

A second *Worker* against the same snapshot needs nothing new installed. Both the head installation and the configuration can be the first one's, reached through symlinks:

```bash
instance=solo26-zod-bw-auth-ft-2026-07-20

sudo ln -s "/opt/musibot/workers/$instance"      "/opt/musibot/workers/${instance}_2"
sudo ln -s "/etc/musibot/worker-$instance.env"   "/etc/musibot/worker-${instance}_2.env"
sudo systemctl enable --now "musibot-worker@${instance}_2"
```

Nothing in that environment file is per-instance — the one thing that is, the pages directory, comes from the unit's `%i` — so sharing it is safe, and it means a credential rotated in one place reaches both. The two workers still get separate state directories, `/var/lib/musibot/${instance}` and `…_2`, because `StateDirectory=` is derived from the instance name.

They announce the same model name and version, which is precisely what Musibot reads as one model scaled horizontally.

Worth knowing before doing this on a CPU-only VM: TensorFlow sizes its thread pools to the whole machine, so two workers on one VM will each try to use every core and be slower than one. The environment file caps that — see the comments in it.


## Not yet exercised

**Batching.** Zeus advertises `supports_batching` and would put several staves through one forward pass, which is most of what makes inference fast. The *Worker Head* reads and announces that flag but never sends an `execute-batch` yet, so today every staff is its own forward pass. Nothing is wrong; there is throughput on the table. See the worker head's [Not yet implemented](../../worker-head/README.md#not-yet-implemented).

**The model's log.** Zeus's stdout — including the per-execution failures written for a human to read — is captured by the head and goes to the head's own journal, not onto `musibot.logs` where the `api` service could stream it to the *Web UI*. So `journalctl -u musibot-worker@solo26-zod-bw-auth-ft-2026-07-20` is where a failed transcription is explained today.
