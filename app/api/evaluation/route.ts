import { runEvaluationEpisode, generateEpisodeReport, personas, type EpisodeConfig } from "../../../lib/evaluation";

export async function POST(request: Request) {
  try {
    const body = await request.json() as Partial<EpisodeConfig>;

    const config: EpisodeConfig = {
      personaId: body.personaId ?? "classical_tunneling_intuition",
      taskMode: body.taskMode ?? "concept",
      capability: body.capability ?? "quick",
      maxTurns: Math.min(body.maxTurns ?? 5, 20),
      seed: body.seed ?? 0,
      offlineMode: body.offlineMode ?? true,
      wallClockTimeoutMs: body.wallClockTimeoutMs ?? 30000,
    };

    if (!personas[config.personaId]) {
      return Response.json({ error: `Unknown persona: ${config.personaId}` }, { status: 400 });
    }

    const episode = await runEvaluationEpisode(config);
    const report = generateEpisodeReport(episode);

    return Response.json({ episode, report });
  } catch (error) {
    return Response.json(
      { error: "Evaluation failed", detail: error instanceof Error ? error.message : "Unknown" },
      { status: 500 }
    );
  }
}

export async function GET(_request: Request) {
  const personaList = Object.entries(personas).map(([id, p]) => ({
    id,
    label: p.label,
    description: p.description,
    knowledgeLevel: p.knowledgeLevel,
    modes: p.modes,
  }));

  return Response.json({ personas: personaList });
}