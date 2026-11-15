# deploy/ (owner: **WS2**)

Production stack for the Vultr VM: `api` (FastAPI + CLAP), `worker` (WS1's job loop, behind the `worker` profile
until it is implemented) and `caddy` (automatic HTTPS on `API_DOMAIN`). The API URL is
`https://45-77-216-35.sslip.io`.

| File | What |
| --- | --- |
| `api.Dockerfile` (+ `.dockerignore`) | python 3.11 slim + ffmpeg + uv; `uv sync --frozen --no-dev` from `api/uv.lock` (CPU torch) |
| `worker.Dockerfile` (+ `.dockerignore`) | same base, `worker/uv.lock` (demucs); `python -m worker.main` |
| `docker-compose.yml` | services + named volumes `hf_cache` (CLAP weights, shared), `torch_cache` (Demucs), `caddy_*` |
| `Caddyfile` | `{$API_DOMAIN}` → `api:8000`; CORS is done by the API (`WEB_ORIGIN`) |
| `vm.env.template` | what `/opt/beatopia/.env` must contain (incl. the C8/C9 values) |
| `vm_setup.sh` | one-time: Docker (official apt repo), 4 GB swap, ufw 22/80/443 |
| `deploy.sh` | ships a git ref as a `git archive` over SSH (the VM needs no GitHub access) and runs `compose up --build` |

The per-Dockerfile `.dockerignore` files need BuildKit (default in current Docker; `vm_setup.sh` installs buildx).

## First deploy
```bash
VM=root@45.77.216.35; KEY=~/.ssh/vultr_hack
ssh -i $KEY $VM 'bash -s' < deploy/vm_setup.sh
# fill a copy of deploy/vm.env.template locally, then:
scp -i $KEY my-vm.env $VM:/opt/beatopia/.env && ssh -i $KEY $VM chmod 600 /opt/beatopia/.env
VM=$VM SSH_KEY=$KEY deploy/deploy.sh            # first build ≈ 10 min (torch), first start downloads CLAP (≈ 3 min)
curl -s https://45-77-216-35.sslip.io/health   # {"ok":true}
```

## Redeploy / operate
```bash
VM=root@45.77.216.35 SSH_KEY=~/.ssh/id_ed25519 deploy/deploy.sh main      # API only (default); any ref
CADDY=1 VM=... SSH_KEY=... deploy/deploy.sh main                            # + Caddy, only if the Caddyfile changed
WORKER=1 VM=... SSH_KEY=... deploy/deploy.sh main                           # + worker (read "Worker data" first)
ssh ... 'cd /opt/beatopia && docker compose -f deploy/docker-compose.yml --env-file .env logs -f --tail=100 api'
ssh ... 'cat /opt/beatopia/DEPLOYED_SHA'
```
`deploy.sh` only rebuilds and recreates the services it names, each with `--no-deps`, and never uses
`--remove-orphans`. The archive is extracted over `/opt/beatopia` in place (no directory swap), so `.env` and
anything not in git survive. At the end it prints each container's image label and its process
`BEATOPIA_REVISION`. They match per container. The worker keeps its own revision until it is recreated with
`WORKER=1`.

Toggle Gemini degraded mode: set `GEMINI_DEGRADED=1` in `/opt/beatopia/.env`, then
`docker compose -f deploy/docker-compose.yml --env-file .env up -d --no-deps --force-recreate api`
(see `api/README.md`).

## Worker data (issue #13)
The worker keeps separation/import checkpoints, receipts and `worker.jsonl` in `WORKER_DATA_DIR`
(`/app/worker/data`). Compose now mounts the named volume `beatopia_worker_data` there. A worker created before
that change keeps the data in its container layer, which a recreate would delete. `WORKER=1 deploy.sh` handles
the move:
1. It prints the old container's mounts and copies `/app/worker/data` to `/opt/beatopia-backups/worker-data-<UTC>`.
2. It builds the image and creates the new container without starting it.
3. If the volume is empty, it seeds the volume from that backup.
4. It starts the worker.

Before running it:
```bash
ssh ... 'docker inspect --format "{{json .Mounts}}" beatopia-worker-1'   # anything besides hf/torch caches?
ssh ... 'docker logs --tail 20 beatopia-worker-1'                         # no job in progress
```
If the old container mounts its data from somewhere else (a host path), copy that into the volume instead and
tell WS1. Never run a bare `docker compose up` (it would recreate the worker). Never run `docker compose config`
(it prints every secret in `.env`).

## Checks against production
```bash
API_URL=https://45-77-216-35.sslip.io uv run --project api pytest api/tests/test_contract.py
uv run --project api python api/scripts/bench.py --url https://45-77-216-35.sslip.io
```
