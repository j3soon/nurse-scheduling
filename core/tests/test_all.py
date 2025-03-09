import glob
import io
import logging
import os

import nurse_scheduling
import pandas
import pytest
from pydantic import ValidationError


current_dir = os.path.dirname(os.path.realpath(__file__))
testcases_dir = f"{current_dir}/testcases"

IGNORE_TESTS = []

def test_all():
    tests = glob.glob(f"{testcases_dir}/*.yaml")
    for test_no, filepath in enumerate(tests):
        base_filepath = os.path.splitext(os.path.basename(filepath))[0]
        if base_filepath in IGNORE_TESTS:
            continue
        logging.info(f"Testing '{base_filepath}' ...")
        # If test should fail
        if os.path.isfile(f"{testcases_dir}/{base_filepath}.txt"):
            with open(f"{testcases_dir}/{base_filepath}.txt", 'r') as f:
                expected_err = f.read()
            # Use pytest.raises without the match parameter to catch the error first
            with pytest.raises(ValidationError) as exc_info:
                df = nurse_scheduling.schedule(filepath, deterministic=True)
            # Then verify the error message contains the expected text
            assert expected_err.strip() in str(exc_info.value), \
                f"Expected error '{expected_err.strip()}' not found in actual error: {str(exc_info.value)}"
            continue
        # If test should pass
        with open(f"{testcases_dir}/{base_filepath}.csv", 'r') as f:
            expected_csv = f.read()
        try:
            df = nurse_scheduling.schedule(filepath, deterministic=True)
        except ValidationError as e:
            logging.debug(f"Validation error for '{base_filepath}': {e}")
            pytest.fail(f"Validation error for '{base_filepath}'")
        actual_csv = df.to_csv(index=False, header=False)
        if actual_csv != expected_csv:
            logging.debug(f"Actual CSV:\n{actual_csv}")
            logging.debug(f"Actual output:\n{df}")
            logging.debug(f"Expected output:\n{pandas.read_csv( io.StringIO(expected_csv), header=None, keep_default_na=False)}")
            pytest.fail(f"Output mismatch for '{base_filepath}' ({test_no}/{len(tests)})")
