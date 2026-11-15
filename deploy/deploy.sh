#!/usr/bin/env bash
# Ship a git ref to the VM and rebuild ONLY the services you name. Run from the repo root on a dev laptop:
#   VM=root@45.77.216.35 SSH_KEY=~/.ssh/id_ed25519 deploy/deploy.sh [ref]          (default ref: HEAD)
#
# Default: API only (`up -d --build --no-deps api`). The worker and Caddy keep running untouched, and nothing is
# removed (no `--remove-orphans`, no directory swap: the archive is extracted over /opt/beatopia in place, so .env
# and anything not in git stay).
#   WORKER=1  also rebuild/recreate the worker. Its data dir (/app/worker/data: separation/import checkpoints and
#             receipts) is backed up from the running container first, to /opt/beatopia-backups/, and the named
#             volume `beatopia_worker_data` is seeded from that backup when it is empty (first move off the
#             container layer). Only do this when no stems/analyze job is running (see deploy/README.md).
#   CADDY=1   also recreate Caddy (only needed when deploy/Caddyfile changed; certs live in the caddy_data volume).
# The VM never needs GitHub access: the tree goes over SSH as a git archive. Create /opt/beatopia/.env once from
# deploy/vm.env.template.
set -euo pipefail

VM="${VM:?set VM, e.g. root@45.77.216.35}"
REF="${1:-HEAD}"
SSH=(ssh -o StrictHostKeyChecking=accept-new)
[[ -n "${SSH_KEY:-}" ]] && SSH+=(-i "$SSH_KEY")
WORKER="${WORKER:-0}"
CADDY="${CADDY:-0}"

sha="$(git rev-parse "$REF")"
services="api"
if [[ "$WORKER" == "1" ]]; then services+=" worker"; fi
if [[ "$CADDY" == "1" ]]; then services+=" caddy"; fi
echo "deploying $REF ($sha) to $VM: $services"

git archive --format=tar "$REF" | "${SSH[@]}" "$VM" "set -euo pipefail
  test -f /opt/beatopia/.env || { echo 'missing /opt/beatopia/.env (see deploy/vm.env.template)' >&2; exit 1; }
  tar -x -C /opt/beatopia
  echo $sha > /opt/beatopia/DEPLOYED_SHA
  cd /opt/beatopia
  dc() { REVISION=$sha docker compose -f deploy/docker-compose.yml --env-file .env --profile worker \"\$@\"; }

  dc up -d --build --no-deps api

  if [ $WORKER = 1 ]; then
    backup=/opt/beatopia-backups/worker-data-\$(date -u +%Y%m%dT%H%M%SZ)
    mkdir -p \"\$backup\"
    if docker inspect beatopia-worker-1 >/dev/null 2>&1; then
      echo \"old worker mounts: \$(docker inspect --format '{{json .Mounts}}' beatopia-worker-1)\"
      docker cp beatopia-worker-1:/app/worker/data \"\$backup/\" && echo \"backed up worker data to \$backup\"
    fi
    dc build worker
    dc create --force-recreate worker      # stops/replaces the old container; the new one is not started yet
    empty=\$(docker run --rm -v beatopia_worker_data:/v --entrypoint sh beatopia-worker:latest -c 'ls -A /v | head -1')
    if [ -z \"\$empty\" ] && [ -d \"\$backup/data\" ]; then
      docker run --rm -v beatopia_worker_data:/v -v \"\$backup/data\":/src:ro --entrypoint sh beatopia-worker:latest \
        -c 'cp -a /src/. /v/' && echo 'seeded beatopia_worker_data from the backup'
    fi
    dc start worker
  fi

  if [ $CADDY = 1 ]; then
    dc up -d --no-deps --force-recreate caddy
  fi

  dc ps
  for c in beatopia-api-1 beatopia-worker-1; do
    docker inspect \"\$c\" >/dev/null 2>&1 || continue
    img=\$(docker inspect --format '{{.Config.Image}}' \"\$c\")
    echo \"\$c: image label \$(docker image inspect --format '{{ index .Config.Labels \"org.opencontainers.image.revision\" }}' \"\$img\")\" \
      \"process \$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' \"\$c\" | grep '^BEATOPIA_REVISION=' | cut -d= -f2)\"
  done"
