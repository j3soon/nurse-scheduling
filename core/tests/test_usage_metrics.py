"""Tests for Redis weekly job telemetry and reporting."""

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

# This test is mostly AI generated.

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import fakeredis
import pytest

from nurse_scheduling.server.config import ServerSettings
from nurse_scheduling.server.jobs.controller import JobController
from nurse_scheduling.server.jobs.models import (
    Job,
    JobRequest,
    JobState,
    OptimizationOutcome,
    OptimizationResult,
    StoredArtifact,
    StoreLimits,
)
from nurse_scheduling.server.usage_metrics import RedisUsageMetrics, week_bounds, week_id_for
from nurse_scheduling.server.usage_report import (
    MailgunReportTransport,
    UsageReporter,
    UsageReportSettings,
    next_report_deadline,
    next_report_wait_seconds,
    render_report,
)


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=False)


def _job(created_at: datetime, *, job_id: str = "job_metrics", client_id: str = "private-client-id") -> Job:
    return Job(
        id=job_id,
        state=JobState.QUEUED,
        request=JobRequest(
            input_name="private-filename.yaml",
            client_id=client_id,
            solver="ortools/cp-sat",
            prettify=True,
            timeout_seconds=60,
        ),
        created_at=created_at,
    )


def _stage(metrics: RedisUsageMetrics, callback) -> None:
    with metrics._redis.pipeline(transaction=True) as transaction:
        callback(transaction)
        transaction.execute()


def test_week_helpers_use_local_sunday_boundaries():
    local_timezone = timezone(timedelta(hours=8))
    before_sunday = datetime(2026, 8, 29, 15, 59, tzinfo=timezone.utc)
    after_sunday = before_sunday + timedelta(minutes=2)

    assert week_id_for(before_sunday, local_timezone) == "2026-08-23"
    assert week_id_for(after_sunday, local_timezone) == "2026-08-30"
    assert week_bounds("2026-08-23", local_timezone) == (
        datetime(2026, 8, 23, tzinfo=local_timezone),
        datetime(2026, 8, 30, tzinfo=local_timezone),
    )
    with pytest.raises(ValueError, match="Invalid Sunday week start"):
        week_bounds("not-a-week")
    with pytest.raises(ValueError, match="Invalid Sunday week start"):
        week_bounds("2026-08-24")


def test_redis_job_store_records_complete_lifecycle_atomically(monkeypatch):
    from nurse_scheduling.server.stores import redis as redis_store

    fake_server = fakeredis.FakeServer()
    monkeypatch.setattr(
        redis_store.redis.Redis,
        "from_url",
        lambda url, **kwargs: fakeredis.FakeRedis.from_url(url, server=fake_server, **kwargs),
    )
    store = redis_store.RedisJobStore(
        url="redis://localhost/0",
        key_prefix="test:jobs",
        usage_metrics_key_prefix="test:usage",
        usage_metrics_retention_days=30,
    )
    now = datetime(2026, 8, 24, 12, tzinfo=timezone.utc)
    clock = lambda: now
    record_download = store._usage_metrics.record_download
    monkeypatch.setattr(
        store._usage_metrics,
        "record_download",
        lambda job_id, _occurred_at: record_download(job_id, now),
    )
    controller = JobController(
        store,
        limits=StoreLimits(max_pending=4, max_retained=8),
        retention_seconds=60,
        worker_lease_seconds=90,
        clock=clock,
        id_factory=lambda: "job_metrics",
    )
    created = controller.create_job(
        input_name="private-filename.yaml",
        client_id="private-client-id",
        solver="ortools/cp-sat",
        prettify=True,
        timeout_seconds=60,
        input_bytes=b"private scheduling input",
    )
    now += timedelta(seconds=10)
    lease = controller.register_worker("worker")
    assert lease is not None
    running = controller.claim_next_job(lease)
    assert running is not None
    now += timedelta(seconds=20)
    result = OptimizationResult(
        outcome=OptimizationOutcome.OPTIMAL,
        score=42,
        solver_status="OPTIMAL",
        termination_reason="optimality_proven",
    )
    artifact = StoredArtifact("schedule.xlsx", "application/test", b"xlsx")
    completed = controller.complete_job(created.id, result, artifact, lease=lease)
    controller.complete_job(created.id, result, artifact, lease=lease)
    assert controller.get_artifact(created.id, "schedule.xlsx") == artifact
    controller.delete_job(created.id)

    report = store._usage_metrics.load_week("2026-08-23")
    entry = report.entries[0]

    assert completed.state == JobState.COMPLETED
    assert entry.job_id == "job_metrics"
    assert entry.client_id == "private-client-id"
    assert entry.solver == "ortools/cp-sat"
    assert entry.state == JobState.COMPLETED
    assert entry.queue_wait_seconds == 10
    assert entry.run_seconds == 20
    assert entry.total_seconds == 30
    assert entry.outcome == "optimal"
    assert entry.solver_status == "OPTIMAL"
    assert entry.termination_reason == "optimality_proven"
    assert entry.download_count == 1
    assert store._redis.get(store._job_key(created.id)) is None
    assert store._redis.get(store._input_key(created.id)) is None
    assert store._redis.get(store._artifact_key(created.id)) is None
    assert store._redis.exists("test:usage:job:job_metrics")
    assert b"input_name" not in store._redis.hgetall("test:usage:job:job_metrics")
    assert not list(store._redis.scan_iter("test:usage:*private-filename*"))


