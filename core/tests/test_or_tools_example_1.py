import nurse_scheduling

def test_or_tools_example_1():
    filepath = "tests/testcases/or_tools_example_1"
    df = nurse_scheduling.schedule(f"{filepath}.yaml", validate=False, deterministic=True)
    print(df)
    with open(f"{filepath}.csv", 'r') as f:
        expected_csv = f.read()
    assert df.to_csv(index=False, header=False) == expected_csv
