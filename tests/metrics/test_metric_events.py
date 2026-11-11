
from dataclasses import FrozenInstanceError

import pytest

from lazy_lab.metrics.events import (
    EventOrigin,
    OriginKind,
    SemanticEvent,
    SemanticEventKind,
)
from lazy_lab.source import OriginKind, SourceSpan


def test_semantic_event_preserves_explicit_origin():
    span = SourceSpan(1, 1, 1, 10)

    event = SemanticEvent(
        kind=SemanticEventKind.BETA_REDUCED,
        origin=EventOrigin(
            kind=OriginKind.GENERATED,
            source_spans=(span,),
        ),
    )

    assert event.kind is SemanticEventKind.BETA_REDUCED
    assert event.origin.kind is OriginKind.GENERATED
    assert event.origin.source_spans == (span,)


def test_semantic_event_has_unknown_origin_by_default():
    event = SemanticEvent(
        kind=SemanticEventKind.THUNK_DEMANDED,
        object_id=5,
    )

    assert event.origin.kind is OriginKind.UNKNOWN
    assert event.object_id == 5

    with pytest.raises(FrozenInstanceError):
        event.object_id = 6


def test_origin_kind_is_shared_with_source_model():
    from lazy_lab.source import OriginKind as SourceOriginKind

    assert OriginKind is SourceOriginKind

    event = SemanticEvent(
        SemanticEventKind.BETA_REDUCED,
        origin=EventOrigin(kind=OriginKind.GENERATED),
    )

    assert event.origin.kind is SourceOriginKind.GENERATED