def test_terminal_events_are_bucketed_when_they_occur(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    created_at = datetime(2026, 8, 29, 23, 59, tzinfo=timezone.utc)
    submitted = _job(created_at)
    started = replace(submitted, state=JobState.RUNNING, started_at=created_at + timedelta(seconds=30))
    completed = replace(
        started,
        state=JobState.COMPLETED,
        finished_at=created_at + timedelta(minutes=2),
        result=OptimizationResult(
            outcome=OptimizationOutcome.FEASIBLE,
            score=1,
            solver_status="FEASIBLE",
        ),
    )

    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    _stage(metrics, lambda transaction: metrics.stage_job_started(transaction, started))
    _stage(metrics, lambda transaction: metrics.stage_job_transition(transaction, started, completed))

    first = metrics.load_week("2026-08-23")
    second = metrics.load_week("2026-08-30")
    assert first.entries == second.entries
    assert first.entries[0].state == JobState.COMPLETED
    assert first.entries[0].outcome == "feasible"
    assert first.entries[0].queue_wait_seconds == 30
    assert first.entries[0].run_seconds == 90
    assert redis_client.type("test:usage:week:2026-08-23:members") == b"zset"
    assert redis_client.zscore("test:usage:week:2026-08-23:members", "job_metrics") == started.started_at.timestamp()
    assert redis_client.zscore("test:usage:week:2026-08-30:members", "job_metrics") == completed.finished_at.timestamp()
    assert not redis_client.exists("test:usage:weeks")


def test_telemetry_preserves_the_requested_solver(redis_client):
    metrics = RedisUsageMetrics(redis_client, key_prefix="test:usage", retention_days=30)
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    submitted = replace(
        submitted,
        request=replace(submitted.request, solver="unknown\nreport-content"),
    )

    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))

    assert metrics.load_week("2026-08-23").entries[0].solver == "unknown\nreport-content"


def test_telemetry_keys_expire_after_the_report_window(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))

    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))

    expected_expiry = datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp()
    assert redis_client.expiretime("test:usage:job:job_metrics") == expected_expiry
    assert redis_client.expiretime("test:usage:week:2026-08-23:members") == expected_expiry


class _RecordingTransport:
    def __init__(self, failures: int = 0):
        self.failures = failures
        self.reports = []

    def send(self, report):
        self.reports.append(report)
        if len(self.reports) <= self.failures:
            raise RuntimeError("mail unavailable")
        return f"message-{report.week_id}"


