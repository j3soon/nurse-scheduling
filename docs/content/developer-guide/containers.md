<!-- This file is mostly AI generated. -->

# Backend Containers and Networks

The production backend Compose variant uses five private networks, while the
memory variant uses four. Both connect services by name.
Docker assigns their addresses. Only the optional inspection UIs publish ports,
and those bind to host loopback. The frontend is deployed separately.

```mermaid
flowchart TB
    Visitor[<b>Public client</b><br/>Cloudflare Tunnel]
    Tunnel[<b>cloudflared</b><br/>Tunnel connector]
    Proxy[<b>NGINX</b><br/>Route HTTP requests]
    API[<b>api</b><br/>Scheduling and jobs]
    AI[<b>ai</b><br/>Assistant]
    Redis[(<b>redis</b><br/>Jobs and usage)]
    Postgres[(<b>postgres</b><br/>AI chat history)]
    Reporter[<b>usage-reporter</b><br/>Production only]
    Diagnostic[<b>diagnostic</b><br/>Optional profile]
    RedisUI[<b>redisinsight</b><br/>Optional profile]
    PostgresUI[<b>pgadmin</b><br/>Optional profile]

    Visitor --> Tunnel
    Tunnel -->|tunnel| Proxy
    Diagnostic -.->|tunnel| Tunnel
    Proxy -->|api| API
    Proxy -->|ai| AI
    AI -->|api: optimizer calls| API
    API -->|redis: production only| Redis
    Reporter -->|redis: production only| Redis
    AI -->|postgres| Postgres
    RedisUI -.->|redis| Redis
    PostgresUI -.->|postgres| Postgres
```

Solid lines show normal traffic. Dotted lines show optional inspection or
diagnostic profiles. The `api` and `ai` labels are distinct networks even though
both services use the same image. In the memory Compose variant, the API keeps
jobs in process, so Redis, RedisInsight, and the usage reporter are absent.

## NGINX routing

The Tunnel hostname points to `http://nginx:8080`. NGINX applies these rules
from [its configuration](../../../docker/nginx.backend.conf):

| Incoming path | Upstream | Path sent upstream |
| --- | --- | --- |
| `/ai/…` | `ai:8001` | `/…` (`/ai/` is replaced by `/`) |
| Every other path | `api:8000` | Unchanged |

NGINX sets `X-Forwarded-For` to Cloudflare's `CF-Connecting-IP`, falling back
to the direct peer address when that header is absent. The API and AI trust
proxy headers from local containers, so this deployment assumes those
containers are trusted. Neither service publishes its port to the host.
