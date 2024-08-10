import glob
import io
import logging
import os

import nurse_scheduling
import pandas
import pytest


def test_all():
    for filepath in glob.glob("tests/testcases/*.yaml"):
        base_filepath = os.path.splitext(filepath)[0]
        logging.info(f"Testing '{base_filepath}' ...")
        df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
        with open(f"{base_filepath}.csv", 'r') as f:
            expected_csv = f.read()
        actual_csv = df.to_csv(index=False, header=False)
        if actual_csv != expected_csv:
            logging.info(f"Actual CSV:\n{actual_csv}")
            logging.info(f"Actual output:\n{df}")
            logging.info(f"Expected output:\n{pandas.read_csv( io.StringIO(expected_csv), header=None, keep_default_na=False)}")
            pytest.fail(f"Output mismatch for '{base_filepath}'")
