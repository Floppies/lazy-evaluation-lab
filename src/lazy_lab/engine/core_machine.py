"""Minimal small-step transitions for Core literals."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.core.nodes import (
    CoreBool,
    CoreInt,
    CoreExpr,
    CoreProgram,
    CoreVar,
    CoreBinding,
    CoreLam,
)
from lazy_lab.semantics.predefined import PREDEFINED_IDENTIFIERS
from lazy_lab.runtime.control import EvaluateCore, Return, InitializeCoreBindings
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
    HeapReference,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import (
    Heap,
    Reserved,
)
from lazy_lab.runtime.stack import Stack
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ExecutionStatus,
    ExecutionPhase,
    MachineKind,
    TraceMode,
    MachineState,
)
from lazy_lab.runtime.transitions import (
    BatchResult,
    BatchStopReason,
    TraceEntry,
    TransitionKind,
    TransitionResult,
)
from lazy_lab.runtime.closures import capture_closure
from lazy_lab.runtime.global_bindings import PendingGlobal

class UnsupportedTransitionError(NotImplementedError):
    """The requested transition is not implemented yet."""


class InvalidMachineStateError(RuntimeError):
    """The current state cannot be advanced."""


class EvaluatorBudgetExhaustedError(RuntimeError):
    """No evaluator transitions remain in the execution budget."""


def _validate_configuration(
    state: ExecutionState,
    config: ExecutionConfig,
) -> None:
    machine = state.machine_state

    if (
        machine.machine_kind is not config.machine_kind
        or machine.strategy is not config.strategy
    ):
        raise ValueError(
            "Execution configuration does not match the machine"
        )

    if machine.machine_kind is not MachineKind.CORE:
        raise UnsupportedTransitionError(
            "STG execution is not implemented yet"
        )

def _evaluate_integer(
    expression: CoreInt,
) -> tuple[Return, str]:
    """Apply the Core integer literal rule."""
    return (
        Return(ImmediateInteger(expression.value)),
        "CORE_EVAL_INTEGER",
    )


def _evaluate_boolean(
    expression: CoreBool,
) -> tuple[Return, str]:
    """Apply the Core boolean literal rule."""
    return (
        Return(ImmediateBoolean(expression.value)),
        "CORE_EVAL_BOOLEAN",
    )


def _dispatch_core_evaluation(
    expression: CoreExpr,
) -> tuple[Return, str]:
    """Select one of the currently supported Core rules."""
    if isinstance(expression, CoreInt):
        return _evaluate_integer(expression)

    if isinstance(expression, CoreBool):
        return _evaluate_boolean(expression)

    raise UnsupportedTransitionError(
        f"Unsupported Core expression: "
        f"{type(expression).__name__}"
    )

def step(
    state: ExecutionState,
    config: ExecutionConfig,
) -> TransitionResult:
    """Apply one supported Core machine transition."""
    _validate_configuration(state, config)

    machine = state.machine_state

    if machine.status is not ExecutionStatus.RUNNING:
        raise InvalidMachineStateError(
            "Only RUNNING states can advance"
        )

    control = machine.control

    if not isinstance(
        control,
        (EvaluateCore, InitializeCoreBindings),
    ):
        raise UnsupportedTransitionError(
            f"Unsupported control: {type(control).__name__}"
        )

    # Legacy B03 controls without an entry remain unsupported.
    # Initialization is only executable for states created
    # through the valid Core initialization contract.
    if isinstance(control, InitializeCoreBindings):
        if (
            machine.phase is not ExecutionPhase.INITIALIZATION
            or control.entry_expression is None
        ):
            raise UnsupportedTransitionError(
                "Invalid or incomplete initialization control"
            )

    if (
        machine.evaluator_transition_count
        >= config.execution_step_limit
    ):
        raise EvaluatorBudgetExhaustedError(
            "Evaluator step limit reached"
        )

    # All mutations below affect isolated successor storage.
    snapshot = state.snapshot()

    if isinstance(control, InitializeCoreBindings):
        next_machine, rule_id = _advance_global_initialization(
            snapshot.machine_state,
            control,
        )
    else:
        next_control, rule_id = _dispatch_core_evaluation(
            control.expression
        )

        next_machine = replace(
            snapshot.machine_state,
            control=next_control,
        )

    next_machine = replace(
        next_machine,
        evaluator_transition_count=(
            machine.evaluator_transition_count + 1
        ),
    )

    next_state = replace(
        snapshot,
        state_id=state.state_id + 1,
        transition_index=state.transition_index + 1,
        machine_state=next_machine,
    )

    return TransitionResult(
        previous_state_id=state.state_id,
        next_state=next_state,
        rule_id=rule_id,
        transition_kind=TransitionKind.EVALUATOR,
        phase_before=machine.phase,
        phase_after=next_machine.phase,
    )

def _stop_reason(
    state: ExecutionState,
    config: ExecutionConfig,
) -> BatchStopReason | None:
    machine = state.machine_state

    if machine.status is not ExecutionStatus.RUNNING:
        return BatchStopReason.TERMINAL_STATUS

    if (
        isinstance(machine.control, Return)
        and machine.stack.depth == 0
    ):
        return BatchStopReason.WHNF_PENDING

    if (
        machine.evaluator_transition_count
        >= config.execution_step_limit
    ):
        return BatchStopReason.EVALUATOR_BUDGET

    return None


def _reserve_global_scope(
    heap: Heap,
    bindings: tuple[CoreBinding, ...],
) -> Environment:
    """Reserve predefined and global references before RHS evaluation.

    Mutates the supplied heap. The caller must provide an owned heap
    or an isolated snapshot rather than a previous execution state's
    heap.
    """
    if not isinstance(heap, Heap):
        raise TypeError("Expected a Heap")

    if not isinstance(bindings, tuple):
        raise TypeError("Expected a tuple of CoreBinding")

    if any(not isinstance(binding, CoreBinding) for binding in bindings):
        raise TypeError("Expected CoreBinding entries")

    names = [binding.name for binding in bindings]

    if len(names) != len(set(names)):
        raise ValueError("Duplicate global binding")

    # Install predefined function values in an outer lexical scope.
    predefined_bindings = {}

    for name in sorted(PREDEFINED_IDENTIFIERS):
        function = PredefinedFunction(name)
        reference = heap.allocate(
            function,
            allocated_slots=function.required_slots,
        )
        predefined_bindings[name] = reference

    predefined_environment = Environment(predefined_bindings)

    # Reserve every user-defined global address before installing
    # or evaluating any global RHS.
    global_bindings = {}

    for binding in bindings:
        reference = heap.allocate(
            Reserved(),
            allocated_slots=1,
        )
        global_bindings[binding.name] = reference

    return predefined_environment.extend(global_bindings)

def _install_global_rhs(
    heap: Heap,
    global_environment: Environment,
    binding: CoreBinding,
) -> HeapReference:
    """Install one global RHS without evaluating its expression.

    The complete global scope must already be reserved.

    Mutates the supplied heap. The caller must use owned or
    snapshot-isolated storage when executing a transition.
    """
    if not isinstance(heap, Heap):
        raise TypeError("Expected a Heap")

    if not isinstance(global_environment, Environment):
        raise TypeError("Expected an Environment")

    if not isinstance(binding, CoreBinding):
        raise TypeError("Expected a CoreBinding")

    # Check the user-defined global scope directly: lexical lookup
    # could otherwise select a shadowed predefined function.
    if binding.name not in global_environment.bindings:
        raise UnboundNameError(
            f"Global binding was not reserved: {binding.name!r}"
        )

    reference = global_environment.bindings[binding.name]

    if not isinstance(reference, HeapReference):
        raise TypeError(
            "Global binding must reference a heap cell"
        )

    cell = heap.get(reference)

    if not isinstance(cell.value, Reserved):
        raise ValueError(
            f"Global binding already initialized: {binding.name!r}"
        )

    if isinstance(binding.rhs, CoreLam):
        # A top-level lambda has no free local bindings to capture.
        # References to globals are resolved through the separate
        # global environment when the closure is applied.
        value = capture_closure(
            binding.rhs,
            Environment(),
            free_local_names=(),
        )
    else:
        value = PendingGlobal(binding.rhs)

    heap.replace(reference, value)

    return reference


def _advance_global_initialization(
    machine: MachineState,
    control: InitializeCoreBindings,
) -> tuple[MachineState, str]:
    """Apply one Core global-initialization rule.

    The supplied machine must belong to an isolated successor
    snapshot. Its heap may be mutated by the installation helpers.
    """
    if machine.phase is not ExecutionPhase.INITIALIZATION:
        raise InvalidMachineStateError(
            "Global initialization requires INITIALIZATION phase"
        )

    if control.entry_expression is None:
        raise InvalidMachineStateError(
            "Global initialization requires an entry expression"
        )

    if type(control.scope_reserved) is not bool:
        raise InvalidMachineStateError(
            "scope_reserved must be a boolean"
        )

    if (
        type(control.next_index) is not int
        or not 0 <= control.next_index <= len(control.bindings)
    ):
        raise InvalidMachineStateError(
            "Invalid global initialization index"
        )

    if machine.stack.depth != 0:
        raise InvalidMachineStateError(
            "Global initialization requires an empty stack"
        )

    # Stage 1: all global addresses must exist before RHS
    # installation can begin.
    if not control.scope_reserved:
        if control.next_index != 0:
            raise InvalidMachineStateError(
                "Cannot install globals before scope reservation"
            )

        environment = _reserve_global_scope(
            machine.heap,
            control.bindings,
        )

        return (
            replace(
                machine,
                global_environment=environment,
                local_environment=environment,
                control=replace(
                    control,
                    scope_reserved=True,
                ),
            ),
            "CORE_INIT_RESERVE_GLOBAL_SCOPE",
        )

    # Stage 2: install exactly one global RHS per transition.
    if control.next_index < len(control.bindings):
        binding = control.bindings[control.next_index]

        _install_global_rhs(
            machine.heap,
            machine.global_environment,
            binding,
        )

        return (
            replace(
                machine,
                control=replace(
                    control,
                    next_index=control.next_index + 1,
                ),
            ),
            "CORE_INIT_INSTALL_GLOBAL",
        )

    # Stage 3: the global group is installed. Begin evaluating
    # the user-selected entry without forcing unrelated globals.
    return (
        replace(
            machine,
            phase=ExecutionPhase.EVALUATION,
            control=EvaluateCore(control.entry_expression),
        ),
        "CORE_INIT_ENTER_ENTRY",
    )

def run_batch(
    state: ExecutionState,
    config: ExecutionConfig,
    *,
    max_steps: int,
) -> BatchResult:
    """Execute a bounded batch of supported transitions."""
    if type(max_steps) is not int or max_steps < 1:
        raise ValueError("max_steps must be a positive integer")

    _validate_configuration(state, config)

    current = state
    entries: list[TraceEntry] = []

    for _ in range(max_steps):
        reason = _stop_reason(current, config)

        if reason is not None:
            return BatchResult(
                state=current,
                trace=tuple(entries),
                stop_reason=reason,
            )

        transition = step(current, config)
        current = transition.next_state

        if config.trace_mode is not TraceMode.METRICS_ONLY:
            entries.append(
                TraceEntry.from_transition(transition)
            )

    return BatchResult(
        state=current,
        trace=tuple(entries),
        stop_reason=(
            _stop_reason(current, config)
            or BatchStopReason.BATCH_LIMIT
        ),
    )

def create_initial_core_state(
    program: CoreProgram,
    config: ExecutionConfig,
    *,
    session_id: str,
    entry: str | CoreExpr | None = None,
) -> ExecutionState:
    """Create a Core machine state before global initialization.

    The program and any explicit entry expression are expected
    to have been validated by the caller.
    """
    if not isinstance(program, CoreProgram):
        raise TypeError("Expected a CoreProgram")

    if not isinstance(config, ExecutionConfig):
        raise TypeError("Expected an ExecutionConfig")

    if config.machine_kind is not MachineKind.CORE:
        raise UnsupportedTransitionError(
            "Only Core initialization is supported"
        )

    if entry is None:
        entry = "main"

    if isinstance(entry, str):
        global_names = {
            binding.name for binding in program.bindings
        }

        if entry not in global_names:
            raise ValueError(
                f"Unknown entry binding: {entry!r}"
            )

        entry_expression = CoreVar(entry)

    elif isinstance(entry, CoreExpr):
        entry_expression = entry

    else:
        raise TypeError(
            "Entry must be a binding name or Core expression"
        )

    environment = Environment()

    machine = MachineState(
        machine_kind=MachineKind.CORE,
        strategy=config.strategy,
        status=ExecutionStatus.RUNNING,
        phase=ExecutionPhase.INITIALIZATION,
        control=InitializeCoreBindings(
            bindings=program.bindings,
            next_index=0,
            entry_expression=entry_expression,
        ),
        local_environment=environment,
        global_environment=environment,
        heap=Heap(),
        stack=Stack(),
    )

    return ExecutionState(
        state_id=0,
        session_id=session_id,
        transition_index=0,
        machine_state=machine,
    )
