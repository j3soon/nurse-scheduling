"""Benchmark sequential and concurrent reads in one warm E2B sandbox."""

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from nurse_scheduling.ai.sandbox import SandboxBackend, managed_sandbox, managed_sandbox_factory
from nurse_scheduling.ai.sandbox.e2b import E2BSandboxFactory

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
Mode = Literal["sequential", "concurrent"]


@dataclass(frozen=True)
class ModeSummary:
    median_seconds: float
    p95_seconds: float
    samples_seconds: list[float]


async def _read_batch(sandbox: SandboxBackend, path: str, calls: int, mode: Mode) -> float:
    started = time.perf_counter()
    if mode == "concurrent":
        contents = await asyncio.gather(*(sandbox.read_file(path) for _ in range(calls)))
    else:
        contents = [await sandbox.read_file(path) for _ in range(calls)]
    elapsed = time.perf_counter() - started
    if len(contents) != calls or len(set(contents)) != 1:
        raise RuntimeError("E2B returned inconsistent benchmark contents")
    return elapsed


def _summarize(samples: list[float]) -> ModeSummary:
    p95 = samples[0] if len(samples) == 1 else statistics.quantiles(samples, n=100, method="inclusive")[94]
    return ModeSummary(statistics.median(samples), p95, samples)


async def benchmark(factory: E2BSandboxFactory, *, runs: int, calls: int, size_bytes: int) -> dict:
    samples: dict[Mode, list[float]] = {"sequential": [], "concurrent": []}
    payload = b"x" * size_bytes
    async with managed_sandbox_factory(factory), managed_sandbox(factory) as sandbox:
        await sandbox.write_file("/workspace/read-benchmark.bin", payload)
        async with sandbox.activity_batch():
            for mode in ("sequential", "concurrent"):
                await _read_batch(sandbox, "/workspace/read-benchmark.bin", calls, mode)
            for index in range(runs):
                modes: tuple[Mode, Mode] = (
                    ("sequential", "concurrent") if index % 2 == 0 else ("concurrent", "sequential")
                )
                for mode in modes:
                    samples[mode].append(await _read_batch(sandbox, "/workspace/read-benchmark.bin", calls, mode))

    sequential = _summarize(samples["sequential"])
    concurrent = _summarize(samples["concurrent"])
    return {
        "config": {"runs": runs, "calls_per_batch": calls, "file_bytes": size_bytes},
        "sequential": asdict(sequential),
        "concurrent": asdict(concurrent),
        "median_speedup": sequential.median_seconds / concurrent.median_seconds,
    }


def _write_report(result: dict, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "results.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    config = result["config"]
    sequential = result["sequential"]
    concurrent = result["concurrent"]
    summary = output_dir / "summary.md"
    summary.write_text(
        "# E2B read-batch benchmark\n\n"
        f"Runs per mode: {config['runs']}  \n"
        f"Calls per batch: {config['calls_per_batch']}  \n"
        f"File bytes: {config['file_bytes']}\n\n"
        "| Mode | Median seconds | p95 seconds |\n"
        "| --- | ---: | ---: |\n"
        f"| Sequential | {sequential['median_seconds']:.4f} | {sequential['p95_seconds']:.4f} |\n"
        f"| Concurrent | {concurrent['median_seconds']:.4f} | {concurrent['p95_seconds']:.4f} |\n\n"
        f"Median speedup: **{result['median_speedup']:.3f}x**\n",
        encoding="utf-8",
    )
    return summary


def _default_output_dir() -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    artifact_root = Path(os.environ.get("AI_EVAL_ARTIFACT_ROOT", REPOSITORY_ROOT / "artifacts"))
    return artifact_root / "ai-read-benchmarks" / timestamp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--calls", type=int, default=3)
    parser.add_argument("--bytes", type=int, default=65536, dest="size_bytes")
    parser.add_argument("--output-dir", type=Path, default=None)
    arguments = parser.parse_args()
    if arguments.runs <= 0 or arguments.calls <= 1 or arguments.size_bytes <= 0:
        parser.error("runs and bytes must be positive, and calls must be greater than one")

    api_key = os.getenv("E2B_API_KEY", "").strip()
    if not api_key:
        parser.error("E2B_API_KEY is required")
    factory = E2BSandboxFactory(
        api_key=api_key,
        template=os.getenv("E2B_TEMPLATE", "nurse-scheduling-ai-sandbox").strip(),
        turn_timeout_seconds=300,
        command_timeout_seconds=10,
    )
    result = asyncio.run(
        benchmark(factory, runs=arguments.runs, calls=arguments.calls, size_bytes=arguments.size_bytes)
    )
    summary = _write_report(result, (arguments.output_dir or _default_output_dir()).resolve())
    print(f"Sequential median: {result['sequential']['median_seconds']:.4f}s")
    print(f"Concurrent median: {result['concurrent']['median_seconds']:.4f}s")
    print(f"Median speedup: {result['median_speedup']:.3f}x")
    print(f"Benchmark report: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
