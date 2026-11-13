
from dataclasses import replace

import pytest

from lazy_lab.engine.core_machine import InvalidMachineStateError, create_initial_core_state, run_batch, step
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.metrics.reducer import reduce_metrics
from lazy_lab.metrics.state import InstrumentationState
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Force, Return
from lazy_lab.runtime.heap import Reserved
from lazy_lab.runtime.references import ImmediateInteger
from lazy_lab.runtime.stack import Stack, UpdateFrame
from lazy_lab.runtime.state import ExecutionStatus, TraceMode
from lazy_lab.runtime.thunks import EvaluatingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId, TraceEntry
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

def test_cbneed_budget_during_nested_forcing_is_resumable():
    program = compile_source(
        "main = let { x = 20 + 1; y = x + 1 } in y + x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-nested-forcing-budget",
    )

    _, reserved = advance_to_letrec_reservation(
        initial, config
    )

    env = reserved.machine_state.local_environment
    x_ref = env.lookup("x")
    y_ref = env.lookup("y")

    # Find the checkpoint after entering x, while
    # both x and y are being evaluated.
    current = reserved

    for _ in range(150):
        transition = step(current, config)
        successor = transition.next_state
        machine = successor.machine_state

        if (
            isinstance(machine.heap.get(x_ref).value, EvaluatingThunk)
            and isinstance(machine.heap.get(y_ref).value, EvaluatingThunk)
        ):
            checkpoint = successor
            break

        current = successor
    else:
        pytest.fail("Nested forcing checkpoint not reached")

    checkpoint_machine = checkpoint.machine_state

    active_updates = {
        frame.thunk_reference
        for frame in checkpoint_machine.stack.frames
        if isinstance(frame, UpdateFrame)
    }
    assert {x_ref, y_ref} <= active_updates

    # The budget is an absolute cumulative limit.
    limited_config = replace(
        config,
        execution_step_limit=checkpoint_machine.evaluator_transition_count,
    )

    paused = run_batch(
        initial,
        limited_config,
        max_steps=200,
    )

    assert paused.stop_reason is BatchStopReason.EVALUATOR_BUDGET

    paused_machine = paused.state.machine_state

    assert paused_machine.status is ExecutionStatus.RUNNING
    assert paused.state.transition_index == checkpoint.transition_index
    assert paused_machine.control == checkpoint_machine.control

    # Both executions preserve the same continuation structure.
    assert tuple(
        type(frame) for frame in paused_machine.stack.frames
    ) == tuple(
        type(frame) for frame in checkpoint_machine.stack.frames
    )

    # Active thunk updates target the same anchors and preserve
    # their WHNF-demand state.
    def update_state(machine):
        return [
            (frame.thunk_reference, frame.awaiting_whnf)
            for frame in machine.stack.frames
            if isinstance(frame, UpdateFrame)
        ]

    assert update_state(paused_machine) == update_state(checkpoint_machine)

    assert (
        paused_machine.local_environment.bindings
        == checkpoint_machine.local_environment.bindings
    )

    for ref in (x_ref, y_ref):
        assert isinstance(
            paused_machine.heap.get(ref).value,
            EvaluatingThunk,
        )

    original_cells = dict(paused_machine.heap.cells)
    original_frames = paused_machine.stack.frames

    # Resume with the original, larger budget.
    resumed = run_batch(
        paused.state,
        config,
        max_steps=200,
    )

    assert resumed.stop_reason is BatchStopReason.WHNF_PENDING
    assert resumed.state.machine_state.control == Return(
        ImmediateInteger(43)
    )

    # The previous checkpoint is not mutated.
    assert paused_machine.status is ExecutionStatus.RUNNING
    assert dict(paused_machine.heap.cells) == original_cells
    assert paused_machine.stack.frames == original_frames

    # The uninterrupted and resumed traces agree.
    full = run_batch(initial, config, max_steps=200)

    assert full.stop_reason is BatchStopReason.WHNF_PENDING
    assert (
        tuple(paused.trace) + tuple(resumed.trace)
        == full.trace
    )

    
