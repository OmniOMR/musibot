#!/usr/bin/env bash
# Fetch the `minio` and `mc` binaries out of Musibot's re-hosted MinIO image.
#
# MinIO no longer distributes its community server: dl.min.io answers 410 Gone,
# and the images on Docker Hub and quay.io are deleted or private. The last
# community release survives as the image Musibot re-hosts on the GitHub
# Container Registry, unmodified, and this pulls the two binaries out of it with
# nothing but curl, tar and python3 — a VM needs no Docker for it.
#
#   deploy/minio/fetch-binaries.sh /tmp/minio-binaries
#
# Both binaries are checked against the checksums below before they are written,
# so what lands is byte for byte what MinIO built. See docs/rough-edges.md for
# why this exists and what replaces it.

set -euo pipefail

REPOSITORY="omniomr/minio"
TAG="RELEASE.2025-09-07T16-13-09Z"

# sha256 of /usr/bin/minio and /usr/bin/mc in that image.
MINIO_SHA256="7c5bd8512c6e966455b1d198209358b2d191c77a83ab377c4073281065fb855f"
MC_SHA256="01f866e9c5f9b87c2b09116fa5d7c06695b106242d829a8bb32990c00312e891"

destination="${1:?usage: $0 <destination directory>}"
mkdir -p "$destination"

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

token="$(curl -fsS "https://ghcr.io/token?scope=repository:${REPOSITORY}:pull" \
    | python3 -c 'import json, sys; print(json.load(sys.stdin)["token"])')"

registry() {
    curl -fsSL -H "Authorization: Bearer ${token}" "$@"
}

accept="application/vnd.oci.image.index.v1+json, application/vnd.oci.image.manifest.v1+json"
accept="${accept}, application/vnd.docker.distribution.manifest.list.v2+json"
accept="${accept}, application/vnd.docker.distribution.manifest.v2+json"

manifest="$(registry -H "Accept: ${accept}" "https://ghcr.io/v2/${REPOSITORY}/manifests/${TAG}")"

# An index names one manifest per platform; this wants linux/amd64's.
if [[ "$(python3 -c 'import json, sys; print("manifests" in json.load(sys.stdin))' <<<"$manifest")" == "True" ]]; then
    digest="$(python3 -c '
import json, sys
index = json.load(sys.stdin)
[digest] = [
    m["digest"] for m in index["manifests"]
    if m.get("platform", {}).get("os") == "linux"
    and m.get("platform", {}).get("architecture") == "amd64"
]
print(digest)
' <<<"$manifest")"
    manifest="$(registry -H "Accept: ${accept}" "https://ghcr.io/v2/${REPOSITORY}/manifests/${digest}")"
fi

layers="$(python3 -c '
import json, sys
for layer in json.load(sys.stdin)["layers"]:
    print(layer["digest"])
' <<<"$manifest")"

# The binaries are in one of the layers; every layer is searched rather than
# that one assumed, and a layer without them is not an error.
for layer in $layers; do
    registry "https://ghcr.io/v2/${REPOSITORY}/blobs/${layer}" \
        | tar -xz -C "$work" --wildcards 'usr/bin/minio' 'usr/bin/mc' 2>/dev/null || true
done

for binary in minio mc; do
    if [[ ! -f "$work/usr/bin/$binary" ]]; then
        echo "The image ${REPOSITORY}:${TAG} holds no /usr/bin/${binary}" >&2
        exit 1
    fi
done

echo "${MINIO_SHA256}  ${work}/usr/bin/minio" | sha256sum --check --quiet
echo "${MC_SHA256}  ${work}/usr/bin/mc" | sha256sum --check --quiet

install -m 0755 "$work/usr/bin/minio" "$work/usr/bin/mc" "$destination/"
"$destination/minio" --version | head -1
"$destination/mc" --version | head -1
