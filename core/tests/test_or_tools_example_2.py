import nurse_scheduling

def test_or_tools_example_2():
    filepath = "tests/testcases/or_tools_example_2.yaml"
    df = nurse_scheduling.schedule(filepath, validate=False, deterministic=True)
    print(df)
    assert df.values.tolist() == [
        ['', 1, 2, 3, 4, 5, 6, 7],
        ['', 'Fri', 'Sat', 'Sun', 'Mon', 'Tue', 'Wed', 'Thu'],
        ['Nurse 0', 'N', '', 'N', '', 'N', 'E', ''],
        ['Nurse 1', '', '', 'E', 'N', 'D', '', 'N'],
        ['Nurse 2', 'E', 'E', '', 'D', '', 'N', 'D'],
        ['Nurse 3', '', 'D', 'D', 'E', '', 'D', ''],
        ['Nurse 4', 'D', 'N', '', '', 'E', '', 'E'],
    ]
