import { runEvaluationEpisode, generateEpisodeReport, personas, type EpisodeConfig } from "../lib/evaluation";

async function main() {
  const personaIds = Object.keys(personas) as Array<keyof typeof personas>;
  const modes = ["concept", "derivation", "experiment", "project"] as const;

  console.log("Quantum Agent — Simulated Student Evaluation\n");
  console.log(`Personas: ${personaIds.length} | Modes: ${modes.length}\n`);

  const results: Array<{
    persona: string;
    mode: string;
    turns: number;
    outcome: string;
    score: number;
    policyPassRate: number;
    citationCoverage: number;
    escalationCount: number;
    completionReason: string;
  }> = [];

  for (const personaId of personaIds.slice(0, 4)) {
    const mode = personas[personaId].modes[0];
    const config: EpisodeConfig = {
      personaId,
      taskMode: mode as EpisodeConfig["taskMode"],
      capability: "quick",
      maxTurns: 5,
      seed: Date.now() % 100,
      offlineMode: true,
    };

    process.stdout.write(`[${personaId}] ${personas[personaId].label} (${mode})... `);

    try {
      const episode = await runEvaluationEpisode(config);
      const report = generateEpisodeReport(episode);

      results.push({
        persona: personaId,
        mode,
        turns: episode.turns.length,
        outcome: episode.currentState,
        score: report.overallScore,
        policyPassRate: report.policyPassRate,
        citationCoverage: report.citationCoverage,
        escalationCount: report.escalationCount,
        completionReason: episode.completionReason ?? "unknown",
      });

      console.log(`${report.overallScore.toFixed(1)}/5 (${episode.turns.length} turns, ${episode.completionReason})`);
    } catch (error) {
      console.log(`ERROR: ${error instanceof Error ? error.message : "unknown"}`);
      results.push({
        persona: personaId,
        mode,
        turns: 0,
        outcome: "error",
        score: 0,
        policyPassRate: 0,
        citationCoverage: 0,
        escalationCount: 0,
        completionReason: `Error: ${error instanceof Error ? error.message : "unknown"}`,
      });
    }
  }

  console.log("\n── Summary ──");
  console.log("Persona | Mode | Turns | Outcome | Score | Policy | Citations | Escalations | Reason");
  console.log("─".repeat(100));

  for (const r of results) {
    console.log(
      `${r.persona.padEnd(35)} | ${r.mode.padEnd(10)} | ${String(r.turns).padStart(5)} | ${r.outcome.padEnd(10)} | ${r.score.toFixed(1)} | ${(r.policyPassRate * 100).toFixed(0)}% | ${(r.citationCoverage * 100).toFixed(0)}% | ${String(r.escalationCount).padStart(2)} | ${r.completionReason.slice(0, 40)}`
    );
  }

  const avgScore = results.reduce((s, r) => s + r.score, 0) / Math.max(results.length, 1);
  console.log(`\nAverage score: ${avgScore.toFixed(1)}/5`);
  console.log("Note: All results are simulated evaluations, not evidence of real learning improvement.");
}

main().catch((err) => {
  console.error("Evaluation script failed:", err);
  process.exit(1);
});