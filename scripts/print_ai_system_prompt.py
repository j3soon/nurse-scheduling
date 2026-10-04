#!/usr/bin/env python3
"""Print the assembled app system prompt to stdout using only the standard library."""

# This file is part of Nurse Scheduling Project, see <https://github.com/j3soon/nurse-scheduling>.
#
# Copyright (C) 2023-2026 Johnson Sun
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# This file is mostly AI generated.

import runpy
from pathlib import Path


def main() -> None:
    # Load the production assembler without the scheduling package's dependencies.
    assembler = (
        Path(__file__).resolve().parents[1]
        / "core/nurse_scheduling/ai/system_prompt.py"
    )
    module = runpy.run_path(str(assembler))
    print(module["compose_system_prompt"]())


if __name__ == "__main__":
    main()
