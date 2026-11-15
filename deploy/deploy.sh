#!/usr/bin/env bash
# Ship a git ref to the VM and (re)start the stack. Run from the repo root on a dev laptop (Git Bash is fine):
#   VM=root@45.77.216.35 SSH_KEY=~/.ssh/vultr_hack deploy/deploy.sh [ref]       (default ref: HEAD)
# The VM never needs GitHub access: the tree goes over SSH as a git archive. /opt/beatopia/.env stays in place
# (create it once from deploy/vm.env.template). Add WORKER=1 to also start the worker profile.
set -euo pipefail

VM="${VM:?set VM, e.g. root@45.77.216.35}"
REF="${1:-HEAD}"
SSH=(ssh -o StrictHostKeyChecking=accept-new)
[[ -n "${SSH_KEY:-}" ]] && SSH+=(-i "$SSH_KEY")
PROFILE=""
[[ "${WORKER:-0}" == "1" ]] && PROFILE="--profile worker"

sha="$(git rev-parse --short "$REF")"
echo "deploying $REF ($sha) to $VM"

git archive --format=tar "$REF" | "${SSH[@]}" "$VM" "set -e
  mkdir -p /opt/beatopia.new
  tar -x -C /opt/beatopia.new
  test -f /opt/beatopia/.env || { echo 'missing /opt/beatopia/.env (see deploy/vm.env.template)' >&2; exit 1; }
  cp /opt/beatopia/.env /opt/beatopia.new/.env
  rm -rf /opt/beatopia.old
  mv /opt/beatopia /opt/beatopia.old && mv /opt/beatopia.new /opt/beatopia
  echo $sha > /opt/beatopia/DEPLOYED_SHA
  cd /opt/beatopia
  docker compose -f deploy/docker-compose.yml --env-file .env $PROFILE up -d --build --remove-orphans
  docker compose -f deploy/docker-compose.yml --env-file .env ps"
