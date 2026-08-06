#!/usr/bin/env bash
#
# Render musibot.conf.template into a finished nginx configuration.
#
#     ./render-config.sh nginx.env > /etc/nginx/sites-available/musibot.conf
#
# The official nginx image does this substitution itself on startup, which is
# how the local compose stack runs the template; a VM has no such entrypoint, so
# this script is the VM's half of it. Both render the same file, which is the
# point of it being a template rather than two configurations.
#
# WHY THIS IS NOT JUST `envsubst < template`.
#
# envsubst with no arguments substitutes *every* $NAME it finds, and an nginx
# configuration is full of nginx's own variables — $host, $remote_addr,
# $proxy_add_x_forwarded_for, $connection_upgrade. Those are not environment
# variables, so they would each be replaced by nothing, and the result is a
# configuration that nginx still accepts: it starts, and then forwards an empty
# Host header and logs an empty client address. So envsubst is given an explicit
# list of the names it may touch, and everything else survives untouched.
#
# The list is read out of the template rather than written down here, so it
# cannot drift from it: a variable added to the template is picked up, and a
# variable removed stops being demanded.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
template="$here/musibot.conf.template"

if [[ $# -gt 1 ]]; then
    echo "usage: $(basename "$0") [ENV_FILE] > musibot.conf" >&2
    exit 2
fi

# The environment file is optional: the values may equally be exported by
# whoever calls this.
if [[ $# -eq 1 ]]; then
    if [[ ! -f "$1" ]]; then
        echo "$(basename "$0"): no such environment file: $1" >&2
        exit 2
    fi
    # Read as a shell fragment, so this file may use ordinary shell quoting.
    # It is a file the operator wrote, on a machine they administer.
    set -a
    # shellcheck disable=SC1090
    source "$1"
    set +a
fi

# Every ${MUSIBOT_*} the template mentions, deduplicated, in the "$VAR $VAR"
# form envsubst wants.
mapfile -t names < <(grep -o '\${MUSIBOT_[A-Z0-9_]*}' "$template" | tr -d '${}' | sort -u)

if [[ ${#names[@]} -eq 0 ]]; then
    echo "$(basename "$0"): $template mentions no MUSIBOT_* variables — is it the right file?" >&2
    exit 1
fi

# A variable that is set but empty renders as empty, which for an upstream
# address produces a configuration nginx rejects and for a prefix produces one
# it accepts and serves wrongly. Demand every one of them.
missing=()
for name in "${names[@]}"; do
    if [[ -z "${!name:-}" ]]; then
        missing+=("$name")
    fi
done

if [[ ${#missing[@]} -gt 0 ]]; then
    echo "$(basename "$0"): these are not set: ${missing[*]}" >&2
    echo "See nginx.env.example beside this script." >&2
    exit 1
fi

printf -v allowed '${%s} ' "${names[@]}"

echo "# Generated from musibot.conf.template by render-config.sh — do not edit."
echo "# Edit the template and render again; see docs/deploying-to-a-vm.md."
envsubst "$allowed" < "$template"
