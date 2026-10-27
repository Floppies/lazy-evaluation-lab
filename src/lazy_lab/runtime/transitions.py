"""Transition results and basic execution trace records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, StrEnum, unique

from .state import ExecutionPhase, ExecutionState


class TransitionKind(str, Enum):
    EVALUATOR = "EVALUATOR"
    RESULT_CONSUMER = "RESULT_CONSUMER"
    GC = "GC"


@unique
class RuleId(StrEnum):
    """Stable identifiers for abstract-machine transitions."""

    # Global initialization
    CORE_INIT_RESERVE_GLOBAL_SCOPE = "CORE_INIT_RESERVE_GLOBAL_SCOPE"
    CORE_INIT_INSTALL_GLOBAL = "CORE_INIT_INSTALL_GLOBAL"
    CORE_INIT_ENTER_ENTRY = "CORE_INIT_ENTER_ENTRY"

    # Core expressions
    CORE_EVAL_INTEGER = "CORE_EVAL_INTEGER"
    CORE_EVAL_BOOLEAN = "CORE_EVAL_BOOLEAN"
    CORE_EVAL_VARIABLE = "CORE_EVAL_VARIABLE"
    CORE_EVAL_LAMBDA = "CORE_EVAL_LAMBDA"
    CORE_EVAL_APPLICATION = "CORE_EVAL_APPLICATION"
    CORE_EVAL_PRIMITIVE_START = "CORE_EVAL_PRIMITIVE_START"
    CORE_EVAL_IF_CONDITION = "CORE_EVAL_IF_CONDITION"

    # WHNF demand
    CORE_FORCE_IMMEDIATE = "CORE_FORCE_IMMEDIATE"
    CORE_FORCE_INDIRECTION = "CORE_FORCE_INDIRECTION"
    CORE_FORCE_FUNCTION_WHNF = "CORE_FORCE_FUNCTION_WHNF"
    CORE_FORCE_GLOBAL_RHS = "CORE_FORCE_GLOBAL_RHS"
    CORE_ROOT_REQUIRE_WHNF = "CORE_ROOT_REQUIRE_WHNF"
    CORE_GLOBAL_REQUIRE_WHNF = "CORE_GLOBAL_REQUIRE_WHNF"
    CORE_GLOBAL_DEMAND_RETURN = "CORE_GLOBAL_DEMAND_RETURN"

    # Function application
    CORE_APPLY_REQUIRE_FUNCTION_WHNF = "CORE_APPLY_REQUIRE_FUNCTION_WHNF"
    CORE_CBV_EVAL_ARGUMENT = "CORE_CBV_EVAL_ARGUMENT"
    CORE_CBV_REQUIRE_ARGUMENT_WHNF = "CORE_CBV_REQUIRE_ARGUMENT_WHNF"
    CORE_CBV_ENTER_BODY = "CORE_CBV_ENTER_BODY"
    CORE_RESTORE_CALLER_ENVIRONMENT = "CORE_RESTORE_CALLER_ENVIRONMENT"

    # Primitive operations
    CORE_PRIM_REQUIRE_OPERAND_WHNF = "CORE_PRIM_REQUIRE_OPERAND_WHNF"
    CORE_PRIM_NEXT_OPERAND = "CORE_PRIM_NEXT_OPERAND"
    CORE_PRIM_OPERANDS_READY = "CORE_PRIM_OPERANDS_READY"
    CORE_PRIM_EXECUTE = "CORE_PRIM_EXECUTE"

    # Conditionals
    CORE_IF_REQUIRE_CONDITION_WHNF = "CORE_IF_REQUIRE_CONDITION_WHNF"
    CORE_IF_SELECT_THEN = "CORE_IF_SELECT_THEN"
    CORE_IF_SELECT_ELSE = "CORE_IF_SELECT_ELSE"

    # Local recursive bindings
    CORE_LETREC_RESERVE_SCOPE = "CORE_LETREC_RESERVE_SCOPE"
    CORE_LETREC_INSTALL_FUNCTION = "CORE_LETREC_INSTALL_FUNCTION"
    CORE_LETREC_ENTER_BODY = "CORE_LETREC_ENTER_BODY"
    CORE_LETREC_EVAL_VALUE = "CORE_LETREC_EVAL_VALUE"
    CORE_LETREC_REQUIRE_VALUE_WHNF = "CORE_LETREC_REQUIRE_VALUE_WHNF"
    CORE_LETREC_STORE_VALUE = "CORE_LETREC_STORE_VALUE"

    # Predefined functions
    CORE_PREDEFINED_PARTIAL_APPLY = "CORE_PREDEFINED_PARTIAL_APPLY"

@dataclass(frozen=True, slots=True)
class TransitionResult:
    previous_state_id: int
    next_state: ExecutionState
    rule_id: RuleId
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
    rule_id: RuleId
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
