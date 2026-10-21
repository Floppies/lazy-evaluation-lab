
"""Execution configuration and abstract machine state."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum

from .control import CoreControl
from .environment import Environment
from .heap import Heap
from .references import RuntimeRef
from .stack import Stack


class MachineKind(str, Enum):
    CORE = "CORE"
    STG = "STG"


class Strategy(str, Enum):
    CBV = "CBV"
    CBN = "CBN"
    CBNEED = "CBNEED"


class ExecutionPhase(str, Enum):
    INITIALIZATION = "INITIALIZATION"
    EVALUATION = "EVALUATION"
    RESULT_MATERIALIZATION = "RESULT_MATERIALIZATION"
    GARBAGE_COLLECTION = "GARBAGE_COLLECTION"


class ExecutionStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    BLACKHOLE_DETECTED = "BLACKHOLE_DETECTED"
    CYCLIC_INITIALIZATION_DETECTED = (
        "CYCLIC_INITIALIZATION_DETECTED"
    )
    STEP_LIMIT_REACHED = "STEP_LIMIT_REACHED"
    RESULT_LIMIT_REACHED = "RESULT_LIMIT_REACHED"
    RUNTIME_ERROR = "RUNTIME_ERROR"


class ResultPolicy(str, Enum):
    WHNF_ONLY = "WHNF_ONLY"
    MATERIALIZE_COMPLETE_VALUE = "MATERIALIZE_COMPLETE_VALUE"
    ASK_AT_WHNF = "ASK_AT_WHNF"


class TraceMode(str, Enum):
    FULL = "FULL"
    EVENTS = "EVENTS"
    METRICS_ONLY = "METRICS_ONLY"


@dataclass(frozen=True, slots=True)
class ExecutionConfig:
    machine_kind: MachineKind
    strategy: Strategy
    result_policy: ResultPolicy
    execution_step_limit: int
    result_node_limit: int
    trace_mode: TraceMode

    def __post_init__(self) -> None:
        if not isinstance(self.machine_kind, MachineKind):
            raise TypeError("Invalid machine kind")

        if not isinstance(self.strategy, Strategy):
            raise TypeError("Invalid evaluation strategy")

        if not isinstance(self.result_policy, ResultPolicy):
            raise TypeError("Invalid result policy")

        if not isinstance(self.trace_mode, TraceMode):
            raise TypeError("Invalid trace mode")

        if (
            self.machine_kind is MachineKind.STG
            and self.strategy is not Strategy.CBNEED
        ):
            raise ValueError(
                "STG supports only call-by-need evaluation"
            )

        if (
            type(self.execution_step_limit) is not int
            or self.execution_step_limit < 1
        ):
            raise ValueError(
                "execution_step_limit must be a positive integer"
            )

        if (
            type(self.result_node_limit) is not int
            or self.result_node_limit < 1
        ):
            raise ValueError(
                "result_node_limit must be a positive integer"
            )


@dataclass(frozen=True, slots=True)
class ResultState:
    """Structural state of the output consumer."""

    result_reference: RuntimeRef | None = None
    resolved_result_mode: ResultPolicy | None = None


@dataclass(frozen=True, slots=True)
class InstrumentationState:
    """Placeholder for future metrics and object history."""


@dataclass(frozen=True, slots=True)
class MachineState:
    machine_kind: MachineKind
    strategy: Strategy
    status: ExecutionStatus
    phase: ExecutionPhase
    control: CoreControl
    local_environment: Environment
    global_environment: Environment
    heap: Heap
    stack: Stack
    result_state: ResultState = field(
        default_factory=ResultState
    )
    gc_state: None = None
    evaluator_transition_count: int = 0

    def __post_init__(self) -> None:
        if (
            type(self.evaluator_transition_count) is not int
            or self.evaluator_transition_count < 0
        ):
            raise ValueError(
                "evaluator_transition_count must be non-negative"
            )

    @property
    def next_object_id(self) -> int:
        return self.heap.next_object_id

@dataclass(frozen=True, slots=True)
class ExecutionState:
    state_id: int
    session_id: str
    transition_index: int
    machine_state: MachineState
    instrumentation_state: InstrumentationState = field(
        default_factory=InstrumentationState
    )

    def __post_init__(self) -> None:
        if type(self.state_id) is not int or self.state_id < 0:
            raise ValueError("state_id must be non-negative")

        if (
            type(self.transition_index) is not int
            or self.transition_index < 0
        ):
            raise ValueError(
                "transition_index must be non-negative"
            )

        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be non-empty")

    def snapshot(self) -> ExecutionState:
        """Copy mutable machine storage for independent inspection."""
        machine_copy = replace(
            self.machine_state,
            heap=self.machine_state.heap.clone(),
            stack=self.machine_state.stack.clone(),
        )

        return replace(
            self,
            machine_state=machine_copy,
        )
