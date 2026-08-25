from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantum_agent.evaluation import (
    EvaluationReport,
    EvaluationVariant,
    build_offline_fixture,
    evaluate_file,
    load_dataset,
    write_dataset,
)
from quantum_agent.evaluation.runner import main


def test_json_input_output_round_trip_is_deterministic(tmp_path: Path) -> None:
    dataset = build_offline_fixture()
    input_path = tmp_path / "dataset.json"
    first_report_path = tmp_path / "report-first.json"
    second_report_path = tmp_path / "report-second.json"
    write_dataset(input_path, dataset)

    assert load_dataset(input_path) == dataset
    first = evaluate_file(input_path, first_report_path)
    second = evaluate_file(input_path, second_report_path)

    assert first == second
    assert first_report_path.read_bytes() == second_report_path.read_bytes()
    parsed = EvaluationReport.model_validate_json(first_report_path.read_text(encoding="utf-8"))
    assert parsed.dataset_id == dataset.dataset_id
    assert len(parsed.case_results) == 7


def test_cli_evaluates_and_exports_the_offline_fixture(tmp_path: Path) -> None:
    report_path = tmp_path / "nested" / "report.json"
    dataset_path = tmp_path / "nested" / "dataset.json"

    exit_code = main(
        [
            "--offline-fixture",
            "--output",
            str(report_path),
            "--export-dataset",
            str(dataset_path),
        ]
    )

    assert exit_code == 0
    assert load_dataset(dataset_path).dataset_id == "quantum-agent-v2.1-offline-smoke"
    report = EvaluationReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    assert [item.variant for item in report.variants] == list(EvaluationVariant)


def test_cli_stdout_is_valid_json_without_runtime_timestamp(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--offline-fixture"]) == 0
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert payload["dataset_id"] == "quantum-agent-v2.1-offline-smoke"
    assert "generated_at" not in payload
