"""Minimal per-job usage telemetry backed by Redis."""

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

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import redis

from .config import MIN_USAGE_METRICS_RETENTION_DAYS
from .jobs.models import Job, JobState

REPORT_LOCK_SECONDS = 30 * 60
"""Lease covering an initial delivery and two ten-minute-spaced retries."""


def _decode(value: bytes | str) -> str:
    """Normalize one Redis response value to text."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


def machine_timezone() -> tzinfo:
    """Load the machine timezone, including daylight-saving transitions."""
    timezone_name = os.getenv("TZ", "").strip()
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            pass
    try:
        with Path("/etc/localtime").open("rb") as timezone_file:
            return ZoneInfo.from_file(timezone_file)
    except (OSError, ValueError):
        return datetime.now().astimezone().tzinfo or timezone.utc


def week_id_for(occurred_at: datetime, report_timezone: tzinfo | None = None) -> str:
    """Return the local Sunday date identifying a reporting week."""
    if occurred_at.tzinfo is None:
        raise ValueError("Usage telemetry timestamps must include a timezone")
    local_date = occurred_at.astimezone(report_timezone or machine_timezone()).date()
    sunday = local_date - timedelta(days=(local_date.weekday() + 1) % 7)
    return sunday.isoformat()


def week_bounds(week_id: str, report_timezone: tzinfo | None = None) -> tuple[datetime, datetime]:
    """Return local Sunday boundaries for one reporting week."""
    try:
        sunday = date.fromisoformat(week_id)
        if sunday.isoformat() != week_id or sunday.weekday() != 6:
            raise ValueError
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid Sunday week start: {week_id}") from error
    selected_timezone = report_timezone or machine_timezone()
    starts_at = datetime.combine(sunday, time.min, tzinfo=selected_timezone)
    ends_at = datetime.combine(sunday + timedelta(days=7), time.min, tzinfo=selected_timezone)
    return starts_at, ends_at


@dataclass(frozen=True)
class JobTelemetry:
    """Minimal lifecycle information retained independently of job payloads."""

    job_id: str
    client_id: str
    solver: str
    state: JobState
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    queue_wait_seconds: float | None
    run_seconds: float | None
    total_seconds: float | None
    outcome: str | None
    failure_code: str | None
    solver_status: str | None
    termination_reason: str | None
    timeout_seconds: int
    download_count: int


@dataclass(frozen=True)
class WeeklyUsageReport:
    """Per-job telemetry associated with one completed local week."""

    week_id: str
    starts_at: datetime
    ends_at: datetime
    entries: tuple[JobTelemetry, ...]


class RedisUsageMetrics:
    """Stage job telemetry atomically and coordinate weekly reports."""

    def __init__(
        self,
        client: redis.Redis,
        *,
        key_prefix: str,
        retention_days: int,
        report_timezone: tzinfo | None = None,
    ):
        """Configure an isolated telemetry namespace on an existing Redis client."""
        self._redis = client
        self._prefix = key_prefix.rstrip(":")
        if not self._prefix:
            raise ValueError("USAGE_METRICS_KEY_PREFIX must not be empty")
        if retention_days < MIN_USAGE_METRICS_RETENTION_DAYS:
            raise ValueError(f"USAGE_METRICS_RETENTION_DAYS must be at least {MIN_USAGE_METRICS_RETENTION_DAYS}")
        self._retention_days = retention_days
        self._timezone = report_timezone or machine_timezone()

    def stage_job_created(self, transaction: Any, job: Job) -> None:
        """Store a queued telemetry row with the job creation transaction."""
        self._stage_snapshot(transaction, job, job.created_at)

    def stage_job_started(self, transaction: Any, job: Job) -> None:
        """Update a telemetry row with start and queue-wait information."""
        self._stage_snapshot(transaction, job, job.started_at or job.created_at)

    def stage_job_transition(self, transaction: Any, previous: Job, updated: Job) -> None:
        """Update a telemetry row when a job first reaches a terminal state."""
        if previous.state.terminal or not updated.state.terminal:
            return
        self._stage_snapshot(transaction, updated, updated.finished_at or datetime.now(timezone.utc))

    def record_download(self, job_id: str, occurred_at: datetime) -> None:
        """Count one successful artifact lookup on an existing telemetry row."""
        entry_key = self._entry_key(job_id)
        week_id = week_id_for(occurred_at, self._timezone)
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(entry_key)
                    if not transaction.exists(entry_key):
                        transaction.unwatch()
                        return
                    transaction.multi()
                    self._stage_week_reference(transaction, week_id, job_id, occurred_at)
                    transaction.hincrby(entry_key, "download_count", 1)
                    transaction.expireat(entry_key, self._week_expires_at(week_id))
                    transaction.execute()
                    return
            except redis.WatchError:
                continue

    def reportable_week_ids(self, now: datetime, *, local_hour: int = 0) -> list[str]:
        """Return retained event weeks whose delivery deadline has passed."""
        if now.tzinfo is None:
            raise ValueError("Reporter timestamps must include a timezone")
        if not 0 <= local_hour <= 23:
            raise ValueError("local_hour must be between 0 and 23")

        candidates = self._candidate_report_week_ids(now, local_hour)
        with self._redis.pipeline() as transaction:
            for week_id in candidates:
                transaction.zcard(self._week_jobs_key(week_id))
            bucket_sizes = transaction.execute()
        return [week_id for week_id, size in zip(candidates, bucket_sizes, strict=True) if size]

    def _candidate_report_week_ids(self, now: datetime, local_hour: int) -> list[str]:
        """Return completed week IDs that may still contain telemetry."""
        local_now = now.astimezone(self._timezone)
        this_sunday = local_now.date() - timedelta(days=(local_now.weekday() + 1) % 7)
        report_time = datetime.combine(
            this_sunday,
            time(hour=local_hour),
            tzinfo=self._timezone,
        )

        latest_report_sunday = this_sunday - timedelta(days=7)
        if local_now < report_time:
            # The week ending this Sunday is not reportable before report_time.
            latest_report_sunday -= timedelta(days=7)

        candidate_week_ids: list[str] = []
        sunday = latest_report_sunday
        while True:
            week_id = sunday.isoformat()
            _, next_sunday = week_bounds(week_id, self._timezone)
            if next_sunday + timedelta(days=self._retention_days) <= local_now:
                break
            candidate_week_ids.append(week_id)
            sunday -= timedelta(days=7)
        return list(reversed(candidate_week_ids))

    def load_week(self, week_id: str) -> WeeklyUsageReport:
        """Load the latest telemetry rows associated with one week."""
        starts_at, ends_at = week_bounds(week_id, self._timezone)
        raw_ids = self._redis.zrangebyscore(
            self._week_jobs_key(week_id),
            starts_at.timestamp(),
            f"({ends_at.timestamp()}",
        )
        job_ids = sorted(_decode(raw_id) for raw_id in raw_ids)
        with self._redis.pipeline() as transaction:
            for job_id in job_ids:
                transaction.hgetall(self._entry_key(job_id))
            raw_entries = transaction.execute()
        entries = [self._parse_entry(raw_entry) for raw_entry in raw_entries if raw_entry]
        return WeeklyUsageReport(
            week_id=week_id,
            starts_at=starts_at,
            ends_at=ends_at,
            entries=tuple(sorted(entries, key=lambda entry: (entry.created_at, entry.job_id))),
        )

    def acquire_report(self, week_id: str) -> str | None:
        """Acquire the delivery lease unless this week was already reported."""
        if self.report_was_sent(week_id):
            return None
        token = uuid4().hex
        if not self._redis.set(self._report_lock_key(week_id), token, nx=True, ex=REPORT_LOCK_SECONDS):
            return None
        if self.report_was_sent(week_id):
            self._release_report_lock(week_id, token)
            return None
        return token

    def report_was_sent(self, week_id: str) -> bool:
        """Return whether one week's delivery is already checkpointed."""
        return self._redis.hget(self._delivery_key(week_id), "status") in {b"sent", "sent"}

    def reserve_report_delivery(self, interval_seconds: int) -> int:
        """Reserve a global delivery slot or return how long the caller must wait."""
        if interval_seconds <= 0:
            raise ValueError("Report delivery interval must be positive")
        key = self._delivery_interval_key()
        if self._redis.set(key, "reserved", nx=True, ex=interval_seconds):
            return 0

        remaining_seconds = self._redis.ttl(key)
        if remaining_seconds == -1:
            # Repair a malformed guard that has no expiry.
            self._redis.expire(key, interval_seconds)
            return interval_seconds
        if remaining_seconds == -2:
            # The guard expired between SET and TTL. Retry after a short pause.
            return 1
        return max(1, remaining_seconds)

    def record_report_sent(
        self,
        report: WeeklyUsageReport,
        token: str,
        message_id: str,
        sent_at: datetime,
    ) -> bool:
        """Checkpoint delivery without changing retained telemetry rows."""
        return self._finish_report_attempt(
            report.week_id,
            token,
            mapping={
                "status": "sent",
                "message_id": message_id,
                "sent_at": sent_at.astimezone(timezone.utc).isoformat(),
                "last_error": "",
            },
        )

    def record_report_failure(self, week_id: str, token: str, error: str, failed_at: datetime) -> bool:
        """Persist a retryable delivery failure while retaining every row."""
        return self._finish_report_attempt(
            week_id,
            token,
            mapping={
                "status": "failed",
                "failed_at": failed_at.astimezone(timezone.utc).isoformat(),
                "last_error": error[:500],
            },
        )

    def _finish_report_attempt(
        self,
        week_id: str,
        token: str,
        *,
        mapping: dict[str, str],
    ) -> bool:
        """Update delivery state and release the lease."""
        lock_key = self._report_lock_key(week_id)
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(lock_key)
                    current_token = transaction.get(lock_key)
                    if current_token is None or _decode(current_token) != token:
                        transaction.unwatch()
                        return False
                    delivery_key = self._delivery_key(week_id)
                    transaction.multi()
                    transaction.hset(delivery_key, mapping=mapping)
                    transaction.hincrby(delivery_key, "attempts", 1)
                    transaction.expireat(delivery_key, self._week_expires_at(week_id))
                    transaction.delete(lock_key)
                    transaction.execute()
                    return True
            except redis.WatchError:
                continue

    def _release_report_lock(self, week_id: str, token: str) -> None:
        """Release a report lease only when its token still matches."""
        lock_key = self._report_lock_key(week_id)
        while True:
            try:
                with self._redis.pipeline() as transaction:
                    transaction.watch(lock_key)
                    current_token = transaction.get(lock_key)
                    if current_token is None or _decode(current_token) != token:
                        transaction.unwatch()
                        return
                    transaction.multi()
                    transaction.delete(lock_key)
                    transaction.execute()
                    return
            except redis.WatchError:
                continue

    def _stage_snapshot(self, transaction: Any, job: Job, occurred_at: datetime) -> None:
        """Write the latest minimal snapshot and associate it with its event week."""
        week_id = week_id_for(occurred_at, self._timezone)
        self._stage_week_reference(transaction, week_id, job.id, occurred_at)
        transaction.hset(self._entry_key(job.id), mapping=self._entry_mapping(job))
        transaction.expireat(self._entry_key(job.id), self._week_expires_at(week_id))

    def _stage_week_reference(
        self,
        transaction: Any,
        week_id: str,
        job_id: str,
        occurred_at: datetime,
    ) -> None:
        """Associate a job with the exact week containing one event."""
        week_jobs_key = self._week_jobs_key(week_id)
        transaction.zadd(week_jobs_key, {job_id: occurred_at.timestamp()})
        transaction.expireat(week_jobs_key, self._week_expires_at(week_id))

    @staticmethod
    def _entry_mapping(job: Job) -> dict[str, str | int | float]:
        """Serialize the reportable fields available in one job snapshot."""
        mapping: dict[str, str | int | float] = {
            "job_id": job.id,
            "client_id": job.request.client_id,
            "solver": job.request.solver,
            "state": job.state.value,
            "created_at": job.created_at.isoformat(),
            "timeout_seconds": job.request.timeout_seconds,
        }
        if job.started_at is not None:
            mapping["started_at"] = job.started_at.isoformat()
            mapping["queue_wait_seconds"] = max(0.0, (job.started_at - job.created_at).total_seconds())
        if job.finished_at is not None:
            mapping["finished_at"] = job.finished_at.isoformat()
            mapping["total_seconds"] = max(0.0, (job.finished_at - job.created_at).total_seconds())
            if job.started_at is not None:
                mapping["run_seconds"] = max(0.0, (job.finished_at - job.started_at).total_seconds())
        if job.result is not None:
            mapping["outcome"] = job.result.outcome.value
            mapping["solver_status"] = job.result.solver_status
            if job.result.termination_reason is not None:
                mapping["termination_reason"] = job.result.termination_reason
        if job.failure is not None:
            mapping["failure_code"] = job.failure.code
        return mapping

    @staticmethod
    def _parse_entry(raw_entry: dict[bytes | str, bytes | str]) -> JobTelemetry:
        """Deserialize one Redis telemetry hash."""
        values = {_decode(key): _decode(value) for key, value in raw_entry.items()}

        def optional_datetime(name: str) -> datetime | None:
            return datetime.fromisoformat(values[name]) if name in values else None

        def optional_float(name: str) -> float | None:
            return float(values[name]) if name in values else None

        return JobTelemetry(
            job_id=values["job_id"],
            client_id=values["client_id"],
            solver=values["solver"],
            state=JobState(values["state"]),
            created_at=datetime.fromisoformat(values["created_at"]),
            started_at=optional_datetime("started_at"),
            finished_at=optional_datetime("finished_at"),
            queue_wait_seconds=optional_float("queue_wait_seconds"),
            run_seconds=optional_float("run_seconds"),
            total_seconds=optional_float("total_seconds"),
            outcome=values.get("outcome"),
            failure_code=values.get("failure_code"),
            solver_status=values.get("solver_status"),
            termination_reason=values.get("termination_reason"),
            timeout_seconds=int(values["timeout_seconds"]),
            download_count=int(values.get("download_count", 0)),
        )

    def _week_expires_at(self, week_id: str) -> int:
        """Return the end of one week's report eligibility window."""
        _starts_at, ends_at = week_bounds(week_id, self._timezone)
        return int((ends_at + timedelta(days=self._retention_days)).timestamp())

    def _entry_key(self, job_id: str) -> str:
        """Return the Redis hash key for one minimal telemetry row."""
        return f"{self._prefix}:job:{job_id}"

    def _week_jobs_key(self, week_id: str) -> str:
        """Return the timestamped jobs associated with one reporting week."""
        return f"{self._prefix}:week:{week_id}:members"

    def _delivery_key(self, week_id: str) -> str:
        """Return the delivery checkpoint key for a week."""
        return f"{self._prefix}:report:{week_id}"

    def _report_lock_key(self, week_id: str) -> str:
        """Return the delivery lease key for a week."""
        return f"{self._prefix}:report:{week_id}:lock"

    def _delivery_interval_key(self) -> str:
        """Return the shared minimum-delivery-interval key."""
        return f"{self._prefix}:report:delivery_interval"
