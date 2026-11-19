
"""Synchronized passive projections for interactive sessions."""

from __future__ import annotations

from lazy_lab.runtime.state import ExecutionState
from lazy_lab.visualizer.heap_diff import project_heap_snapshot_diff
from lazy_lab.visualizer.heap_graph import project_memory_graph
from lazy_lab.visualizer.heap_roots import project_memory_roots
from lazy_lab.visualizer.heap_table import project_heap_table
from lazy_lab.visualizer.projections import (
    project_control_and_stack,
    project_execution_overview,
    project_metrics_and_result,
)
from lazy_lab.visualizer.session import (
    InteractiveSession,
    available_session_indices,
    get_inspected_state,
)
from lazy_lab.visualizer.source_core import project_source_and_core
from lazy_lab.visualizer.source_highlighting import (
    project_source_highlighting,
)


def _project_adjacent_heap_diff(
    session: InteractiveSession,
    inspected: ExecutionState,
) -> dict[str, object]:
    """Compare against T-1 only when that exact state was retained."""

    index = inspected.transition_index

    if index == 0:
        return {
            "available": False,
            "reason": "initial_state",
            "comparison": None,
        }

    previous_index = index - 1

    if previous_index not in session.history.available_indices:
        return {
            "available": False,
            "reason": "previous_state_not_retained",
            "comparison": None,
        }

    previous = session.history.get_snapshot(previous_index)

    return {
        "available": True,
        "reason": None,
        "comparison": project_heap_snapshot_diff(
            previous,
            inspected,
        ),
    }

def project_interactive_session(
    session: InteractiveSession,
) -> dict[str, object]:
    """Project every dynamic panel from one inspected state."""

    if not isinstance(session, InteractiveSession):
        raise TypeError("Expected an InteractiveSession")

    inspected = get_inspected_state(session)

    read_index = inspected.transition_index
    live_index = session.live_state.transition_index

    return {
        "navigation": {
            "session_id": session.session_id,
            "read_cursor_index": read_index,
            "live_transition_index": live_index,
            "following_live_head": read_index == live_index,
            "available_indices": list(
                available_session_indices(session)
            ),
            "auto_run_requested": session.auto_run_requested,
            "trace_mode": session.config.trace_mode.value,
            "capture_categories": sorted(session.capture_categories),
        },
        "execution": project_execution_overview(
            inspected,
            session.config,
        ),
        "control_stack": project_control_and_stack(inspected),
        "metrics_result": project_metrics_and_result(inspected),
        "source_core": project_source_and_core(
            session.source,
            session.core_program,
        ),
        "source_highlighting": project_source_highlighting(
            inspected,
            session.core_program,
        ),
        "memory": {
            "heap_table": project_heap_table(inspected),
            "heap_graph": project_memory_graph(inspected),
            "roots": project_memory_roots(inspected),
            "diff": _project_adjacent_heap_diff(
                session,
                inspected,
            ),
        },
    }