def test_cbneed_budget_before_blackhole_detection():
    program = compile_source(
        "main = a\n"
        "a = b\n"
        "b = a"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-blackhole-budget-boundary",
    )

    # Find the predecessor of blackhole detection.
    current = initial

    for _ in range(150):
        transition = step(current, config)

        if transition.rule_id is RuleId.CORE_BLACKHOLE_DETECTED:
            checkpoint = current
            break

        current = transition.next_state
    else:
        pytest.fail("Blackhole detection was not reached")

    checkpoint_machine = checkpoint.machine_state
    budget = checkpoint_machine.evaluator_transition_count

    assert checkpoint_machine.status is ExecutionStatus.RUNNING

    limited_config = replace(
        config,
        execution_step_limit=budget,
    )

    paused = run_batch(
        initial,
        limited_config,
        max_steps=200,
    )

    assert paused.stop_reason is BatchStopReason.EVALUATOR_BUDGET
    assert paused.state.machine_state.status is ExecutionStatus.RUNNING
    assert paused.state.transition_index == checkpoint.transition_index

    paused_cells = dict(paused.state.machine_state.heap.cells)
    paused_frames = paused.state.machine_state.stack.frames

    # Allow exactly one additional evaluator transition.
    extended_config = replace(
        config,
        execution_step_limit=budget + 1,
    )

    detected = run_batch(
        paused.state,
        extended_config,
        max_steps=2,
    )

    assert detected.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert detected.state.machine_state.status is (
        ExecutionStatus.BLACKHOLE_DETECTED
    )

    assert len(detected.trace) == 1
    assert detected.trace[0].rule_id is (
        RuleId.CORE_BLACKHOLE_DETECTED
    )

    assert (
        detected.state.machine_state.evaluator_transition_count
        == budget + 1
    )

    # Detection preserves the heap and stack.
    assert dict(
        detected.state.machine_state.heap.cells
    ) == paused_cells
    assert detected.state.machine_state.stack.frames == paused_frames

    # The budget checkpoint remains unchanged.
    assert paused.state.machine_state.status is ExecutionStatus.RUNNING
    assert dict(paused.state.machine_state.heap.cells) == paused_cells
    assert paused.state.machine_state.stack.frames == paused_frames


def test_cbneed_terminal_blackhole_is_priority_over_budget_limit():
    program = compile_source(
        "main = main"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-nested-forcing-budget",
    )

    detected = run_batch(
            initial,
            config,
            max_steps=200,
        )

    assert detected.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert detected.state.machine_state.status is (
        ExecutionStatus.BLACKHOLE_DETECTED
    )

    detected_machine = detected.state.machine_state

    # The budget is an absolute cumulative limit.
    limited_config = replace(
        config,
        execution_step_limit=detected_machine.evaluator_transition_count,
    )

    again = run_batch(
        detected.state,
        limited_config,
        max_steps=1,
    )

    assert again.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert again.state is detected.state
    assert again.trace == ()


def test_cbneed_blackhole_is_equivalent_across_trace_modes():
    program = compile_source(
        "main = let { x = y; y = x } in x"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-blackhole-trace-modes",
    )

    _, reserved = advance_to_letrec_reservation(
        initial, config
    )

    env = reserved.machine_state.local_environment
    x_ref = env.lookup("x")
    y_ref = env.lookup("y")

    results = {
        mode: run_batch(
            reserved,
            replace(config, trace_mode=mode),
            max_steps=150,
        )
        for mode in TraceMode
    }

    full = results[TraceMode.FULL]
    events = results[TraceMode.EVENTS]
    metrics = results[TraceMode.METRICS_ONLY]

    # Tracing does not affect terminal semantics.
    for result in results.values():
        assert result.stop_reason is BatchStopReason.TERMINAL_STATUS

        machine = result.state.machine_state

        assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED
        assert machine.control == Force(x_ref)

        for ref in (x_ref, y_ref):
            assert isinstance(
                machine.heap.get(ref).value,
                EvaluatingThunk,
            )

        active_updates = [
            (frame.thunk_reference, frame.awaiting_whnf)
            for frame in machine.stack.frames
            if isinstance(frame, UpdateFrame)
        ]

        assert [ref for ref, _ in active_updates if ref in (x_ref, y_ref)] == [
            x_ref, y_ref
        ]

    # FULL and EVENTS currently expose the same basic trace.
    assert full.trace == events.trace

    # METRICS_ONLY omits trace entries, not execution steps.
    assert metrics.trace == ()

    full_machine = full.state.machine_state

    for result in (events, metrics):
        machine = result.state.machine_state

        assert result.state.transition_index == full.state.transition_index
        assert machine.evaluator_transition_count == (
            full_machine.evaluator_transition_count
        )
        assert machine.heap.current_slots == full_machine.heap.current_slots
        assert machine.heap.next_object_id == full_machine.heap.next_object_id

        assert tuple(type(frame) for frame in machine.stack.frames) == (
            tuple(type(frame) for frame in full_machine.stack.frames)
        )

    rules = [entry.rule_id for entry in full.trace]

    assert rules.count(RuleId.CORE_BLACKHOLE_DETECTED) == 1
    assert rules[-1] is RuleId.CORE_BLACKHOLE_DETECTED

    # The shared starting snapshot remains reserved.
    assert isinstance(
        reserved.machine_state.heap.get(x_ref).value,
        Reserved,
    )
    assert isinstance(
        reserved.machine_state.heap.get(y_ref).value,
        Reserved,
    )