def test_reporter_retries_failures_and_checkpoints_success(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    transport = _RecordingTransport(failures=1)
    reporter = UsageReporter(
        metrics,
        transport,
        retry_delays=(),
        minimum_interval_seconds=0,
    )
    now = datetime(2026, 8, 30, 10, tzinfo=timezone.utc)

    assert reporter.run_once(now) is False
    assert reporter.run_once(now) is True
    assert reporter.run_once(now) is True

    assert len(transport.reports) == 2
    delivery = redis_client.hgetall("test:usage:report:2026-08-23")
    assert delivery[b"status"] == b"sent"
    assert delivery[b"attempts"] == b"2"
    rendered = render_report(transport.reports[-1])
    assert "Jobs: 1" in rendered
    assert "job_id,client_id,solver,state" in rendered
    assert "private-client-id" in rendered
    assert "private-filename.yaml" not in rendered
    assert redis_client.exists("test:usage:job:job_metrics")


def test_reporter_retries_transport_within_one_weekly_run(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    transport = _RecordingTransport(failures=1)
    waits = []

    def wait(delay):
        waits.append(delay)
        return False

    reserve_delivery = Mock(side_effect=[0, 0])
    metrics.reserve_report_delivery = reserve_delivery

    reporter = UsageReporter(
        metrics,
        transport,
        retry_delays=(10 * 60,),
        retry_wait=wait,
    )

    assert reporter.run_once(datetime(2026, 8, 30, 10, tzinfo=timezone.utc)) is True
    assert len(transport.reports) == 2
    assert waits == [10 * 60]
    assert reserve_delivery.call_count == 2


def test_reporter_catches_up_retained_completed_weeks(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    older = _job(datetime(2026, 8, 10, 12, tzinfo=timezone.utc), job_id="older")
    newer = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc), job_id="newer")
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, older))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, newer))
    transport = _RecordingTransport()
    waits = []

    def wait(delay):
        waits.append(delay)
        return False

    reserve_delivery = Mock(side_effect=[0, 10 * 60, 0])
    metrics.reserve_report_delivery = reserve_delivery

    reporter = UsageReporter(
        metrics,
        transport,
        retry_delays=(),
        retry_wait=wait,
    )
    now = datetime(2026, 8, 30, 10, tzinfo=timezone.utc)

    assert reporter.run_once(now) is True
    assert [report.week_id for report in transport.reports] == ["2026-08-09", "2026-08-23"]
    assert waits == [10 * 60]
    assert reporter.run_once(now) is True


def test_reporter_force_resends_only_latest_reportable_week(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    older = _job(datetime(2026, 8, 10, 12, tzinfo=timezone.utc), job_id="older")
    newer = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc), job_id="newer")
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, older))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, newer))
    transport = _RecordingTransport()
    reporter = UsageReporter(metrics, transport, retry_delays=(), minimum_interval_seconds=0)
    now = datetime(2026, 8, 30, 10, tzinfo=timezone.utc)

    assert reporter.run_once(now) is True
    assert [report.week_id for report in transport.reports] == ["2026-08-09", "2026-08-23"]

    transport.reports.clear()
    assert reporter.run_once(now, force_latest=True) is True
    assert [report.week_id for report in transport.reports] == ["2026-08-23"]
    assert redis_client.hget("test:usage:report:2026-08-09", "attempts") == b"1"
    assert redis_client.hget("test:usage:report:2026-08-23", "attempts") == b"2"


