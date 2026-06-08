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

## Start

The backend image clones the latest `dev` branch from GitHub during the Docker
build. The checkout is expected to be clean, and the build reports an error if
`git describe --tags --always --dirty` is empty or contains `dirty`.

```sh
docker compose -f compose.backend.yml up -d --build
```

Check the API through Cloudflare:

```sh
curl https://api.nursescheduling.org/health
```

Check the backend directly from the VM:

```sh
docker compose -f compose.backend.yml exec backend curl -fsS http://127.0.0.1:8000/health
```

## Frontend

Set the frontend build environment variable:

```sh
NEXT_PUBLIC_BACKEND_API_URL=https://api.nursescheduling.org
```

The current backend keeps optimization jobs, SSE events, and XLSX outputs in
process memory. Keep `uvicorn` at one worker and run one backend replica until
job state is moved to a shared store.
