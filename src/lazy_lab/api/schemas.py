
"""HTTP request schemas for interactive sessions."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lazy_lab.runtime.state import ResultPolicy, TraceMode


class SessionCreateRequest(BaseModel):
    """Validated parameters for a new Core execution session."""

    model_config = ConfigDict(extra="forbid")

    source: str = Field(min_length=1)
    strategy: Literal["CBV", "CBNEED"] = "CBNEED"
    result_policy: ResultPolicy = ResultPolicy.WHNF_ONLY
    trace_mode: TraceMode = TraceMode.FULL

    execution_step_limit: int = Field(
        default=500,
        gt=0,
        strict=True,
    )
    result_node_limit: int = Field(
        default=100,
        gt=0,
        strict=True,
    )

    entry: str = Field(default="main", min_length=1)

    capture_categories: frozenset[str] = Field(
        default_factory=frozenset,
    )
