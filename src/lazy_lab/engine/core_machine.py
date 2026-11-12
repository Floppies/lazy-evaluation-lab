"""Small-step Core CBV and CBNeed evaluation with explicit WHNF demand and continuations."""

from __future__ import annotations

from dataclasses import replace

from lazy_lab.core.nodes import (
    CoreBool,
    CoreCase,
    CoreCon,
    CoreConAlt,
    CoreDefaultAlt,
    CoreInt,
    CoreExpr,
    CoreProgram,
    CoreVar,
    CoreBinding,
    CoreLam,
    CoreApp,
    CorePrimOp,
    CoreIf,
    CoreLetRec,
)
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.runtime.constructors import ConstructorValue, allocate_constructor
from lazy_lab.runtime.materialization import resume_materialization
from lazy_lab.semantics.predefined import PREDEFINED_IDENTIFIERS
from lazy_lab.runtime.predefined import (
    PredefinedFunction,
    PartialPredefinedFunction,
)
from lazy_lab.runtime.control import ( 
    EvaluateCore,
    Return,
    InitializeCoreBindings,
    Force,
    ApplyPrimitive,
    InitializeLocalBindings,
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
    ConstructorFieldsFrame,
    CoreCaseFrame,
    MaterializationDemandFrame,
    Stack,
    ApplyFunctionFrame,
    ApplyArgumentFrame,
    RestoreEnvironmentFrame,
    GlobalDemandFrame,
    PrimitiveOperandsFrame,
    IfFrame,
    LocalValueInitializationFrame,
    UpdateFrame,
    SeqFirstArgumentFrame,
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
    RuleId,
)
from lazy_lab.runtime.closures import (
    capture_closure,
    allocate_closure,
    Closure,
)
from lazy_lab.runtime.global_bindings import PendingGlobal
from lazy_lab.runtime.thunks import (
    allocate_thunk,
    ThunkPayload,
    PendingThunk,
    EvaluatingThunk,
)
from lazy_lab.metrics.recording import (
    SemanticEventRecorder,
    HeapEffectRecorder,
)
from lazy_lab.metrics.effects import HeapBaselineRecorded


class UnsupportedTransitionError(NotImplementedError):
    """The requested transition is not implemented yet."""


class InvalidMachineStateError(RuntimeError):
    """The current state cannot be advanced."""

    
class UninitializedLocalBindingError(InvalidMachineStateError):
    """A strict local RHS demanded a binding before initialization."""


class EvaluatorBudgetExhaustedError(RuntimeError):
    """No evaluator transitions remain in the execution budget."""


class PatternMatchError(RuntimeError):
    """No CoreCase alternative matches the scrutinee WHNF."""


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
) -> tuple[Return, RuleId]:
    """Apply the Core integer literal rule."""
    return (
        Return(ImmediateInteger(expression.value)),
        RuleId.CORE_EVAL_INTEGER,
    )


def _evaluate_boolean(
    expression: CoreBool,
) -> tuple[Return, RuleId]:
    """Apply the Core boolean literal rule."""
    return (
        Return(ImmediateBoolean(expression.value)),
        RuleId.CORE_EVAL_BOOLEAN,
    )



