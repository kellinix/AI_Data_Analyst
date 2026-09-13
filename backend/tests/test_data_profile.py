"""What the Profile JSON sends to the model.

The profile is the model's only source of truth, and it is also the bulk of a
request that runs against a 30,000 tokens-per-minute ceiling — one analysis was
measured by OpenAI at 30,196 tokens. What goes in it is therefore a budget
decision as much as a correctness one.
"""

from __future__ import annotations

from app.services.data_profile import _spec_shape


def test_spec_shape_drops_the_plotted_rows_but_keeps_the_count():
    """Regression: the spec carried every plotted row, making the charts a
    third of the whole profile — data the model has no use for when it is
    choosing a layout."""
    spec = {
        "mark": {"type": "bar"},
        "encoding": {"x": {"field": "category"}, "y": {"field": "value"}},
        "data": {"values": [{"category": "MOD", "value": 9152.3}] * 40},
    }

    shape = _spec_shape(spec)

    assert "data" not in shape
    assert shape["data_points"] == 40
    # The structure the model actually reasons about survives.
    assert shape["mark"] == {"type": "bar"}
    assert shape["encoding"]["x"]["field"] == "category"


def test_spec_shape_handles_a_spec_with_no_data():
    assert _spec_shape({"mark": {"type": "arc"}})["data_points"] == 0


def test_spec_shape_tolerates_a_missing_or_malformed_spec():
    assert _spec_shape(None) == {}
    assert _spec_shape("not a spec") == {}
    assert _spec_shape({"data": "unexpected"})["data_points"] == 0
