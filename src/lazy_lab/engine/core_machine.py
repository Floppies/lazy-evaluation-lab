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
    CoreApp,
    CorePrimOp,
)
from lazy_lab.semantics.predefined import PREDEFINED_IDENTIFIERS
from lazy_lab.runtime.control import ( 
    EvaluateCore,
    Return,
    InitializeCoreBindings,
    Force,
    ApplyPrimitive,
)
from lazy_lab.runtime.references import (
    ImmediateBoolean,
    ImmediateInteger,
    HeapReference,
)
from lazy_lab.runtime.environment import Environment, UnboundNameError
from lazy_lab.runtime.heap import (
    Heap,
    Reserved,
    Indirection,
)
from lazy_lab.runtime.stack import (
    Stack,
    ApplyFunctionFrame,
    ApplyArgumentFrame,
    RestoreEnvironmentFrame,
    GlobalDemandFrame,
    PrimitiveOperandsFrame,
)
from lazy_lab.runtime.predefined import PredefinedFunction
from lazy_lab.runtime.state import (
    ExecutionConfig,
    ExecutionState,
    ExecutionStatus,
    ExecutionPhase,
    MachineKind,
    TraceMode,
    MachineState,
    Strategy,
)
from lazy_lab.runtime.transitions import (
    BatchResult,
    BatchStopReason,
    TraceEntry,
    TransitionKind,
    TransitionResult,
)
from lazy_lab.runtime.closures import (
    capture_closure,
    allocate_closure,
    Closure,
)
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
    machine: MachineState,
) -> tuple[MachineState, str]:
    """Apply one Core expression evaluation rule.

    The supplied machine belongs to an isolated successor
    snapshot. Rules may modify its heap.
    """
    control = machine.control

    if not isinstance(control, EvaluateCore):
        raise InvalidMachineStateError(
            "Expected EvaluateCore control"
        )

    expression = control.expression

    if isinstance(expression, CoreInt):
        next_control, rule_id = _evaluate_integer(expression)

    elif isinstance(expression, CoreBool):
        next_control, rule_id = _evaluate_boolean(expression)

    elif isinstance(expression, CoreVar):
        # Name resolution returns the existing reference.
        # It must not force or dereference the heap object.
        reference = machine.local_environment.lookup(
            expression.name
        )
        next_control = Return(reference)
        rule_id = "CORE_EVAL_VARIABLE"

    elif isinstance(expression, CoreLam):
        # Allocate a closure using the current definition-site
        # environment, without evaluating the lambda body.
        reference = allocate_closure(
            machine.heap,
            expression,
            machine.local_environment,
            machine.global_environment,
        )
        next_control = Return(reference)
        rule_id = "CORE_EVAL_LAMBDA"

    elif isinstance(expression, CoreApp):
        # Preserve the argument and its lexical call-site
        # environment while evaluating the function position.
        machine.stack.push(
            ApplyFunctionFrame(
                argument=expression.argument,
                environment=machine.local_environment,
            )
        )

        # Evaluate only the function position.
        # The argument remains unevaluated in its frame.
        next_control = EvaluateCore(expression.function)
        rule_id = "CORE_EVAL_APPLICATION"
    
    elif isinstance(expression, CorePrimOp):
        if not expression.arguments:
            raise InvalidMachineStateError(
                "Core primitive requires at least one operand"
            )

        # Primitive operands are evaluated from left to right.
        first_argument = expression.arguments[0]

        machine.stack.push(
            PrimitiveOperandsFrame(
                operator=expression.operator,
                remaining_arguments=expression.arguments[1:],
                evaluated_arguments=(),
                environment=machine.local_environment,
            )
        )

        next_control = EvaluateCore(first_argument)
        rule_id = "CORE_EVAL_PRIMITIVE_START"

    else:
        raise UnsupportedTransitionError(
            f"Unsupported Core expression: "
            f"{type(expression).__name__}"
        )

    return (
        replace(machine, control=next_control),
        rule_id,
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
        (EvaluateCore, InitializeCoreBindings, Force, Return),
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

    elif isinstance(control, Force):
        next_machine, rule_id = _advance_force(
            snapshot.machine_state,
            control,
        )

    elif isinstance(control, Return):
        next_machine, rule_id = _advance_return(
            snapshot.machine_state,
            control,
        )
    else:
        next_machine, rule_id = _dispatch_core_evaluation(
        snapshot.machine_state
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
        and _reference_is_whnf(
            machine,
            machine.control.reference,
        )
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

def _reference_is_whnf(
    machine: MachineState,
    reference,
) -> bool:
    """Recognize supported weak-head-normal-form references."""
    if isinstance(
        reference,
        (ImmediateInteger, ImmediateBoolean),
    ):
        return True

    if not isinstance(reference, HeapReference):
        raise TypeError("Expected a runtime reference")

    value = machine.heap.get(reference).value

    return isinstance(
        value,
        (Closure, PredefinedFunction),
    )

def _advance_force(
    machine: MachineState,
    control: Force,
) -> tuple[MachineState, str]:
    """Demand WHNF without implementing thunk updates."""
    reference = control.reference

    if isinstance(
        reference,
        (ImmediateInteger, ImmediateBoolean),
    ):
        return (
            replace(machine, control=Return(reference)),
            "CORE_FORCE_IMMEDIATE",
        )

    if not isinstance(reference, HeapReference):
        raise TypeError("Expected a runtime reference")

    value = machine.heap.get(reference).value

    if isinstance(value, Indirection):
        return (
            replace(machine, control=Force(value.target)),
            "CORE_FORCE_INDIRECTION",
        )

    if isinstance(value, (Closure, PredefinedFunction)):
        return (
            replace(machine, control=Return(reference)),
            "CORE_FORCE_FUNCTION_WHNF",
        )

    if isinstance(value, PendingGlobal):
        machine.stack.push(
            GlobalDemandFrame(
                return_environment=machine.local_environment,
                pending_reference=reference,
            )
        )

        return (
            replace(
                machine,
                local_environment=machine.global_environment,
                control=EvaluateCore(value.expression),
            ),
            "CORE_FORCE_GLOBAL_RHS",
        )

    if isinstance(value, Reserved):
        raise InvalidMachineStateError(
            "Cannot force an uninitialized heap cell"
        )

    raise UnsupportedTransitionError(
        f"Unsupported heap object: {type(value).__name__}"
    )

def _advance_return(
    machine: MachineState,
    control: Return,
) -> tuple[MachineState, str]:
    """Resume a continuation or demand a root result."""
    reference = control.reference

    if machine.stack.depth > 0:
        frame = machine.stack.peek()

        # 1. Resume a pending global RHS evaluation.
        if isinstance(frame, GlobalDemandFrame):
            if not frame.awaiting_whnf:
                machine.stack.pop()
                machine.stack.push(
                    replace(frame, awaiting_whnf=True)
                )

                return (
                    replace(
                        machine,
                        control=Force(reference),
                    ),
                    "CORE_GLOBAL_REQUIRE_WHNF",
                )

            if not _reference_is_whnf(machine, reference):
                raise InvalidMachineStateError(
                    "Global demand resumed without WHNF"
                )

            machine.stack.pop()

            return (
                replace(
                    machine,
                    local_environment=frame.return_environment,
                    control=Return(reference),
                ),
                "CORE_GLOBAL_DEMAND_RETURN",
            )

        # 2. Primitive operand evaluation.
        if isinstance(frame, PrimitiveOperandsFrame):
            return _resume_primitive_operand(
                machine,
                control,
                frame,
            )

        # 3. Function position has returned.
        # Demand the function and prepare its argument.
        if isinstance(frame, ApplyFunctionFrame):
            return _resume_apply_function(
                machine,
                control,
                frame,
            )

        # 4. Argument has returned.
        # Under CBV, demand WHNF and enter the closure body.
        if isinstance(frame, ApplyArgumentFrame):
            return _resume_apply_argument(
                machine,
                control,
                frame,
            )

        # 5. Function body has returned.
        # Restore the caller's lexical environment.
        if isinstance(frame, RestoreEnvironmentFrame):
            return _resume_caller_environment(
                machine,
                control,
                frame,
            )

        raise UnsupportedTransitionError(
            "Unsupported return continuation: "
            f"{type(frame).__name__}"
        )

    # 6. No continuation remains: handle the root result.
    # A root reference to a pending object still requires WHNF.
    if isinstance(reference, HeapReference):
        value = machine.heap.get(reference).value

        if isinstance(value, (PendingGlobal, Indirection)):
            return (
                replace(
                    machine,
                    control=Force(reference),
                ),
                "CORE_ROOT_REQUIRE_WHNF",
            )

        if isinstance(value, Reserved):
            raise InvalidMachineStateError(
                "Root result refers to an uninitialized cell"
            )

    # An already-WHNF root Return belongs to the result
    # consumer, not to another evaluator transition.
    raise UnsupportedTransitionError(
        "Root result is awaiting observation"
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

def _resume_apply_function(
    machine: MachineState,
    control: Return,
    frame: ApplyFunctionFrame,
) -> tuple[MachineState, str]:
    """Demand the function, then begin strict CBV argument evaluation."""
    reference = control.reference

    if not frame.awaiting_whnf:
        machine.stack.pop()
        machine.stack.push(
            replace(frame, awaiting_whnf=True)
        )

        return (
            replace(machine, control=Force(reference)),
            "CORE_APPLY_REQUIRE_FUNCTION_WHNF",
        )

    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Function demand returned without WHNF"
        )

    if machine.strategy is not Strategy.CBV:
        raise UnsupportedTransitionError(
            "Non-strict application is not implemented yet"
        )

    if not isinstance(reference, HeapReference):
        raise TypeError("Cannot apply a non-function value")

    function_value = machine.heap.get(reference).value

    if isinstance(function_value, PredefinedFunction):
        raise UnsupportedTransitionError(
            "Predefined function application is not implemented yet"
        )

    if not isinstance(function_value, Closure):
        raise TypeError("Cannot apply a non-function value")

    # The function is ready. CBV evaluates its argument
    # in the original call-site environment.
    machine.stack.pop()
    machine.stack.push(
        ApplyArgumentFrame(
            function=reference,
            return_environment=frame.environment,
        )
    )

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=EvaluateCore(frame.argument),
        ),
        "CORE_CBV_EVAL_ARGUMENT",
    )

