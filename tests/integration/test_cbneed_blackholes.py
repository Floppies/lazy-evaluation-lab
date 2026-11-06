
from lazy_lab.engine.core_machine import create_initial_core_state, run_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Force
from lazy_lab.runtime.stack import UpdateFrame
from lazy_lab.runtime.state import ExecutionStatus
from lazy_lab.runtime.thunks import EvaluatingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from tests.integration.test_cbneed_application import make_cbneed_config


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
