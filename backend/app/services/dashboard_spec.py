"""Bounded, deterministic edits to a saved chart layout."""

from __future__ import annotations

from typing import Any, Literal

DashboardAction = Literal["hide", "show", "move_up", "move_down", "set_palette", "pin_metric", "unpin_metric", "save_filters", "undo"]
PALETTES = {"aurora", "sunset", "ocean", "garden"}


def default_spec(charts: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [chart["id"] for chart in charts if isinstance(chart.get("id"), str)]
    return {"schema_version": 1, "chart_order": list(dict.fromkeys(ids)), "hidden_chart_ids": [], "chart_palettes": {}, "metric_family_ids": [], "saved_filters": []}


def reconcile_spec(spec: dict[str, Any], charts: list[dict[str, Any]], metric_ids: list[str] | None = None) -> dict[str, Any]:
    """Keep a saved layout useful after a regenerated analysis changes charts."""
    current_ids = default_spec(charts)["chart_order"]
    old_order = spec.get("chart_order") if isinstance(spec.get("chart_order"), list) else []
    order = list(dict.fromkeys(
        [item for item in old_order if item in current_ids] +
        [item for item in current_ids if item not in old_order]
    ))
    old_hidden = spec.get("hidden_chart_ids") if isinstance(spec.get("hidden_chart_ids"), list) else []
    old_palettes = spec.get("chart_palettes") if isinstance(spec.get("chart_palettes"), dict) else {}
    return {
        "schema_version": 1,
        "chart_order": order,
        "hidden_chart_ids": [item for item in order if item in old_hidden],
        "chart_palettes": {item: old_palettes[item] for item in order if old_palettes.get(item) in PALETTES},
        "metric_family_ids": [item for item in dict.fromkeys(spec.get("metric_family_ids", [])) if item in (metric_ids or [])],
        "saved_filters": spec.get("saved_filters", []) if isinstance(spec.get("saved_filters"), list) else [],
    }


def edit_spec(
    spec: dict[str, Any], action: DashboardAction, chart_id: str | None,
    *, metric_ids: list[str] | None = None, metric_family_id: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    palette: str | None = None,
) -> dict[str, Any]:
    if action == "undo":
        raise ValueError("Undo requires a prior revision")
    order = list(spec["chart_order"])
    hidden = list(spec["hidden_chart_ids"])
    palettes = dict(spec.get("chart_palettes", {}))
    pinned = list(spec.get("metric_family_ids", []))
    saved_filters = list(spec.get("saved_filters", []))
    if action in ("pin_metric", "unpin_metric"):
        if metric_family_id not in (metric_ids or []):
            raise ValueError("Approved metric is not in this analysis")
        if action == "pin_metric" and metric_family_id not in pinned:
            pinned.append(metric_family_id)
        elif action == "unpin_metric":
            pinned = [item for item in pinned if item != metric_family_id]
    elif action == "save_filters":
        saved_filters = filters or []
    else:
        if chart_id not in order:
            raise ValueError("Chart is not in this dashboard")
        if action == "set_palette":
            if palette not in PALETTES:
                raise ValueError("Unknown chart palette")
            if palette == "aurora":
                palettes.pop(chart_id, None)
            else:
                palettes[chart_id] = palette
        elif action == "hide":
            if chart_id not in hidden:
                hidden.append(chart_id)
        elif action == "show":
            hidden = [item for item in hidden if item != chart_id]
        else:
            visible = [item for item in order if item not in hidden]
            if chart_id in visible:
                index = visible.index(chart_id)
                target = index + (-1 if action == "move_up" else 1)
                if 0 <= target < len(visible):
                    source_position = order.index(chart_id)
                    target_position = order.index(visible[target])
                    order[source_position], order[target_position] = order[target_position], order[source_position]
    return {"schema_version": 1, "chart_order": order, "hidden_chart_ids": hidden,
            "chart_palettes": palettes,
            "metric_family_ids": pinned, "saved_filters": saved_filters}
