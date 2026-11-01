
# attack_metrics.py

import csv
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AttackMetrics:
    benchmark: str
    method: str = "standard_sat"

    oracle_queries: int = 0
    # Every solver call made during DIP generation, including a strategy's
    # extra checks. The final unsat check is not counted.
    sat_iterations: int = 0

    hamming_distances: list[int] = field(default_factory=list)
    optimal_iterations: int = 0

    # One entry per DIP selected by the partitioning strategy.
    partition_selections: list[dict] = field(default_factory=list)

    dip_generation_time: float = 0.0
    final_dip_check_time: float = 0.0
    oracle_time: float = 0.0
    constraint_update_time: float = 0.0

    attack_start: float = field(
        default_factory=time.perf_counter
    )

    attack_end: float | None = None
    success: bool = False

    def record_dip(self, elapsed):
        self.dip_generation_time += elapsed

    def record_final_dip_check(self, elapsed):
        self.final_dip_check_time = elapsed

    def record_oracle(self, elapsed):
        self.oracle_queries += 1
        self.oracle_time += elapsed

    def record_update(self, elapsed):
        self.constraint_update_time += elapsed

    def record_iteration(self):
        self.sat_iterations += 1

    def record_hamming(self, distance, optimal=False):
        self.hamming_distances.append(distance)

        if optimal:
            self.optimal_iterations += 1

    def record_partition(self, selection):
        self.partition_selections.append(dict(selection))

    @property
    def mean_hamming_distance(self):
        if not self.hamming_distances:
            return None

        return sum(self.hamming_distances) / len(self.hamming_distances)

    def finish(self, success):
        self.attack_end = time.perf_counter()
        self.success = success

    @property
    def total_runtime(self):
        end = self.attack_end

        if end is None:
            end = time.perf_counter()

        return end - self.attack_start

    def save_csv(self, filename):
        filename = Path(filename)
        filename.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        row = {
            "benchmark": self.benchmark,
            "method": self.method,
            "oracle_queries": self.oracle_queries,
            "sat_iterations": self.sat_iterations,
            "mean_hamming_distance": self.mean_hamming_distance,
            "optimal_iterations": self.optimal_iterations,
            "dip_generation_time": self.dip_generation_time,
            "final_dip_check_time": self.final_dip_check_time,
            "oracle_time": self.oracle_time,
            "constraint_update_time": self.constraint_update_time,
            "total_runtime": self.total_runtime,
            "success": self.success,
        }

        write_header = not filename.exists()

        with filename.open("a", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=row.keys()
            )

            if write_header:
                writer.writeheader()

            writer.writerow(row)
