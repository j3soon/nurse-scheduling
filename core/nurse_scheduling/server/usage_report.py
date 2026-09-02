"""Deliver weekly per-job usage telemetry from Redis."""

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

import argparse
import csv
import io
import logging
import os
import signal
import threading
import time as time_module
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from typing import Protocol

import httpx
import redis

from .config import DEFAULT_USAGE_METRICS_RETENTION_DAYS, MIN_USAGE_METRICS_RETENTION_DAYS
from .usage_metrics import RedisUsageMetrics, WeeklyUsageReport, machine_timezone

REPORTER_LOGGER = logging.getLogger("nurse_scheduling.usage_report")
REDIS_TIMEOUT_SECONDS = 5.0
MAILGUN_TIMEOUT_SECONDS = 15.0
MIN_REPORT_INTERVAL_SECONDS = 10 * 60
"""Minimum delay between any two report delivery attempts."""
REPORT_RETRY_DELAYS_SECONDS = (MIN_REPORT_INTERVAL_SECONDS,) * 2
"""Bounded delays for transient delivery failures during one weekly run."""


def _positive_int(name: str, default: int) -> int:
    """Read a positive integer environment setting."""
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _hour(name: str, default: int) -> int:
    """Read an hour of day in the inclusive range from zero to 23."""
    value = int(os.getenv(name, default))
    if not 0 <= value <= 23:
        raise ValueError(f"{name} must be between 0 and 23")
    return value


@dataclass(frozen=True)
class UsageReportSettings:
    """Environment-backed settings for the standalone reporter."""

    redis_url: str
    metrics_key_prefix: str
    metrics_retention_days: int
    local_hour: int
    transport: str
    mailgun_api_url: str
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_from: str
    mailgun_to: str

    @classmethod
    def from_env(cls) -> "UsageReportSettings":
        """Load and validate reporter configuration."""
        settings = cls(
            redis_url=os.getenv("JOB_REDIS_URL", "redis://localhost:6379/0"),
            metrics_key_prefix=os.getenv("USAGE_METRICS_KEY_PREFIX", "nurse_scheduling:usage:v0"),
            metrics_retention_days=_positive_int(
                "USAGE_METRICS_RETENTION_DAYS",
                DEFAULT_USAGE_METRICS_RETENTION_DAYS,
            ),
            local_hour=_hour("USAGE_REPORT_LOCAL_HOUR", 0),
            transport=os.getenv("USAGE_REPORT_TRANSPORT", "stdout").strip().lower(),
            mailgun_api_url=os.getenv("MAILGUN_API_URL", "https://api.mailgun.net/v3").rstrip("/"),
            mailgun_api_key=os.getenv("MAILGUN_API_KEY", ""),
            mailgun_domain=os.getenv("MAILGUN_DOMAIN", ""),
            mailgun_from=os.getenv("MAILGUN_FROM", ""),
            mailgun_to=os.getenv("MAILGUN_TO", ""),
        )
        if not settings.metrics_key_prefix.strip().rstrip(":"):
            raise ValueError("USAGE_METRICS_KEY_PREFIX must not be empty")
        if settings.metrics_retention_days < MIN_USAGE_METRICS_RETENTION_DAYS:
            raise ValueError(f"USAGE_METRICS_RETENTION_DAYS must be at least {MIN_USAGE_METRICS_RETENTION_DAYS}")
        if settings.transport not in {"mailgun", "stdout"}:
            raise ValueError("USAGE_REPORT_TRANSPORT must be 'mailgun' or 'stdout'")
        if settings.transport == "mailgun":
            missing = [
                name
                for name, value in (
                    ("MAILGUN_API_KEY", settings.mailgun_api_key),
                    ("MAILGUN_DOMAIN", settings.mailgun_domain),
                    ("MAILGUN_FROM", settings.mailgun_from),
                    ("MAILGUN_TO", settings.mailgun_to),
                )
                if not value.strip()
            ]
            if missing:
                raise ValueError(f"Mailgun reporting requires: {', '.join(missing)}")
        return settings


class ReportTransport(Protocol):
    """Delivery adapter for a rendered weekly report."""

    def send(self, report: WeeklyUsageReport) -> str:
        """Deliver one report and return a provider message identifier."""
        ...


