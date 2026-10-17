"""Run scripted adversarial checks against the isolated security-scan stack."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

# Usage: python skills/security-scan/scripts/probe.py [REPO_ROOT]
# Reads artifacts/security-scan/stack/stack.env from isolated_stack.sh. The URLs must be loopback,
# so a misconfigured run cannot reach a deployment. Prints one line per check and exits 1 on a FAIL.

import re
import sys
import time
import uuid
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path
from urllib.parse import urlsplit

import httpx

REPO_ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(REPO_ROOT / "core"))

from nurse_scheduling.ai.app import create_app as create_ai_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.lifecycle import TERMINAL_EVENTS
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory
from nurse_scheduling.server.app import create_app as create_api_app
from nurse_scheduling.server.config import ServerSettings

LONG_SCHEDULE = REPO_ROOT / "core/tests/testcases/real/large-ward-with-87-people-2025-11.yaml"
PUBLIC_API_ROUTES = {"/info", "/ready"}
PUBLIC_AI_ROUTES = {"/health", "/ready", "/capabilities"}
ALLOWED_ORIGINS = ["https://nursescheduling.org", "https://app.nursescheduling.org", "http://localhost:3000"]
HOSTILE_ORIGINS = [
    "https://evil.example",
    "https://nursescheduling.org.evil.example",
    "https://evilnursescheduling.org",
    "http://nursescheduling.org",
    "http://192.168.1.20:3000",
    "http://10.0.0.5:3000",
    "null",
]
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'} {name}{f': {detail}' if detail and not ok else ''}", flush=True)


def load_stack() -> dict[str, str]:
    env_file = REPO_ROOT / "artifacts/security-scan/stack/stack.env"
    values = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line)
    for key in ("API_OPEN_URL", "API_KEYED_URL", "AI_URL"):
        if urlsplit(values[key]).hostname != "127.0.0.1":
            raise SystemExit(f"{key} must be a loopback URL, got {values[key]}")
    return values


def routes(app) -> Iterator[tuple[str, str]]:
    for route in app.routes:
        for method in sorted(getattr(route, "methods", None) or ()):
            if method not in {"HEAD", "OPTIONS"} and not route.path.startswith(("/docs", "/redoc", "/openapi")):
                yield method, route.path


def concrete(path: str) -> str:
    return re.sub(
        r"\{[^}]+\}", lambda match: f"job_{uuid.uuid4().hex}" if "job" in match[0] else str(uuid.uuid4()), path
    )


def submit(client: httpx.Client, url: str, address: str, timeout: int = 20, **headers: str) -> httpx.Response:
    return client.post(
        f"{url}/optimize",
        files={"file": ("ward.yaml", LONG_SCHEDULE.read_bytes(), "application/yaml")},
        data={"timeout": str(timeout), "prettify": "false"},
        headers={"X-Forwarded-For": address, **headers},
    )


def leaks_internals(response: httpx.Response) -> bool:
    return bool(re.search(r"Traceback|File \"/|nurse_scheduling/|site-packages", response.text))


def check_route_auth(client: httpx.Client, name: str, url: str, app, public: set[str], auth: dict[str, str]) -> None:
    exposed = []
    for method, path in routes(app):
        response = client.request(method, url + concrete(path), headers=auth)
        if path in public:
            continue
        if response.status_code != 401:
            exposed.append(f"{method} {path} -> {response.status_code}")
    check(f"{name}: every private route rejects the request", not exposed, "; ".join(exposed))


def check_cors(client: httpx.Client, name: str, url: str, path: str, method: str) -> None:
    allowed_wrongly = []
    for origin in HOSTILE_ORIGINS:
        response = client.options(url + path, headers={"Origin": origin, "Access-Control-Request-Method": method})
        if response.headers.get("access-control-allow-origin") in {origin, "*"}:
            allowed_wrongly.append(origin)
    check(f"{name}: hostile origins get no CORS grant", not allowed_wrongly, ", ".join(allowed_wrongly))
    missing = []
    for origin in ALLOWED_ORIGINS:
        response = client.options(url + path, headers={"Origin": origin, "Access-Control-Request-Method": method})
        if response.headers.get("access-control-allow-origin") != origin:
            missing.append(origin)
    check(f"{name}: allowed origins keep their CORS grant", not missing, ", ".join(missing))


def received_stub_reply(lines: Iterable[str]) -> bool:
    """Stop at a reply, a terminal event, or the total wait limit despite keepalives."""
    deadline = time.monotonic() + 15
    for line in lines:
        if time.monotonic() >= deadline:
            return False
        if line.startswith("event:") and line.partition(":")[2].strip() in TERMINAL_EVENTS:
            return False
        if "Scan reply." in line:
            return True
    return False


def check_api(client: httpx.Client, stack: dict[str, str]) -> None:
    open_url, keyed_url = stack["API_OPEN_URL"], stack["API_KEYED_URL"]
    bearer = {"Authorization": f"Bearer {stack['API_TOKEN']}"}
    api_app = create_api_app(settings=ServerSettings(), start_background=False)

    check_route_auth(client, "api keyed, no key", keyed_url, api_app, PUBLIC_API_ROUTES, {})
    check_route_auth(
        client, "api keyed, wrong key", keyed_url, api_app, PUBLIC_API_ROUTES, {"Authorization": "Bearer " + "x" * 32}
    )
    response = client.get(f"{keyed_url}/optimize/options", params={"token": stack["API_TOKEN"]})
    check("api keyed: a key in the query string is refused", response.status_code == 401, str(response.status_code))
    check("api keyed: generated docs are hidden", client.get(f"{keyed_url}/openapi.json").status_code == 404)
    check_cors(client, "api", open_url, "/optimize", "POST")

    # The scanner stands in for NGINX, which sets one forwarded address per visitor.
    created = []
    try:
        statuses = []
        for _ in range(4):
            response = submit(client, open_url, "198.51.100.7")
            statuses.append(response.status_code)
            if response.status_code == 202:
                created.append(response.json()["id"])
        code = response.json().get("error", {}).get("code") if response.status_code == 429 else None
        check(
            "api open: one address cannot hold more than its job share",
            statuses == [202, 202, 202, 429] and code == "client_job_capacity_exceeded",
            f"statuses={statuses} code={code}",
        )
        other = submit(client, open_url, "198.51.100.8")
        if other.status_code == 202:
            created.append(other.json()["id"])
        check("api open: another address still gets a slot", other.status_code == 202, str(other.status_code))

        keyed_ids = [submit(client, keyed_url, "198.51.100.9", **bearer) for _ in range(4)]
        created_keyed = [response.json()["id"] for response in keyed_ids if response.status_code == 202]
        check("api keyed: key holders are not limited per address", len(created_keyed) == 4, str(len(created_keyed)))

        forged = client.get(
            f"{keyed_url}/optimize/{created_keyed[0]}/events", params={"token": "9999999999." + "0" * 64}
        )
        check("api keyed: a forged stream token is refused", forged.status_code == 401, str(forged.status_code))
        minted = client.get(f"{keyed_url}/optimize/{created_keyed[0]}", headers=bearer).json()["links"]["events"]
        token = minted.split("token=", 1)[1]
        reused = client.get(f"{keyed_url}/optimize/{created_keyed[1]}/events", params={"token": token})
        check("api keyed: a stream token does not open another job", reused.status_code == 401, str(reused.status_code))
        for keyed_id in created_keyed:
            client.post(f"{keyed_url}/optimize/{keyed_id}/cancel", headers=bearer)
    finally:
        for job_id in created:
            client.post(f"{open_url}/optimize/{job_id}/cancel")

    big = b"a" * (3 * 1024 * 1024)
    response = client.post(f"{open_url}/optimize", content=big, headers={"Content-Type": "application/x-yaml"})
    check("api: an oversize declared body is refused", response.status_code == 413, str(response.status_code))

    def chunks() -> Iterator[bytes]:
        boundary = b'--scan\r\nContent-Disposition: form-data; name="yaml_content"\r\n\r\n'
        yield boundary
        for _ in range(48):
            yield b"a" * (64 * 1024)
        yield b"\r\n--scan--\r\n"

    response = client.post(
        f"{open_url}/optimize", content=chunks(), headers={"Content-Type": "multipart/form-data; boundary=scan"}
    )
    check("api: an oversize chunked body is refused", response.status_code == 413, str(response.status_code))
    bomb = "a: &a [x, x, x, x, x, x, x, x, x]\n" + "".join(
        f"{chr(98 + index)}: &{chr(98 + index)} [{', '.join([f'*{chr(97 + index)}'] * 9)}]\n" for index in range(8)
    )
    response = client.post(f"{open_url}/optimize", data={"yaml_content": bomb})
    check("api: a YAML alias bomb is refused", response.status_code == 400, str(response.status_code))
    response = client.post(f"{open_url}/optimize", data={"yaml_content": "[" * 5000})
    check("api: deeply nested YAML is refused", response.status_code == 400, str(response.status_code))
    probes = [
        client.post(f"{open_url}/optimize", content=b"--x\r\nbroken", headers={"Content-Type": "multipart/form-data"}),
        client.get(f"{open_url}/optimize/{'%00' * 4}"),
        client.post(f"{open_url}/optimize", data={"yaml_content": "a", "timeout": "1e309"}),
        client.post(f"{open_url}/optimize", data={"yaml_content": "a", "solver": "../../bin/sh"}),
    ]
    leaking = [f"{response.request.method} {response.status_code}" for response in probes if leaks_internals(response)]
    check("api: malformed requests do not reveal internals", not leaking, ", ".join(leaking))
    check("api: no malformed request causes a server error", all(r.status_code < 500 for r in probes))


def check_ai(client: httpx.Client, stack: dict[str, str]) -> None:
    url = stack["AI_URL"]
    bearer = {"Authorization": f"Bearer {stack['AI_TOKEN']}"}
    settings = AiSettings(provider_base_url="http://127.0.0.1:9/v1", provider_api_key="x", provider_model="x")
    ai_app = create_ai_app(settings=settings, sandbox_factory=FakeSandboxFactory())
    check_route_auth(client, "ai, no key", url, ai_app, PUBLIC_AI_ROUTES, {})
    check("ai: generated docs are hidden", client.get(f"{url}/openapi.json").status_code == 404)
    check_cors(client, "ai", url, "/sessions", "POST")

    schedule = (REPO_ROOT / "web-frontend/public/examples/large-ward-with-87-people-2025-11.yaml").read_text()

    def browser() -> tuple[httpx.Client, httpx.Response]:
        # The owner cookie is Secure, which httpx withholds over plain HTTP, so carry it by hand.
        client = httpx.Client(timeout=30, headers=bearer)
        created = client.post(f"{url}/sessions", json={"schedule_yaml": schedule})
        owner_cookie = created.headers.get("set-cookie", "").split(";", 1)[0]
        client.cookies.clear()
        client.headers["Cookie"] = owner_cookie
        return client, created

    owner, response = browser()
    intruder, _intruder_session = browser()
    try:
        check("ai: a session can be created", response.status_code == 201, response.text[:200])
        if response.status_code != 201:
            return
        session_id = response.json()["id"]
        cookie = response.headers.get("set-cookie", "")
        flags = {flag.strip().lower().split("=")[0] for flag in cookie.split(";")[1:]}
        check("ai: the owner cookie is HttpOnly and Secure", {"httponly", "secure"} <= flags, cookie.split(";", 1)[-1])
        owner.post(f"{url}/sessions/{session_id}/messages", json={"message": "hello"})
        with owner.stream("GET", f"{url}/sessions/{session_id}/events", timeout=15) as events:
            answered = received_stub_reply(events.iter_lines())
        check("ai: the stub provider answers a message", answered)
        foreign = [
            intruder.get(f"{url}/sessions/{session_id}/export"),
            intruder.get(f"{url}/sessions/{session_id}/uploads"),
            intruder.post(f"{url}/sessions/{session_id}/messages", json={"message": "x"}),
            intruder.put(f"{url}/sessions/{session_id}/schedule", json={"schedule_yaml": schedule}),
        ]
        statuses = [response.status_code for response in foreign]
        check("ai: another browser cannot use the session", all(code == 404 for code in statuses), str(statuses))

        files = [("files", (f"{index}.txt", b"x", "text/plain")) for index in range(40)]
        response = owner.post(f"{url}/sessions/{session_id}/uploads", files=files)
        check("ai: too many attachments are refused", response.status_code == 413, str(response.status_code))
        traversal = ("files", ("../../../../etc/passwd", b"x", "text/plain"))
        response = owner.post(f"{url}/sessions/{session_id}/uploads", files=[traversal])
        check("ai: an attachment with a path in its name is accepted only as data", response.status_code < 500)
        response = owner.post(
            f"{url}/sessions",
            content=b'{"schedule_yaml": "\\ud800 SECRET-MARKER"',
            headers={"Content-Type": "application/json"},
        )
        check(
            "ai: validation errors do not echo the request body",
            "SECRET-MARKER" not in response.text and not leaks_internals(response),
            response.text[:200],
        )
    finally:
        owner.close()
        intruder.close()


def main() -> None:
    stack = load_stack()
    checks: list[Callable[[httpx.Client, dict[str, str]], None]] = [check_api, check_ai]
    with httpx.Client(timeout=60) as client:
        for run in checks:
            try:
                run(client, stack)
            except Exception as error:  # noqa: BLE001
                check(f"{run.__name__} completed", False, f"{type(error).__name__}: {error}")
    failed = [name for name, ok, _detail in results if not ok]
    print(f"{len(results) - len(failed)} passed, {len(failed)} failed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
