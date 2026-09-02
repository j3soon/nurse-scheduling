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
import math
import os
import signal
import threading
import time as time_module
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo
from string import Formatter
from typing import Protocol
from urllib.parse import urlsplit

import httpx
import redis

from ..sentry import flush_sentry, init_sentry
from ..version import get_app_version
from .config import DEFAULT_USAGE_METRICS_RETENTION_DAYS, MIN_USAGE_METRICS_RETENTION_DAYS
from .usage_metrics import REPORT_LOCK_SECONDS, RedisUsageMetrics, WeeklyUsageReport, machine_timezone

REPORTER_LOGGER = logging.getLogger("nurse_scheduling.usage_report")
REDIS_TIMEOUT_SECONDS = 5.0
MAILGUN_TIMEOUT_SECONDS = 15.0
MAILGUN_API_HOSTS = frozenset({"api.mailgun.net", "api.eu.mailgun.net"})
MAILGUN_API_PATH = "/v3"
DEFAULT_MAILGUN_API_URL = "https://api.mailgun.net/v3"
DEFAULT_USAGE_REPORT_SUBJECT = "Nurse Scheduling backend usage: {week_id}"
MIN_REPORT_INTERVAL_SECONDS = 10 * 60
"""Minimum delay between any two report delivery attempts."""
REPORT_RETRY_DELAYS_SECONDS = (MIN_REPORT_INTERVAL_SECONDS,) * 2
"""Bounded delays for transient delivery failures during one weekly run."""
REPORT_LEASE_RENEWAL_SECONDS = REPORT_LOCK_SECONDS // 3
"""Maximum time between report lease renewals while delivery is pending."""
RUN_MINUTES_BUCKETS = (
    ("[0,1)", 0.0, 1.0),
    ("[1,3)", 1.0, 3.0),
    ("[3,10)", 3.0, 10.0),
    ("[10,30)", 10.0, 30.0),
    ("[30,60)", 30.0, 60.0),
    ("[60,inf)", 60.0, None),
)
"""Disjoint runtime ranges used in the report summary."""


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