def _dispatch_core_evaluation(
    machine: MachineState,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
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
        recorder.emit(
            SemanticEventKind.VARIABLE_LOOKED_UP,
            node=expression,
        )
        next_control = Return(reference)
        rule_id = RuleId.CORE_EVAL_VARIABLE

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
        rule_id = RuleId.CORE_EVAL_LAMBDA

    elif isinstance(expression, CoreApp):
        # Preserve the argument and its lexical call-site
        # environment while evaluating the function position.
        machine.stack.push(
            ApplyFunctionFrame(
                argument=expression.argument,
                environment=machine.local_environment,
                application=expression,
            )
        )

        # Evaluate only the function position.
        # The argument remains unevaluated in its frame.
        next_control = EvaluateCore(expression.function)
        rule_id = RuleId.CORE_EVAL_APPLICATION
    
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
                primitive=expression,
            )
        )

        next_control = EvaluateCore(first_argument)
        rule_id = RuleId.CORE_EVAL_PRIMITIVE_START

    elif isinstance(expression, CoreIf):
        # Preserve both branches without evaluating them.
        machine.stack.push(
            IfFrame(
                then_branch=expression.then_branch,
                else_branch=expression.else_branch,
                environment=machine.local_environment,
                conditional=expression
            )
        )

        next_control = EvaluateCore(expression.condition)
        rule_id = RuleId.CORE_EVAL_IF_CONDITION

    elif isinstance(expression, CoreLetRec):
        return _enter_local_letrec(
            machine,
            expression,
            recorder,
        )

    elif isinstance(expression, CoreCase):
        machine.stack.push(
            CoreCaseFrame(
                alternatives=expression.alternatives,
                environment=machine.local_environment,
                case_expression=expression
            )
        )

        next_control = EvaluateCore(expression.scrutinee)
        rule_id = RuleId.CORE_EVAL_CASE_SCRUTINEE

    elif isinstance(expression, CoreCon):
        if machine.strategy is Strategy.CBNEED:
            field_references = tuple(
                allocate_thunk(
                    machine.heap,
                    field,
                    machine.local_environment,
                    machine.global_environment,
                )
                for field in expression.fields
            )

            constructor_reference = allocate_constructor(
                machine.heap,
                expression.constructor,
                field_references,
            )

            next_control = Return(constructor_reference)
            rule_id = RuleId.CORE_CBNEED_EVAL_CONSTRUCTOR

        elif machine.strategy is Strategy.CBV:
            if not expression.fields:
                # Nil has no fields to evaluate.
                reference = allocate_constructor(
                    machine.heap,
                    expression.constructor,
                    (),
                )

                next_control = Return(reference)
                rule_id = RuleId.CORE_CBV_ALLOCATE_CONSTRUCTOR

            else:
                # Start evaluating the first field.
                machine.stack.push(
                    ConstructorFieldsFrame(
                        constructor=expression.constructor,
                        remaining_fields=expression.fields[1:],
                        evaluated_fields=(),
                        environment=machine.local_environment,
                    )
                )

                next_control = EvaluateCore(expression.fields[0])
                rule_id = RuleId.CORE_CBV_EVAL_CONSTRUCTOR_START

        else:
            raise UnsupportedTransitionError(
                "Unsupported constructor evaluation strategy"
            )
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
        (
            EvaluateCore,
            InitializeCoreBindings,
            InitializeLocalBindings,
            Force,
            Return,
            ApplyPrimitive,
        ),
    ):
        raise UnsupportedTransitionError(
            f"Unsupported control: {type(control).__name__}"
        )

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

    recorder = SemanticEventRecorder()
    heap_recorder = HeapEffectRecorder()

    with snapshot.machine_state.heap.capture_effects(
        heap_recorder.record
    ):
        if isinstance(control, InitializeCoreBindings):
            next_machine, rule_id = _advance_global_initialization(
                snapshot.machine_state,
                control,
                heap_recorder,
        )

        elif isinstance(control, InitializeLocalBindings):
            next_machine, rule_id = _advance_local_initialization(
                snapshot.machine_state,
                control,
            )

        elif isinstance(control, Force):
            next_machine, rule_id = _advance_force(
                snapshot.machine_state,
                control,
                recorder,
            )

        elif isinstance(control, Return):
            next_machine, rule_id = _advance_return(
                snapshot.machine_state,
                control,
                recorder,
            )

        elif isinstance(control, ApplyPrimitive):
            next_machine, rule_id = _advance_apply_primitive(
                snapshot.machine_state,
                control,
                recorder,
            )

        else:
            next_machine, rule_id = _dispatch_core_evaluation(
            snapshot.machine_state,
            recorder,
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
        semantic_events=recorder.freeze(),
        heap_effects=heap_recorder.freeze(),
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
    strategy: Strategy,
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
        # Top-level functions remain ready closures.
        value = capture_closure(
            binding.rhs,
            Environment(),
            free_local_names=(),
        )
        heap.replace(reference, value)

    elif strategy is Strategy.CBNEED:
        # Initialize the existing reserved global anchor
        # using the ordinary Call-by-Need thunk protocol.
        allocate_thunk(
            heap,
            binding.rhs,
            global_environment,
            global_environment,
            anchor_reference=reference,
        )

    else:
        # Preserve the existing CBV/CBN initialization path.
        heap.replace(
            reference,
            PendingGlobal(binding.rhs),
        )

    return reference

def _advance_global_initialization(
    machine: MachineState,
    control: InitializeCoreBindings,
    heap_recorder: HeapEffectRecorder,
) -> tuple[MachineState, RuleId]:
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
            RuleId.CORE_INIT_RESERVE_GLOBAL_SCOPE,
        )

    # Stage 2: install exactly one global RHS per transition.
    if control.next_index < len(control.bindings):
        binding = control.bindings[control.next_index]

        _install_global_rhs(
            machine.heap,
            machine.global_environment,
            binding,
            machine.strategy,
        )

        return (
            replace(
                machine,
                control=replace(
                    control,
                    next_index=control.next_index + 1,
                ),
            ),
            RuleId.CORE_INIT_INSTALL_GLOBAL,
        )

    # Stage 3: the global group is installed. Begin evaluating
    # the user-selected entry without forcing unrelated globals.
    heap_recorder.record(
        HeapBaselineRecorded(
            slots=machine.heap.current_slots,
        )
    )

    return (
        replace(
            machine,
            phase=ExecutionPhase.EVALUATION,
            control=EvaluateCore(control.entry_expression),
        ),
        RuleId.CORE_INIT_ENTER_ENTRY,
    )


