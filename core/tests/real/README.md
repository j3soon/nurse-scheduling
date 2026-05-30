# Real-World Scenario Checks

These checks solve larger real-world scenarios with a fixed optimization budget.
They are slower and less deterministic than the normal unit and regression tests.

The Python files in this directory intentionally omit pytest's `test_` filename
prefix so that the default test suite does not collect them.

Run a real-world check explicitly:

```sh
cd core
pytest --log-cli-level=INFO tests/real/schedule_ortools_cp_sat.py
```
