
"""Synchronized passive projections for interactive sessions."""

from __future__ import annotations

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
from lazy_lab.visualizer.source_core import (
    project_source_and_core,
)
from lazy_lab.visualizer.source_highlighting import (
    project_source_highlighting,
)


def project_interactive_session(
    session: InteractiveSession,
) -> dict[str, object]:
    """Project all visual panels from one inspected state."""

    if not isinstance(session, InteractiveSession):
        raise TypeError("Expected an InteractiveSession")

    # Resolve the read cursor once. All dynamic panels use
    # exactly the same inspected state.
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
        },
        "execution": project_execution_overview(
            inspected,
            session.config,
        ),
        "control_stack": project_control_and_stack(
            inspected,
        ),
        "metrics_result": project_metrics_and_result(
            inspected,
        ),
        "source_core": project_source_and_core(
            session.source,
            session.core_program,
        ),
        "source_highlighting": project_source_highlighting(
            inspected,
            session.core_program,
        ),
    }