def test_failed_forced_resend_preserves_successful_checkpoint(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    transport = _RecordingTransport()
    reporter = UsageReporter(metrics, transport, retry_delays=(), minimum_interval_seconds=0)
    now = datetime(2026, 8, 30, 10, tzinfo=timezone.utc)

    assert reporter.run_once(now) is True
    original_delivery = redis_client.hgetall("test:usage:report:2026-08-23")

    transport.failures = 2
    assert reporter.run_once(now, force_latest=True) is False
    forced_delivery = redis_client.hgetall("test:usage:report:2026-08-23")
    assert forced_delivery[b"status"] == b"sent"
    assert forced_delivery[b"message_id"] == original_delivery[b"message_id"]
    assert forced_delivery[b"sent_at"] == original_delivery[b"sent_at"]
    assert forced_delivery[b"attempts"] == b"2"
    assert forced_delivery[b"last_force_error"] == b"mail unavailable"

    assert reporter.run_once(now) is True
    assert len(transport.reports) == 2


def test_report_delivery_interval_is_shared_in_redis(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )

    assert metrics.reserve_report_delivery(10 * 60) == 0
    remaining = metrics.reserve_report_delivery(10 * 60)
    assert 10 * 60 - 1 <= remaining <= 10 * 60


def test_forced_report_still_respects_the_week_lock(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )

    assert metrics.acquire_report("2026-08-23") is not None
    assert metrics.acquire_report("2026-08-23", force=True) is None


def test_report_delivery_interval_repairs_guard_without_expiry(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    redis_client.set("test:usage:report:delivery_interval", "malformed")

    assert metrics.reserve_report_delivery(10 * 60) == 10 * 60
    remaining = redis_client.ttl("test:usage:report:delivery_interval")
    assert 10 * 60 - 1 <= remaining <= 10 * 60


def test_reporter_ignores_week_membership_outside_retention(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    redis_client.zadd(
        "test:usage:week:2026-07-26:members",
        {"expired-job": datetime(2026, 7, 27, tzinfo=timezone.utc).timestamp()},
    )
    transport = _RecordingTransport()
    reporter = UsageReporter(metrics, transport, retry_delays=())

    assert reporter.run_once(datetime(2026, 9, 2, tzinfo=timezone.utc)) is True
    assert transport.reports == []


def test_successful_report_retains_terminal_telemetry(redis_client):
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    completed = replace(
        submitted,
        state=JobState.COMPLETED,
        finished_at=submitted.created_at + timedelta(seconds=20),
        result=OptimizationResult(
            outcome=OptimizationOutcome.OPTIMAL,
            score=1,
            solver_status="OPTIMAL",
        ),
    )
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    _stage(metrics, lambda transaction: metrics.stage_job_transition(transaction, submitted, completed))
    terminal_expiry = int(datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp())
    assert redis_client.expiretime("test:usage:job:job_metrics") == terminal_expiry

    reporter = UsageReporter(metrics, _RecordingTransport())
    assert reporter.run_once(datetime(2026, 8, 30, 1, tzinfo=timezone.utc)) is True

    assert redis_client.exists("test:usage:job:job_metrics")
    assert redis_client.expiretime("test:usage:job:job_metrics") == terminal_expiry
    metrics.record_download("job_metrics", datetime(2026, 8, 30, 2, tzinfo=timezone.utc))
    assert redis_client.hget("test:usage:job:job_metrics", "download_count") == b"1"
    assert (
        redis_client.expiretime("test:usage:job:job_metrics")
        == datetime(
            2026,
            10,
            6,
            tzinfo=timezone.utc,
        ).timestamp()
    )


def test_server_metrics_are_opt_in_and_require_redis(monkeypatch):
    assert ServerSettings().usage_metrics_enabled is False
    with pytest.raises(ValueError, match="requires JOB_BACKEND=redis"):
        ServerSettings(usage_metrics_enabled=True)
    with pytest.raises(ValueError, match="must differ from JOB_REDIS_KEY_PREFIX"):
        ServerSettings(
            job_backend="redis",
            redis_key_prefix="same:prefix:",
            usage_metrics_enabled=True,
            usage_metrics_key_prefix="same:prefix",
        )

    monkeypatch.setenv("JOB_BACKEND", "redis")
    monkeypatch.setenv("USAGE_METRICS_ENABLED", "true")
    settings = ServerSettings.from_env()
    assert settings.usage_metrics_enabled is True
    assert settings.usage_metrics_key_prefix == "nurse_scheduling:usage:v0"
    assert settings.usage_metrics_retention_days == 30


def test_usage_metrics_require_enough_retention_for_weekly_reporting(monkeypatch, redis_client):
    with pytest.raises(ValueError, match="must be at least 9"):
        ServerSettings(
            job_backend="redis",
            usage_metrics_enabled=True,
            usage_metrics_retention_days=8,
        )
    with pytest.raises(ValueError, match="must be at least 9"):
        RedisUsageMetrics(redis_client, key_prefix="test:usage", retention_days=8)

    monkeypatch.setenv("USAGE_METRICS_RETENTION_DAYS", "8")
    with pytest.raises(ValueError, match="must be at least 9"):
        UsageReportSettings.from_env()


def test_redis_job_store_rejects_colliding_metrics_prefix():
    from nurse_scheduling.server.stores.redis import RedisJobStore

    with pytest.raises(ValueError, match="must differ from JOB_REDIS_KEY_PREFIX"):
        RedisJobStore(
            url="redis://unneeded",
            key_prefix="same:prefix",
            usage_metrics_key_prefix="same:prefix:",
        )


def test_reporter_stdout_mode_does_not_require_mailgun(monkeypatch):
    monkeypatch.delenv("USAGE_REPORT_TRANSPORT", raising=False)
    monkeypatch.delenv("USAGE_REPORT_SUBJECT", raising=False)
    for name in ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "MAILGUN_FROM", "MAILGUN_TO"):
        monkeypatch.delenv(name, raising=False)

    settings = UsageReportSettings.from_env()
    assert settings.transport == "stdout"
    assert settings.local_hour == 0
    assert settings.subject == "Nurse Scheduling backend usage: {week_id}"


def test_reporter_catches_up_only_after_the_local_weekly_deadline(redis_client):
    local_timezone = timezone(timedelta(hours=8))
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=local_timezone,
    )
    submitted = _job(datetime(2026, 8, 29, 15, tzinfo=timezone.utc))
    current_week = _job(
        datetime(2026, 8, 30, 2, tzinfo=timezone.utc),
        job_id="current-week",
    )
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, current_week))
    transport = _RecordingTransport()
    reporter = UsageReporter(metrics, transport, retry_delays=())

    assert (
        reporter.run_once(
            datetime(2026, 8, 30, 0, 59, tzinfo=timezone.utc),
            local_hour=9,
        )
        is True
    )
    assert transport.reports == []
    assert (
        reporter.run_once(
            datetime(2026, 8, 30, 1, tzinfo=timezone.utc),
            local_hour=9,
        )
        is True
    )
    assert [entry.job_id for entry in transport.reports[0].entries] == ["job_metrics"]


