
from dataclasses import FrozenInstanceError, replace

import pytest

from lazy_lab.metrics.state import (
    InstrumentationState,
    MetricCounters,
)


def test_initial_instrumentation_is_empty():
    state = InstrumentationState()

    assert state.counters.semantic_reductions == 0
    assert state.counters.current_frames == 0
    assert state.counters.thunks_never_forced == 0
    assert state.baseline_slots is None
    assert state.additional_peak_over_baseline is None


def test_derived_metrics():
    counters = MetricCounters(
        beta_reductions=3,
        primitive_reductions=2,
        seq_reductions=1,
        function_applications=4,
        pushes=7,
        pops=5,
        thunks_created=6,
        thunks_forced=2,
        peak_heap_slots=18,
    )

    state = InstrumentationState(
        counters=counters,
        baseline_slots=10,
    )

    assert counters.semantic_reductions == 6
    assert counters.current_frames == 2
    assert counters.thunks_never_forced == 4
    assert state.additional_peak_over_baseline == 8


def test_metric_state_is_immutable():
    original = InstrumentationState()

    updated = replace(
        original,
        counters=replace(
            original.counters,
            beta_reductions=1,
        ),
    )

    assert original.counters.beta_reductions == 0
    assert updated.counters.beta_reductions == 1

    with pytest.raises(FrozenInstanceError):
        original.baseline_slots = 10
