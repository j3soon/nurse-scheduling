#!/usr/bin/env bash
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

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
environment_file="${AI_ENV_FILE:-${repository_root}/docker/.env}"
if [[ -f "${environment_file}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${environment_file}"
  set +a
fi
python_command="python"
if [[ -x "${repository_root}/core/.venv/bin/python" ]]; then
  python_command="${repository_root}/core/.venv/bin/python"
fi
cd "${repository_root}/core"
exec "${python_command}" -m tests.ai_eval.prefix_cache_probe "$@"
