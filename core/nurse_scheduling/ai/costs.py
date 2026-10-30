"""Decimal cost totals from replaceable provider call records."""

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

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .provider import ProviderCall


@dataclass
class CostTotals:
    usd: Decimal = Decimal(0)
    calls: int = 0
    pending: int = 0
    unavailable: int = 0
    streaming_calls: int = 0
    streaming_output_tokens: int = 0
    streaming_seconds: float = 0

    def update(self, call: ProviderCall, previous: ProviderCall | None = None) -> None:
        """Replace one call's contribution without counting its streamed updates twice."""
        for item, sign in ((previous, -1), (call, 1)):
            if item is None:
                continue
            self.calls += sign
            self.pending += sign * (item.status == "pending")
            self.unavailable += sign * (item.status == "unavailable")
            self.usd += sign * Decimal(item.cost_usd or "0")
            if (
                item.streaming_seconds is not None
                and item.streaming_seconds > 0
                and item.usage
                and item.usage.completion_tokens > 0
            ):
                self.streaming_calls += sign
                self.streaming_output_tokens += sign * item.usage.completion_tokens
                self.streaming_seconds += sign * item.streaming_seconds

    def public(self) -> dict[str, Any]:
        # Apply arithmetic precision after recovery and keep tiny values compact.
        result = {
            "usd": str(+self.usd),
            "calls": self.calls,
            "pending": self.pending,
            "unavailable": self.unavailable,
        }
        if self.streaming_calls:
            result["streaming"] = {
                "calls": self.streaming_calls,
                "output_tokens": self.streaming_output_tokens,
                "seconds": self.streaming_seconds,
            }
        return result

    @classmethod
    def restored(cls, data: dict | None) -> "CostTotals":
        if data is None:
            return cls()
        streaming = data.get("streaming", {})
        return cls(
            Decimal(data["usd"]),
            data["calls"],
            data["pending"],
            data["unavailable"],
            streaming.get("calls", 0),
            streaming.get("output_tokens", 0),
            streaming.get("seconds", 0),
        )
