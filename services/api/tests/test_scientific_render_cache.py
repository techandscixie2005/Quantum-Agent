"""Bounded render reuse with independent caller-owned plot data."""

from __future__ import annotations

import pytest

import quantum_agent.science.toolbox as toolbox
from quantum_agent.science.models import LineVisualizationRequest, PlotSeries, VisualizationSpec


def _request(index: int = 0) -> LineVisualizationRequest:
    return LineVisualizationRequest(
        title=f"Automated test {index}",
        x_label="width (m)",
        y_label="T",
        x=[1e-10, 2e-10],
        series=[PlotSeries(label="T", y=[0.33, 0.04])],
    )


def test_render_cache_reuses_work_without_sharing_mutable_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    toolbox._cached_line_spec_json.cache_clear()
    original = toolbox._render_line_spec_uncached
    rendered: list[str] = []

    def render(request: LineVisualizationRequest) -> VisualizationSpec:
        rendered.append(request.title)
        return original(request)

    monkeypatch.setattr(toolbox, "_render_line_spec_uncached", render)
    first = toolbox._render_line_spec(_request())
    first.x[0] = 999
    first.series[0].y[0] = 999
    second = toolbox._render_line_spec(_request())
    assert rendered == ["Automated test 0"]
    assert second.x == [1e-10, 2e-10]
    assert second.series[0].y == [0.33, 0.04]
    assert first.rendering_sha256 == second.rendering_sha256
    toolbox._cached_line_spec_json.cache_clear()


def test_render_cache_has_fixed_entry_budget() -> None:
    toolbox._cached_line_spec_json.cache_clear()
    for index in range(18):
        toolbox._render_line_spec(_request(index))
    assert toolbox._cached_line_spec_json.cache_info().currsize == 16
    toolbox._cached_line_spec_json.cache_clear()


def test_large_plots_are_not_retained_in_cache() -> None:
    toolbox._cached_line_spec_json.cache_clear()
    request = _request()
    # A valid request can carry substantially more data than the cache budget.
    request = request.model_copy(update={
        "x": [index / 1000 for index in range(5_000)],
        "series": [PlotSeries(label="T", y=[0.123456789012345] * 5_000)],
    })
    assert len(request.model_dump_json().encode("utf-8")) > 64_000
    toolbox._render_line_spec(request)
    assert toolbox._cached_line_spec_json.cache_info().currsize == 0
