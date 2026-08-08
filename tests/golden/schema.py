from typing import Any, Literal

from pydantic import BaseModel, model_validator

AssertType = Literal[
    "exact_match",
    "contains",
    "regex_match",
    "numeric_tolerance",
    "llm_judge",
    "custom",
]


class GoldenCase(BaseModel):
    tool_name: str
    input: dict[str, Any]
    assert_type: AssertType
    expected: Any = None
    # Optional: check a single key of the tool's dict output instead of the
    # whole thing. Leave unset to compare against the full result.
    field: str | None = None
    tolerance: float | None = None  # required when assert_type == "numeric_tolerance"
    custom_assertion: str | None = (
        None  # "module.path:function_name", required when assert_type == "custom"
    )
    description: str | None = None  # human label, used as the pytest id and in failure messages

    @model_validator(mode="after")
    def _validate_shape(self) -> "GoldenCase":
        if self.assert_type == "custom" and not self.custom_assertion:
            raise ValueError("custom_assertion is required when assert_type='custom'")
        if self.assert_type == "numeric_tolerance" and self.tolerance is None:
            raise ValueError("tolerance is required when assert_type='numeric_tolerance'")
        if self.assert_type != "custom" and self.expected is None:
            raise ValueError(f"expected is required when assert_type='{self.assert_type}'")
        return self
