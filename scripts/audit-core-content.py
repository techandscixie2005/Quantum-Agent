"""Read-only course coverage and pedagogical review packet (run in the API image)."""

import asyncio
import json
from collections import Counter

from sqlalchemy import text

from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine

TOPICS = {
    "原子模型与旧量子论": ["bohr", "atomic model"],
    "量子力学基础": ["wave function", "schr"],
    "表象理论与矩阵力学": ["representation", "matrix mechanics"],
    "原子结构": ["atomic structure", "hydrogen"],
    "近似理论方法": ["perturbation", "variational"],
    "双原子分子": ["diatomic"],
    "分子光谱": ["spectroscopy", "molecular spectra"],
}


async def main():
    engine = create_database_engine(Settings())
    try:
        async with engine.connect() as connection:
            chunks = (await connection.execute(text(
                "SELECT id, publication_curriculum_edition_id AS edition_id, "
                "source_document_title, physical_page, content FROM student_visible_chunks"
            ))).mappings().all()
            candidates = (await connection.execute(text("""
                SELECT n.id, n.curriculum_edition_id, n.node_type, n.label, n.description,
                       n.status, n.confidence, d.title AS document_title, c.physical_page,
                       c.content_sha256, e.evidence_snippet AS quote
                FROM graph_node_candidates n
                JOIN node_candidate_evidence_support s ON s.node_candidate_id=n.id
                JOIN evidence e ON e.id=s.evidence_id
                JOIN document_chunks c ON c.id=e.source_chunk_id
                JOIN source_document_versions v ON v.id=c.document_version_id
                JOIN source_documents d ON d.id=v.document_id
                WHERE n.origin='llm'
                ORDER BY n.node_type,d.title,c.physical_page,n.label
            """))).mappings().all()
            relations = (await connection.execute(text("""
                SELECT r.id, r.relation_type, s.label AS source, t.label AS target,
                       r.status, e.evidence_snippet AS quote
                FROM graph_relation_candidates r
                JOIN graph_node_candidates s ON s.id=r.source_node_candidate_id
                JOIN graph_node_candidates t ON t.id=r.target_node_candidate_id
                JOIN relation_candidate_evidence_support p ON p.relation_candidate_id=r.id
                JOIN evidence e ON e.id=p.evidence_id
                WHERE r.origin='llm' ORDER BY r.relation_type,r.id
            """))).mappings().all()
        coverage = {}
        for topic, terms in TOPICS.items():
            matches = [row for row in chunks if any(t in row["content"].lower() for t in terms)]
            coverage[topic] = {
                "matching_chunks": len({row["id"] for row in matches}),
                "examples": [{k: row[k] for k in (
                    "id", "edition_id", "source_document_title", "physical_page"
                )} for row in matches[:3]],
            }
        print(json.dumps({
            "coverage_method": "lexical presence only; not scientific/pedagogical coverage certification",
            "coverage": coverage,
            "candidate_counts": dict(Counter(row["node_type"] for row in candidates)),
            "review_required": True,
            "candidates": [dict(row) for row in candidates],
            "relations": [dict(row) for row in relations],
        }, ensure_ascii=False, indent=2, default=str))
    finally:
        await engine.dispose()


asyncio.run(main())