def _advance_local_initialization(
    machine: MachineState,
    control: InitializeLocalBindings,
) -> tuple[MachineState, RuleId]:
    """Initialize local recursive bindings in source order."""
    if machine.strategy not in (Strategy.CBV, Strategy.CBNEED):
        raise UnsupportedTransitionError(
            "Local initialization is not implemented for this strategy"
        )

    if machine.phase not in (
        ExecutionPhase.EVALUATION,
        ExecutionPhase.RESULT_MATERIALIZATION,
    ):
        raise InvalidMachineStateError(
            "Local initialization requires EVALUATION "
            "or RESULT_MATERIALIZATION phase"
        )

    if (
        type(control.next_index) is not int
        or not 0 <= control.next_index <= len(control.bindings)
    ):
        raise InvalidMachineStateError(
            "Invalid local initialization index"
        )

    # Every RHS is initialized: execute the let body.
    if control.next_index == len(control.bindings):
        return (
            replace(
                machine,
                control=EvaluateCore(control.body),
            ),
            RuleId.CORE_LETREC_ENTER_BODY,
        )

    binding = control.bindings[control.next_index]

    # Resolve only within the current recursive scope.
    reference = machine.local_environment.bindings.get(
        binding.name
    )

    if not isinstance(reference, HeapReference):
        raise InvalidMachineStateError(
            "Local binding has no reserved heap reference"
        )

    if not isinstance(machine.heap.get(reference).value, Reserved):
        raise InvalidMachineStateError(
            "Local binding is already initialized"
        )

    # Function-valued RHS: allocate its closure without
    # evaluating the function body.
    if isinstance(binding.rhs, CoreLam):
        closure_reference = allocate_closure(
            machine.heap,
            binding.rhs,
            machine.local_environment,
            machine.global_environment,
        )

        machine.heap.replace(
            reference,
            Indirection(closure_reference),
        )

        return (
            replace(
                machine,
                control=replace(
                    control,
                    next_index=control.next_index + 1,
                ),
            ),
            RuleId.CORE_LETREC_INSTALL_FUNCTION,
        )

    if machine.strategy is Strategy.CBNEED:
        # All local anchors were reserved before initialization.
        # Capture free local references from the complete
        # recursive environment without evaluating the RHS.
        allocate_thunk(
            machine.heap,
            binding.rhs,
            machine.local_environment,
            machine.global_environment,
            anchor_reference=reference,
        )

        return (
            replace(
                machine,
                control=replace(
                    control,
                    next_index=control.next_index + 1,
                ),
            ),
            RuleId.CORE_LETREC_INSTALL_THUNK,
        )

    # Non-lambda RHS: evaluate it strictly and wait
    # for WHNF before initializing its reserved cell.
    machine.stack.push(
        LocalValueInitializationFrame(
            binding_reference=reference,
            continuation=replace(
                control,
                next_index=control.next_index + 1,
            ),
            environment=machine.local_environment,
        )
    )

    return (
        replace(
            machine,
            control=EvaluateCore(binding.rhs),
        ),
        RuleId.CORE_LETREC_EVAL_VALUE,
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
        (
            Closure,
            PredefinedFunction,
            PartialPredefinedFunction,
            ConstructorValue,
        ),
    )

