"""End-to-end test for the Coding Agent integration in the tutor graph (PRD V3.1 §6)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from quantum_agent.coding import CodeVerificationStatus, CodingAgent, SubprocessSandbox
from quantum_agent.coding.models import CodeArtifact, CodeLanguage
from quantum_agent.llm.gateway import FakeModelGateway
from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.teaching.models import (
    TeachingMode,
    TeachingTurnInput,
    TeachingTurnResult,
    WorkflowStepName,
)
from quantum_agent.tutor.graph import TutorGraph
from tests.test_tutor_graph import (  # noqa: F401  pytest fixture re-export
    StaticRetriever,
    _packet,
    _seed,
    teaching_database,
)

_TUNNELLING_CODE = (
    "import math\n"
    "joule_per_eV = 1.602176634e-19\n"
    "hbar_j_s = 1.054571817e-34\n"
    "m_e = 9.1093837015e-31\n"
    "E = 5.0; V0 = 10.0; a = 1e-10\n"
    "E_j = E * joule_per_eV; V0_j = V0 * joule_per_eV\n"
    "kappa = math.sqrt(2.0 * m_e * (V0_j - E_j)) / hbar_j_s\n"
    "sinh_sq = math.sinh(kappa * a) ** 2\n"
    "T = 1.0 / (1.0 + (V0_j * V0_j * sinh_sq) / (4.0 * E_j * (V0_j - E_j)))\n"
    "R = 1.0 - T\n"
    "cons = abs(R + T - 1.0)\n"
    'print("### METRICS_JSON: " + \'{"T": \' + str(T) + \', "R": \' + str(R) + \', "conservation_error": \' + str(cons) + \'}\')\n'
)


async def test_tutor_graph_runs_coding_agent_and_keeps_ten_step_trace(
    teaching_database: async_sessionmaker[AsyncSession],  # noqa: F811  pytest fixture
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        artifact = CodeArtifact(
            language=CodeLanguage.PYTHON,
            purpose="rectangular barrier tunnelling T/R",
            code=_TUNNELLING_CODE,
            expected_outputs=["T", "R", "conservation_error"],
            verification_plan="match oracle within 1e-6",
        )
        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["tunnelling"],
                    "needs_scientific_verification": True,
                    "confidence": 0.8,
                },
                "diagnose_student_progress_structured": {
                    "status": "observed",
                    "summary": "student predicted T decreases with width",
                    "likely_misconception": "thinks T is constant",
                    "observation_basis": ["student_message"],
                    "target_concepts": ["tunnelling"],
                    "first_error": None,
                    "misconception_candidates": [],
                    "missing_prerequisites": [],
                    "progress_state": "started",
                    "confidence": 0.7,
                    "verification_needed": True,
                    "reason": "prediction needs verification",
                },
                "compose_grounded_teaching_response": {
                    "orientation": "Compare your prediction to the simulation.",
                    "claims": [],
                    "next_question": "How does T change as the barrier widens?",
                    "status": "grounded",
                    "limitations": [],
                },
                "generate_coding_artifact": artifact.model_dump(mode="json"),
            }
        )
        sandbox = SubprocessSandbox()
        coding_agent = CodingAgent(sandbox=sandbox)
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=gateway,
            coding_agent=coding_agent,
            sandbox=sandbox,
        )
        science_request = RectangularBarrierRequest(
            energy_eV=5.0,
            barrier_height_eV=10.0,
            barrier_width_m=1e-10,
            particle_mass_kg=9.1093837015e-31,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.RUN_EXPERIMENTS,
                message="计算电子隧穿矩形势垒的透射率。",
                student_attempt="我预测 T 会随势垒宽度增加而减小。",
                scientific_request=science_request,
            ),
        )
        await session.commit()

    assert isinstance(result, TeachingTurnResult)
    # The deterministic oracle still runs (dual-path).
    assert len(result.scientific_results) >= 1
    oracle_t = float(result.scientific_results[-1].metrics["T"])
    assert abs(oracle_t - 0.333682) < 1e-4
    # The Coding Agent artifact is populated and verified.
    assert result.code_artifact is not None
    assert result.code_artifact.verification.status is CodeVerificationStatus.PASS
    agent_t = float(result.code_artifact.verification.agent_metrics["T"])
    assert abs(agent_t - oracle_t) < 1e-6
    # The trace stays at the fixed 10-step workflow.
    assert [step.name for step in result.trace] == list(WorkflowStepName)
    assert len(result.trace) == 10


async def test_failed_coding_agent_cannot_surface_oracle_computation_as_success(
    teaching_database: async_sessionmaker[AsyncSession],  # noqa: F811
) -> None:
    async with teaching_database() as session:
        seeded = await _seed(session)
        packet = _packet(seeded.actor.course_id, seeded.edition_id)
        broken_artifact = CodeArtifact(
            purpose="does not compute the requested result",
            code="raise RuntimeError('agent computation failed')",
            expected_outputs=["T", "R", "conservation_error"],
            verification_plan="must fail transparently",
        )
        gateway = FakeModelGateway(
            {
                "interpret_teaching_turn": {
                    "task_kind": "exercise_help",
                    "relevant_concepts": ["tunnelling"],
                    "needs_scientific_verification": True,
                    "confidence": 0.8,
                },
                "diagnose_student_progress_structured": {
                    "status": "observed",
                    "summary": "student supplied a prediction",
                    "likely_misconception": None,
                    "observation_basis": ["student_attempt"],
                    "target_concepts": ["tunnelling"],
                    "first_error": None,
                    "misconception_candidates": [],
                    "missing_prerequisites": [],
                    "progress_state": "started",
                    "confidence": 0.5,
                    "verification_needed": True,
                    "reason": "the prediction needs computation",
                },
                "compose_grounded_teaching_response": {
                    "orientation": "The computation must complete before using its result.",
                    "claims": [],
                    "next_question": "What failed?",
                    "status": "grounded",
                    "limitations": [],
                },
                "generate_coding_artifact": broken_artifact.model_dump(mode="json"),
            }
        )
        sandbox = SubprocessSandbox()
        graph = TutorGraph(
            evidence_retriever=StaticRetriever(packet),
            model_gateway=gateway,
            coding_agent=CodingAgent(sandbox=sandbox, max_repairs=0),
            sandbox=sandbox,
        )
        result = await graph.run(
            session=session,
            actor=seeded.actor,
            curriculum_edition_id=seeded.edition_id,
            request=TeachingTurnInput(
                mode=TeachingMode.RUN_EXPERIMENTS,
                message="Compute rectangular-barrier transmission.",
                student_attempt="I predict a non-zero transmission.",
                scientific_request=RectangularBarrierRequest(
                    energy_eV=5.0,
                    barrier_height_eV=10.0,
                    barrier_width_m=1e-10,
                    particle_mass_kg=9.1093837015e-31,
                ),
            ),
        )

    assert isinstance(result, TeachingTurnResult)
    assert result.code_artifact is not None
    assert result.code_artifact.verification.status is CodeVerificationStatus.INCONCLUSIVE
    assert not any(item.status.value == "pass" for item in result.scientific_results)
