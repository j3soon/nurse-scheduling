import glob
import os

import nurse_scheduling


def test_all():
    for filepath in glob.glob("tests/testcases/*.yaml"):
        print(f"Testing '{filepath}' ...")
        base_filepath = os.path.splitext(filepath)[0]
        df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
        print(df)
        with open(f"{base_filepath}.csv", 'r') as f:
            expected_csv = f.read()
        assert df.to_csv(index=False, header=False) == expected_csv
