"""Legacy optimizer submission adapter."""

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

from fastapi import APIRouter, File, Form, Request, Response, UploadFile

from .optimize import create_job

router = APIRouter()


@router.post("/optimize", status_code=202, deprecated=True, include_in_schema=False)
async def create_legacy_job(
    request: Request,
    response: Response,
    file: UploadFile | None = File(None),  # noqa: B008
    yaml_content: str | None = Form(None),
    prettify: bool | None = Form(None),
    timeout: int | None = Form(None),
    solver: str | None = Form(None),
):
    """Forward old form names to the current submission handler."""
    return await create_job(request, response, file, yaml_content, prettify, timeout, solver)
