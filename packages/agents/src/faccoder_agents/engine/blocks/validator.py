from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from faccoder_agents.engine.blocks.base import BaseBlock
from faccoder_agents.engine.models import BlockResult, BlockStatus


class ValidatorBlock(BaseBlock):
    """Validates pipeline state keys, schemas, or custom predicates."""

    def __init__(
        self,
        name: str,
        required_keys: list[str] | None = None,
        schema: type[BaseModel] | None = None,
        custom_validator: Callable[[dict[str, Any]], tuple[bool, str | None]] | None = None,
        target_key: str | None = None,
        raise_on_error: bool = False,
    ) -> None:
        super().__init__(name=name, block_type="validator")
        self.required_keys = required_keys or []
        self.schema = schema
        self.custom_validator = custom_validator
        self.target_key = target_key
        self.raise_on_error = raise_on_error

    def execute(self, state: dict[str, Any], context: dict[str, Any] | None = None) -> BlockResult:
        data = state.get("data", {})
        target = data.get(self.target_key, {}) if self.target_key else data

        errors: list[str] = []

        # 1. Required keys check
        for key in self.required_keys:
            if key not in target or target[key] is None:
                errors.append(f"Missing required key: '{key}'")

        # 2. Schema validation
        if self.schema is not None and not errors:
            try:
                self.schema.model_validate(target)
            except ValidationError as exc:
                errors.append(f"Schema validation error: {exc}")

        # 3. Custom validator callable
        if self.custom_validator is not None and not errors:
            valid, reason = self.custom_validator(target)
            if not valid:
                errors.append(reason or "Custom validation failed")

        if errors:
            err_msg = "; ".join(errors)
            if self.raise_on_error:
                raise ValueError(f"[{self.name}] Validation failed: {err_msg}")
            return BlockResult(
                block_name=self.name,
                status=BlockStatus.FAILURE,
                error=err_msg,
                message=f"Validation failed with {len(errors)} error(s)",
            )

        return BlockResult(
            block_name=self.name,
            status=BlockStatus.SUCCESS,
            message="Validation passed successfully",
        )