def _advance_force(
    machine: MachineState,
    control: Force,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Demand WHNF, entering CBNeed thunks or detecting reentrant demand.

    Thunk entry installs an UpdateFrame; its return continuation
    verifies WHNF and performs the memoizing update.
    """
    reference = control.reference

    if isinstance(
        reference,
        (ImmediateInteger, ImmediateBoolean),
    ):
        return (
            replace(machine, control=Return(reference)),
            RuleId.CORE_FORCE_IMMEDIATE,
        )

    if not isinstance(reference, HeapReference):
        raise TypeError("Expected a runtime reference")

    value = machine.heap.get(reference).value

    if isinstance(value, Indirection):
        return (
            replace(machine, control=Force(value.target)),
            RuleId.CORE_FORCE_INDIRECTION,
        )

    if isinstance(
        value,
        (Closure, PredefinedFunction, PartialPredefinedFunction)
    ):
        return (
            replace(machine, control=Return(reference)),
            RuleId.CORE_FORCE_FUNCTION_WHNF,
        )

    if isinstance(value, ConstructorValue):
        return (
            replace(
                machine,
                control=Return(reference),
            ),
            RuleId.CORE_FORCE_CONSTRUCTOR_WHNF,
        )

    if isinstance(value, PendingThunk):
        if machine.strategy is not Strategy.CBNEED:
            raise UnsupportedTransitionError(
                "Thunk forcing requires Call-by-Need"
            )

        # The anchor must retain its one-slot identity.
        anchor_cell = machine.heap.get(reference)

        if anchor_cell.allocated_slots != 1:
            raise InvalidMachineStateError(
                "Thunk anchor must occupy exactly one slot"
            )

        # Resolve and validate the separate immutable payload
        # before changing the heap or continuation stack.
        payload_cell = machine.heap.get(
            value.payload_reference
        )
        payload = payload_cell.value

        if not isinstance(payload, ThunkPayload):
            raise InvalidMachineStateError(
                "PendingThunk does not reference a ThunkPayload"
            )

        # Reconstruct the definition-site lexical environment.
        # Captured locals shadow global and predefined names.
        thunk_environment = machine.global_environment.extend(
            payload.captured_locals.bindings
        )

        update_frame = UpdateFrame(
            thunk_reference=reference,
            return_environment=machine.local_environment,
        )

        # The original anchor changes state, not identity.
        # This heap already belongs to an isolated successor.
        machine.heap.replace(
            reference,
            EvaluatingThunk(
                payload_reference=value.payload_reference,
            ),
        )

        machine.stack.push(update_frame)

        return (
            replace(
                machine,
                local_environment=thunk_environment,
                control=EvaluateCore(payload.expression),
            ),
            RuleId.CORE_FORCE_THUNK_ENTER,
        )

    if isinstance(value, EvaluatingThunk):
        if machine.strategy is not Strategy.CBNEED:
            raise InvalidMachineStateError(
                "EvaluatingThunk requires Call-by-Need"
            )

        # A legitimate evaluating thunk must have an
        # active update continuation for its stable anchor.
        active_update = any(
            isinstance(frame, UpdateFrame)
            and frame.thunk_reference == reference
            for frame in machine.stack.frames
        )

        if not active_update:
            raise InvalidMachineStateError(
                "EvaluatingThunk has no active UpdateFrame"
            )

        # Preserve the control, heap, stack and environments.
        # The enclosing step() owns the isolated successor state
        # and advances the transition counters.
        return (
            replace(
                machine,
                status=ExecutionStatus.BLACKHOLE_DETECTED,
            ),
            RuleId.CORE_BLACKHOLE_DETECTED,
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
            RuleId.CORE_FORCE_GLOBAL_RHS,
        )

    if isinstance(value, Reserved):
        # Identify a premature demand on a local recursive
        # binding while strict initialization is active.
        for frame in reversed(machine.stack.frames):
            if not isinstance(
                frame,
                LocalValueInitializationFrame,
            ):
                continue

            for name, binding_ref in frame.environment.bindings.items():
                if binding_ref == reference:
                    raise UninitializedLocalBindingError(
                        f"Local binding {name!r} is uninitialized: "
                        "strict evaluation demanded it before "
                        "its RHS was installed"
                    )

        # A Reserved cell outside a recognized local
        # initialization is still an invalid machine state.
        raise InvalidMachineStateError(
            "Cannot force an uninitialized heap cell"
        )

    raise UnsupportedTransitionError(
        f"Unsupported heap object: {type(value).__name__}"
    )

def _advance_return(
    machine: MachineState,
    control: Return,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Resume a continuation or demand a root result."""
    reference = control.reference

    if machine.stack.depth > 0:
        frame = machine.stack.peek()

        # 1. Resume updating a frame.
        if isinstance(frame, UpdateFrame):
            return _resume_update_frame(
                machine,
                control,
                frame,
            )

        # 2. Resume a pending global RHS evaluation.
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
                    RuleId.CORE_GLOBAL_REQUIRE_WHNF,
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
                RuleId.CORE_GLOBAL_DEMAND_RETURN,
            )

        # 3. Initializing ocal bindings
        if isinstance(frame, LocalValueInitializationFrame):
            return _resume_local_value(
                machine,
                control,
                frame,
            )

        # 4. Primitive operand evaluation.
        if isinstance(frame, PrimitiveOperandsFrame):
            return _resume_primitive_operand(
                machine,
                control,
                frame,
            )
        
        # 5. If evaluation.
        if isinstance(frame, IfFrame):
            return _resume_if_condition(
                machine,
                control,
                frame,
                recorder,
            )

        # 6. Function position has returned.
        # Demand the function and prepare its argument.
        if isinstance(frame, ApplyFunctionFrame):
            return _resume_apply_function(
                machine,
                control,
                frame,
                recorder,
            )

        # 7. Argument has returned.
        # Under CBV, demand WHNF and enter the closure body.
        if isinstance(frame, ApplyArgumentFrame):
            return _resume_apply_argument(
                machine,
                control,
                frame,
                recorder,
            )

        # 8. Function body has returned.
        # Restore the caller's lexical environment.
        if isinstance(frame, RestoreEnvironmentFrame):
            return _resume_caller_environment(
                machine,
                control,
                frame,
            )
        # 9. First seq argument has returned
        if isinstance(frame, SeqFirstArgumentFrame):
            return _resume_seq_first_argument(
                machine,
                control,
                frame,
                recorder,
            )

        # 10. Constructor evaluation
        if isinstance(frame, ConstructorFieldsFrame):
            return _resume_constructor_field(
                machine,
                control,
                frame,
            )

        #11 . Core case evaluation
        if isinstance(frame, CoreCaseFrame):
            return _resume_core_case(
                machine,
                control,
                frame,
                recorder,
            )

        #12. Continueation for materailization
        if isinstance(frame, MaterializationDemandFrame):
            return _resume_materialization_field(
                machine,
                control,
                frame,
            )

        raise UnsupportedTransitionError(
            "Unsupported return continuation: "
            f"{type(frame).__name__}"
        )

    # 13. No continuation remains: handle the root result.
    # A root reference to a pending object still requires WHNF.
    if isinstance(reference, HeapReference):
        value = machine.heap.get(reference).value

        if isinstance(value, (PendingGlobal, Indirection, PendingThunk)):
            return (
                replace(
                    machine,
                    control=Force(reference),
                ),
                RuleId.CORE_ROOT_REQUIRE_WHNF,
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

def _advance_apply_primitive(
    machine: MachineState,
    control: ApplyPrimitive,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Execute a primitive with fully evaluated WHNF operands."""
    operator = control.operator
    arguments = control.arguments

    binary_operators = {
        "+", "-", "*",
        "<", "<=", ">", ">=",
        "==", "!=",
    }

    if operator == "negate":
        expected_arity = 1
    elif operator in binary_operators:
        expected_arity = 2
    else:
        raise InvalidMachineStateError(
            f"Unsupported primitive operator: {operator!r}"
        )

    if len(arguments) != expected_arity:
        raise InvalidMachineStateError(
            f"Primitive {operator!r} expects "
            f"{expected_arity} operands, got {len(arguments)}"
        )

    # Equality is supported for values of the same primitive
    # type: Integer == Integer or Boolean == Boolean.
    if operator in {"==", "!="}:
        left, right = arguments

        if (
            type(left) is not type(right)
            or type(left) not in (
                ImmediateInteger,
                ImmediateBoolean,
            )
        ):
            raise TypeError(
                f"Primitive {operator!r} requires operands "
                "of the same primitive type"
            )

        equal = left.value == right.value
        result = ImmediateBoolean(
            equal if operator == "==" else not equal
        )

    else:
        # Arithmetic, ordering and negation require integers.
        if not all(
            isinstance(argument, ImmediateInteger)
            for argument in arguments
        ):
            raise TypeError(
                f"Primitive {operator!r} requires integer operands"
            )

        if operator == "negate":
            result = ImmediateInteger(-arguments[0].value)

        else:
            left, right = (
                argument.value for argument in arguments
            )

            if operator == "+":
                result = ImmediateInteger(left + right)
            elif operator == "-":
                result = ImmediateInteger(left - right)
            elif operator == "*":
                result = ImmediateInteger(left * right)
            elif operator == "<":
                result = ImmediateBoolean(left < right)
            elif operator == "<=":
                result = ImmediateBoolean(left <= right)
            elif operator == ">":
                result = ImmediateBoolean(left > right)
            elif operator == ">=":
                result = ImmediateBoolean(left >= right)
            else:
                raise InvalidMachineStateError(
                    f"Unexpected primitive operator: {operator!r}"
                )

    recorder.emit(
        SemanticEventKind.PRIMITIVE_REDUCED,
        node=control.primitive,
    )

    return (
        replace(
            machine,
            control=Return(result),
        ),
        RuleId.CORE_PRIM_EXECUTE,
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
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Demand the function, then dispatch CBV or CBNeed application.

    CBV evaluates its argument strictly. CBNeed defers closure arguments
    and partial seq arguments; saturated seq first demands its stored argument.
    """
    reference = control.reference

    if not frame.awaiting_whnf:
        machine.stack.pop()
        machine.stack.push(
            replace(frame, awaiting_whnf=True)
        )

        return (
            replace(machine, control=Force(reference)),
            RuleId.CORE_APPLY_REQUIRE_FUNCTION_WHNF,
        )

    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Function demand returned without WHNF"
        )

    if machine.strategy is Strategy.CBN:
        raise UnsupportedTransitionError(
            "Non-strict application is not implemented yet"
        )

    if not isinstance(reference, HeapReference):
        raise TypeError("Cannot apply a non-function value")

    function_value = machine.heap.get(reference).value

    if not isinstance(
        function_value,
        (
            Closure,
            PredefinedFunction,
            PartialPredefinedFunction,
        ),
    ):
        raise TypeError("Cannot apply a non-function value")

    if machine.strategy is Strategy.CBNEED:
        if isinstance(function_value, PredefinedFunction):
            if function_value.name != "seq" or function_value.arity != 2:
                raise UnsupportedTransitionError(
                    "Unsupported CBNeed predefined function"
                )

            # Preserve the original call-site lexical context.
            # The argument is neither evaluated nor forced.
            argument_reference = allocate_thunk(
                machine.heap,
                frame.argument,
                frame.environment,
                machine.global_environment,
            )

            partial = PartialPredefinedFunction(
                name="seq",
                applied_arguments=(argument_reference,),
            )

            partial_reference = machine.heap.allocate(
                partial,
                allocated_slots=partial.required_slots,
            )

            machine.stack.pop()

            recorder.emit(
                SemanticEventKind.FUNCTION_APPLIED,
                node=frame.application,
            )

            return (
                replace(
                    machine,
                    local_environment=frame.environment,
                    control=Return(partial_reference),
                ),
                RuleId.CORE_PREDEFINED_PARTIAL_APPLY,
            )

        if isinstance(function_value, PartialPredefinedFunction):
            if (
                function_value.name != "seq"
                or function_value.remaining_arity != 1
            ):
                raise UnsupportedTransitionError(
                    "Unsupported CBNeed predefined saturation"
                )

            first_reference = function_value.applied_arguments[0]

            machine.stack.pop()
            machine.stack.push(
                SeqFirstArgumentFrame(
                    first_argument_reference=first_reference,
                    second_expression=frame.argument,
                    return_environment=frame.environment,
                    application= frame.application,
                )
            )

            recorder.emit(
                SemanticEventKind.FUNCTION_APPLIED,
                node=frame.application,
            )

            return (
                replace(machine, control=Force(first_reference)),
                RuleId.CORE_SEQ_REQUIRE_FIRST_WHNF,
            )

        if not isinstance(function_value, Closure):
            raise TypeError("Cannot apply a non-function value")

        # Capture the argument's original lexical call-site
        # references without evaluating its Core expression.
        argument_reference = allocate_thunk(
            machine.heap,
            frame.argument,
            frame.environment,
            machine.global_environment,
        )

        # The closure body uses the definition-site captures,
        # the global environment and the new parameter binding.
        call_environment = function_value.call_environment(
            argument_reference,
            machine.global_environment,
        )

        machine.stack.pop()
        machine.stack.push(
            RestoreEnvironmentFrame(frame.environment)
        )

        recorder.emit(
            SemanticEventKind.FUNCTION_APPLIED,
            node=frame.application,
        )
        recorder.emit(
            SemanticEventKind.BETA_REDUCED,
            node=function_value.lambda_expression,
        )

        return (
            replace(
                machine,
                local_environment=call_environment,
                control=EvaluateCore(
                    function_value.lambda_expression.body
                ),
            ),
            RuleId.CORE_CBNEED_ENTER_BODY,
        )

    if machine.strategy is not Strategy.CBV:
        raise UnsupportedTransitionError(
            "Unsupported evaluation strategy for application"
        )

    # The function is ready. CBV evaluates its argument
    # in the original call-site environment.
    machine.stack.pop()
    machine.stack.push(
        ApplyArgumentFrame(
            function=reference,
            return_environment=frame.environment,
            application=frame.application,
        )
    )

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=EvaluateCore(frame.argument),
        ),
        RuleId.CORE_CBV_EVAL_ARGUMENT,
    )

