import nurse_scheduling

def test_example_1():
    filepath = "tests/testcases/example_1.yaml"
    df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
    assert df.values.tolist() == [
        ['', 18, 19, 20],
        ['', 'Fri', 'Sat', 'Sun'],
        ['Nurse 0', 'E', 'E', 'E'],
        ['Nurse 1', 'D', 'D', 'D'],
        ['Nurse 2', '', '', ''],
        ['Nurse 3', 'N', 'N', 'N']
    ]
