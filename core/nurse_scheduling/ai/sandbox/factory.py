"""Configured creation of disposable AI sandbox providers."""

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

from ..config import AiSettings
from .base import SandboxFactory


def create_sandbox_factory(settings: AiSettings) -> SandboxFactory:
    """Build the selected provider without leaking it into agent logic."""
    if settings.sandbox_backend == "e2b":
        from .e2b import E2BSandboxFactory

        return E2BSandboxFactory.from_settings(settings)
    raise ValueError("A sandbox backend must be configured for the AI assistant")
