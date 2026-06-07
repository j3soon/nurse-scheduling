"""Shared test helper for schedule regression tests across solver backends."""

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

import glob
import io
import logging
import os
import sys

# Add the project root to the Python path so imports will work when running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import nurse_scheduling
import pandas
import pytest
from pydantic import ValidationError


CURRENT_DIR = os.path.dirname(os.path.realpath(__file__))
TESTCASES_DIR = f"{CURRENT_DIR}/testcases"

IGNORE_TESTS = []
EXCLUDED_TESTCASE_DIRS = {"real"}
WRITE_TO_CSV = False
CONTINUE_ON_ERROR = True  # False


def get_regression_testcases() -> list[str]:
    tests = glob.glob(f"{TESTCASES_DIR}/**/*.yaml", recursive=True)
    return [
        filepath
        for filepath in tests
        if os.path.relpath(filepath, TESTCASES_DIR).split(os.sep, maxsplit=1)[0] not in EXCLUDED_TESTCASE_DIRS
    ]


def run_schedule_regression_test(solver: str) -> None:
    tests = get_regression_testcases()
    total_tests = len(tests)
    error_count = 0
    failed_cases: list[str] = []
    for test_no, filepath in enumerate(tests, start=1):
        relative_filepath = filepath[len(TESTCASES_DIR) + 1 :]
        base_filepath = os.path.splitext(os.path.basename(filepath))[0]
        test_dir = os.path.dirname(filepath)
        if base_filepath in IGNORE_TESTS:
            continue
        logging.info(f"[{solver}] Testing '{relative_filepath}' ...")

        # Read file content
        with open(filepath, "rb") as f:
            file_content = f.read()

        # If test should fail
        if os.path.isfile(f"{test_dir}/{base_filepath}.txt"):
            with open(f"{test_dir}/{base_filepath}.txt", "r") as f:
                expected_err = f.read()
            # Use pytest.raises without the match parameter to catch the error first
            with pytest.raises((ValidationError, ValueError)) as exc_info:
                nurse_scheduling.schedule(file_content, solver=solver)
            # Then verify the error message contains the expected text
            logging.info(f"Expected error: {expected_err.strip()}")
            logging.info(f"Actual error: {str(exc_info.value)}")
            assert expected_err.strip() in str(exc_info.value), (
                f"Expected error '{expected_err.strip()}' not found in actual error: {str(exc_info.value)}"
            )
            continue

        # If test should pass
        if not WRITE_TO_CSV or os.path.isfile(f"{test_dir}/{base_filepath}.csv"):
            with open(f"{test_dir}/{base_filepath}.csv", "r") as f:
                expected_csv = f.read()

        try:
            df, solution, score, status, _cell_export_info = nurse_scheduling.schedule(
                file_content,
                solver=solver,
            )
            df2, _solution2, score2, _status2, _cell_export_info2 = nurse_scheduling.schedule(
                file_content,
                avoid_solution=solution,
                solver=solver,
            )
        except ValidationError as e:
            logging.debug(f"Validation error for '{base_filepath}': {e}")
            error_count += 1
            failed_cases.append(f"{relative_filepath} [validation error]")
            if not CONTINUE_ON_ERROR:
                pytest.fail(f"Validation error for '{base_filepath}'")
            continue
        except Exception as e:
            logging.debug(f"Unexpected error for '{base_filepath}': {e}")
            error_count += 1
            failed_cases.append(f"{relative_filepath} [unexpected error]")
            if not CONTINUE_ON_ERROR:
                pytest.fail(f"Unexpected error for '{base_filepath}'")
            continue

        if df is not None:
            actual_csv = df.to_csv(index=False, header=False, lineterminator="\n")
        else:
            actual_csv = status

        if WRITE_TO_CSV:
            with open(f"{test_dir}/{base_filepath}.csv", "w") as f:
                f.write(actual_csv)
            expected_csv = actual_csv

        # Check if the optimal solution is unique by running the solver again with the previous solution avoided
        not_unique_optimal = df2 is not None and score == score2
        if not_unique_optimal:
            logging.warning("The optimal solution is not unique")

        if actual_csv != expected_csv:
            logging.debug(f"Actual CSV:\n{actual_csv}")
            logging.debug(f"Actual output:\n{df}")
            logging.debug(
                "Expected output:\n%s",
                pandas.read_csv(io.StringIO(expected_csv), header=None, keep_default_na=False),
            )
            error_count += 1
            failed_cases.append(f"{relative_filepath} [output mismatch]")
            if not CONTINUE_ON_ERROR:
                pytest.fail(f"Output mismatch for '{filepath}' ({test_no}/{total_tests})")
            continue

        if not_unique_optimal:
            logging.debug(f"Optimal Solution 1:\n{df}")
            logging.debug(f"Optimal Solution 2:\n{df2}")
            error_count += 1
            failed_cases.append(f"{relative_filepath} [non-unique optimal]")
            if not CONTINUE_ON_ERROR:
                pytest.fail(
                    f"The optimal solution should be unique, but it is not for '{filepath}' ({test_no}/{total_tests})"
                )
            continue

    if error_count > 0:
        logging.error("Found %s/%s errors during testing:", error_count, total_tests)
        for failed_case in failed_cases:
            logging.error("  - %s", failed_case)
        pytest.fail(f"Found {error_count}/{total_tests} errors during testing:\n- " + "\n- ".join(failed_cases))
    else:
        logging.info(f"All {total_tests} tests passed for solver={solver}")