@pytest.mark.parametrize(
    ("arguments", "force_latest"),
    [
        (["--once"], False),
        (["--once", "--force"], True),
    ],
)
def test_reporter_once_mode_returns_nonzero_after_delivery_failure(monkeypatch, arguments, force_latest):
    from nurse_scheduling.server import usage_report

    settings = Mock(
        redis_url="redis://localhost/0",
        metrics_key_prefix="test:usage",
        metrics_retention_days=30,
        local_hour=0,
    )
    redis_client = Mock()
    reporter = Mock()
    reporter.run_once.return_value = False
    monkeypatch.setattr(usage_report.UsageReportSettings, "from_env", Mock(return_value=settings))
    monkeypatch.setattr(usage_report.redis.Redis, "from_url", Mock(return_value=redis_client))
    monkeypatch.setattr(usage_report, "RedisUsageMetrics", Mock())
    monkeypatch.setattr(usage_report, "_transport", Mock())
    monkeypatch.setattr(usage_report, "UsageReporter", Mock(return_value=reporter))
    monkeypatch.setattr("sys.argv", ["usage-report", *arguments])

    assert usage_report.main() == 1
    reporter.run_once.assert_called_once_with(local_hour=0, force_latest=force_latest)


def test_reporter_force_requires_once(monkeypatch):
    from nurse_scheduling.server import usage_report

    monkeypatch.setattr("sys.argv", ["usage-report", "--force"])

    with pytest.raises(SystemExit) as error:
        usage_report.main()
    assert error.value.code == 2


def test_next_report_deadline_is_the_next_local_sunday():
    local_timezone = timezone(timedelta(hours=8))

    assert next_report_deadline(
        datetime(2026, 8, 30, 0, 59, tzinfo=timezone.utc),
        local_timezone,
        9,
    ) == datetime(2026, 8, 30, 9, tzinfo=local_timezone)
    assert next_report_deadline(
        datetime(2026, 8, 30, 1, tzinfo=timezone.utc),
        local_timezone,
        9,
    ) == datetime(2026, 9, 6, 9, tzinfo=local_timezone)
    assert next_report_deadline(
        datetime(2026, 8, 31, 0, tzinfo=timezone.utc),
        local_timezone,
        9,
    ) == datetime(2026, 9, 6, 9, tzinfo=local_timezone)


def test_next_report_deadline_preserves_local_hour_across_dst():
    new_york = ZoneInfo("America/New_York")

    deadline = next_report_deadline(
        datetime(2026, 3, 7, 12, tzinfo=timezone.utc),
        new_york,
        9,
    )

    assert deadline == datetime(2026, 3, 8, 9, tzinfo=new_york)
    assert deadline.astimezone(timezone.utc) == datetime(2026, 3, 8, 13, tzinfo=timezone.utc)


def test_next_report_wait_has_ten_minute_minimum():
    local_timezone = timezone(timedelta(hours=8))

    assert (
        next_report_wait_seconds(
            datetime(2026, 8, 30, 0, 59, tzinfo=timezone.utc),
            local_timezone,
            9,
        )
        == 10 * 60
    )