def _validated_mailgun_api_url(value: str) -> str:
    """Validate and normalize a credential-bearing Mailgun API base URL."""
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except ValueError as error:
        raise ValueError("MAILGUN_API_URL must be an approved Mailgun HTTPS API URL") from error
    if (
        parsed.scheme.lower() != "https"
        or parsed.hostname not in MAILGUN_API_HOSTS
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != MAILGUN_API_PATH
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("MAILGUN_API_URL must be an approved Mailgun HTTPS API URL")
    return f"https://{parsed.hostname}{MAILGUN_API_PATH}"


def _validated_subject_template(value: str) -> str:
    """Validate a one-line report subject with an optional week placeholder."""
    subject = value.strip()
    if not subject or "\n" in subject or "\r" in subject:
        raise ValueError("USAGE_REPORT_SUBJECT must be one nonempty line")
    try:
        fields = [
            (field_name, format_spec, conversion)
            for _literal, field_name, format_spec, conversion in Formatter().parse(subject)
            if field_name is not None
        ]
    except ValueError as error:
        raise ValueError("USAGE_REPORT_SUBJECT must be a valid template") from error
    if any(field_name != "week_id" or format_spec or conversion for field_name, format_spec, conversion in fields):
        raise ValueError("USAGE_REPORT_SUBJECT supports only the {week_id} placeholder")
    return subject


@dataclass(frozen=True)
class UsageReportSettings:
    """Environment-backed settings for the standalone reporter."""

    redis_url: str
    metrics_key_prefix: str
    metrics_retention_days: int
    local_hour: int
    subject: str
    transport: str
    mailgun_api_url: str
    mailgun_api_key: str
    mailgun_domain: str
    mailgun_from: str
    mailgun_to: str

    @classmethod
    def from_env(cls) -> "UsageReportSettings":
        """Load and validate reporter configuration."""
        transport = os.getenv("USAGE_REPORT_TRANSPORT", "stdout").strip().lower()
        subject = _validated_subject_template(os.getenv("USAGE_REPORT_SUBJECT", DEFAULT_USAGE_REPORT_SUBJECT))
        mailgun_api_url = os.getenv("MAILGUN_API_URL", DEFAULT_MAILGUN_API_URL).rstrip("/")
        if transport == "mailgun":
            mailgun_api_url = _validated_mailgun_api_url(mailgun_api_url)
        settings = cls(
            redis_url=os.getenv("JOB_REDIS_URL", "redis://localhost:6379/0"),
            metrics_key_prefix=os.getenv("USAGE_METRICS_KEY_PREFIX", "nurse_scheduling:usage:v0"),
            metrics_retention_days=_positive_int(
                "USAGE_METRICS_RETENTION_DAYS",
                DEFAULT_USAGE_METRICS_RETENTION_DAYS,
            ),
            local_hour=_hour("USAGE_REPORT_LOCAL_HOUR", 0),
            subject=subject,
            transport=transport,
            mailgun_api_url=mailgun_api_url,
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
        if settings.transport == "stdout":
            configured_mailgun_settings = [
                name
                for name, value in (
                    ("MAILGUN_API_KEY", settings.mailgun_api_key),
                    ("MAILGUN_DOMAIN", settings.mailgun_domain),
                    ("MAILGUN_FROM", settings.mailgun_from),
                    ("MAILGUN_TO", settings.mailgun_to),
                )
                if value.strip()
            ]
            if settings.mailgun_api_url.strip().rstrip("/") != DEFAULT_MAILGUN_API_URL:
                configured_mailgun_settings.append("MAILGUN_API_URL")
            if configured_mailgun_settings:
                REPORTER_LOGGER.warning(
                    "[usage-report] Mailgun settings are configured while "
                    "USAGE_REPORT_TRANSPORT=stdout. Reports will not be emailed settings=%s",
                    ",".join(configured_mailgun_settings),
                )
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
                REPORTER_LOGGER.warning(
                    "[usage-report] USAGE_REPORT_TRANSPORT=mailgun but required settings are missing settings=%s",
                    ",".join(missing),
                )
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
        self._api_url = _validated_mailgun_api_url(settings.mailgun_api_url)
        self._api_key = settings.mailgun_api_key
        self._domain = settings.mailgun_domain
        self._sender = settings.mailgun_from
        self._recipient = settings.mailgun_to
        self._subject = _validated_subject_template(settings.subject)

    def send(self, report: WeeklyUsageReport) -> str:
        """Deliver one report and return Mailgun's message identifier."""
        response = httpx.post(
            f"{self._api_url}/{self._domain}/messages",
            auth=("api", self._api_key),
            files={
                "from": (None, self._sender),
                "to": (None, self._recipient),
                "subject": (None, report_subject(report, self._subject)),
                "text": (None, render_report(report, self._subject)),
            },
            timeout=MAILGUN_TIMEOUT_SECONDS,
            follow_redirects=False,
        )
        response.raise_for_status()
        body = response.json()
        message_id = body.get("id")
        return str(message_id) if message_id else f"mailgun-http-{response.status_code}"


class StdoutReportTransport:
    """Write reports to the service log for diagnostics and manual use."""

    def __init__(self, subject: str = DEFAULT_USAGE_REPORT_SUBJECT):
        """Capture the validated report subject template."""
        self._subject = _validated_subject_template(subject)

    def send(self, report: WeeklyUsageReport) -> str:
        """Log one report and return a local delivery identifier."""
        REPORTER_LOGGER.info("\n%s", render_report(report, self._subject))
        return f"stdout:{report.week_id}"


def report_subject(report: WeeklyUsageReport, subject: str = DEFAULT_USAGE_REPORT_SUBJECT) -> str:
    """Return a stable subject identifying the report period."""
    return subject.format(week_id=report.week_id)


def _counts_summary(values: Sequence[str]) -> str:
    """Render sorted value counts on one compact summary line."""
    counts = Counter(values)
    return ", ".join(f"{value}={count}" for value, count in sorted(counts.items())) or "none"


def _run_minutes_summary(report: WeeklyUsageReport) -> str:
    """Render disjoint runtime bucket counts, including unavailable values."""
    counts = {label: 0 for label, _lower, _upper in RUN_MINUTES_BUCKETS}
    unavailable = 0
    for entry in report.entries:
        seconds = entry.run_seconds
        if seconds is None or not math.isfinite(seconds):
            unavailable += 1
            continue
        minutes = seconds / 60
        for label, lower, upper in RUN_MINUTES_BUCKETS:
            if lower <= minutes and (upper is None or minutes < upper):
                counts[label] += 1
                break
        else:
            unavailable += 1
    summaries = [f"{label}={counts[label]}" for label, _lower, _upper in RUN_MINUTES_BUCKETS]
    summaries.append(f"unavailable={unavailable}")
    return ", ".join(summaries)


def render_report(report: WeeklyUsageReport, subject: str = DEFAULT_USAGE_REPORT_SUBJECT) -> str:
    """Render a plain-text summary and CSV table of minimal per-job telemetry."""
    local_timezone = machine_timezone()
    starts_at = report.starts_at.astimezone(local_timezone)
    ends_at = report.ends_at.astimezone(local_timezone)
    timezone_name = getattr(local_timezone, "key", None) or starts_at.tzname() or "local time"
    states = _counts_summary([entry.state.value for entry in report.entries])
    outcomes = _counts_summary([entry.outcome or "unavailable" for entry in report.entries])
    output = io.StringIO()
    output.write(
        "\n".join(
            [
                report_subject(report, subject),
                "",
                (f"Period: {starts_at.isoformat()} to {ends_at.isoformat()} ({timezone_name}, end exclusive)"),
                f"Jobs: {len(report.entries)}",
                f"States: {states}",
                f"Outcomes: {outcomes}",
                f"Run minutes: {_run_minutes_summary(report)}",
                "",
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
    """Claim and deliver scheduled or explicitly forced weekly usage reports."""

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

    def _require_report_lease(self, week_id: str, token: str) -> None:
        """Renew a report lease or stop before another delivery can begin."""
        if not self._metrics.renew_report(week_id, token):
            raise RuntimeError("Report delivery lease expired before transport send")

    def _wait_with_report_lease(self, delay: float, week_id: str, token: str) -> bool:
        """Wait in bounded intervals while keeping a report lease valid."""
        self._require_report_lease(week_id, token)
        remaining = delay
        if remaining == 0:
            if self._retry_wait(0):
                return False
            self._require_report_lease(week_id, token)
            return True
        while remaining > 0:
            interval = min(remaining, REPORT_LEASE_RENEWAL_SECONDS)
            if self._retry_wait(interval):
                return False
            remaining -= interval
            self._require_report_lease(week_id, token)
        return True

    def _wait_for_delivery_slot(self, report_lease: tuple[str, str] | None = None) -> bool:
        """Reserve the shared delivery slot, waiting when another attempt owns it."""
        if self._minimum_interval_seconds == 0:
            if report_lease is not None:
                self._require_report_lease(*report_lease)
            return True
        while True:
            remaining = self._metrics.reserve_report_delivery(self._minimum_interval_seconds)
            if remaining == 0:
                if report_lease is not None:
                    self._require_report_lease(*report_lease)
                return True
            if report_lease is None:
                stopped = self._retry_wait(remaining)
            else:
                stopped = not self._wait_with_report_lease(remaining, *report_lease)
            if stopped:
                return False

    def _send(self, report: WeeklyUsageReport, token: str, *, bypass_delivery_interval: bool = False) -> str:
        """Send one report with bounded retries inside its delivery lease."""
        report_lease = (report.week_id, token)
        for attempt in range(len(self._retry_delays) + 1):
            if attempt > 0 and not bypass_delivery_interval and not self._wait_for_delivery_slot(report_lease):
                raise RuntimeError("Reporter stopped before delivery retry")
            self._require_report_lease(*report_lease)
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
                if not self._wait_with_report_lease(delay, *report_lease):
                    raise RuntimeError("Reporter stopped before delivery retry") from error
        raise AssertionError("delivery retry loop ended without returning or raising")

    def run_once(
        self,
        now: datetime | None = None,
        *,
        local_hour: int = 0,
        force_latest: bool = False,
    ) -> bool:
        """Attempt every due report and return whether every delivery succeeded."""
        observed_at = now or datetime.now(timezone.utc)
        successful = True
        week_ids = self._metrics.reportable_week_ids(
            observed_at,
            local_hour=local_hour,
            include_current=force_latest,
        )
        if force_latest:
            week_ids = week_ids[-1:]
            if not week_ids:
                REPORTER_LOGGER.error("[usage-report] forced delivery failed reason=no-retained-telemetry")
                return False
        for week_id in week_ids:
            report = self._metrics.load_week(week_id)
            if not report.entries:
                if force_latest:
                    REPORTER_LOGGER.error(
                        "[usage-report] forced delivery failed week=%s reason=no-retained-entries",
                        week_id,
                    )
                    successful = False
                continue
            if not force_latest and self._metrics.report_was_sent(week_id):
                continue
            if not force_latest and not self._wait_for_delivery_slot():
                break
            token = self._metrics.acquire_report(week_id, force=force_latest)
            if token is None:
                if force_latest:
                    REPORTER_LOGGER.error(
                        "[usage-report] forced delivery failed week=%s reason=delivery-lock-held",
                        week_id,
                    )
                    successful = False
                continue
            preserved_sent_checkpoint = force_latest and self._metrics.report_was_sent(week_id)
            partial_week = force_latest and observed_at < report.ends_at
            try:
                message_id = self._send(report, token, bypass_delivery_interval=force_latest)
                sent_at = datetime.now(timezone.utc)
                if partial_week:
                    checkpoint_stored = self._metrics.record_partial_report_sent(report, token, message_id, sent_at)
                else:
                    checkpoint_stored = self._metrics.record_report_sent(report, token, message_id, sent_at)
                if not checkpoint_stored:
                    raise RuntimeError("Report delivery lease expired before the checkpoint was stored")
                REPORTER_LOGGER.info(
                    "[usage-report] sent week=%s partial=%s message_id=%s",
                    week_id,
                    str(partial_week).lower(),
                    message_id,
                )
            except Exception as error:
                successful = False
                failed_at = datetime.now(timezone.utc)
                if partial_week:
                    self._metrics.record_partial_report_failure(week_id, token, str(error), failed_at)
                elif preserved_sent_checkpoint:
                    self._metrics.record_forced_report_failure(week_id, token, str(error), failed_at)
                else:
                    self._metrics.record_report_failure(week_id, token, str(error), failed_at)
                REPORTER_LOGGER.exception("[usage-report] delivery failed week=%s", week_id)
        return successful


def _transport(settings: UsageReportSettings) -> ReportTransport:
    """Construct the configured delivery adapter."""
    if settings.transport == "stdout":
        return StdoutReportTransport(settings.subject)
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


def _run() -> int:
    """Run once or deliver after each weekly deadline until stopped."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once",
        action="store_true",
        help="Attempt completed unsent reports immediately and exit",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send the newest retained week now, including a partial or already sent week",
    )
    arguments = parser.parse_args()
    if arguments.force and not arguments.once:
        parser.error("--force requires --once")
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
        return 0 if reporter.run_once(local_hour=settings.local_hour, force_latest=arguments.force) else 1

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


def main() -> int:
    """Run the reporter with process-specific Sentry logging."""
    init_sentry(get_app_version(), app="usage-reporter")
    try:
        return _run()
    finally:
        flush_sentry()


if __name__ == "__main__":
    raise SystemExit(main())
