
# results_store.py

import fcntl
import json
import os
import tempfile
import uuid

from datetime import datetime, timezone
from pathlib import Path


VALID_METHODS = {
    "standard_sat",
    "partitioning",
    "maxsat",
    "maxsat_optimize",
}


def save_attack_result(
    locked_file,
    method,
    metrics,
    status,
    functional_equivalence=None,
    solver_seed=None,
    error=None,
):
    """
    Append an attack result to the benchmark's JSON file.

    All strategies share the same attack_metrics.json.

    Existing results are preserved.
    Linux file locking prevents concurrent writes
    from corrupting the JSON.
    """

    if method not in VALID_METHODS:
        raise ValueError(
            f"Unsupported attack method: {method}"
        )

    locked_file = Path(locked_file).resolve()
    benchmark_dir = locked_file.parent
    benchmark_name = locked_file.stem

    results_file = benchmark_dir / "attack_metrics.json"
    lock_file = benchmark_dir / ".attack_metrics.lock"

    record = {
        "run_id": str(uuid.uuid4()),
        "timestamp_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "status": status,
        "oracle_queries": metrics.oracle_queries,
        "sat_iterations": metrics.sat_iterations,
        "total_runtime_seconds": metrics.total_runtime,
        "dip_generation_seconds": metrics.dip_generation_time,
        "final_dip_check_seconds": metrics.final_dip_check_time,
        "oracle_seconds": metrics.oracle_time,
        "constraint_update_seconds": (
            metrics.constraint_update_time
        ),
        "hamming_distances": metrics.hamming_distances,
        "optimal_iterations": metrics.optimal_iterations,
        "functional_equivalence": functional_equivalence,
        "solver_seed": solver_seed,
        "error": str(error) if error else None,
    }

    # Serialize writes to the same benchmark file.
    with lock_file.open("a+") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)

        if results_file.exists():
            with results_file.open("r") as f:
                data = json.load(f)
        else:
            data = {
                "schema_version": 1,
                "benchmark": benchmark_name,
                "results": {
                    "standard_sat": [],
                    "partitioning": [],
                    "maxsat": [],
                    "maxsat_optimize": [],
                },
            }

        data["results"].setdefault(method, [])
        data["results"][method].append(record)

        # Write atomically to avoid partial JSON files.
        temporary_path = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                dir=benchmark_dir,
                prefix=".attack_metrics_",
                suffix=".tmp",
                delete=False,
            ) as temp:
                temporary_path = Path(temp.name)

                json.dump(data, temp, indent=2)
                temp.write("\n")
                temp.flush()
                os.fsync(temp.fileno())

            os.replace(
                temporary_path,
                results_file,
            )

        finally:
            if (
                temporary_path is not None
                and temporary_path.exists()
            ):
                temporary_path.unlink()

        fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    return results_file