def _resume_seq_first_argument(
    machine: MachineState,
    control: Return,
    frame: SeqFirstArgumentFrame,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Complete CBNeed seq without forcing its second argument."""

    if machine.strategy is not Strategy.CBNEED:
        raise InvalidMachineStateError(
            "SeqFirstArgumentFrame requires Call-by-Need"
        )

    if not _reference_is_whnf(machine, control.reference):
        raise InvalidMachineStateError(
            "seq first argument did not reach WHNF"
        )

    # Only now construct the deferred second argument.
    second_reference = allocate_thunk(
        machine.heap,
        frame.second_expression,
        frame.return_environment,
        machine.global_environment,
    )

    machine.stack.pop()

    recorder.emit(
        SemanticEventKind.SEQ_REDUCED,
        node=frame.application,
    )

    return (
        replace(
            machine,
            local_environment=frame.return_environment,
            control=Return(second_reference),
        ),
        RuleId.CORE_SEQ_SATURATE,
    )

def _resume_apply_argument(
    machine: MachineState,
    control: Return,
    frame: ApplyArgumentFrame,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
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
            RuleId.CORE_CBV_REQUIRE_ARGUMENT_WHNF,
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

    if isinstance(function_value, PartialPredefinedFunction):
        if (
            function_value.name != "seq"
            or function_value.remaining_arity != 1
        ):
            raise UnsupportedTransitionError(
                "Unsupported saturated predefined function"
            )

        first_argument = function_value.applied_arguments[0]

        # Under CBV, the first argument was already
        # demanded to WHNF when the partial application
        # was constructed.
        if not _reference_is_whnf(machine, first_argument):
            raise InvalidMachineStateError(
                "CBV seq first argument is not in WHNF"
            )

        # The current argument has already been evaluated
        # and forced by ApplyArgumentFrame.
        # Saturated seq returns that second argument.
        machine.stack.pop()

        recorder.emit(
            SemanticEventKind.FUNCTION_APPLIED,
            node=frame.application,
        )
        recorder.emit(
            SemanticEventKind.SEQ_REDUCED,
            node=frame.application,
        )

        return (
            replace(
                machine,
                local_environment=frame.return_environment,
                control=Return(reference),
            ),
            RuleId.CORE_SEQ_SATURATE,
        )

    if isinstance(function_value, PredefinedFunction):
        # B04.7.2 only supports the first, non-saturating
        # application of a predefined function.
        if function_value.arity <= 1:
            raise UnsupportedTransitionError(
                "Saturated predefined function application "
                "is not implemented yet"
            )

        partial = PartialPredefinedFunction(
            name=function_value.name,
            applied_arguments=(reference,),
        )

        partial_reference = machine.heap.allocate(
            partial,
            allocated_slots=partial.required_slots,
        )

        machine.stack.pop()

        recorder.emit(
            SemanticEventKind.FUNCTION_APPLIED,
            node=frame.application,
        )

        return (
            replace(
                machine,
                local_environment=frame.return_environment,
                control=Return(partial_reference),
            ),
            RuleId.CORE_PREDEFINED_PARTIAL_APPLY,
        )
    
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

    recorder.emit(
        SemanticEventKind.FUNCTION_APPLIED,
        node=frame.application,
    )
    recorder.emit(
        SemanticEventKind.BETA_REDUCED,
        node=function_value.lambda_expression,
    )

    return (
        replace(
            machine,
            local_environment=call_environment,
            control=EvaluateCore(
                function_value.lambda_expression.body
            ),
        ),
        RuleId.CORE_CBV_ENTER_BODY,
    )

def _resume_caller_environment(
    machine: MachineState,
    control: Return,
    frame: RestoreEnvironmentFrame,
) -> tuple[MachineState, RuleId]:
    """Leave a function body without changing its returned reference."""
    machine.stack.pop()

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=Return(control.reference),
        ),
        RuleId.CORE_RESTORE_CALLER_ENVIRONMENT,
    )

def _resume_primitive_operand(
    machine: MachineState,
    control: Return,
    frame: PrimitiveOperandsFrame,
) -> tuple[MachineState, RuleId]:
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
            RuleId.CORE_PRIM_REQUIRE_OPERAND_WHNF,
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
            RuleId.CORE_PRIM_NEXT_OPERAND,
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
                primitive=frame.primitive,
            ),
        ),
        RuleId.CORE_PRIM_OPERANDS_READY,
    )

def _resume_if_condition(
    machine: MachineState,
    control: Return,
    frame: IfFrame,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Demand a boolean condition and select exactly one branch."""
    reference = control.reference

    # First return: the condition produced a reference,
    # which may still point to a pending computation.
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
            RuleId.CORE_IF_REQUIRE_CONDITION_WHNF,
        )

    # Second return: the WHNF demand must have completed.
    # In the current subset, booleans are immediate values.
    if not isinstance(reference, ImmediateBoolean):
        raise TypeError(
            "If condition must evaluate to a Boolean"
        )

    selected_branch = (
        frame.then_branch
        if reference.value
        else frame.else_branch
    )

    rule_id = (
        RuleId.CORE_IF_SELECT_THEN
        if reference.value
        else RuleId.CORE_IF_SELECT_ELSE
    )

    # The condition continuation is finished.
    machine.stack.pop()

    recorder.emit(
        SemanticEventKind.CONDITIONAL_SELECTED,
        node=frame.conditional,
    )

    # Evaluate only the selected branch, using the lexical
    # environment of the original conditional expression.
    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=EvaluateCore(selected_branch),
        ),
        rule_id,
    )

