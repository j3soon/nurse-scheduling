"""Load bounded, model-readable frontend schedule YAML references."""

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

from pathlib import Path

MAX_SCHEMA_REFERENCE_CHARS = 50_000
REFERENCE_DIRECTORY = Path(__file__).with_name("references")
SCHEMA_REFERENCE_FILES = {
    "core": REFERENCE_DIRECTORY / "schema-core.md",
    "preferences": REFERENCE_DIRECTORY / "schema-preferences.md",
    "export": REFERENCE_DIRECTORY / "schema-export.md",
}


def load_schedule_reference(group: str) -> str | None:
    """Load one task-sized schema reference from its Markdown source."""
    path = SCHEMA_REFERENCE_FILES.get(group)
    if path is None:
        return None
    reference = path.read_text(encoding="utf-8")
    if len(reference) > MAX_SCHEMA_REFERENCE_CHARS:
        raise ValueError(f"{group} schedule reference exceeds {MAX_SCHEMA_REFERENCE_CHARS} characters")
    return reference
