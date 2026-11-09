import pytest

from lazy_lab.runtime.constructors import ConstructorValue
from lazy_lab.runtime.references import (
    ImmediateInteger,
    HeapReference,
    ObjectId,
)


def test_constructor_representation_and_slots():
    nil = ConstructorValue("Nil", ())

    cons = ConstructorValue(
        "Cons",
        (
            ImmediateInteger(1),
            HeapReference(ObjectId(0)),
        ),
    )

    assert nil.tag == "Nil"
    assert nil.fields == ()
    assert nil.required_slots == 1

    assert cons.tag == "Cons"
    assert len(cons.fields) == 2
    assert cons.required_slots == 3


def test_constructor_rejects_invalid_structure():
    with pytest.raises(ValueError):
        ConstructorValue("Tree", ())

    with pytest.raises(ValueError):
        ConstructorValue("Cons", (ImmediateInteger(1),))

    with pytest.raises(TypeError):
        ConstructorValue("Nil", [])