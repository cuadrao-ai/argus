from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "qa" / "assert_pytest_gate.py"
REAL_POSTGRES_FIVE_FAILURES = (
    REPO_ROOT / "tests" / "fixtures" / "pytest_gate" / "real_postgres_five_failures.xml"
)


def _run_gate(junit_xml: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GATE), str(junit_xml)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_xml(tmp_path: Path, xml: str) -> Path:
    report = tmp_path / "junit.xml"
    report.write_text(xml, encoding="utf-8")
    return report


def _write_report(tmp_path: Path, suite_attributes: str, cases: str) -> Path:
    return _write_xml(
        tmp_path,
        f'<testsuites><testsuite name="pytest" {suite_attributes}>'
        f"{cases}</testsuite></testsuites>",
    )


def test_real_report_with_five_failures_fails_and_names_them() -> None:
    result = _run_gate(REAL_POSTGRES_FIVE_FAILURES)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 7 tests, 2 passed, 5 failed, 0 errors, 0 skipped\n"
        "  failed: tests.test_bounded_read_indexes_postgres"
        "::test_forward_indexes_exist_without_changing_rls_or_select_grants\n"
        "  failed: tests.test_guest_workspace_postgres"
        "::test_owner_scoped_rls_separates_guest_and_registered_product_rows\n"
        "  failed: tests.test_guest_workspace_postgres"
        "::test_expired_guest_cannot_read_or_write_product_rows\n"
        "  failed: tests.test_guest_workspace_postgres"
        "::test_profile_and_usage_table_grants_stay_service_owned\n"
        "  failed: tests.test_invite_code_security_postgres"
        "::test_no_client_role_can_ever_read_a_code_digest\n"
    )


def test_report_with_an_error_fails_and_names_it(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="2" failures="0" errors="1" skipped="0"',
        '<testcase classname="tests.test_a" name="test_ok" />'
        '<testcase classname="tests.test_a" name="test_setup_breaks">'
        '<error message="fixture raised" /></testcase>',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 1 passed, 0 failed, 1 errors, 0 skipped\n"
        "  error: tests.test_a::test_setup_breaks\n"
    )


def test_clean_report_passes_with_every_count(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="2" failures="0" errors="0" skipped="0"',
        '<testcase classname="tests.test_a" name="test_one" />'
        '<testcase classname="tests.test_a" name="test_two" />',
    )

    result = _run_gate(report)

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "required pytest gate passed: 2 tests, 2 passed, 0 failed, 0 errors, 0 skipped\n"
    )


def test_report_with_a_skip_fails_and_names_it(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="2" failures="0" errors="0" skipped="1"',
        '<testcase classname="tests.test_a" name="test_one" />'
        '<testcase classname="tests.test_a" name="test_needs_stack">'
        '<skipped message="no local stack" /></testcase>',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 1 passed, 0 failed, 0 errors, 1 skipped\n"
        "  skipped: tests.test_a::test_needs_stack\n"
    )


def test_report_that_collected_nothing_fails(tmp_path: Path) -> None:
    report = _write_report(tmp_path, 'tests="0" failures="0" errors="0" skipped="0"', "")

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == "required pytest gate collected zero tests\n"


def test_failure_element_fails_even_when_the_suite_counts_zero_failures(
    tmp_path: Path,
) -> None:
    report = _write_report(
        tmp_path,
        'tests="2" failures="0" errors="0" skipped="0"',
        '<testcase classname="a" name="t1" />'
        '<testcase classname="a" name="t2"><failure message="x" /></testcase>',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 1 passed, 1 failed, 0 errors, 0 skipped\n"
        "  failed: a::t2\n"
        '  mismatch: suite "pytest" says failures=0, testcase elements show 1\n'
    )


def test_failure_element_fails_when_the_suite_has_no_count_attributes(
    tmp_path: Path,
) -> None:
    report = _write_xml(
        tmp_path,
        '<testsuites><testsuite><testcase classname="a" name="t1" />'
        '<testcase classname="a" name="t2"><failure message="x" /></testcase>'
        "</testsuite></testsuites>",
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 1 passed, 1 failed, 0 errors, 0 skipped\n"
        "  failed: a::t2\n"
    )


def test_suite_claiming_more_tests_than_it_holds_fails(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="7" failures="0" errors="0" skipped="0"',
        '<testcase classname="a" name="t1" />',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 1 tests, 1 passed, 0 failed, 0 errors, 0 skipped\n"
        '  mismatch: suite "pytest" says tests=7, testcase elements show 1\n'
    )


