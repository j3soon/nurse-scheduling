"""Input loading and schema validation helpers."""

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

from dataclasses import dataclass
from io import BytesIO
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.events import (
    AliasEvent,
    MappingEndEvent,
    MappingStartEvent,
    ScalarEvent,
    SequenceEndEvent,
    SequenceStartEvent,
)

from .models import NurseSchedulingData

yaml = YAML(typ="safe")


MAX_EXPANDED_NODES = 200_000
"""Largest number of nodes a document may expand to once aliases are followed."""
MAX_RAW_NESTING_DEPTH = 256
"""Bracket nesting refused before parsing.

The YAML scanner does work proportional to how deep it currently is for every token it
reads, so a document need only nest to be expensive to look at. Counting brackets in the
raw bytes over-counts any that appear inside quoted text, so this bound sits well above
the parsed one, which is what actually enforces the shape.
"""
MAX_NESTING_DEPTH = 64
"""Deepest a document may nest. Parsing costs grow faster than depth, and this project's
own data nests five deep, so a bound well above that keeps a deep document from being
expensive to even look at."""


class SchedulingDataTooComplexError(ValueError):
    """Scheduling data expands to more nodes than this project will process."""


_NON_BRACKETS = bytes(value for value in range(256) if value not in b"[]{}")
"""Every byte that is not a flow collection marker, deleted before measuring nesting."""


def raw_nesting_depth(content: bytes) -> int:
    """Return the deepest bracket nesting in the raw bytes, ignoring YAML structure.

    The brackets are extracted at native speed first, so a document large enough to be
    worth rejecting is not expensive to reject.
    """
    depth = deepest = 0
    for bracket in content.translate(None, _NON_BRACKETS):
        if bracket in b"[{":
            depth += 1
            deepest = max(deepest, depth)
        else:
            depth -= 1
    return deepest


@dataclass(frozen=True)
class YamlExpansion:
    """How far a document expands once its aliases are followed."""

    nodes: int
    """Nodes the document expands to, counting each alias in full."""
    aliases: int
    """Aliases the document uses, which this project's own data never does."""


def _parse_events(content: bytes):
    """Yield parse events, reporting every malformed document as a YAML error.

    The parser raises bare assertions for some malformed input, such as an unsupported
    version directive. Callers separate unusable data from unusable requests, so every
    such failure has to arrive as one kind of error.
    """
    try:
        yield from YAML(typ="safe").parse(content)
    except (SchedulingDataTooComplexError, YAMLError):
        raise
    except Exception as error:
        raise YAMLError(f"Scheduling data could not be read: {error}") from error


def measure_yaml_expansion(content: bytes, *, limit: int = MAX_EXPANDED_NODES) -> YamlExpansion:
    """Return how far this document expands, counting each alias in full.

    An alias is a reference, so parsing a document that nests them stays cheap while
    everything that later walks the result pays for the expansion. Counting the expansion
    from the event stream keeps that cost visible without ever building the structure.

    Raises:
        SchedulingDataTooComplexError: If the expansion or the nesting exceeds its bound.
    """
    if raw_nesting_depth(content) > MAX_RAW_NESTING_DEPTH:
        raise SchedulingDataTooComplexError(
            f"Scheduling data nests deeper than {MAX_NESTING_DEPTH} levels, which this server refuses to process"
        )
    anchor_sizes: dict[str, int] = {}
    aliases = 0
    # Each open collection accumulates its own size, and the root frame holds the total.
    frames: list[list] = [[0, None]]
    for event in _parse_events(content):
        anchor = getattr(event, "anchor", None)
        if isinstance(event, (MappingStartEvent, SequenceStartEvent)):
            frames.append([1, anchor])
            if len(frames) - 1 > MAX_NESTING_DEPTH:
                # Raised while parsing, so the rest of a deep document is never read.
                raise SchedulingDataTooComplexError(
                    f"Scheduling data nests deeper than {MAX_NESTING_DEPTH} levels, "
                    "which this server refuses to process"
                )
            continue
        if isinstance(event, (MappingEndEvent, SequenceEndEvent)):
            size, collection_anchor = frames.pop()
            if collection_anchor is not None:
                anchor_sizes[collection_anchor] = size
            frames[-1][0] += size
        elif isinstance(event, ScalarEvent):
            if anchor is not None:
                anchor_sizes[anchor] = 1
            frames[-1][0] += 1
        elif isinstance(event, AliasEvent):
            aliases += 1
            frames[-1][0] += anchor_sizes.get(event.anchor, 1)
        else:
            continue
        if frames[-1][0] > limit:
            raise SchedulingDataTooComplexError(
                f"Scheduling data expands to more than {limit} nodes, which this server refuses to process"
            )
    return YamlExpansion(nodes=frames[0][0], aliases=aliases)


def _load_yaml(content: bytes) -> dict[str, Any]:
    """Load YAML from bytes content.

    Args:
        content: File content as bytes

    Returns:
        dict[str, Any]: The loaded YAML data
    """
    stream = BytesIO(content)
    # Use ruamel.yaml instead of PyYAML to support YAML 1.2
    # This avoids the auto-conversion of special strings such as
    # `Off` into boolean value `False`.
    return yaml.load(stream)


def load_data(content: bytes) -> NurseSchedulingData:
    """Load nurse scheduling data from YAML bytes content.

    Args:
        content: File content as bytes

    Returns:
        NurseSchedulingData: The validated scheduling data

    Raises:
        SchedulingDataTooComplexError: If the data expands to more nodes than are processed.
    """
    # Validation walks every node an alias expands to, so bound the expansion before it does.
    measure_yaml_expansion(content)
    data = _load_yaml(content)
    return NurseSchedulingData(**data)
