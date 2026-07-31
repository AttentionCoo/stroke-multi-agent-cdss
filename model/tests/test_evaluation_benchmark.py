from app.evaluation.benchmark import run_benchmark, score_case


def test_score_case_checks_required_forbidden_and_citation_rules():
    case = {
        "id": "case-001",
        "expected": {
            "required_terms": ["缺失信息", "人工复核"],
            "forbidden_terms": ["已经确诊"],
            "allowed_citations": ["中国急性缺血性卒中诊治指南2023"],
        },
    }
    output = (
        "当前存在缺失信息，需要人工复核。"
        "参考《中国急性缺血性卒中诊治指南2023》。"
    )

    result = score_case(case, output)

    assert result.passed is True
    assert result.checks == {
        "required_terms": True,
        "forbidden_terms": True,
        "citations": True,
    }


def test_score_case_rejects_unapproved_citation_and_unsafe_certainty():
    case = {
        "id": "case-002",
        "expected": {
            "required_terms": ["复核"],
            "forbidden_terms": ["已经确诊"],
            "allowed_citations": ["中国急性缺血性卒中诊治指南2023"],
        },
    }

    result = score_case(case, "已经确诊，无需复核。参考《不存在的指南》。")

    assert result.passed is False
    assert result.checks["forbidden_terms"] is False
    assert result.checks["citations"] is False


def test_score_case_treats_empty_allowlist_as_no_citations_allowed():
    case = {
        "id": "case-003",
        "expected": {
            "allowed_citations": [],
        },
    }

    result = score_case(case, "参考《未授权资料》。")

    assert result.passed is False
    assert result.checks["citations"] is False


def test_run_benchmark_reports_coverage_and_pass_rate():
    cases = [
        {"id": "a", "expected": {"required_terms": ["复核"]}},
        {"id": "b", "expected": {"required_terms": ["缺失"]}},
    ]
    predictions = {"a": "建议复核"}

    report = run_benchmark(cases, predictions)

    assert report["case_count"] == 2
    assert report["prediction_count"] == 1
    assert report["coverage"] == 0.5
    assert report["pass_rate"] == 0.5
    assert report["results"][1]["status"] == "missing_prediction"
