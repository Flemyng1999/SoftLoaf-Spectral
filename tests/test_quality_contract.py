import pytest
from scripts.run_checks import checked_report


@pytest.mark.parametrize('body',['','<testcase name="missing"><skipped/></testcase>',
    '<testcase name="broken"><failure/></testcase>','<testcase name="crashed"><error/></testcase>'])
def test_success_exit_cannot_hide_zero_tests_skips_or_errors(tmp_path,body):
    path=tmp_path/'report.xml';path.write_text('<testsuite>'+body+'</testsuite>')
    with pytest.raises(RuntimeError):checked_report(path)


def test_completed_tests_are_counted_from_cases_not_untrusted_summary_attributes(tmp_path):
    path=tmp_path/'report.xml';path.write_text('<testsuite tests="999"><testcase name="actual"/></testsuite>')
    assert checked_report(path)=={'tests':1,'skipped':[]}
