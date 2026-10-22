"""Credential-scoped model discovery and validated reasoning choices."""

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

import asyncio
import json
import logging
import time
from dataclasses import dataclass, replace
from typing import Any

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator

from .config import AiSettings
from .provider import OpenAiCompatibleProvider

logger = logging.getLogger(__name__)


class ModelSelection(BaseModel):
    """Public settings frozen when a turn is accepted."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    model: str = Field(min_length=1, max_length=256)
    reasoning: str = Field(default="default", min_length=1, max_length=64)


class ProviderProfile(BaseModel):
    """Server-only credentials for one AI access key."""

    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1)
    default_model: str = Field(min_length=1, max_length=256)


REASONING_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


class ReasoningOption(BaseModel):
    """Gateway metadata describing an exact supported request configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=80)
    parameters: dict[str, Any]

    @model_validator(mode="after")
    def validate_parameters(self):
        # Metadata cannot override routing, messages, tools, or streaming options.
        if self.id == "default" or not self.parameters:
            raise ValueError("Reasoning options must have parameters and cannot replace Default")
        if set(self.parameters) - {"reasoning_effort", "thinking", "chat_template_kwargs"}:
            raise ValueError("Unsupported reasoning parameter")
        effort = self.parameters.get("reasoning_effort")
        if "reasoning_effort" in self.parameters and effort not in REASONING_EFFORTS:
            raise ValueError("Unsupported reasoning effort")
        thinking = self.parameters.get("thinking")
        if "thinking" in self.parameters:
            if not isinstance(thinking, dict) or set(thinking) - {"type", "budget_tokens"}:
                raise ValueError("Invalid thinking configuration")
            if thinking.get("type") not in {"enabled", "disabled", "adaptive"}:
                raise ValueError("Invalid thinking type")
            budget = thinking.get("budget_tokens")
            if budget is not None and (type(budget) is not int or budget <= 0):
                raise ValueError("Thinking budget must be a positive integer")
            if thinking.get("type") == "disabled" and budget is not None:
                raise ValueError("Disabled thinking cannot have a budget")
        if "chat_template_kwargs" in self.parameters:
            template = self.parameters["chat_template_kwargs"]
            if (
                not isinstance(template, dict)
                or set(template) - {"enable_thinking", "reasoning_effort"}
                or "enable_thinking" not in template
                or type(template["enable_thinking"]) is not bool
            ):
                raise ValueError("Chat template reasoning must set enable_thinking to a boolean")
            if "reasoning_effort" in template and template["reasoning_effort"] not in REASONING_EFFORTS:
                raise ValueError("Unsupported chat template reasoning effort")
        return self


@dataclass(frozen=True)
class AvailableModel:
    id: str
    name: str
    reasoning: tuple[ReasoningOption, ...] = ()
    context_tokens: int | None = None
    default_reasoning: str = "default"

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "context_tokens": self.context_tokens,
            "default_reasoning": self.default_reasoning,
            "reasoning_options": [
                *([{"id": "default", "label": "Provider default"}] if self.default_reasoning == "default" else []),
                *[{"id": option.id, "label": option.label} for option in self.reasoning],
            ],
        }


def _matches_parameters(expected: dict, configured: dict) -> bool:
    """Match only advertised reasoning fields, without publishing deployment secrets."""
    return all(
        key in configured
        and (
            isinstance(configured[key], dict) and _matches_parameters(value, configured[key])
            if isinstance(value, dict)
            else type(value) is type(configured[key]) and value == configured[key]
        )
        for key, value in expected.items()
    )


