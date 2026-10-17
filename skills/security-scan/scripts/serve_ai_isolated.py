"""Run the AI service for isolated security scans with an in-memory sandbox."""

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

# Settings come from the environment like the deployed service. Only the sandbox is replaced, so
# a scan never creates E2B sandboxes or needs an E2B key. Run with `core/` on `PYTHONPATH`.

import argparse

import uvicorn
from nurse_scheduling.ai.app import create_app
from nurse_scheduling.ai.config import AiSettings
from nurse_scheduling.ai.sandbox.fake import FakeSandboxFactory


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    app = create_app(settings=AiSettings.from_env(), sandbox_factory=FakeSandboxFactory())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
        access_log=False,
    )


if __name__ == "__main__":
    main()