def test_pass_then_teardown_error_counts_one_test_that_did_not_pass(
    tmp_path: Path,
) -> None:
    # Shape pytest 8.4.2 writes: one testcase, tests="2".
    report = _write_report(
        tmp_path,
        'errors="1" failures="0" skipped="0" tests="2"',
        '<testcase classname="test_pass_teardown"'
        ' name="test_pass_then_teardown_error" time="0.000">'
        '<error message="failed on teardown with &quot;RuntimeError&quot;">tb</error>'
        "</testcase>",
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 1 tests, 0 passed, 0 failed, 1 errors, 0 skipped\n"
        "  error: test_pass_teardown::test_pass_then_teardown_error\n"
        '  mismatch: suite "pytest" says tests=2, testcase elements show 1\n'
    )


def test_fail_then_teardown_error_reports_both_entries_and_the_mismatch(
    tmp_path: Path,
) -> None:
    # Shape pytest 8.4.2 writes: two testcases for one test, tests="1".
    case = (
        '<testcase classname="test_fail_teardown"'
        ' name="test_fail_then_teardown_error" time="0.000">{outcome}</testcase>'
    )
    report = _write_report(
        tmp_path,
        'errors="1" failures="1" skipped="0" tests="1"',
        case.format(outcome='<failure message="assert False">tb</failure>')
        + case.format(outcome='<error message="failed on teardown">tb</error>'),
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 0 passed, 1 failed, 1 errors, 0 skipped\n"
        "  failed: test_fail_teardown::test_fail_then_teardown_error\n"
        "  error: test_fail_teardown::test_fail_then_teardown_error\n"
        '  mismatch: suite "pytest" says tests=1, testcase elements show 2\n'
    )


def test_testcase_with_failure_and_error_counts_once(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="1" failures="1" errors="0" skipped="0"',
        '<testcase classname="a" name="t1"><failure /><error /></testcase>',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 1 tests, 0 passed, 1 failed, 0 errors, 0 skipped\n"
        "  failed, error: a::t1\n"
    )


def test_single_testsuite_root_passes_and_fails_from_its_testcases(
    tmp_path: Path,
) -> None:
    clean = _write_xml(
        tmp_path,
        '<testsuite name="pytest" tests="1" failures="0" errors="0" skipped="0">'
        '<testcase classname="a" name="t1" /></testsuite>',
    )
    result = _run_gate(clean)
    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout == (
        "required pytest gate passed: 1 tests, 1 passed, 0 failed, 0 errors, 0 skipped\n"
    )

    failing = _write_xml(
        tmp_path,
        '<testsuite name="pytest" tests="1" failures="1" errors="0" skipped="0">'
        '<testcase classname="a" name="t1"><failure /></testcase></testsuite>',
    )
    result = _run_gate(failing)
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 1 tests, 0 passed, 1 failed, 0 errors, 0 skipped\n"
        "  failed: a::t1\n"
    )


def test_several_suites_are_counted_together(tmp_path: Path) -> None:
    report = _write_xml(
        tmp_path,
        "<testsuites>"
        '<testsuite name="one" tests="2" failures="0" errors="1" skipped="0">'
        '<testcase classname="a" name="t1" />'
        '<testcase classname="a" name="t2"><error /></testcase></testsuite>'
        '<testsuite name="two" tests="1" failures="0" errors="0" skipped="1">'
        '<testcase classname="b" name="t3"><skipped type="pytest.skip" /></testcase>'
        "</testsuite></testsuites>",
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 3 tests, 1 passed, 0 failed, 1 errors, 1 skipped\n"
        "  error: a::t2\n"
        "  skipped: b::t3\n"
    )


def test_nested_suites_with_counts_only_on_the_inner_suite(tmp_path: Path) -> None:
    report = _write_xml(
        tmp_path,
        '<testsuites><testsuite name="outer">'
        '<testsuite name="inner" tests="2" failures="1" errors="0" skipped="0">'
        '<testcase classname="a" name="t1" />'
        '<testcase classname="a" name="t2"><failure /></testcase>'
        "</testsuite></testsuite></testsuites>",
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 2 tests, 1 passed, 1 failed, 0 errors, 0 skipped\n"
        "  failed: a::t2\n"
    )


def test_xfail_is_named_as_xfail_and_still_fails_the_gate(tmp_path: Path) -> None:
    report = _write_report(
        tmp_path,
        'tests="1" failures="0" errors="0" skipped="1"',
        '<testcase classname="a" name="t1">'
        '<skipped type="pytest.xfail" message="known" /></testcase>',
    )

    result = _run_gate(report)

    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == (
        "required pytest gate failed:"
        " 1 tests, 0 passed, 0 failed, 0 errors, 1 skipped\n"
        "  xfail: a::t1\n"
    )
