# Backend Deployment

This deployment scaffold publishes the FastAPI backend through Cloudflare
Tunnel for `api.nursescheduling.org`. Cloudflare terminates public HTTPS, while
`cloudflared` connects outbound from the VM to the backend container.

## Cloudflare Tunnel

- Create a [Cloudflare Tunnel](https://developers.cloudflare.com/tunnel/setup/).
- Add a public hostname for `api.nursescheduling.org`.
- Point the hostname service to `http://backend:8000`.
- Copy `.env.example` to `.env`.
- Set `CLOUDFLARE_TUNNEL_TOKEN` in `.env` to the token from the dashboard.
- Enable [Always Use HTTPS](https://developers.cloudflare.com/ssl/edge-certificates/additional-options/always-use-https/).
- Add a WAF/rate limit rule for `POST /optimize`.
- Keep ports `80` and `443` closed on the VM unless another service needs them.

> We used Cloudflare Tunnel for ease of setup, but you can easily switch to NGINX and Certbot if you have a dedicated public IP and are comfortable exposing it to the internet.

## Start

Run these commands from the `docker/` directory.

The backend image clones the latest `dev` branch from GitHub during the Docker
build. The checkout is expected to be clean, and the build reports an error if
`git describe --tags --always --dirty` is empty or contains `dirty`.

```sh
cd docker
docker compose -f compose.backend.yml up -d --build
```

The compose file starts Redis alongside the backend. The backend runs with:

- `JOB_BACKEND=redis`
- `JOB_REDIS_URL=redis://redis:6379/0`
- `JOB_REDIS_KEY_PREFIX=nurse_scheduling:jobs:v0`
- `JOB_CLAIM_LEASE_SECONDS=90` by default

The backend container runs multiple Uvicorn workers. Each worker claims jobs
from Redis and runs at most one optimization job locally. Active workers renew
their claims; a job is failed and its capacity is released if its worker stops
renewing the claim.

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
docker compose -f compose.backend.yml exec backend curl -fsS http://127.0.0.1:8000/health
```

Check Redis from the backend container:

```sh
docker compose -f compose.backend.yml exec backend redis-cli -u redis://redis:6379/0 ping
```

## Frontend

The frontend selects an available backend from its built-in candidate list at
page load.

When `JOB_BACKEND=redis`, optimization jobs, SSE events, YAML inputs,
and XLSX outputs are stored in Redis so status, event, and download requests can
be served by any backend worker.
