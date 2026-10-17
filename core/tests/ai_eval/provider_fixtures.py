"""Inject one interrupted attempt through the production provider retry policy."""

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

# This test is mostly AI generated.

from contextlib import aclosing

import httpx

from nurse_scheduling.ai.provider import OpenAiCompatibleProvider, TextDelta


class TimeoutOnceProvider(OpenAiCompatibleProvider):
    """Seed a partial answer once, then send the recovery request to the provider."""

    def __init__(self, settings, provider: OpenAiCompatibleProvider, partial_text: str):
        super().__init__(settings, include_usage=True, include_attempts=True)
        self._provider = provider
        self._partial_text = partial_text

    async def _stream_attempt(self, timeout, headers, payload):
        if self._partial_text:
            partial_text, self._partial_text = self._partial_text, ""
            yield TextDelta(partial_text)
            raise httpx.ReadTimeout("Injected evaluation timeout after partial text")
        async with aclosing(self._provider._stream_attempt(timeout, headers, payload)) as events:
            async for event in events:
                yield event