def test_cbneed_blackhole_transition_replays_from_snapshot():
    program = compile_source(
        "main = a\n"
        "a = b\n"
        "b = a"
    )
    config = make_cbneed_config()

    checkpoint = create_initial_core_state(
        program,
        config,
        session_id="cbneed-blackhole-replay",
    )

    # Locate the predecessor of the terminal transition.
    for _ in range(150):
        transition = step(checkpoint, config)

        if transition.rule_id is RuleId.CORE_BLACKHOLE_DETECTED:
            break

        checkpoint = transition.next_state
    else:
        pytest.fail("Blackhole detection not reached")

    before = checkpoint.machine_state
    a_ref = before.global_environment.lookup("a")

    assert before.status is ExecutionStatus.RUNNING
    assert before.control == Force(a_ref)

    original_cells = dict(before.heap.cells)
    original_frames = before.stack.frames
    original_index = checkpoint.transition_index

    first = step(checkpoint, config)
    second = step(checkpoint, config)

    assert first.rule_id is RuleId.CORE_BLACKHOLE_DETECTED
    assert second.rule_id is RuleId.CORE_BLACKHOLE_DETECTED

    # The emitted trace entry is deterministic.
    assert TraceEntry.from_transition(first) == (
        TraceEntry.from_transition(second)
    )

    left = first.next_state.machine_state
    right = second.next_state.machine_state

    for machine in (left, right):
        assert machine.status is ExecutionStatus.BLACKHOLE_DETECTED
        assert machine.control == Force(a_ref)
        assert dict(machine.heap.cells) == original_cells
        assert machine.stack.frames == original_frames
        assert machine.local_environment is before.local_environment

    # Independent successor storage.
    assert left.heap is not right.heap
    assert left.stack is not right.stack

    assert first.next_state.transition_index == original_index + 1
    assert second.next_state.transition_index == original_index + 1

    # The common predecessor remains unchanged.
    assert checkpoint.transition_index == original_index
    assert before.status is ExecutionStatus.RUNNING
    assert dict(before.heap.cells) == original_cells
    assert before.stack.frames == original_frames

    # A batch from the same checkpoint performs exactly
    # the same terminal transition.
    batch = run_batch(checkpoint, config, max_steps=3)

    assert batch.stop_reason is BatchStopReason.TERMINAL_STATUS
    assert len(batch.trace) == 1
    assert batch.trace[0] == TraceEntry.from_transition(first)


def test_cbneed_evaluating_thunk_without_update_frame_is_invalid():
    program = compile_source("main = main")
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-missing-update-frame",
    )

    # Reach a legitimate EvaluatingThunk state.
    current = initial

    for _ in range(100):
        transition = step(current, config)

        if transition.rule_id is RuleId.CORE_FORCE_THUNK_ENTER:
            checkpoint = transition.next_state
            break

        current = transition.next_state
    else:
        pytest.fail("Thunk entry was not reached")

    machine = checkpoint.machine_state
    main_ref = machine.global_environment.lookup("main")

    assert isinstance(
        machine.heap.get(main_ref).value,
        EvaluatingThunk,
    )

    assert any(
        isinstance(frame, UpdateFrame)
        and frame.thunk_reference == main_ref
        for frame in machine.stack.frames
    )

    # Construct an intentionally inconsistent state:
    # the anchor remains EVALUATING, but its UpdateFrame
    # is missing.
    malformed = checkpoint.snapshot()

    malformed_stack = Stack()

    for frame in malformed.machine_state.stack.frames:
        if not isinstance(frame, UpdateFrame):
            malformed_stack.push(frame)

    malformed = replace(
        malformed,
        machine_state=replace(
            malformed.machine_state,
            stack=malformed_stack,
            control=Force(main_ref),
        ),
    )

    assert not any(
        isinstance(frame, UpdateFrame)
        and frame.thunk_reference == main_ref
        for frame in malformed.machine_state.stack.frames
    )

    before_machine = malformed.machine_state
    before_cells = dict(before_machine.heap.cells)
    before_frames = before_machine.stack.frames
    before_index = malformed.transition_index
    before_count = before_machine.evaluator_transition_count

    # An inconsistent machine state is not a semantic
    # blackhole and must never become a terminal transition.
    with pytest.raises(
        InvalidMachineStateError,
        match="no active UpdateFrame",
    ):
        step(malformed, config)

    # The failed transition must not mutate its input.
    assert malformed.transition_index == before_index
    assert (
        malformed.machine_state.evaluator_transition_count
        == before_count
    )
    assert malformed.machine_state.status is ExecutionStatus.RUNNING
    assert dict(malformed.machine_state.heap.cells) == before_cells
    assert malformed.machine_state.stack.frames == before_frames
    assert malformed.machine_state.control == Force(main_ref)

    # The original, valid checkpoint is unchanged.
    assert any(
        isinstance(frame, UpdateFrame)
        and frame.thunk_reference == main_ref
        for frame in checkpoint.machine_state.stack.frames
    )
    assert isinstance(
        checkpoint.machine_state.heap.get(main_ref).value,
        EvaluatingThunk,
    )


