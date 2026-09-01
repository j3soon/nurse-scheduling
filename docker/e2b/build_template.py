"""Build the minimal E2B template used by the experimental AI assistant."""

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

# This code is mostly AI generated.

import os
from pathlib import Path

from e2b import Template, default_build_logger

DEFAULT_TEMPLATE_ALIAS = "nurse-scheduling-ai-sandbox"


def main() -> None:
    """Build and publish the configured minimal sandbox template."""
    if not os.getenv("E2B_API_KEY", "").strip():
        raise SystemExit("E2B_API_KEY is required")

    alias = os.getenv("E2B_TEMPLATE", DEFAULT_TEMPLATE_ALIAS).strip()
    if not alias:
        raise SystemExit("E2B_TEMPLATE must not be empty")

    dockerfile = Path(__file__).with_name("e2b.Dockerfile")
    template = Template().from_dockerfile(str(dockerfile))
    result = Template.build(
        template,
        alias=alias,
        cpu_count=1,
        memory_mb=512,
        on_build_logs=default_build_logger(),
    )
    print(f"Built E2B template {alias}: {result.template_id}")


if __name__ == "__main__":
    main()