def _resume_local_value(
    machine: MachineState,
    control: Return,
    frame: LocalValueInitializationFrame,
) -> tuple[MachineState, RuleId]:
    """Complete strict initialization of one local RHS."""
    reference = control.reference

    # Stage 1: the RHS returned a reference.
    # Its result must be demanded to WHNF.
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
            RuleId.CORE_LETREC_REQUIRE_VALUE_WHNF,
        )

    # Stage 2: WHNF demand has completed.
    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Local RHS did not reach WHNF"
        )

    # The binding must still be awaiting initialization.
    binding_cell = machine.heap.get(
        frame.binding_reference
    )

    if not isinstance(binding_cell.value, Reserved):
        raise InvalidMachineStateError(
            "Local binding was initialized more than once"
        )

    # Preserve the stable recursive binding address.
    machine.heap.replace(
        frame.binding_reference,
        Indirection(reference),
    )

    machine.stack.pop()

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=frame.continuation,
        ),
        RuleId.CORE_LETREC_STORE_VALUE,
    )

def _resume_update_frame(
    machine: MachineState,
    control: Return,
    frame: UpdateFrame,
) -> tuple[MachineState, RuleId]:
    """Demand a thunk RHS result before its memoizing update."""

    if machine.strategy is not Strategy.CBNEED:
        raise InvalidMachineStateError(
            "UpdateFrame requires Call-by-Need"
        )

    anchor_value = machine.heap.get(
        frame.thunk_reference
    ).value

    if not isinstance(anchor_value, EvaluatingThunk):
        raise InvalidMachineStateError(
            "UpdateFrame requires an evaluating thunk anchor"
        )

    reference = control.reference

    # Stage 1: the RHS returned a reference, which may not
    # yet denote a WHNF value.
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
            RuleId.CORE_THUNK_REQUIRE_WHNF,
        )

    # Stage 2: Force has returned. Its result must be WHNF.
    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Thunk demand resumed without WHNF"
        )

    # The RHS result has reached WHNF.
    # Memoize it in the original stable thunk anchor.
    if reference == frame.thunk_reference:
        raise InvalidMachineStateError(
            "Thunk cannot update to itself"
        )

    machine.heap.replace(
        frame.thunk_reference,
        Indirection(reference),
    )

    # The update is complete. Resume the suspended caller.
    machine.stack.pop()

    return (
        replace(
            machine,
            local_environment=frame.return_environment,
            control=Return(reference),
        ),
        RuleId.CORE_THUNK_UPDATE_WHNF,
    )

