import { runSimulation, runWidthScan, type SimulationParams } from "../../../lib/simulation";

export async function POST(request: Request) {
  try {
    const body = await request.json() as Partial<SimulationParams> & { widths?: number[] };
    const result = runSimulation(body);
    const widthScan = body.widths?.length
      ? runWidthScan(body.widths, body)
      : null;
    return Response.json({ steps: result.steps, finalProbabilities: result.finalProbabilities, grid: result.grid, potential: result.potential, params: result.params, widthScan });
  } catch (error) {
    return Response.json(
      { error: "Simulation failed", detail: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 },
    );
  }
}
