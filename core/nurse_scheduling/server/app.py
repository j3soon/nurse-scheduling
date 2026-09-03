"""FastAPI application factory and dependency composition for the server."""

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

import logging
import subprocess
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler, request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..sentry import capture_invalid_request, init_sentry
from .api.optimize import events_router as optimize_events_router
from .api.optimize import router as optimize_router
from .auth import AUTH_SCHEME, create_auth_dependency, create_stream_auth_dependency
from .config import ServerSettings
from .errors import (
    JobArtifactNotFoundError,
    JobArtifactNotReadyError,
    JobCapacityError,
    JobInputNotFoundError,
    JobNotFoundError,
    JobOperationContentionError,
    JobOperationNotAllowedError,
    ServerApplicationError,
)
from .job_store import JobStore
from .jobs.controller import JobController
from .jobs.models import StoreLimits
from .jobs.runner import OptimizationRunner
from .jobs.worker import JobWorker
from .maintenance import JobMaintenance
from .runtime_identity import get_deployment_id
from .solver_options import validate_solver_availability
from .stores.memory import MemoryJobStore

TITLE = "Nurse Scheduling API"
SERVICE_NAME = "nurse-scheduling-api"
API_VERSION = "0.2.0"
REPO_ROOT = Path(__file__).resolve().parents[3]
APP_VERSION_FILE = REPO_ROOT / ".app-version"
UNEXPECTED_ERROR_VERSION_ADVICE = (
    "If this error was unexpected, check that your frontend and backend versions match. "
    "Older YAML may not work after breaking changes, though we try to preserve compatibility."
)
ORIGIN_REGEX = r"^(http://(localhost|127\.0\.0\.1):[0-9]+|https://([a-zA-Z0-9-]+\.)?nursescheduling\.org)$"


# Keep API output focused on server behavior. Solver progress is delivered to
# clients through job events and remains available from the CLI's verbose logs.
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
server_logger = logging.getLogger("nurse_scheduling.server")
server_logger.setLevel(logging.INFO)


def get_app_version() -> str:
    """Return the generated build version or the current Git description."""
    try:
        generated_version = APP_VERSION_FILE.read_text(encoding="utf-8").strip()
        if generated_version:
            return generated_version
    except OSError:
        pass
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT}",
                "-C",
                str(REPO_ROOT),
                "describe",
                "--tags",
                "--always",
                "--dirty",
            ],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "v0.0.0-unknown"


def _create_store(settings: ServerSettings, instance_id: str) -> JobStore:
    """Construct the configured persistence adapter.

    Redis is imported lazily so memory-only deployments do not require startup access to it.
    """
    if settings.job_backend == "memory":
        return MemoryJobStore(store_id=instance_id, max_events_per_job=settings.max_events_per_job)
    from .stores.redis import RedisJobStore

    return RedisJobStore(
        url=settings.redis_url,
        key_prefix=settings.redis_key_prefix,
        event_stream_keepalive_seconds=settings.sse_keepalive_seconds,
        max_events_per_job=settings.max_events_per_job,
        usage_metrics_key_prefix=(settings.usage_metrics_key_prefix if settings.usage_metrics_enabled else None),
        usage_metrics_retention_days=settings.usage_metrics_retention_days,
    )


def _format_unexpected_error(error: Exception) -> str:
    """Add version-mismatch guidance to an unexpected execution error."""
    return f"{error}\n\n{UNEXPECTED_ERROR_VERSION_ADVICE}"


def _is_form_parser_size_error(exc: StarletteHTTPException) -> bool:
    """Return whether Starlette reported multipart size overflow as a generic 400."""
    detail = str(exc.detail).lower()
    return exc.status_code == 400 and "size" in detail and ("exceeded" in detail or "too large" in detail)


