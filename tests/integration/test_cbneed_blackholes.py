
from lazy_lab.engine.core_machine import create_initial_core_state, run_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Force
from lazy_lab.runtime.heap import Reserved
from lazy_lab.runtime.stack import UpdateFrame
from lazy_lab.runtime.state import ExecutionStatus
from lazy_lab.runtime.thunks import EvaluatingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from tests.integration.test_cbneed_application import make_cbneed_config, thunk_transition_anchors
from tests.integration.test_cbneed_local_bindings import advance_to_letrec_reservation


def test_cbneed_direct_global_blackhole_stops_batch():
    program = compile_source("main = main")
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-direct-global-blackhole",
    )

    result = run_batch(
        initial,
        config,
        max_steps=100,
    )

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS

    machine = result.state.machine_state
    main_ref = machine.global_environment.lookup("main")

    assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED

    assert machine.control == Force(main_ref)

    assert isinstance(
        machine.heap.get(main_ref).value,
        EvaluatingThunk,
    )

    update_frames = [
        frame
        for frame in machine.stack.frames
        if isinstance(frame, UpdateFrame)
    ]

    assert len(update_frames) == 1
    assert update_frames[0].thunk_reference == main_ref
    assert update_frames[0].awaiting_whnf

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 1
    assert rules.count(RuleId.CORE_BLACKHOLE_DETECTED) == 1

    assert rules[-1] is RuleId.CORE_BLACKHOLE_DETECTED

    # Detection is not evaluator budget exhaustion.
    assert (
        machine.evaluator_transition_count
        < config.execution_step_limit
    )

    # The initial snapshot remains unchanged.
    assert initial.transition_index == 0
    assert initial.machine_state.status is ExecutionStatus.RUNNING
    assert initial.machine_state.heap.current_slots == 0


def test_cbneed_indirect_global_blackhole():
    program = compile_source(
        "main = a\n"
        "a = b\n"
        "b = a"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-indirect-global-blackhole",
    )

    result = run_batch(
        initial,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS

    machine = result.state.machine_state
    env = machine.global_environment

    main_ref = env.lookup("main")
    a_ref = env.lookup("a")
    b_ref = env.lookup("b")

    assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED

    # The cycle closes by demanding a again.
    assert machine.control == Force(a_ref)

    # All three computations are still active.
    for ref in (main_ref, a_ref, b_ref):
        assert isinstance(
            machine.heap.get(ref).value,
            EvaluatingThunk,
        )

    active_updates = [
        frame.thunk_reference
        for frame in machine.stack.frames
        if isinstance(frame, UpdateFrame)
    ]

    assert active_updates == [main_ref, a_ref, b_ref]

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 3
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 0
    assert rules.count(RuleId.CORE_BLACKHOLE_DETECTED) == 1

    assert rules[-1] is RuleId.CORE_BLACKHOLE_DETECTED

    # A blackhole is detected before exhausting the budget.
    assert (
        machine.evaluator_transition_count
        < config.execution_step_limit
    )

    # The original snapshot remains unchanged.
    assert initial.machine_state.status is ExecutionStatus.RUNNING
    assert initial.transition_index == 0
    assert initial.machine_state.heap.current_slots == 0


def test_cbneed_direct_local_blackhole():
    program = compile_source(
        "main = let { x = x } in x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-direct-local-blackhole",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial,
        config,
    )

    reserved_machine = reserved_state.machine_state

    x_ref = reserved_machine.local_environment.lookup("x")
    main_ref = reserved_machine.global_environment.lookup("main")

    assert isinstance(
        reserved_machine.heap.get(x_ref).value,
        Reserved,
    )

    result = run_batch(
        reserved_state,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS

    machine = result.state.machine_state

    assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED
    assert machine.control == Force(x_ref)

    assert isinstance(
        machine.heap.get(x_ref).value,
        EvaluatingThunk,
    )
    assert isinstance(
        machine.heap.get(main_ref).value,
        EvaluatingThunk,
    )

    active_updates = [
        frame.thunk_reference
        for frame in machine.stack.frames
        if isinstance(frame, UpdateFrame)
    ]

    assert main_ref in active_updates
    assert x_ref in active_updates

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_FORCE_THUNK_ENTER) == 1
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 0
    assert rules.count(RuleId.CORE_BLACKHOLE_DETECTED) == 1

    # Reservation snapshot must still contain x as Reserved.
    assert isinstance(
        reserved_machine.heap.get(x_ref).value,
        Reserved,
    )


def test_cbneed_indirect_local_blackhole():
    program = compile_source(
        "main = let { x = y; y = x } in x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-indirect-local-blackhole",
    )

    _, reserved_state = advance_to_letrec_reservation(
        initial,
        config,
    )

    env = reserved_state.machine_state.local_environment

    x_ref = env.lookup("x")
    y_ref = env.lookup("y")

    result = run_batch(
        reserved_state,
        config,
        max_steps=150,
    )

    assert result.stop_reason is BatchStopReason.TERMINAL_STATUS

    machine = result.state.machine_state

    assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED

    # x -> y -> x
    assert machine.control == Force(x_ref)

    for ref in (x_ref, y_ref):
        assert isinstance(
            machine.heap.get(ref).value,
            EvaluatingThunk,
        )

    active_updates = [
        frame.thunk_reference
        for frame in machine.stack.frames
        if isinstance(frame, UpdateFrame)
    ]

    assert x_ref in active_updates
    assert y_ref in active_updates
    assert active_updates.index(x_ref) < active_updates.index(y_ref)

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_BLACKHOLE_DETECTED) == 1
    assert rules.count(RuleId.CORE_THUNK_UPDATE_WHNF) == 0

    # Verify the exact local anchors that were entered.
    anchors = thunk_transition_anchors(
        reserved_state,
        config,
        result.trace,
    )

    assert anchors[RuleId.CORE_FORCE_THUNK_ENTER] == [
        x_ref,
        y_ref,
    ]

    assert anchors[RuleId.CORE_THUNK_UPDATE_WHNF] == []
