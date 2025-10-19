# Nurse Scheduling System

[![tests](https://img.shields.io/github/actions/workflow/status/j3soon/nurse-scheduling/test-core.yaml?label=tests)](https://github.com/j3soon/nurse-scheduling/actions/workflows/test-core.yaml)
[![codecov](https://codecov.io/github/j3soon/nurse-scheduling/graph/badge.svg?token=DPOvtAW1k2)](https://codecov.io/github/j3soon/nurse-scheduling)

The nurse scheduling (or employee scheduling) problem is a well-known problem in the field of operations research (OR) and can be (approximately) solved efficiently by constrained optimization.

However, constraints can differ greatly between hospitals and wards, and there is currently no unified framework for modeling these diverse requirements. Most existing literature focuses on modeling an over-simplified constraint set, which is not applicable to real-world situations. Therefore, in practice, the problem is still often solved by hand with the help of Excel, which is often extremely time-consuming. The entire process requires several hours or even more than ten hours, depending on the problem complexity (e.g., co-scheduling of multiple understaffed wards).

This project (Nurse Scheduling System, or 護理排班系統 in Mandarin) aims to develop a flexible web app to automate the nurse scheduling task, and to provide a unified framework for modeling all types of real-world scenarios without sacrificing flexibility.

> This project is in active development. Breaking changes may occur without notice. Please proceed with caution. Although the current version has been verified by domain experts and used successfully (with minimal post-adjustment) in several complex multi-ward scenarios involving up to ~100 nurses, it currently has a steep learning curve and lacks proper documentation.

## How to run

### Prerequisites

- [Node.js, nvm, and npm](https://nodejs.org/en/download).
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

These are not hard requirements. If you know what you are doing, you can also use other tools to manage dependencies, such as `virtualenv` or `conda`.

### Web Frontend

Development version hosted on: <https://j3soon.github.io/nurse-scheduling/>

```sh
cd web-frontend
npm install
npm run dev
```

For building static site, run:

```sh
cd web-frontend
npm run build
```

### Core

```sh
cd core
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
# run CLI
python -m nurse_scheduling.cli <input_file_path> [output_csv_path]
# run CLI with prettify and verbose
python -m nurse_scheduling.cli <input_file_path> [output_xlsx_path] --verbose --prettify
# run all tests
pytest --log-cli-level=INFO
# Note that setting `WRITE_TO_CSV=True` in `core/tests/test_all.py` is often useful for creating new test cases
```

Note: The tests and code coverage are only for the core module. The web frontend is not covered by tests.

### Documentation

```sh
cd docs
# create virtual environment
uv venv --python 3.12
# activate virtual environment
source .venv/bin/activate
# install dependencies
uv pip install -r requirements.txt
# preview documentation
mkdocs serve
```

For building static site, run:

```sh
cd docs
mkdocs build
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
