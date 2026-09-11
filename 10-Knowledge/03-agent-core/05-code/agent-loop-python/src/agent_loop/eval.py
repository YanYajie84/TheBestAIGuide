import argparse
import json
from pathlib import Path

from . import EvidenceModel, default_tools, run_agent


def evaluate(path: str | Path) -> dict:
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = []
    for case in fixture["tasks"]:
        state = run_agent(EvidenceModel(), default_tools(), case["query"])
        actual = [
            doc["id"]
            for item in state.observations
            if item.get("ok")
            for doc in item.get("data", {}).get("documents", [])
        ]
        rows.append(
            {
                "query": case["query"],
                "expected_ids": case["expected_ids"],
                "actual_ids": actual,
                "passed": actual == case["expected_ids"],
            }
        )
    return {
        "synthetic": fixture.get("synthetic", False),
        "passed": sum(r["passed"] for r in rows),
        "total": len(rows),
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the synthetic teaching search task"
    )
    parser.add_argument("fixture")
    args = parser.parse_args()
    print(json.dumps(evaluate(args.fixture), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
