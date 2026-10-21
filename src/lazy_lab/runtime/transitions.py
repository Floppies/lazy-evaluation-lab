"""Transition results and basic execution trace records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .state import ExecutionPhase, ExecutionState


class TransitionKind(str, Enum):
    EVALUATOR = "EVALUATOR"
    RESULT_CONSUMER = "RESULT_CONSUMER"
    GC = "GC"


@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous_state_id: int
    next_state: ExecutionState
    rule_id: str
    transition_kind: TransitionKind
    phase_before: ExecutionPhase
    phase_after: ExecutionPhase
    semantic_events: tuple[str, ...] = ()
    heap_effects: tuple[str, ...] = ()
    stack_effects: tuple[str, ...] = ()
    source_origins: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class TraceEntry:
    previous_state_id: int
    next_state_id: int
    rule_id: str
    transition_kind: TransitionKind
    phase_before: ExecutionPhase
    phase_after: ExecutionPhase

    @classmethod
    def from_transition(
        cls, transition: TransitionResult
    ) -> TraceEntry:
        return cls(
            previous_state_id=transition.previous_state_id,
            next_state_id=transition.next_state.state_id,
            rule_id=transition.rule_id,
            transition_kind=transition.transition_kind,
            phase_before=transition.phase_before,
            phase_after=transition.phase_after,
        )


class BatchStopReason(str, Enum):
    WHNF_PENDING = "WHNF_PENDING"
    BATCH_LIMIT = "BATCH_LIMIT"
    EVALUATOR_BUDGET = "EVALUATOR_BUDGET"
    TERMINAL_STATUS = "TERMINAL_STATUS"


@dataclass(frozen=True, slots=True)
class BatchResult:
    state: ExecutionState
    trace: tuple[TraceEntry, ...]
    stop_reason: BatchStopReason
