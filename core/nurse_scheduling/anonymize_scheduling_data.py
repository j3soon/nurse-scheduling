"""Helpers for anonymizing sensitive identifiers in scheduling data."""

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

from io import BytesIO
from typing import Any

from ruamel.yaml import YAML

_PEOPLE_REFERENCE_KEYS = frozenset({"person", "qualifiedPeople", "people1", "people2", "people", "countPeople"})


def _anonymize_people_reference(value: Any, id_map: dict[Any, str]) -> Any:
    if isinstance(value, list):
        return [_anonymize_people_reference(item, id_map) for item in value]
    return id_map.get(value, value)


def _anonymize_people_references(value: Any, id_map: dict[Any, str]) -> None:
    if isinstance(value, list):
        for item in value:
            _anonymize_people_references(item, id_map)
        return
    if not isinstance(value, dict):
        return

    for key, item in value.items():
        if key in _PEOPLE_REFERENCE_KEYS and not isinstance(item, dict):
            value[key] = _anonymize_people_reference(item, id_map)
        else:
            _anonymize_people_references(item, id_map)


def _remove_description_fields(value: Any) -> None:
    if isinstance(value, list):
        for item in value:
            _remove_description_fields(item)
        return
    if not isinstance(value, dict):
        return

    value.pop("description", None)
    for item in value.values():
        _remove_description_fields(item)


def _anonymize_yaml_content(content: bytes) -> bytes:
    yaml = YAML(typ="safe")
    data = yaml.load(BytesIO(content))
    if not isinstance(data, dict):
        return content

    _remove_description_fields(data)

    people = data.get("people")
    if not isinstance(people, dict):
        return _dump_yaml(data)
    items = people.get("items", [])
    groups = people.get("groups", [])
    if not isinstance(items, list) or not isinstance(groups, list):
        return _dump_yaml(data)

    retained_ids = {group["id"] for group in groups if isinstance(group, dict) and "id" in group}
    id_map: dict[Any, str] = {}
    next_index = 1
    for item in items:
        if not isinstance(item, dict) or "id" not in item:
            continue
        original_id = item["id"]
        anonymized_id = f"P{next_index}"
        while anonymized_id in retained_ids:
            next_index += 1
            anonymized_id = f"P{next_index}"
        id_map[original_id] = anonymized_id
        retained_ids.add(anonymized_id)
        next_index += 1

    _anonymize_people_references(data, id_map)
    for item in items:
        if isinstance(item, dict) and "id" in item:
            item["id"] = id_map.get(item["id"], item["id"])
    for group in groups:
        if isinstance(group, dict) and "members" in group:
            group["members"] = _anonymize_people_reference(group["members"], id_map)

    return _dump_yaml(data)


def _dump_yaml(data: Any) -> bytes:
    yaml = YAML(typ="safe")
    output = BytesIO()
    yaml.dump(data, output)
    return output.getvalue()


def anonymize_scheduling_data_in_yaml(content: bytes) -> bytes:
    """Return YAML with supported sensitive scheduling data anonymized, or the original on failure."""
    try:
        return _anonymize_yaml_content(content)
    except Exception:
        return content