class MailgunReportTransport:
    """Send plain-text weekly reports through the Mailgun HTTP API."""

    def __init__(self, settings: UsageReportSettings):
        """Capture validated Mailgun endpoint and message settings."""
        self._api_url = settings.mailgun_api_url
        self._api_key = settings.mailgun_api_key
        self._domain = settings.mailgun_domain
        self._sender = settings.mailgun_from
        self._recipient = settings.mailgun_to

    def send(self, report: WeeklyUsageReport) -> str:
        """Deliver one report and return Mailgun's message identifier."""
        response = httpx.post(
            f"{self._api_url}/{self._domain}/messages",
            auth=("api", self._api_key),
            files={
                "from": (None, self._sender),
                "to": (None, self._recipient),
                "subject": (None, report_subject(report)),
                "text": (None, render_report(report)),
            },
            timeout=MAILGUN_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        body = response.json()
        message_id = body.get("id")
        return str(message_id) if message_id else f"mailgun-http-{response.status_code}"


class StdoutReportTransport:
    """Write reports to the service log for diagnostics and manual use."""

    def send(self, report: WeeklyUsageReport) -> str:
        """Log one report and return a local delivery identifier."""
        REPORTER_LOGGER.info("\n%s", render_report(report))
        return f"stdout:{report.week_id}"


def report_subject(report: WeeklyUsageReport) -> str:
    """Return a stable subject identifying the report period."""
    return f"Nurse Scheduling backend usage: {report.week_id}"


def render_report(report: WeeklyUsageReport) -> str:
    """Render a plain-text CSV table of minimal per-job telemetry."""
    timezone_name = getattr(report.starts_at.tzinfo, "key", None) or report.starts_at.tzname() or "local time"
    output = io.StringIO()
    output.write(
        "\n".join(
            [
                report_subject(report),
                (
                    f"Period: {report.starts_at.isoformat()} to {report.ends_at.isoformat()} "
                    f"({timezone_name}, end exclusive)"
                ),
                f"Jobs: {len(report.entries)}",
                "",
            ]
        )
    )
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(
        [
            "job_id",
            "client_id",
            "solver",
            "state",
            "created_at",
            "started_at",
            "finished_at",
            "queue_wait_seconds",
            "run_seconds",
            "total_seconds",
            "outcome",
            "failure_code",
            "solver_status",
            "termination_reason",
            "timeout_seconds",
            "download_count",
        ]
    )
    for entry in report.entries:
        writer.writerow(
            [
                entry.job_id,
                entry.client_id,
                entry.solver,
                entry.state.value,
                entry.created_at.isoformat(),
                entry.started_at.isoformat() if entry.started_at is not None else "",
                entry.finished_at.isoformat() if entry.finished_at is not None else "",
                entry.queue_wait_seconds if entry.queue_wait_seconds is not None else "",
                entry.run_seconds if entry.run_seconds is not None else "",
                entry.total_seconds if entry.total_seconds is not None else "",
                entry.outcome or "",
                entry.failure_code or "",
                entry.solver_status or "",
                entry.termination_reason or "",
                entry.timeout_seconds,
                entry.download_count,
            ]
        )
    output.write("\nTelemetry excludes scheduling inputs, filenames, email addresses, and IP addresses.\n")
    return output.getvalue()


class UsageReporter:
    """Claim and deliver every retained completed week that is not checkpointed."""

    def __init__(
        self,
        metrics: RedisUsageMetrics,
        transport: ReportTransport,
        *,
        retry_delays: Sequence[float] = REPORT_RETRY_DELAYS_SECONDS,
        retry_wait: Callable[[float], bool] | None = None,
        minimum_interval_seconds: int = MIN_REPORT_INTERVAL_SECONDS,
    ):
        """Compose durable telemetry storage with one delivery transport."""
        self._metrics = metrics
        self._transport = transport
        self._retry_delays = tuple(retry_delays)
        if any(delay < 0 for delay in self._retry_delays):
            raise ValueError("Report retry delays must be nonnegative")
        if minimum_interval_seconds < 0:
            raise ValueError("Minimum report interval must be nonnegative")
        self._retry_wait = retry_wait or self._sleep_for_retry
        self._minimum_interval_seconds = minimum_interval_seconds

    @staticmethod
    def _sleep_for_retry(delay: float) -> bool:
        """Wait before a delivery retry and report that no stop was requested."""
        time_module.sleep(delay)
        return False

    def _wait_for_delivery_slot(self) -> bool:
        """Reserve the shared delivery slot, waiting when another attempt owns it."""
        if self._minimum_interval_seconds == 0:
            return True
        while True:
            remaining = self._metrics.reserve_report_delivery(self._minimum_interval_seconds)
            if remaining == 0:
                return True
            if self._retry_wait(remaining):
                return False

    def _send(self, report: WeeklyUsageReport) -> str:
        """Send one report with bounded retries inside its delivery lease."""
        for attempt in range(len(self._retry_delays) + 1):
            if attempt > 0 and not self._wait_for_delivery_slot():
                raise RuntimeError("Reporter stopped before delivery retry")
            try:
                return self._transport.send(report)
            except Exception as error:
                if attempt == len(self._retry_delays):
                    raise
                delay = self._retry_delays[attempt]
                REPORTER_LOGGER.warning(
                    "[usage-report] delivery retry week=%s delay_seconds=%s error=%s",
                    report.week_id,
                    delay,
                    error,
                )
                if self._retry_wait(delay):
                    raise RuntimeError("Reporter stopped before delivery retry") from error
        raise AssertionError("delivery retry loop ended without returning or raising")

    def run_once(self, now: datetime | None = None, *, local_hour: int = 0) -> bool:
        """Attempt every due report and return whether every delivery succeeded."""
        observed_at = now or datetime.now(timezone.utc)
        successful = True
        for week_id in self._metrics.reportable_week_ids(observed_at, local_hour=local_hour):
            report = self._metrics.load_week(week_id)
            if not report.entries or self._metrics.report_was_sent(week_id):
                continue
            if not self._wait_for_delivery_slot():
                break
            token = self._metrics.acquire_report(week_id)
            if token is None:
                continue
            try:
                message_id = self._send(report)
                if not self._metrics.record_report_sent(report, token, message_id, datetime.now(timezone.utc)):
                    raise RuntimeError("Report delivery lease expired before the checkpoint was stored")
                REPORTER_LOGGER.info("[usage-report] sent week=%s message_id=%s", week_id, message_id)
            except Exception as error:
                successful = False
                self._metrics.record_report_failure(week_id, token, str(error), datetime.now(timezone.utc))
                REPORTER_LOGGER.exception("[usage-report] delivery failed week=%s", week_id)
        return successful


def _transport(settings: UsageReportSettings) -> ReportTransport:
    """Construct the configured delivery adapter."""
    if settings.transport == "stdout":
        return StdoutReportTransport()
    return MailgunReportTransport(settings)


def next_report_deadline(now: datetime, report_timezone: tzinfo, local_hour: int) -> datetime:
    """Return the next local Sunday reporting deadline after `now`."""
    if now.tzinfo is None:
        raise ValueError("Reporter timestamps must include a timezone")
    if not 0 <= local_hour <= 23:
        raise ValueError("local_hour must be between 0 and 23")
    local_now = now.astimezone(report_timezone)
    sunday = local_now.date() - timedelta(days=(local_now.weekday() + 1) % 7)
    deadline = datetime.combine(sunday, time(hour=local_hour), tzinfo=report_timezone)
    if deadline <= local_now:
        deadline = datetime.combine(sunday + timedelta(days=7), time(hour=local_hour), tzinfo=report_timezone)
    return deadline


def next_report_wait_seconds(now: datetime, report_timezone: tzinfo, local_hour: int) -> float:
    """Wait for the next deadline, with a minimum guard against tight loops."""
    deadline = next_report_deadline(now, report_timezone, local_hour)
    return max(
        MIN_REPORT_INTERVAL_SECONDS,
        (deadline.astimezone(timezone.utc) - now.astimezone(timezone.utc)).total_seconds(),
    )


def main() -> int:
    """Run once or deliver after each weekly deadline until stopped."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Attempt completed unsent reports immediately and exit",
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    settings = UsageReportSettings.from_env()
    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    client.ping()
    report_timezone = machine_timezone()
    metrics = RedisUsageMetrics(
        client,
        key_prefix=settings.metrics_key_prefix,
        retention_days=settings.metrics_retention_days,
        report_timezone=report_timezone,
    )
    stopped = threading.Event()
    reporter = UsageReporter(metrics, _transport(settings), retry_wait=stopped.wait)
    if arguments.once:
        return 0 if reporter.run_once(local_hour=settings.local_hour) else 1

    def request_stop(_signal_number, _frame) -> None:
        """Interrupt the weekly wait after a normal container stop signal."""
        stopped.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    REPORTER_LOGGER.info(
        "[usage-report] scheduled Sunday at %02d:00 timezone=%s",
        settings.local_hour,
        getattr(report_timezone, "key", None) or datetime.now(report_timezone).tzname(),
    )
    reporter.run_once(datetime.now(timezone.utc), local_hour=settings.local_hour)
    while not stopped.is_set():
        now = datetime.now(timezone.utc)
        deadline = next_report_deadline(now, report_timezone, settings.local_hour)
        wait_seconds = next_report_wait_seconds(now, report_timezone, settings.local_hour)
        REPORTER_LOGGER.info("[usage-report] next deadline=%s", deadline.isoformat())
        if stopped.wait(wait_seconds):
            break
        reporter.run_once(datetime.now(timezone.utc), local_hour=settings.local_hour)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
