"""Synthetic local latency benchmark; no provider or classroom claims."""

import json
import platform
import statistics
import time

from quantum_agent.science.models import RectangularBarrierRequest
from quantum_agent.science.toolbox import ScientificToolbox, _cached_line_spec_json


def main() -> None:
    request = RectangularBarrierRequest(
        energy_eV=5,
        barrier_height_eV=10,
        barrier_width_m=1e-10,
        particle_mass_kg=9.1093837015e-31,
    )
    toolbox = ScientificToolbox()
    _cached_line_spec_json.cache_clear()
    start = time.perf_counter()
    toolbox.verify(request)
    cold_ms = (time.perf_counter() - start) * 1000
    samples = []
    for _ in range(15):
        start = time.perf_counter()
        result = toolbox.verify(request)
        assert result.status.value == "pass"
        samples.append((time.perf_counter() - start) * 1000)
    print(
        json.dumps(
            {
                "kind": "automated_synthetic_benchmark",
                "platform": platform.platform(),
                "python": platform.python_version(),
                "samples": 15,
                "cold_ms": cold_ms,
                "warm_ms": samples,
                "warm_median_ms": statistics.median(samples),
                "cache": str(_cached_line_spec_json.cache_info()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
