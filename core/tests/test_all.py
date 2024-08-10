import glob
import io
import logging
import os

import nurse_scheduling
import pandas
import pytest


current_dir = os.path.dirname(os.path.realpath(__file__))
testcases_dir = f"{current_dir}/testcases"

def test_all():
    for filepath in glob.glob(f"{testcases_dir}/*.yaml"):
        base_filepath = os.path.splitext(os.path.basename(filepath))[0]
        logging.info(f"Testing '{base_filepath}' ...")
        # If test should fail
        if os.path.isfile(f"{testcases_dir}/{base_filepath}.txt"):
            with open(f"{testcases_dir}/{base_filepath}.txt", 'r') as f:
                expected_err = f.read()
            with pytest.raises(ValueError, match=expected_err.strip()):
                df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
            continue
        # If test should pass
        with open(f"{testcases_dir}/{base_filepath}.csv", 'r') as f:
            expected_csv = f.read()
        df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
        actual_csv = df.to_csv(index=False, header=False)
        if actual_csv != expected_csv:
            logging.debug(f"Actual CSV:\n{actual_csv}")
            logging.debug(f"Actual output:\n{df}")
            logging.debug(f"Expected output:\n{pandas.read_csv( io.StringIO(expected_csv), header=None, keep_default_na=False)}")
            pytest.fail(f"Output mismatch for '{base_filepath}'")
