import nurse_scheduling
import pandas as pd


def test_example_1():
    filepath = "tests/testcases/example_1"
    df = nurse_scheduling.schedule(f"{filepath}.yaml", validate=False, deterministic=True)
    print(df)
    with open(f"{filepath}.csv", 'r') as f:
        expected_csv = f.read()
    assert df.to_csv(index=False, header=False) == expected_csv
