from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from scripts.summarize_pytest_junit import TimingError, summarize

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "summarize_pytest_junit.py"


def test_summarize_aggregates_file_totals_and_slowest_cases(tmp_path: Path):
    junit_xml = tmp_path / "junit.xml"
    junit_xml.write_text(
        """<?xml version=\"1.0\" encoding=\"utf-8\"?>
<testsuites>
  <testsuite name=\"suite-one\">
    <testcase classname=\"tests.test_alpha\" name=\"test_fast\" time=\"0.5\" />
    <testcase classname=\"tests.test_alpha\" name=\"test_slow[param]\" time=\"3.0\" />
  </testsuite>
  <testsuite name=\"suite-two\">
    <testcase classname=\"tests.test_beta\" name=\"test_skipped\" time=\"0.25\">
      <skipped message=\"not run\" />
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )

    result = summarize(junit_xml)

    assert result["case_count"] == 3
    assert result["total_seconds"] == pytest.approx(3.75)
    assert result["files"]["tests/test_alpha.py"] == {
        "seconds": pytest.approx(3.5),
        "cases": 2,
    }
    assert result["slowest"][0] == {
        "node_id": "tests.test_alpha.test_slow[param]",
        "seconds": pytest.approx(3.0),
    }


def test_summarize_groups_test_classes_with_their_module(tmp_path: Path, monkeypatch):
    junit_xml = tmp_path / "junit.xml"
    junit_xml.write_text(
        """<testsuite>
  <testcase classname="tests.test_client_discovery" name="test_module" time="1" />
  <testcase classname="tests.test_client_discovery.TestStableSessions" name="test_class" time="2" />
  <testcase classname="tests.test_client_discovery.TestStableSessions.TestNested" name="test_nested" time="3" />
</testsuite>""",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    result = summarize(junit_xml)

    assert result["files"] == {
        "tests/test_client_discovery.py": {"seconds": 6.0, "cases": 3}
    }
    assert result["case_count"] == 3
    assert result["slowest"][0]["node_id"] == (
        "tests.test_client_discovery.TestStableSessions.TestNested.test_nested"
    )


def test_summarize_raises_timing_error_for_malformed_xml(tmp_path: Path):
    malformed = tmp_path / "malformed.xml"
    malformed.write_text("<testsuites><testsuite>", encoding="utf-8")

    with pytest.raises(TimingError, match="Malformed JUnit XML"):
        summarize(malformed)


def test_summarize_missing_input_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        summarize(tmp_path / "missing.xml")


def test_summarize_preserves_resource_properties(tmp_path: Path):
    junit_xml = tmp_path / "resource.xml"
    junit_xml.write_text(
        """<testsuite>
  <testcase classname="tests.test_resource" name="test_maximum" time="4.5">
    <properties>
      <property name="resource.subprocess_wall_seconds" value="4.25" />
      <property name="resource.memory_metric" value="traced_peak_bytes" />
      <property name="resource.memory_peak" value="1234" />
      <property name="unrelated" value="ignored" />
    </properties>
  </testcase>
</testsuite>""",
        encoding="utf-8",
    )

    result = summarize(junit_xml)

    assert result["resource_evidence"] == [
        {
            "node_id": "tests.test_resource.test_maximum",
            "properties": {
                "resource.memory_metric": "traced_peak_bytes",
                "resource.memory_peak": "1234",
                "resource.subprocess_wall_seconds": "4.25",
            },
        }
    ]


def test_budget_markers_are_strict_and_registered():
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    pytest_config = config["tool"]["pytest"]["ini_options"]
    assert pytest_config["addopts"] == "--strict-markers"
    assert pytest_config["markers"] == [
        "extended: distinct exhaustive or rare compatibility contracts",
        "resource: maximum-size, allocation, or performance probes",
        "mutation: optional test-strength checks that alter implementations",
    ]


def test_only_maximum_response_owns_fleet_transport_resource_marker():
    target = ROOT / "tests" / "test_fleetsharing_transport_resources.py"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(target),
            "--collect-only",
            "-q",
            "-m",
            "resource",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    collected = {line.strip() for line in result.stdout.splitlines() if "::" in line}
    assert collected == {
        "tests/test_fleetsharing_transport_resources.py::"
        "test_maximum_legal_response_actual_reader_and_codec_in_subprocess"
    }


def test_cli_if_present_returns_zero_and_skips_output(tmp_path: Path):
    missing_input = tmp_path / "missing.xml"
    output_json = tmp_path / "timing.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            str(missing_input),
            str(output_json),
            "--if-present",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert not output_json.exists()
