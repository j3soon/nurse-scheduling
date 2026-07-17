# Backend Deployment

This deployment scaffold publishes the FastAPI backend through Cloudflare
Tunnel for `api.nursescheduling.org`. Cloudflare terminates public HTTPS, while
`cloudflared` connects outbound from the VM to the API container.

## Cloudflare Tunnel

- Create a [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/).
- Add a public hostname for `api.nursescheduling.org`.
- Point the hostname service to `http://api:8000`.
- Copy `.env.example` to `.env`.
- Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env` to the token from the dashboard.
- Enable [Always Use HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/).
- (Optional) Add a WAF/rate limit rule for `POST /optimize`.
- Keep ports `80` and `443` closed on the VM unless another service needs them.

> We used Cloudflare Tunnel for ease of setup, but you can easily switch to NGINX and Certbot if you have a dedicated public IP and are comfortable exposing it to the internet.

## Start

Run these commands from the `docker/` directory.

The production API image uses `Dockerfile.api` and clones the latest `dev`
branch from GitHub during the Docker build. The checkout is expected to be
clean, and the build reports an error if
`git describe --tags --always --dirty` is empty or contains `dirty`.

```sh
cd docker
docker compose -f compose.backend.yml up -d --build
```

For staging, create a separate ignored environment file and use a staging-only
Cloudflare Tunnel token:

```sh
cp .env.staging.example .env.staging
# Set CLOUDFLARE_TUNNEL_TOKEN in .env.staging.
docker compose --env-file .env.staging -f compose.backend.yml up -d --build
```

The staging environment selects `Dockerfile.api.staging`, which copies the
current repository's `core/` directory into the image instead of cloning
GitHub. It also sets
`COMPOSE_PROJECT_NAME=nurse-scheduling-backend-staging`. This overrides the
default `nurse-scheduling-backend` project name and gives staging its own
containers, network, and `redis-data` volume. Production and staging can then
run side by side on the same host.

Always pass `--env-file .env.staging` for every staging command, including
`ps`, `logs`, and `down`. Without it, Docker Compose loads `.env` and targets
production by default.

```sh
docker compose --env-file .env.staging -f compose.backend.yml ps
docker compose --env-file .env.staging -f compose.backend.yml logs -f
docker compose --env-file .env.staging -f compose.backend.yml down
```

The default compose file starts Redis alongside the backend. The backend runs
with:

- `JOB_BACKEND=redis`
- `JOB_REDIS_URL=redis://redis:6379/0`
- `JOB_REDIS_KEY_PREFIX=nurse_scheduling:jobs:v0`
- `JOB_CLAIM_LEASE_SECONDS=90` by default
- `JOB_MAX_EVENTS_PER_JOB=1000` by default

The API container runs multiple Uvicorn workers. Each worker claims jobs
from Redis and runs at most one optimization job locally. Active workers renew
their claims; a job is failed and its capacity is released if its worker stops
renewing the claim.

To run one backend worker with process-local memory and no Redis service, use
the pre-Redis deployment configuration:

```sh
docker compose -f compose.backend.memory.yml up -d --build
```

Use the same compose file name for later commands when running the memory
configuration.

Check the API through Cloudflare:

```sh
curl https://api.nursescheduling.org/health
```

Run the public healthcheck test:

```sh
./test_public_healthcheck.sh
```

Check the backend directly from the VM:

```sh
docker compose -f compose.backend.yml exec api curl -fsS http://127.0.0.1:8000/health
```

Check Redis from the API container:

```sh
docker compose -f compose.backend.yml exec api redis-cli -u redis://redis:6379/0 ping
```

## Frontend

The frontend selects an available backend from its built-in candidate list at
page load.

When `JOB_BACKEND=redis`, optimization jobs, SSE events, YAML inputs,
and XLSX outputs are stored in Redis so status, event, and download requests can
be served by any backend worker.

The bundled Redis service uses the image's default RDB snapshot policy and the
`redis-data` volume. This is sufficient for multi-worker coordination, but an
abrupt Redis or host failure can lose writes since the latest snapshot. A
deployment that requires a smaller recovery-point window should enable Redis
AOF persistence or use a managed Redis service with an appropriate persistence
policy. AOF is not required for the backend's job-sharing behavior and adds
disk I/O for stored YAML, event streams, and XLSX artifacts.