class ModelCatalog:
    """Discover with the caller's gateway key and keep metadata out of the browser."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.profiles: dict[str, ProviderProfile] = {}
        if settings.provider_profiles_json:
            try:
                raw = json.loads(settings.provider_profiles_json)
                if not isinstance(raw, dict):
                    raise TypeError
                self.profiles = {key: ProviderProfile.model_validate(value) for key, value in raw.items()}
            except (ValueError, TypeError, ValidationError):
                # Pydantic validation errors may contain a secret input value.
                raise ValueError(
                    "AI_PROVIDER_PROFILES must map AI credential IDs to api_key and default_model"
                ) from None
        self._cache: dict[str | None, tuple[float, tuple[AvailableModel, ...]]] = {}
        self._locks: dict[str | None, asyncio.Lock] = {}

    def profile(self, credential_id: str | None) -> ProviderProfile:
        if self.profiles:
            profile = self.profiles.get(credential_id or "")
            if profile is None:
                raise HTTPException(403, "This AI key has no provider profile.")
            return profile
        return ProviderProfile(api_key=self.settings.provider_api_key, default_model=self.settings.provider_model)

    async def models(self, credential_id: str | None) -> tuple[AvailableModel, ...]:
        profile = self.profile(credential_id)
        saved = self._cache.get(credential_id)
        if saved is not None and saved[0] > time.monotonic():
            return saved[1]
        async with self._locks.setdefault(credential_id, asyncio.Lock()):
            saved = self._cache.get(credential_id)
            if saved is not None and saved[0] > time.monotonic():
                return saved[1]
            headers = {"Authorization": f"Bearer {profile.api_key.get_secret_value()}"}
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(f"{self.settings.provider_base_url}/models", headers=headers)
                    response.raise_for_status()
                    data = response.json()["data"]
                    if not isinstance(data, list):
                        raise TypeError
                    # This endpoint is optional on other OpenAI-compatible servers.
                    try:
                        info_response = await client.get(
                            f"{self.settings.provider_base_url}/model/info", headers=headers
                        )
                        info = info_response.json().get("data", []) if info_response.is_success else []
                    except (httpx.HTTPError, ValueError, AttributeError):
                        logger.exception("AI reasoning metadata discovery failed")
                        info = []
            except (httpx.HTTPError, ValueError, KeyError, TypeError):
                logger.exception("AI model discovery failed")
                raise HTTPException(503, "AI model discovery is unavailable. Please try again.") from None
            metadata = (
                {
                    item["model_name"]: item
                    for item in info
                    if isinstance(item, dict) and isinstance(item.get("model_name"), str)
                }
                if isinstance(info, list)
                else {}
            )
            models = []
            try:
                for item in data:
                    if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                        continue
                    model_id = item["id"]
                    deployment = metadata.get(model_id, {})
                    details = {**item, **deployment.get("model_info", {})}
                    if details.get("mode", "chat") != "chat" or details.get("supports_function_calling") is False:
                        continue
                    # Explicit choices avoid guessing effort levels from model names.
                    choices = tuple(
                        ReasoningOption.model_validate(option) for option in details.get("chat_reasoning_options", [])
                    )
                    if len({option.id for option in choices}) != len(choices):
                        raise TypeError
                    configured = deployment.get("litellm_params") or {}
                    defaults = [option.id for option in choices if _matches_parameters(option.parameters, configured)]
                    default_reasoning = defaults[0] if len(defaults) == 1 else "default"
                    limit = next(
                        (
                            details[key]
                            for key in ("max_input_tokens", "max_model_len", "context_length", "max_tokens")
                            if type(details.get(key)) is int and details[key] > 0
                        ),
                        None,
                    )
                    models.append(
                        AvailableModel(
                            model_id,
                            str(details.get("chat_display_name") or model_id),
                            choices,
                            limit,
                            default_reasoning,
                        )
                    )
            except (ValueError, TypeError):
                logger.exception("AI model reasoning metadata is invalid")
                raise HTTPException(503, "AI model reasoning metadata is invalid.") from None
            result = tuple({model.id: model for model in models}.values())
            self._cache[credential_id] = (time.monotonic() + 60, result)
            return result

    async def resolve(self, credential_id: str | None, selection: ModelSelection | None):
        profile = self.profile(credential_id)
        selection = selection or ModelSelection(model=profile.default_model)
        models = await self.models(credential_id)
        model = next((item for item in models if item.id == selection.model), None)
        if model is None:
            raise HTTPException(422, "The selected model is not available to this AI key.")
        if selection.reasoning == "default":
            selection = selection.model_copy(update={"reasoning": model.default_reasoning})
        parameters = {}
        if selection.reasoning != "default":
            option = next((item for item in model.reasoning if item.id == selection.reasoning), None)
            if option is None:
                raise HTTPException(422, "The selected reasoning option is not supported by this model.")
            parameters = option.parameters
        settings = replace(self.settings, provider_api_key=profile.api_key.get_secret_value(), provider_model=model.id)
        provider = OpenAiCompatibleProvider(settings, include_usage=True, parameters=parameters, include_costs=True)
        provider.context_tokens = model.context_tokens
        provider._context_tokens_loaded = True
        return selection, settings, provider
