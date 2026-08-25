"""JSON I/O and command-line runner for the deterministic evaluator."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from quantum_agent.evaluation.fixtures import build_offline_fixture
from quantum_agent.evaluation.metrics import evaluate_dataset
from quantum_agent.evaluation.models import EvaluationDataset, EvaluationReport


def load_dataset(path: Path) -> EvaluationDataset:
    """Load and strictly validate a JSON evaluation dataset."""

    return EvaluationDataset.model_validate_json(path.read_text(encoding="utf-8"))


def dataset_json(dataset: EvaluationDataset) -> str:
    return json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def report_json(report: EvaluationReport) -> str:
    return json.dumps(
        report.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )


def write_dataset(path: Path, dataset: EvaluationDataset) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dataset_json(dataset) + "\n", encoding="utf-8")


def write_report(path: Path, report: EvaluationReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report_json(report) + "\n", encoding="utf-8")


def evaluate_file(input_path: Path, output_path: Path) -> EvaluationReport:
    report = evaluate_dataset(load_dataset(input_path))
    write_report(output_path, report)
    return report


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m quantum_agent.evaluation",
        description="Score captured Quantum Agent B0-B4 runs without model calls.",
    )
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Validated evaluation dataset JSON")
    source.add_argument(
        "--offline-fixture",
        action="store_true",
        help="Evaluate the deterministic bundled B0-B4 fixture",
    )
    parser.add_argument("--output", type=Path, help="Report JSON path; defaults to stdout")
    parser.add_argument(
        "--export-dataset",
        type=Path,
        help="Also write the validated input/fixture dataset as canonical JSON",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    dataset = (
        build_offline_fixture()
        if arguments.offline_fixture
        else load_dataset(arguments.input)
    )
    if arguments.export_dataset is not None:
        write_dataset(arguments.export_dataset, dataset)
    report = evaluate_dataset(dataset)
    if arguments.output is None:
        sys.stdout.write(report_json(report) + "\n")
    else:
        write_report(arguments.output, report)
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through the package entry point
    raise SystemExit(main())