def test_reporter_mailgun_mode_requires_credentials(monkeypatch):
    monkeypatch.setenv("USAGE_REPORT_TRANSPORT", "mailgun")
    for name in ("MAILGUN_API_KEY", "MAILGUN_DOMAIN", "MAILGUN_FROM", "MAILGUN_TO"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Mailgun reporting requires"):
        UsageReportSettings.from_env()


@pytest.mark.parametrize(
    "subject",
    [
        "",
        "Usage report\n{week_id}",
        "Usage report {starts_at}",
        "Usage report {week_id!r}",
        "Usage report {week_id:>10}",
        "Usage report {",
    ],
)
def test_reporter_rejects_invalid_subject_templates(monkeypatch, subject):
    monkeypatch.setenv("USAGE_REPORT_SUBJECT", subject)

    with pytest.raises(ValueError, match="USAGE_REPORT_SUBJECT"):
        UsageReportSettings.from_env()


@pytest.mark.parametrize(
    "api_url",
    [
        "http://api.mailgun.net/v3",
        "https://example.com/v3",
        "https://api.mailgun.net/v4",
        "https://api.mailgun.net/v3?destination=example.com",
        "https://api.mailgun.net/v3#destination",
        "https://api.mailgun.net:444/v3",
        "https://user@api.mailgun.net/v3",
    ],
)
def test_reporter_mailgun_mode_rejects_unapproved_api_urls(monkeypatch, api_url):
    monkeypatch.setenv("USAGE_REPORT_TRANSPORT", "mailgun")
    monkeypatch.setenv("MAILGUN_API_URL", api_url)
    monkeypatch.setenv("MAILGUN_API_KEY", "secret-key")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setenv("MAILGUN_FROM", "Reports <reports@mg.example.com>")
    monkeypatch.setenv("MAILGUN_TO", "operator@example.com")

    with pytest.raises(ValueError, match="approved Mailgun HTTPS API URL"):
        UsageReportSettings.from_env()


@pytest.mark.parametrize(
    ("api_url", "expected_url"),
    [
        ("https://api.mailgun.net:443/v3/", "https://api.mailgun.net/v3/mg.example.com/messages"),
        ("https://api.eu.mailgun.net/v3", "https://api.eu.mailgun.net/v3/mg.example.com/messages"),
    ],
)
def test_mailgun_transport_sends_plain_text_job_table(monkeypatch, redis_client, api_url, expected_url):
    monkeypatch.setenv("USAGE_REPORT_TRANSPORT", "mailgun")
    monkeypatch.setenv("USAGE_REPORT_SUBJECT", "Private backend report: {week_id}")
    monkeypatch.setenv("MAILGUN_API_URL", api_url)
    monkeypatch.setenv("MAILGUN_API_KEY", "secret-key")
    monkeypatch.setenv("MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setenv("MAILGUN_FROM", "Reports <reports@mg.example.com>")
    monkeypatch.setenv("MAILGUN_TO", "operator@example.com")
    settings = UsageReportSettings.from_env()
    response = Mock(status_code=200)
    response.json.return_value = {"id": "mailgun-message"}
    post = Mock(return_value=response)
    monkeypatch.setattr("nurse_scheduling.server.usage_report.httpx.post", post)
    metrics = RedisUsageMetrics(
        redis_client,
        key_prefix="test:usage",
        retention_days=30,
        report_timezone=timezone.utc,
    )
    submitted = _job(datetime(2026, 8, 24, 12, tzinfo=timezone.utc))
    _stage(metrics, lambda transaction: metrics.stage_job_created(transaction, submitted))
    report = metrics.load_week("2026-08-23")

    assert MailgunReportTransport(settings).send(report) == "mailgun-message"

    response.raise_for_status.assert_called_once_with()
    assert post.call_args.args == (expected_url,)
    assert post.call_args.kwargs["auth"] == ("api", "secret-key")
    assert post.call_args.kwargs["follow_redirects"] is False
    assert post.call_args.kwargs["files"]["subject"] == (None, "Private backend report: 2026-08-23")
    assert post.call_args.kwargs["files"]["text"][1].startswith("Private backend report: 2026-08-23\n")
    assert post.call_args.kwargs["files"]["to"] == (None, "operator@example.com")
    assert "private-client-id" in post.call_args.kwargs["files"]["text"][1]
    assert "private-filename.yaml" not in post.call_args.kwargs["files"]["text"][1]