def _resume_constructor_field(
    machine: MachineState,
    control: Return,
    frame: ConstructorFieldsFrame,
) -> tuple[MachineState, RuleId]:
    """Resume left-to-right strict constructor field evaluation."""

    if machine.strategy is not Strategy.CBV:
        raise InvalidMachineStateError(
            "ConstructorFieldsFrame requires Call-by-Value"
        )

    reference = control.reference

    # Stage 1: the field returned a reference.
    # Explicitly demand its WHNF.
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
            RuleId.CORE_CBV_REQUIRE_CONSTRUCTOR_FIELD_WHNF,
        )

    # Stage 2: Force returned.
    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Constructor field returned without WHNF"
        )

    evaluated_fields = (
        frame.evaluated_fields + (reference,)
    )

    machine.stack.pop()

    # Stage 3: evaluate the next field, if any.
    if frame.remaining_fields:
        next_field = frame.remaining_fields[0]

        machine.stack.push(
            replace(
                frame,
                remaining_fields=frame.remaining_fields[1:],
                evaluated_fields=evaluated_fields,
                awaiting_whnf=False,
            )
        )

        return (
            replace(
                machine,
                local_environment=frame.environment,
                control=EvaluateCore(next_field),
            ),
            RuleId.CORE_CBV_EVAL_NEXT_CONSTRUCTOR_FIELD,
        )

    # Stage 4: every field is in WHNF.
    constructor_reference = allocate_constructor(
        machine.heap,
        frame.constructor,
        evaluated_fields,
    )

    return (
        replace(
            machine,
            local_environment=frame.environment,
            control=Return(constructor_reference),
        ),
        RuleId.CORE_CBV_ALLOCATE_CONSTRUCTOR,
    )

