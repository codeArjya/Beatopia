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
VM=root@45.77.216.35 SSH_KEY=~/.ssh/vultr_hack deploy/deploy.sh ws2-api      # any ref; .env is kept
WORKER=1 VM=... deploy/deploy.sh                                              # also start the worker
ssh ... 'cd /opt/beatopia && docker compose -f deploy/docker-compose.yml logs -f --tail=100 api'
ssh ... 'cat /opt/beatopia/DEPLOYED_SHA'
```
Toggle Gemini degraded mode: set `GEMINI_DEGRADED=1` in `/opt/beatopia/.env`, then
`docker compose -f deploy/docker-compose.yml --env-file .env up -d api` (recreates the container with the new env).

## Checks against production
```bash
API_URL=https://45-77-216-35.sslip.io uv run --project api pytest api/tests/test_contract.py
uv run --project api python api/scripts/bench.py --url https://45-77-216-35.sslip.io
```