def test_reentrant_demand_does_not_start_second_force():
    config = make_cbneed_config()

    initial = create_initial_core_state(
        compile_source("main = main"),
        config,
        session_id="reentrant-thunk-demand",
    )

    current = initial
    events = []

    for _ in range(100):
        transition = step(current, config)
        events.extend(transition.semantic_events)
        current = transition.next_state

        if transition.rule_id is RuleId.CORE_BLACKHOLE_DETECTED:
            break
    else:
        pytest.fail("Expected blackhole was not reached")

    anchor = current.machine_state.global_environment.lookup(
        "main"
    )

    anchor_events = [
        event.kind
        for event in events
        if event.object_id == anchor.object_id
    ]

    assert anchor_events == [
        SemanticEventKind.THUNK_CREATED,
        SemanticEventKind.THUNK_DEMANDED,
        SemanticEventKind.THUNK_FORCE_STARTED,
        SemanticEventKind.THUNK_DEMANDED,
        SemanticEventKind.BLACKHOLE_DETECTED,
    ]

    assert (
        current.machine_state.status
        is ExecutionStatus.BLACKHOLE_DETECTED
    )


@pytest.mark.parametrize(
    ("source", "expected_forces"),
    [
        ("main = main", 1),
        (
            "main = a\n"
            "a = b\n"
            "b = a",
            3,
        ),
    ],
)
def test_blackhole_metrics_preserve_anchor_identity(
    source,
    expected_forces,
):
    config = make_cbneed_config()

    current = create_initial_core_state(
        compile_source(source),
        config,
        session_id="blackhole-metrics",
    )

    metrics = InstrumentationState()
    events = []

    for _ in range(150):
        transition = step(current, config)

        metrics = reduce_metrics(metrics, transition)
        events.extend(transition.semantic_events)

        current = transition.next_state

        if transition.rule_id is RuleId.CORE_BLACKHOLE_DETECTED:
            break
    else:
        pytest.fail("Expected a blackhole")

    # A terminal reentrant demand produces exactly
    # one demand and one blackhole event.
    assert [
        event.kind
        for event in transition.semantic_events
    ] == [
        SemanticEventKind.THUNK_DEMANDED,
        SemanticEventKind.BLACKHOLE_DETECTED,
    ]

    control = current.machine_state.control

    assert isinstance(control, Force)

    anchor = control.reference

    assert all(
        event.object_id == anchor.object_id
        for event in transition.semantic_events
    )

    assert isinstance(
        current.machine_state.heap.get(anchor).value,
        EvaluatingThunk,
    )

    assert any(
        isinstance(frame, UpdateFrame)
        and frame.thunk_reference == anchor
        for frame in current.machine_state.stack.frames
    )

    created_ids = {
        event.object_id
        for event in events
        if event.kind is SemanticEventKind.THUNK_CREATED
    }

    forced_ids = [
        event.object_id
        for event in events
        if event.kind is SemanticEventKind.THUNK_FORCE_STARTED
    ]

    # Every first force belongs to a created thunk,
    # and no thunk begins evaluation twice.
    assert len(forced_ids) == expected_forces
    assert len(set(forced_ids)) == expected_forces
    assert set(forced_ids) <= created_ids

    counters = metrics.counters

    assert counters.thunks_created == expected_forces
    assert counters.thunks_forced == expected_forces
    assert counters.thunk_demands == expected_forces + 1

    assert counters.blackholes == 1
    assert counters.thunks_updated == 0
    assert counters.shared_result_hits == 0
    assert counters.thunks_never_forced == 0
