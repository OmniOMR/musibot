"""Import every module of an installed Musibot, in a production-shaped venv.

This is the check that `api/v0.2.0` and `worker-head/v0.2.0` needed and did not
have. Both imported `S3Client` from `mypy_boto3_s3` at module scope — a package
that comes from `boto3-stubs[s3]`, which every component declares under `dev`
and none declares as a runtime dependency. So both crashed on startup in a
deployed virtual environment, and only there: a development environment
installs the dev extra, so the whole of both test suites, ruff and mypy ran
against code that could not start, and all of them passed.

Nothing that runs inside a development environment can catch that, because the
fault *is* the difference between the two environments. Hence a job that builds
the other one and does the one thing a deployment does first.

It walks every module rather than just the entrypoints. A dev-only import on a
path reached later — inside a request handler, or when a *Model* first uploads
something — is worse than one at startup, not better: it turns a crash-loop
that is obvious in the first journal line into a failure some hours in.

Run it locally the same way CI does:

    python -m venv /tmp/prodcheck
    /tmp/prodcheck/bin/pip install ./components/core ./components/api \\
        ./components/worker-head ./components/python-client
    /tmp/prodcheck/bin/python .github/scripts/import_every_module.py
"""

import importlib
import importlib.metadata
import pkgutil
import sys

# If any of these is importable, the environment is not the one we meant to
# test, and a green result here would mean nothing. Checked rather than assumed
# because the failure mode is silent: adding `[dev]` to the install line in the
# workflow would weaken this job to nothing without changing its output.
DEV_ONLY = ["pytest", "ruff", "mypy", "boto3-stubs", "mypy-boto3-s3"]


def refuse_a_development_environment() -> None:
    present = []
    for distribution in DEV_ONLY:
        try:
            importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            continue
        present.append(distribution)

    if present:
        sys.exit(
            f"This environment has {', '.join(present)} installed, so it is a development "
            f"environment and proves nothing about a deployed one. Install the components "
            f"without their `dev` extra."
        )


def import_everything() -> None:
    import musibot

    failures = []
    imported = 0

    for module in pkgutil.walk_packages(musibot.__path__, "musibot."):
        # `__main__` runs the service when imported under its own name, and is
        # covered by the console script check in the workflow instead.
        if module.name.rsplit(".", 1)[-1] == "__main__":
            continue

        imported += 1
        try:
            importlib.import_module(module.name)
        except Exception as exception:  # noqa: BLE001 — every failure is a finding
            failures.append(f"  {module.name}\n    {type(exception).__name__}: {exception}")

    if failures:
        sys.exit(
            f"{len(failures)} of {imported} modules could not be imported with only their "
            f"runtime dependencies installed:\n\n" + "\n".join(failures)
        )

    print(f"{imported} modules imported with runtime dependencies only")


refuse_a_development_environment()
import_everything()
