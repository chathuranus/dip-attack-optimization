import argparse
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

    parser.add_argument("--dip-timeout-ms", type=int, default=None,
        help="maxsat only: time limit for each extra solver check (default: no limit)"
    )
    parser.add_argument("--max-extra-checks", type=int, default=None,
        help="maxsat only: cap on extra solver checks per DIP (default: no limit)"
    )

    args = parser.parse_args()

    attack_method = args.method
    locked_file = Path(args.locked_ckt)

    strategy_options = {}
    if attack_method == "maxsat":
        strategy_options = {
            "timeout_ms": args.dip_timeout_ms,
            "max_extra_checks": args.max_extra_checks,
        }
    elif args.dip_timeout_ms is not None or args.max_extra_checks is not None:
        parser.error("--dip-timeout-ms and --max-extra-checks only apply to --method maxsat")

    metrics = AttackMetrics(
        benchmark=locked_file.stem,
        method=args.method
    )

    attack = sat_attack.SatAttack(args.locked_ckt, args.oracle, method=attack_method,
                                  metrics=metrics, strategy_options=strategy_options)

    verified_success = attack.run()

    metrics.finish(success=verified_success)

    print("\nDIPs / oracle queries: %i" % (metrics.oracle_queries))
    print("SAT iterations: %i" % (metrics.sat_iterations))
    if metrics.mean_hamming_distance is not None:
        print("Mean Hamming distance: %.2f" % (metrics.mean_hamming_distance))

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