def _resume_apply_argument(
    machine: MachineState,
    control: Return,
    frame: ApplyArgumentFrame,
) -> tuple[MachineState, str]:
    """Demand the CBV argument, then enter the closure body."""
    if frame.return_environment is None:
        raise UnsupportedTransitionError(
            "Incomplete application-argument continuation"
        )

    reference = control.reference

    if not frame.awaiting_whnf:
        machine.stack.pop()
        machine.stack.push(
            replace(frame, awaiting_whnf=True)
        )

        return (
            replace(machine, control=Force(reference)),
            "CORE_CBV_REQUIRE_ARGUMENT_WHNF",
        )

    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "CBV argument returned without WHNF"
        )

    function_reference = frame.function

    if not isinstance(function_reference, HeapReference):
        raise InvalidMachineStateError(
            "Applied function has an invalid reference"
        )

    function_value = machine.heap.get(
        function_reference
    ).value

    if not isinstance(function_value, Closure):
        raise InvalidMachineStateError(
            "Applied function is no longer a closure"
        )

    # Reconstruct lexical scope from the closure's captures.
    call_environment = function_value.call_environment(
        reference,
        machine.global_environment,
    )

    machine.stack.pop()
    machine.stack.push(
        RestoreEnvironmentFrame(frame.return_environment)
    )

    return (
        replace(
            machine,
            local_environment=call_environment,
            control=EvaluateCore(
                function_value.lambda_expression.body
            ),
        ),
        "CORE_CBV_ENTER_BODY",
    )

