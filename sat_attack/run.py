import argparse
import time
from pathlib import Path
from attack_metrics import AttackMetrics

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

    metrics = AttackMetrics(
    benchmark=Path(args.locked_ckt).stem,
    method=attack_method
)

    attack = sat_attack.SatAttack(args.locked_ckt, args.oracle, method=attack_method)

    start = time.time()
    attack.run()
    end = time.time()

    print("\nIterations: %i" % (attack.iterations))
    print("Elapsed time: %.3fs" % (end - start))

