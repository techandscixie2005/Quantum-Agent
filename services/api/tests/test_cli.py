from __future__ import annotations

from quantum_agent.cli import DEFAULT_MANIFEST, build_parser


def test_cli_defaults_to_versioned_real_course_manifest() -> None:
    arguments = build_parser().parse_args(["ingest"])
    assert arguments.manifest == str(DEFAULT_MANIFEST)
    assert DEFAULT_MANIFEST.is_file()


def test_graph_worker_has_bounded_non_watch_default() -> None:
    arguments = build_parser().parse_args(["sync-graph"])
    assert arguments.limit == 100
    assert arguments.watch is False
