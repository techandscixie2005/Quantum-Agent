"""Read-only, allowlisted evidence export; run inside the existing API container."""
import asyncio
import json

from sqlalchemy import text

from quantum_agent.config import Settings
from quantum_agent.database import create_database_engine


async def main():
    engine = create_database_engine(Settings())
    result = {}
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SET TRANSACTION READ ONLY"))
            async def query(sql, params=None):
                return [dict(row) for row in (await connection.execute(
                    text(sql), params or {}
                )).mappings()]

            rows = await query("""
                SELECT t.id, t.sequence_number, t.created_at, t.completed_at,
                       t.evidence_packet_json, t.scientific_results_json,
                       t.validation_json, a.steps_json, a.model_gateway_status
                FROM teaching_turns t JOIN agent_traces a ON a.teaching_turn_id=t.id
                WHERE t.conversation_id=(SELECT conversation_id FROM teaching_turns
                    WHERE id='30e80fdc-0c43-4e75-9431-1f528143565c')
                ORDER BY t.sequence_number
            """)
            evidence = {}
            turns = []
            for row in rows:
                packet = row.pop("evidence_packet_json") or {}
                steps = row.pop("steps_json") or {}
                scientific = row.pop("scientific_results_json") or {}
                row["scientific_results"] = [{k: item.get(k) for k in (
                    "kind", "status", "metrics", "inputs_sha256", "limitations"
                )} for item in scientific.get("results", [])]
                snapshot = scientific.get("__result_snapshot") or {}
                row["coding_artifact"] = snapshot.get("code_artifact")
                row["learning_loop_completed"] = snapshot.get("learning_loop_completed")
                row["phase"] = (steps.get("learning_native") or {}).get("phase")
                row["workflow_steps"] = steps.get("steps")
                row["evidence_ids"] = [item["evidence_id"] for item in packet.get("evidence", [])]
                row["graph_nodes"] = packet.get("graph_nodes")
                row["graph_edges"] = packet.get("graph_edges")
                row["edition_id"] = packet.get("curriculum_edition_id")
                for item in packet.get("evidence", []):
                    evidence[item["evidence_id"]] = {k: item.get(k) for k in (
                        "evidence_id", "chunk_id", "document_version_id", "document_title",
                        "document_version", "source_file_sha256", "source_chunk_sha256",
                        "evidence_sha256", "locator", "evidence_snippet", "curriculum_edition_id"
                    )}
                turns.append(row)
            result["turns"] = turns
            result["evidence"] = list(evidence.values())
            edition = "64077260-0470-5742-8424-c73697d9f399"
            result["edition"] = await query("SELECT id,title,status FROM curriculum_editions WHERE id=:e", {"e": edition})
            result["publications"] = await query("""
                SELECT d.title,v.id AS document_version_id,v.version_number,
                       v.source_file_sha256,v.status AS version_status,
                       p.status AS publication_status,p.published_at
                FROM document_publications p JOIN source_document_versions v
                ON v.id=p.document_version_id JOIN source_documents d ON d.id=v.document_id
                WHERE p.curriculum_edition_id=:e
            """, {"e": edition})
            result["llm_candidates"] = await query("""
                SELECT id,label,node_type,status FROM graph_node_candidates
                WHERE curriculum_edition_id=:e AND origin='llm' ORDER BY label
            """, {"e": edition})
            result["bridge_source"] = await query("""
                SELECT e.id,e.status,e.evidence_snippet,e.char_start,e.char_end,
                       e.evidence_sha256,c.id AS chunk_id,c.content,c.content_sha256,
                       c.physical_page,v.id AS document_version_id,v.source_file_sha256
                FROM evidence e JOIN document_chunks c ON c.id=e.source_chunk_id
                JOIN source_document_versions v ON v.id=c.document_version_id
                WHERE e.id='4c42d987-b11f-58ca-9f89-e97db9fb9476'
            """)
            result["case_source_pages"] = await query("""
                SELECT c.id,c.physical_page,c.content,c.content_sha256
                FROM document_chunks c WHERE c.document_version_id=
                '3de8d896-67d0-5651-b10e-aefb911181c1'
                AND c.physical_page IN (77,78,79,80) ORDER BY c.physical_page,c.ordinal
            """)
            result["evidence_status"] = []
            for eid in evidence:
                result["evidence_status"] += await query(
                    "SELECT id,status FROM evidence WHERE id=:id", {"id": eid})
    finally:
        await engine.dispose()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


asyncio.run(main())
