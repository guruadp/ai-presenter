import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.evals import run_default_regression_suite


def main() -> int:
    report = run_default_regression_suite()
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.release_gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
