
from lazy_lab.core.nodes import CoreVar
from lazy_lab.metrics.events import SemanticEventKind
from lazy_lab.metrics.recording import SemanticEventRecorder
from lazy_lab.runtime.references import ObjectId
from lazy_lab.source import OriginKind, SourceSpan


def test_recorder_preserves_event_order_and_provenance():
    recorder = SemanticEventRecorder()

    expression = CoreVar(
        "x",
        span=SourceSpan(1, 1, 1, 2),
        origin=OriginKind.GENERATED,
    )

    recorder.emit(
        SemanticEventKind.VARIABLE_LOOKED_UP,
        node=expression,
    )

    recorder.emit(
        SemanticEventKind.THUNK_DEMANDED,
        object_id=ObjectId(7),
    )

    recorded = recorder.freeze()

    assert isinstance(recorded, tuple)
    assert len(recorded) == 2

    assert recorded[0].origin.kind is OriginKind.GENERATED
    assert recorded[0].origin.source_spans == (
        expression.span,
    )

    assert recorded[1].object_id == ObjectId(7)
    assert recorded[1].origin.kind is OriginKind.UNKNOWN