
import pytest

from lazy_lab.runtime.environment import (
    Environment,
    UnboundNameError,
)
from lazy_lab.runtime.references import (
    HeapReference,
    ImmediateBoolean,
    ImmediateInteger,
    ObjectId,
)


def test_lexical_lookup_and_shadowing():
    root = Environment({
        "x": ImmediateInteger(1),
        "enabled": ImmediateBoolean(True),
    })

    nested = root.extend({"x": ImmediateInteger(2)})

    assert root.lookup("x") == ImmediateInteger(1)
    assert nested.lookup("x") == ImmediateInteger(2)
    assert nested.lookup("enabled") == ImmediateBoolean(True)


def test_lookup_does_not_force_or_dereference():
    reference = HeapReference(ObjectId(7))
    env = Environment({"pending": reference})

    assert env.lookup("pending") is reference


def test_recursive_group_can_be_bound_simultaneously():
    references = {
        "even": HeapReference(ObjectId(10)),
        "odd": HeapReference(ObjectId(11)),
    }

    env = Environment().extend(references)

    assert env.lookup("even") == references["even"]
    assert env.lookup("odd") == references["odd"]


def test_environment_cannot_be_mutated():
    source = {"x": ImmediateInteger(3)}
    env = Environment(source)

    source["x"] = ImmediateInteger(99)

    assert env.lookup("x") == ImmediateInteger(3)

    with pytest.raises(TypeError):
        env.bindings["x"] = ImmediateInteger(10)


def test_unbound_name_raises():
    env = Environment()

    with pytest.raises(UnboundNameError):
        env.lookup("unknown")


def test_deep_lexical_chain_is_iterative():
    root = Environment({
        "target": ImmediateInteger(42)
    })

    current = root

    for index in range(2000):
        current = current.extend({
            f"local{index}": ImmediateInteger(index)
        })

    assert current.lookup("target") == ImmediateInteger(42)


@pytest.mark.parametrize("value", [True, "12", 1.2])
def test_immediate_integer_rejects_invalid_values(value):
    with pytest.raises(TypeError):
        ImmediateInteger(value)
