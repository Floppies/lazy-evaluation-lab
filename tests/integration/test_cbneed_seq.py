from lazy_lab.engine.core_machine import create_initial_core_state, run_batch
from lazy_lab.pipeline import compile_source
from lazy_lab.runtime.control import Return
from lazy_lab.runtime.predefined import PartialPredefinedFunction
from lazy_lab.runtime.thunks import PendingThunk
from lazy_lab.runtime.transitions import BatchStopReason, RuleId
from tests.integration.test_cbneed_application import make_cbneed_config


def test_cbneed_partial_seq_does_not_force_argument():
    program = compile_source(
        "loop = loop\n"
        "main = seq loop"
    )
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-partial-divergent",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    machine = result.state.machine_state
    assert isinstance(machine.control, Return)

    partial_ref = machine.control.reference
    partial = machine.heap.get(partial_ref).value

    assert isinstance(partial, PartialPredefinedFunction)
    assert partial.name == "seq"
    assert partial.remaining_arity == 1

    argument_ref = partial.applied_arguments[0]
    assert isinstance(
        machine.heap.get(argument_ref).value,
        PendingThunk,
    )

    loop_ref = machine.global_environment.lookup("loop")
    assert isinstance(
        machine.heap.get(loop_ref).value,
        PendingThunk,
    )

    rules = [entry.rule_id for entry in result.trace]

    assert rules.count(RuleId.CORE_PREDEFINED_PARTIAL_APPLY) == 1
    assert RuleId.CORE_BLACKHOLE_DETECTED not in rules

def test_cbneed_partial_seq_defers_arithmetic():
    program = compile_source("main = seq (2 + 3)")
    config = make_cbneed_config()

    initial = create_initial_core_state(
        program,
        config,
        session_id="cbneed-seq-partial-arithmetic",
    )

    result = run_batch(initial, config, max_steps=150)

    assert result.stop_reason is BatchStopReason.WHNF_PENDING

    partial_ref = result.state.machine_state.control.reference
    partial = result.state.machine_state.heap.get(partial_ref).value

    assert isinstance(partial, PartialPredefinedFunction)

    argument_ref = partial.applied_arguments[0]
    assert isinstance(
        result.state.machine_state.heap.get(argument_ref).value,
        PendingThunk,
    )

    rules = [entry.rule_id for entry in result.trace]

    assert RuleId.CORE_PRIM_EXECUTE not in rules
    assert RuleId.CORE_PREDEFINED_PARTIAL_APPLY in rules