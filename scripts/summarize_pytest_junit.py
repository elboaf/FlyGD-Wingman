from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from functools import cache
from pathlib import Path


class TimingError(Exception):
    """Raised when junit timing input is malformed."""


@cache
def _file_key(classname: str) -> str:
    if classname.startswith("tests."):
        parts = classname.split(".")
        root = Path(__file__).resolve().parents[1]
        # Pytest appends class names; resolve the module without importing tests
        # or depending on the timing command's current working directory.
        for end in range(len(parts), 1, -1):
            candidate = "/".join(parts[:end]) + ".py"
            if (root / candidate).is_file():
                return candidate
        return "/".join(parts) + ".py"
    return "<unknown>"


def _node_id(classname: str, name: str) -> str:
    if classname and name:
        return f"{classname}.{name}"
    if classname:
        return classname
    if name:
        return name
    return "<unknown>"


def _parse_seconds(value: str, node_id: str) -> float:
    try:
        return float(value)
    except ValueError as exc:
        raise TimingError(f"Invalid testcase time for {node_id}") from exc


def summarize(input_path: Path) -> dict[str, object]:
    try:
        root = ET.parse(input_path).getroot()
    except ET.ParseError as exc:
        raise TimingError(f"Malformed JUnit XML: {input_path}") from exc

    files: dict[str, dict[str, float | int]] = {}
    slowest: list[dict[str, str | float]] = []
    total_seconds = 0.0
    case_count = 0

    for testcase in root.iter("testcase"):
        classname = testcase.get("classname", "")
        name = testcase.get("name", "")
        node_id = _node_id(classname, name)
        seconds = _parse_seconds(testcase.get("time", "0"), node_id)
        file_key = _file_key(classname)

        case_count += 1
        total_seconds += seconds

        file_totals = files.setdefault(file_key, {"seconds": 0.0, "cases": 0})
        file_totals["seconds"] = float(file_totals["seconds"]) + seconds
        file_totals["cases"] = int(file_totals["cases"]) + 1

        slowest.append({"node_id": node_id, "seconds": seconds})

    slowest.sort(key=lambda item: (-float(item["seconds"]), str(item["node_id"])))

    return {
        "total_seconds": total_seconds,
        "case_count": case_count,
        "files": files,
        "slowest": slowest[:30],
    }


def _print_summary(summary: dict[str, object]) -> None:
    print(f"Total seconds: {float(summary['total_seconds']):.3f}")
    print("File totals:")
    file_totals = summary["files"]
    assert isinstance(file_totals, dict)
    for file_name in sorted(file_totals):
        row = file_totals[file_name]
        assert isinstance(row, dict)
        seconds = float(row.get("seconds", 0.0))
        cases = int(row.get("cases", 0))
        print(f"  {file_name}: {seconds:.3f}s ({cases} cases)")

    print("Slowest cases:")
    slowest = summary["slowest"]
    assert isinstance(slowest, list)
    for row in slowest:
        assert isinstance(row, dict)
        node_id = str(row.get("node_id", "<unknown>"))
        seconds = float(row.get("seconds", 0.0))
        print(f"  {seconds:.3f}s {node_id}")


def _write_json_atomic(output_path: Path, summary: dict[str, object]) -> None:
    payload = json.dumps(summary, indent=2, sort_keys=True)
    temp_path = output_path.with_name(f".{output_path.name}.tmp")
    temp_path.write_text(f"{payload}\n", encoding="utf-8")
    temp_path.replace(output_path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_path", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--if-present", action="store_true")
    args = parser.parse_args(argv)

    if args.if_present and not args.input_path.exists():
        print(f"Input not present, skipping: {args.input_path}")
        return 0

    try:
        summary = summarize(args.input_path)
    except TimingError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _print_summary(summary)
    _write_json_atomic(args.output_path, summary)
    print(f"Wrote {args.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