def _resume_caller_environment(
    machine: MachineState,
    control: Return,
    frame: RestoreEnvironmentFrame,
) -> tuple[MachineState, str]:
    """Leave a function body without changing its returned reference."""
    machine.stack.pop()

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=Return(control.reference),
        ),
        "CORE_RESTORE_CALLER_ENVIRONMENT",
    )

def _resume_primitive_operand(
    machine: MachineState,
    control: Return,
    frame: PrimitiveOperandsFrame,
) -> tuple[MachineState, str]:
    """Demand an operand to WHNF and continue left to right."""
    reference = control.reference

    # Stage 1: the operand expression returned a reference.
    # Its value may still require evaluation.
    if not frame.awaiting_whnf:
        machine.stack.pop()
        machine.stack.push(
            replace(frame, awaiting_whnf=True)
        )

        return (
            replace(
                machine,
                control=Force(reference),
            ),
            "CORE_PRIM_REQUIRE_OPERAND_WHNF",
        )

    # Stage 2: Force returned. The operand must now be WHNF.
    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Primitive operand demand returned without WHNF"
        )

    evaluated_arguments = (
        frame.evaluated_arguments + (reference,)
    )

    machine.stack.pop()

    # Stage 3: evaluate the next operand, if present.
    if frame.remaining_arguments:
        next_argument = frame.remaining_arguments[0]
        remaining = frame.remaining_arguments[1:]

        machine.stack.push(
            replace(
                frame,
                remaining_arguments=remaining,
                evaluated_arguments=evaluated_arguments,
                awaiting_whnf=False,
            )
        )

        return (
            replace(
                machine,
                local_environment=frame.environment,
                control=EvaluateCore(next_argument),
            ),
            "CORE_PRIM_NEXT_OPERAND",
        )

    # Stage 4: all operands reached WHNF.
    # Actual operator execution belongs to B04.5.3.
    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=ApplyPrimitive(
                operator=frame.operator,
                arguments=evaluated_arguments,
            ),
        ),
        "CORE_PRIM_OPERANDS_READY",
    )
