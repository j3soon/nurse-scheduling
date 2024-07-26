import nurse_scheduling

def test_example_1():
    filepath = "tests/testcases/or_tools_example_1.yaml"
    df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
    assert df.values.tolist() == [
        ['', 18, 19, 20],
        ['', 'Fri', 'Sat', 'Sun'],
        ['Nurse 0', '', 'N', 'D'],
        ['Nurse 1', 'E', 'E', 'E'],
        ['Nurse 2', 'N', '', 'N'],
        ['Nurse 3', 'D', 'D', '']
    ]