def _resume_core_case(
    machine: MachineState,
    control: Return,
    frame: CoreCaseFrame,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Demand the case scrutinee before matching alternatives."""

    reference = control.reference

    # Stage 1: preserve the original reference and demand WHNF.
    if not frame.awaiting_whnf:
        machine.stack.pop()

        machine.stack.push(
            replace(
                frame,
                awaiting_whnf=True,
                scrutinee_reference=reference,
            )
        )

        return (
            replace(
                machine,
                control=Force(reference),
            ),
            RuleId.CORE_CASE_REQUIRE_SCRUTINEE_WHNF,
        )

    # Stage 2: the demand must have completed.
    if frame.scrutinee_reference is None:
        raise InvalidMachineStateError(
            "CoreCase lost its original scrutinee reference"
        )

    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "CoreCase scrutinee returned without WHNF"
        )

    if frame.selected_alternative is not None:
        alternative = frame.selected_alternative

        if isinstance(alternative, CoreConAlt):
            if not isinstance(reference, HeapReference):
                raise InvalidMachineStateError(
                    "Constructor alternative requires a heap reference"
                )

            value = machine.heap.get(reference).value

            if (
                not isinstance(value, ConstructorValue)
                or value.tag != alternative.constructor
                or len(value.fields) != len(alternative.binders)
            ):
                raise InvalidMachineStateError(
                    "Selected constructor alternative is inconsistent"
                )

            bindings = dict(
                zip(alternative.binders, value.fields)
            )
            rule_id = RuleId.CORE_CASE_ENTER_CONSTRUCTOR_BODY

        elif isinstance(alternative, CoreDefaultAlt):
            original_reference = frame.scrutinee_reference

            if original_reference is None:
                raise InvalidMachineStateError(
                    "CoreCase lost its original scrutinee reference"
                )

            bindings = {
                alternative.binder: original_reference
            }
            rule_id = RuleId.CORE_CASE_ENTER_DEFAULT_BODY

        else:
            raise InvalidMachineStateError(
                "Unsupported selected CoreCase alternative"
            )

        machine.stack.pop()

        machine.stack.push(
            RestoreEnvironmentFrame(frame.environment)
        )

        return (
            replace(
                machine,
                local_environment=frame.environment.extend(bindings),
                control=EvaluateCore(alternative.body),
            ),
            rule_id,
        )

    # Inspect only the outer constructor, if present.
    constructor = None

    if isinstance(reference, HeapReference):
        value = machine.heap.get(reference).value

        if isinstance(value, ConstructorValue):
            constructor = value

    selected = None
    selection_rule = None

    for alternative in frame.alternatives:
        if isinstance(alternative, CoreConAlt):
            if (
                constructor is not None
                and constructor.tag == alternative.constructor
            ):
                selected = alternative
                selection_rule = RuleId.CORE_CASE_SELECT_CONSTRUCTOR
                break

        elif isinstance(alternative, CoreDefaultAlt):
            selected = alternative
            selection_rule = RuleId.CORE_CASE_SELECT_DEFAULT
            break

        else:
            raise InvalidMachineStateError(
                "Unsupported CoreCase alternative"
            )

    if selected is None:
        raise PatternMatchError(
            "Non-exhaustive CoreCase: no alternative matches"
        )

    machine.stack.pop()
    machine.stack.push(
        replace(
            frame,
            selected_alternative=selected,
        )
    )

    recorder.emit(
        SemanticEventKind.CASE_ALTERNATIVE_SELECTED,
        node=frame.case_expression,
    )

    return (
        replace(
            machine,
            control=Return(reference),
        ),
        selection_rule,
    )

def _resume_materialization_field(
    machine: MachineState,
    control: Return,
    frame: MaterializationDemandFrame,
) -> tuple[MachineState, RuleId]:
    """Return a demanded WHNF field to the result materializer."""

    if machine.phase is not ExecutionPhase.RESULT_MATERIALIZATION:
        raise InvalidMachineStateError(
            "Materialization continuation in an invalid phase"
        )

    reference = control.reference

    if not _reference_is_whnf(machine, reference):
        raise InvalidMachineStateError(
            "Materialization field returned without WHNF"
        )

    progress = machine.result_state.materialization

    if (
        progress is None
        or not progress.awaiting_whnf
        or progress.root_reference != frame.root_reference
    ):
        raise InvalidMachineStateError(
            "Invalid materialization continuation state"
        )

    resumed = resume_materialization(progress, reference)

    machine.stack.pop()

    return (
        replace(
            machine,
            local_environment=frame.return_environment,
            control=Return(frame.root_reference),
            result_state=replace(
                machine.result_state,
                materialization=resumed,
            ),
        ),
        RuleId.CORE_MATERIALIZATION_FIELD_RESUME,
    )

def _enter_local_letrec(
    machine: MachineState,
    expression: CoreLetRec,
    recorder: SemanticEventRecorder,
) -> tuple[MachineState, RuleId]:
    """Reserve every local binding before evaluating any RHS."""
    if machine.strategy not in (
        Strategy.CBV,
        Strategy.CBNEED,
    ):
        raise UnsupportedTransitionError(
            "Local recursive bindings are not implemented for this strategy"
        )

    bindings = expression.bindings

    if (
        not isinstance(bindings, tuple)
        or not bindings
        or any(not isinstance(b, CoreBinding) for b in bindings)
    ):
        raise InvalidMachineStateError(
            "CoreLetRec requires a non-empty binding group"
        )

    names = [binding.name for binding in bindings]

    if (
        any(not isinstance(name, str) or not name for name in names)
        or len(names) != len(set(names))
    ):
        raise InvalidMachineStateError(
            "Invalid or duplicate local binding names"
        )

    outer_environment = machine.local_environment

    # Every binding receives a stable one-slot address.
    references = {}

    for binding in bindings:
        references[binding.name] = machine.heap.allocate(
            Reserved(),
            allocated_slots=1,
        )

    # All group names are visible in every RHS.
    recursive_environment = outer_environment.extend(
        references
    )

    # Restore the enclosing scope when the let body returns.
    machine.stack.push(
        RestoreEnvironmentFrame(outer_environment)
    )

    recorder.emit(
        SemanticEventKind.LET_ACTIVATED,
        node=expression,
    )

    return (
        replace(
            machine,
            local_environment=recursive_environment,
            control=InitializeLocalBindings(
                bindings=bindings,
                body=expression.body,
            ),
        ),
        RuleId.CORE_LETREC_RESERVE_SCOPE,
    )
