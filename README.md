# Nurse Scheduling System

[![tests](https://img.shields.io/github/actions/workflow/status/j3soon/nurse-scheduling/test-core.yaml?label=tests)](https://github.com/j3soon/nurse-scheduling/actions/workflows/test-core.yaml)
[![codecov](https://codecov.io/github/j3soon/nurse-scheduling/graph/badge.svg?token=DPOvtAW1k2)](https://codecov.io/github/j3soon/nurse-scheduling)

The nurse scheduling (or employee scheduling) problem is a well-known problem in the field of operations research (OR) and can be (approximately) solved efficiently by constrained optimization.

However, the constraints vary significantly across hospitals or wards. Therefore, in practice, the problem is often solved by hand or with the help of Excel, which is really time-consuming. The entire process requires several hours or even more than ten hours, depending on the problem complexity (e.g., multiple wards).

This project (Nurse Scheduling System, or 護理排班系統 in Mandarin) aims to develop a user-friendly web app to automate the nurse scheduling task.

> This project is currently a **Work in Progress**, so it may not function as intended. A preliminary version (or a POC) of a command-line interface is implemented and verified by domain experts under a multi-ward scenario at 2023/08/20. We are currently refactoring the codebase along with test cases to make it more maintainable.

## How to run

```sh
cd core
# install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
# run CLI
python -m nurse_scheduling.cli <input_file_path> [output_csv_path]
# run all tests
pytest --log-cli-level=INFO
# Note that setting `WRITE_TO_CSV=True` in `core/tests/test_all.py` is often useful for creating new test cases
```

## Design Philosophy

### Choice of Solver

Since I'm not an expert in operations research, I've done some research on suitable (open-source) solvers for this problem. The most popular ones seem to be [Timefold](https://github.com/TimefoldAI/timefold-solver) (previously [OptaPlanner](https://github.com/kiegroup/optaplanner)) and [Google OR-Tools](https://github.com/google/or-tools). There's also a [comparison](https://www.optaplanner.org/competitor/or-tools.html) between the two.

Google OR-Tools is chosen due to the support of Python, which is the language I'm most familiar with this kind of project.

### Choice of Input Format

We prioritize human readability and ease of editing by hand over machine parsing simplicity.

The YAML format uses camelCase field names, following the conventions of Kubernetes.

To allow quick prototyping without defining data type classes, we choose to keep the YAML input intact in memory. This requires extracting data explicitly using utility functions.

<!-- TODO: Compare with INRC format and describe the differences and rationale) -->

## References

- [Nurse rostering - Timefold](https://timefold.ai/docs/timefold-solver/latest/use-cases-and-examples/nurse-rostering/nurse-rostering.html)
- [A nurse scheduling problem - OR-Tools](https://developers.google.com/optimization/scheduling/employee_scheduling#a_nurse_scheduling_problem)
- Haspeslagh et al., 2010, [First International Nurse Rostering Competition 2010](https://nrpcompetition.kuleuven-kulak.be/wp-content/uploads/2020/06/nrpcompetition_description.pdf) [[website](https://nrpcompetition.kuleuven-kulak.be/)]
- Ceschia et al., 2015, [Second International Nurse Rostering Competition (INRC-II) --- Problem Description and Rules ---](https://arxiv.org/abs/1501.04177) [[website](https://mobiz.vives.be/inrc2/)]