def create_app(
    *,
    settings: ServerSettings | None = None,
    store: JobStore | None = None,
    runner: OptimizationRunner | None = None,
    start_background: bool = True,
) -> FastAPI:
    """Construct an independently testable server and all dependencies.

    Explicit dependencies support isolated tests; omitted values come from configuration.
    """
    settings = settings or ServerSettings.from_env()
    validate_solver_availability(settings.solver_ids)
    deployment_id = get_deployment_id()
    instance_id = str(uuid4())
    store = store or _create_store(settings, instance_id)
    runner = runner or OptimizationRunner()
    started_at = datetime.now(timezone.utc)
    app_version = get_app_version()
    claimed_performance = (
        {
            "score": settings.claimed_performance.score,
            "app_version": settings.claimed_performance.app_version,
            "measured_at": settings.claimed_performance.measured_at.isoformat(),
        }
        if settings.claimed_performance is not None
        else None
    )
    # Authentication is advertised publicly so clients can prompt for credentials before
    # calling a protected route, and so older clients keep working against open deployments.
    require_auth = create_auth_dependency(settings.auth_token)
    require_stream_auth = create_stream_auth_dependency(settings.auth_token)
    auth_descriptor = {"required": settings.auth_token is not None, "scheme": AUTH_SCHEME}
    runtime_identity = {
        "service_name": SERVICE_NAME,
        "api_version": API_VERSION,
        "app_version": app_version,
        "deployment_id": deployment_id,
        "instance_id": instance_id,
        "started_at": started_at.isoformat(),
        "job_backend": settings.job_backend,
        "job_store_id": store.store_id,
    }
    controller = JobController(
        store,
        limits=StoreLimits(
            max_pending=settings.max_pending_jobs,
            max_retained=settings.max_retained_jobs,
        ),
        retention_seconds=settings.job_retention_seconds,
        worker_lease_seconds=settings.worker_lease_seconds,
        runtime_identity=runtime_identity,
    )
    worker = JobWorker(
        controller,
        runner,
        worker_id=instance_id,
        claim_poll_seconds=settings.claim_poll_seconds,
        worker_lease_seconds=settings.worker_lease_seconds,
        timeout_grace_seconds=settings.timeout_grace_seconds,
        unexpected_error_formatter=_format_unexpected_error,
    )
    maintenance = JobMaintenance(controller, interval_seconds=settings.maintenance_interval_seconds)
    init_sentry(app_version)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        """Own startup and shutdown of process-local background threads."""
        server_logger.info(
            "[server:start] title=%s api_version=%s app_version=%s deployment_id=%s "
            "instance_id=%s backend=%s job_store_id=%s auth=%s",
            TITLE,
            API_VERSION,
            app_version,
            deployment_id,
            instance_id,
            settings.job_backend,
            store.store_id,
            AUTH_SCHEME if settings.auth_token is not None else "disabled",
        )
        if start_background:
            worker.start()
            maintenance.start()
        try:
            yield
        finally:
            if start_background:
                maintenance.stop()
                worker.stop()

    generated_docs_are_public = settings.auth_token is None
    app = FastAPI(
        title=TITLE,
        version=API_VERSION,
        lifespan=lifespan,
        openapi_url="/openapi.json" if generated_docs_are_public else None,
        docs_url="/docs" if generated_docs_are_public else None,
        redoc_url="/redoc" if generated_docs_are_public else None,
    )
    app.state.settings = settings
    app.state.job_store = store
    app.state.job_controller = controller
    app.state.job_runner = runner
    app.state.job_worker = worker
    app.state.job_maintenance = maintenance
    app.state.app_version = app_version
    app.state.deployment_id = deployment_id
    app.state.instance_id = instance_id
    app.state.started_at = started_at
    app.state.runtime_identity = runtime_identity

    @app.exception_handler(ServerApplicationError)
    async def application_error_handler(request: Request, exc: ServerApplicationError):
        """Translate application failures into stable JSON HTTP errors."""
        if isinstance(exc, (JobNotFoundError, JobInputNotFoundError, JobArtifactNotFoundError)):
            status_code = 404
        elif isinstance(exc, JobCapacityError):
            status_code = 429
        elif isinstance(exc, (JobOperationNotAllowedError, JobOperationContentionError, JobArtifactNotReadyError)):
            # Internal store write conflicts are consumed by the controller, not mapped here.
            status_code = 409
        else:
            status_code = 500
        if status_code < 500:
            capture_invalid_request(request, status_code, str(exc), exc.code)
        else:
            server_logger.exception(
                "[server:request] unexpected application error method=%s path=%s",
                request.method,
                request.url.path,
                exc_info=(type(exc), exc, exc.__traceback__),
            )
        headers = {"Retry-After": "1"} if status_code == 429 else None
        return JSONResponse(
            status_code=status_code,
            content={"error": {"code": exc.code, "message": str(exc)}},
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        """Capture request-schema failures before using FastAPI's response format."""
        capture_invalid_request(request, 422, exc.errors())
        return await request_validation_exception_handler(request, exc)

    @app.exception_handler(StarletteHTTPException)
    async def starlette_http_error_handler(request: Request, exc: StarletteHTTPException):
        """Capture client HTTP errors and normalize multipart size failures."""
        if request.url.path == "/optimize" and _is_form_parser_size_error(exc):
            exc = StarletteHTTPException(status_code=413, detail="Scheduling YAML is too large")
        if 400 <= exc.status_code < 500:
            capture_invalid_request(request, exc.status_code, exc.detail)
        return await http_exception_handler(request, exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=ORIGIN_REGEX,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
        expose_headers=["Content-Disposition", "Location", "Retry-After"],
    )
    app.include_router(optimize_router, dependencies=[Depends(require_auth)])
    app.include_router(optimize_events_router, dependencies=[Depends(require_stream_auth)])

    @app.get("/", dependencies=[Depends(require_auth)])
    async def root() -> dict[str, str]:
        """Return API identity and backend build version."""
        return {"message": TITLE, "api_version": API_VERSION, "app_version": app_version}

    def info_payload(status: str):
        """Build public service identity and job-store metadata."""
        return {
            "status": status,
            **runtime_identity,
            "auth": auth_descriptor,
            "claimed_performance": claimed_performance,
        }

    def check_readiness() -> str | None:
        """Return the first unavailable dependency reason, or `None` when ready."""
        try:
            store.check_health()
        except Exception as error:  # noqa: BLE001
            server_logger.warning(
                "[server:readiness] job store unavailable backend=%s error=%s",
                settings.job_backend,
                error,
            )
            return "job_store_unavailable"
        if start_background and not worker.is_ready():
            return "job_worker_unavailable"
        return None

    @app.get("/info")
    def info() -> JSONResponse:
        """Return service identity and readiness for clients and diagnostics."""
        unavailable_reason = check_readiness()
        if unavailable_reason is not None:
            return JSONResponse(
                status_code=503,
                content={**info_payload("unavailable"), "reason": unavailable_reason},
                headers={"Cache-Control": "no-store"},
            )
        try:
            activity = controller.get_activity()
        except Exception as error:  # noqa: BLE001
            server_logger.warning(
                "[server:info] job activity unavailable backend=%s error=%s",
                settings.job_backend,
                error,
            )
            return JSONResponse(
                status_code=503,
                content={**info_payload("unavailable"), "reason": "job_store_unavailable"},
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            content={
                **info_payload("ready"),
                "jobs": {
                    "running": activity.running_jobs,
                    "queued": activity.queued_jobs,
                    "cancelling": activity.cancelling_jobs,
                },
                "workers": {"online": activity.online_workers},
            },
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/ready")
    def ready() -> JSONResponse:
        """Return minimal readiness status for deployment and routing probes."""
        unavailable_reason = check_readiness()
        if unavailable_reason is not None:
            return JSONResponse(
                status_code=503,
                content={
                    "status": "unavailable",
                    "reason": unavailable_reason,
                },
                headers={"Cache-Control": "no-store"},
            )
        return JSONResponse(
            content={"status": "ready"},
            headers={"Cache-Control": "no-store"},
        )

    return app
