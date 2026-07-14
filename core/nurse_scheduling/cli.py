"""CLI entry point for the nurse scheduling tool."""

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

import sys
import argparse
import json
import logging
import os.path
import subprocess
import time
from io import BytesIO
from pathlib import Path
from . import scheduler, exporter
from .model_build_stats import ModelBuildStatsSummary
from .solver_interface import (
    SchedulePhaseProgress,
    SolverProgress,
    count_export_comments,
    serialize_schedule_phase_progress,
    serialize_solver_progress,
)

# TODO: Better CLI
# Ref: https://packaging.python.org/en/latest/guides/creating-command-line-tools/


def _get_app_version() -> str:
    repo_root = Path(__file__).resolve().parents[2]
    try:
        return subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={repo_root}",
                "-C",
                str(repo_root),
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


def _create_cli_progress_callback(progress_output_file=None, print_to_stdout: bool = True):
    """Create a CLI progress printer for solver best-score updates."""

    def print_progress(payload):
        if isinstance(payload, SchedulePhaseProgress):
            progress_payload = serialize_schedule_phase_progress(payload)
            if progress_output_file is not None:
                progress_output_file.write(json.dumps(progress_payload, sort_keys=True) + "\n")
                progress_output_file.flush()
            return

        progress_payload = serialize_solver_progress(payload, include_export_summary=True)
        if progress_output_file is not None:
            progress_output_file.write(json.dumps(progress_payload, sort_keys=True) + "\n")
            progress_output_file.flush()
        if print_to_stdout:
            comment_text = ""
            if progress_payload["commentCount"] is not None:
                comment_text = f", comments={progress_payload['commentCount']}"
            print(
                "[+] NURSE-SCHEDULING PROGRESS "
                f"(score={payload.currentBestScore}, "
                f"source={payload.source}, elapsed={payload.elapsedSeconds}s{comment_text})",
                flush=True,
            )

    return print_progress


def main():
    parser = argparse.ArgumentParser(description="Nurse Scheduling Tool")
    parser.add_argument("input_file_path", nargs="?", help="Path to the input file")
    parser.add_argument("output_path", nargs="?", help="Path to save the output file (optional)")
    parser.add_argument("--version", action="store_true", help="Print the current git version and exit")
    parser.add_argument("--prettify", action="store_true", help="Enable prettify mode for enhanced output formatting")
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Increase verbosity (can be used multiple times: -v, -vv, -vvv)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=None,
        help="Maximum running time in seconds. If reached, the solver will stop and the current best result (if any) will be exported.",
    )
    parser.add_argument(
        "--solver",
        type=str,
        default="ortools/cp-sat",
        choices=["ortools/cp-sat", "pulp/cbc", "pulp/cuopt"],
        help="Solver selector (e.g., 'ortools/cp-sat', 'pulp/cbc', or 'pulp/cuopt').",
    )
    parser.add_argument(
        "--show-model-build-stats",
        action="store_true",
        help="Print model-build timing and variable/constraint deltas for each build step.",
    )
    parser.add_argument(
        "--progress-output",
        help="Write solver progress events as JSON Lines for later plotting.",
    )
    args = parser.parse_args()
    if args.version:
        print(f"nurse-scheduling {_get_app_version()}")
        return
    if args.input_file_path is None:
        parser.error("the following arguments are required: input_file_path")
    filepath = args.input_file_path
    output_path = args.output_path
    prettify = args.prettify
    verbose = args.verbose
    solver = args.solver

    if args.progress_output and not prettify:
        print("Error: --progress-output requires --prettify")
        sys.exit(1)

    # Configure logging based on verbosity level
    if verbose >= 2:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    elif verbose == 1:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

    # Infer output format from file extension
    output_format = None
    if output_path:
        file_ext = os.path.splitext(output_path)[1].lower()
        if file_ext == ".xlsx":
            output_format = "xlsx"
        elif file_ext == ".csv":
            if prettify:
                print("Error: Prettify mode is not supported for CSV files")
                sys.exit(1)
            output_format = "csv"
        elif file_ext and file_ext not in [".csv", ".xlsx"]:
            print(f"Error: Unsupported output file extension '{file_ext}'. Supported formats: .csv, .xlsx")
            sys.exit(1)

    # Read input file
    if not os.path.isfile(filepath):
        print(f"Error: File '{filepath}' not found")
        sys.exit(1)

    with open(filepath, "rb") as f:
        file_content = f.read()

    print(f"nurse-scheduling {_get_app_version()}")

    model_build_stats_callback = ModelBuildStatsSummary() if args.show_model_build_stats else None
    progress_output_file = None
    solve_started_at = time.monotonic()
    try:
        if args.progress_output:
            progress_output_file = open(args.progress_output, "w", encoding="utf-8")
        progress_callback = None
        if not args.show_model_build_stats or progress_output_file is not None:
            progress_callback = _create_cli_progress_callback(
                progress_output_file,
                print_to_stdout=not args.show_model_build_stats,
            )
        schedule_result = scheduler.schedule(
            file_content,
            prettify=prettify,
            timeout=args.timeout,
            solver=solver,
            progress_callback=progress_callback,
            model_build_stats_callback=model_build_stats_callback,
        )
        df = schedule_result.dataframe
        solution = schedule_result.solution
        score = schedule_result.score
        status = schedule_result.solver_status
        cell_export_info = schedule_result.cell_export_info
        if progress_output_file is not None and df is not None:
            progress_callback(
                SolverProgress(
                    source="cli:final-result",
                    currentBestScore=score,
                    elapsedSeconds=round(time.monotonic() - solve_started_at, 3),
                    df=df,
                    cell_export_info=cell_export_info,
                )
            )
    finally:
        if progress_output_file is not None:
            progress_output_file.close()
        if model_build_stats_callback is not None:
            model_build_stats_callback.print_summary()

    if df is None:
        print("No solution found")
        sys.exit(0)

    if output_path:
        # Export to buffer and write to file
        buffer = BytesIO()
        if output_format == "xlsx":
            exporter.export_to_excel(df, buffer, cell_export_info)
        else:  # csv format
            exporter.export_to_csv(df, buffer)

        # Write buffer to file
        with open(output_path, "wb") as f:
            f.write(buffer.getvalue())

        print(f"Results saved to {output_path}")
        print(f"Score: {score}")
        print(f"Status: {status}")
        comment_count = count_export_comments(cell_export_info)
        if comment_count is not None:
            print(f"Comments: {comment_count}")
    elif args.show_model_build_stats:
        print(f"Score: {score}")
        print(f"Status: {status}")
        comment_count = count_export_comments(cell_export_info)
        if comment_count is not None:
            print(f"Comments: {comment_count}")
    else:
        comment_count = count_export_comments(cell_export_info)
        if comment_count is not None:
            print(f"Comments: {comment_count}")
        print(df, solution, score, status)


if __name__ == "__main__":
    main()
