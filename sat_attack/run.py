import argparse
import time
from pathlib import Path
from attack_metrics import AttackMetrics
from results_store import save_attack_result

import sat_attack

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perform a SAT attack on a locked circuit.")
    parser.add_argument("locked_ckt", help="The locked benchmark file")
    parser.add_argument("oracle", help="The unlocked benchmark file")
    parser.add_argument("--method", type=str,
        choices=[
            "standard_sat",
            "partitioning",
            "maxsat"
        ],
        default="standard_sat",
        help="DIP selection strategy"
    )

    args = parser.parse_args()
    
    attack_method = args.method
    locked_file = Path(args.locked_ckt)

    metrics = AttackMetrics(
        benchmark=locked_file.stem,
        method=args.method
    )

    attack = sat_attack.SatAttack(args.locked_ckt, args.oracle, method=attack_method)

    start = time.time()
    verified_success = attack.run()
    end = time.time()

    print("\nIterations: %i" % (attack.iterations))
    print("Elapsed time: %.3fs" % (end - start))

    metrics.finish(success=verified_success)

    save_attack_result(
        locked_file=locked_file,
        method=args.method,
        metrics=metrics,
        status="success" if verified_success else "failed",
        functional_equivalence=verified_success,
    )

    print(f"Benchmark: {locked_file.stem}")
    print(f"Method: {args.method}")
    print(f"Runtime: {metrics.total_runtime:.4f} seconds")
    print(f"Oracle queries: {metrics.oracle_queries}")

