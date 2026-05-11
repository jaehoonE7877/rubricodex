from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from rubricodex.artifacts import (
    APP_CARDS_TYPE,
    APP_COLLECTION_TYPE,
    APP_SESSION_TYPE,
    ArtifactError,
    GOAL_HEADINGS,
    BRIEF_TYPE,
    EVIDENCE_TYPE,
    MATRIX_TYPE,
    PROBE_PLAN_TYPE,
    PROBE_RESULT_TYPE,
    RUN_MANIFEST_TYPE,
    ORCHESTRATOR_TYPE,
    SCHEMA_VERSION,
    SCORECARD_TYPE,
    app_cards_path,
    app_collection_path,
    app_session_path,
    assess_request_readiness,
    classify_mode,
    collect_app_artifacts,
    compile_goal,
    compute_scorecard,
    draft_harness,
    goal_lock_path,
    import_app_session,
    init_project,
    intent_path,
    lint_goal_file,
    lint_goal_text,
    matrix_path,
    orchestrate_run,
    orchestrate_status,
    orchestrator_path,
    plan_probes,
    probe_plan_path,
    probe_prompt_path,
    probe_result_path,
    read_json,
    run_local,
    run_probes,
    run_dir,
    run_manifest_path,
    validate_brief,
    validate_evidence,
    validate_app_cards,
    validate_app_collection,
    validate_app_session,
    validate_matrix,
    validate_orchestrator,
    validate_probe_plan,
    validate_probe_result,
    validate_run_manifest,
    verify_matrix_lock,
    validate_scorecard,
    write_json,
    write_report,
)
from rubricodex.cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[1]


def sample_brief(mode: str = "standard") -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": BRIEF_TYPE,
        "rubricodex_version": "0.1.0",
        "created_at": "2026-05-11T00:00:00Z",
        "mode": mode,
        "task_kind": "source-code-endpoint",
        "blocks": {
            "purpose": "Add a POST /api/widgets endpoint.",
            "desired_outcome": "Valid widget input returns a 201 response with a persisted widget object.",
            "deliverable_shape": "Small Express endpoint plus node:test coverage.",
            "reference_context": ["examples/source-code-endpoint/src/server.js", "examples/source-code-endpoint/test/server.test.js"],
            "scope_in": ["POST /api/widgets", "name validation", "happy path and invalid input tests"],
            "scope_out": ["database persistence", "auth", "frontend UI"],
            "working_rules": ["Keep implementation in memory.", "Do not add runtime dependencies."],
            "evaluation_basis": ["Endpoint contract", "Input validation", "Test evidence"],
            "done_when": ["All hard gates pass.", "Summarized evidence is available."],
        },
    }


def criterion(index: int, hard_gate: bool = False) -> dict:
    return {
        "id": f"C-{index:02d}",
        "name": {
            1: "Endpoint contract",
            2: "Input validation",
            3: "Data integrity",
            4: "Test coverage",
            5: "Maintainability",
            6: "Report quality",
            7: "Retune quality",
            8: "Policy compliance",
        }.get(index, f"Criterion {index}"),
        "claim": f"Criterion {index} is satisfied.",
        "check_question": f"Does criterion {index} have summarized evidence?",
        "evidence_required": [f"Evidence summary for C-{index:02d}"],
        "hard_gate": hard_gate,
        "levels": {
            "pass": "Evidence proves the criterion.",
            "partial": "Evidence is present but incomplete.",
            "fail": "Evidence disproves the criterion.",
        },
        "retune_hint": f"Fix C-{index:02d} without changing passed criteria.",
    }


def sample_matrix(mode: str = "standard", count: int = 5, hard_ids: set[int] | None = None) -> dict:
    hard_ids = hard_ids if hard_ids is not None else {1, 2}
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": MATRIX_TYPE,
        "rubricodex_version": "0.1.0",
        "created_at": "2026-05-11T00:00:00Z",
        "mode": mode,
        "method": "gqe-r-lite",
        "criteria": [criterion(index, hard_gate=index in hard_ids) for index in range(1, count + 1)],
    }


def sample_evidence(
    matrix: dict,
    statuses: dict[str, str] | None = None,
    scope_out_drift: str | None = None,
    run_id: str = "example-v0.1",
) -> dict:
    statuses = statuses or {}
    items = []
    for item in matrix["criteria"]:
        status = statuses.get(item["id"], "pass")
        if status == "omit":
            continue
        evidence_item = {
            "id": f"E-{item['id']}",
            "criterion_id": item["id"],
            "kind": "test",
            "summary": f"{item['id']} has summarized verification evidence.",
            "artifact_refs": ["python -m unittest"],
            "status": status,
            "confidence": 0.9,
        }
        if scope_out_drift == item["id"]:
            evidence_item["scope_out_drift"] = True
        items.append(evidence_item)
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": EVIDENCE_TYPE,
        "rubricodex_version": "0.1.0",
        "created_at": "2026-05-11T00:00:00Z",
        "mode": matrix["mode"],
        "run_id": run_id,
        "executor": "codex-cli-goal",
        "raw_output_stored": False,
        "evidence_items": items,
    }


def sample_app_session() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": APP_SESSION_TYPE,
        "rubricodex_version": "0.1.0",
        "created_at": "2026-05-11T00:00:00Z",
        "session_id": "example-session",
        "run_id": "example-v0.1",
        "entrypoint": "@Rubricodex",
        "mention": "@Rubricodex 우리 서비스에 POST /api/widgets endpoint를 추가해줘.",
        "mode": "standard",
        "user_goal_summary": "Add a small POST /api/widgets endpoint with basic tests.",
        "selected_context_refs": ["examples/source-code-endpoint"],
        "approved_decisions_ref": ".rubricodex/app/sessions/example-session/decisions.json",
        "raw_transcript_stored": False,
    }


def sample_app_cards() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": APP_CARDS_TYPE,
        "rubricodex_version": "0.1.0",
        "created_at": "2026-05-11T00:00:00Z",
        "session_id": "example-session",
        "run_id": "example-v0.1",
        "raw_transcript_stored": False,
        "cards": [
            {
                "card_type": "harness_plan",
                "title": "Harness Plan",
                "summary": "Bounded source-code endpoint task.",
                "artifact_refs": [".rubricodex/intent/brief.json"],
            },
            {
                "card_type": "matrix",
                "title": "Matrix",
                "summary": "Five criteria with two hard gates.",
                "artifact_refs": [".rubricodex/matrix/evaluation-matrix.json"],
            },
            {
                "card_type": "report",
                "title": "Report",
                "summary": "Current report is available for review.",
                "artifact_refs": [".rubricodex/runs/example-v0.1/report.md"],
            },
            {
                "card_type": "retune",
                "title": "Retune",
                "summary": "Retune card targets non-pass criteria only.",
                "artifact_refs": [".rubricodex/runs/example-v0.1/retune_goal.md"],
            },
        ],
    }


class RubricodexContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def write_default_contract(self, matrix: dict | None = None, evidence: dict | None = None) -> dict:
        write_json(intent_path(self.root), sample_brief())
        matrix = matrix or sample_matrix()
        write_json(matrix_path(self.root), matrix)
        if evidence is not None:
            write_json(run_dir(self.root, "example-v0.1") / "evidence.json", evidence)
        return matrix

    def test_init_creates_minimal_tree(self) -> None:
        init_project(self.root)
        base = self.root / ".rubricodex"
        for child in ("intent", "matrix", "taskpacks", "runs"):
            self.assertTrue((base / child).is_dir())

    def test_init_writes_config_and_plugin_skill(self) -> None:
        init_project(self.root)
        self.assertTrue((self.root / ".rubricodex" / "config.json").is_file())
        self.assertTrue((REPO_ROOT / "plugins/rubricodex/.codex-plugin/plugin.json").is_file())
        self.assertTrue((REPO_ROOT / "plugins/rubricodex/skills/rubricodex/SKILL.md").is_file())

    def test_cli_accepts_root_after_subcommand(self) -> None:
        with redirect_stdout(StringIO()):
            exit_code = cli_main(["init", "--root", str(self.root)])
        self.assertEqual(exit_code, 0)
        self.assertTrue((self.root / ".rubricodex" / "config.json").is_file())

    def test_plugin_has_only_manifest_and_skill_surface(self) -> None:
        plugin_root = REPO_ROOT / "plugins/rubricodex"
        self.assertTrue((plugin_root / ".codex-plugin/plugin.json").is_file())
        self.assertTrue((plugin_root / "skills/rubricodex/SKILL.md").is_file())
        self.assertFalse((plugin_root / ".mcp.json").exists())
        self.assertFalse((plugin_root / ".app.json").exists())
        self.assertFalse((plugin_root / "hooks.json").exists())
        self.assertFalse((plugin_root / "hooks").exists())

    def test_brief_valid_passes(self) -> None:
        self.assertEqual(validate_brief(sample_brief()), [])

    def test_brief_missing_any_of_9_blocks_fails(self) -> None:
        for block in sample_brief()["blocks"].keys():
            with self.subTest(block=block):
                brief = sample_brief()
                del brief["blocks"][block]
                self.assertTrue(validate_brief(brief))

    def test_brief_empty_scope_in_fails_standard(self) -> None:
        brief = sample_brief()
        brief["blocks"]["scope_in"] = []
        self.assertTrue(validate_brief(brief, "standard"))

    def test_brief_raw_transcript_key_fails(self) -> None:
        brief = sample_brief()
        brief["raw_transcript"] = "do not store this"
        self.assertTrue(validate_brief(brief))

    def test_matrix_valid_passes(self) -> None:
        self.assertEqual(validate_matrix(sample_matrix()), [])

    def test_matrix_duplicate_criterion_id_fails(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][1]["id"] = matrix["criteria"][0]["id"]
        self.assertTrue(validate_matrix(matrix))

    def test_matrix_missing_evidence_required_fails(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][0]["evidence_required"] = []
        self.assertTrue(validate_matrix(matrix))

    def test_matrix_missing_hard_gate_standard_fails(self) -> None:
        matrix = sample_matrix(hard_ids=set())
        self.assertTrue(validate_matrix(matrix, "standard"))

    def test_matrix_criteria_count_by_mode(self) -> None:
        self.assertEqual(validate_matrix(sample_matrix(mode="micro", count=1, hard_ids={1}), "micro"), [])
        self.assertTrue(validate_matrix(sample_matrix(mode="micro", count=3, hard_ids={1}), "micro"))
        self.assertEqual(validate_matrix(sample_matrix(mode="strict", count=6, hard_ids={1}), "strict"), [])
        self.assertTrue(validate_matrix(sample_matrix(mode="strict", count=5, hard_ids={1}), "strict"))

    def test_matrix_rejects_unknown_declared_mode(self) -> None:
        matrix = sample_matrix()
        matrix["mode"] = "nonsense"

        issues = validate_matrix(matrix)

        self.assertIn("$.mode", {issue.path for issue in issues})

    def test_matrix_rejects_non_string_declared_mode(self) -> None:
        matrix = sample_matrix()
        matrix["mode"] = ["standard"]

        issues = validate_matrix(matrix, "standard")

        self.assertIn("$.mode", {issue.path for issue in issues})

    def test_plan_draft_auto_classifies_and_writes_taskpack(self) -> None:
        result = draft_harness(
            self.root,
            "draft-strict",
            "결제 권한 migration 위험을 고려해서 API endpoint를 수정하고 테스트로 검증해줘.",
        )

        brief = read_json(intent_path(self.root))
        matrix = read_json(matrix_path(self.root))

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["mode"], "strict")
        self.assertEqual(brief["request_readiness"]["max_score"], 6)
        self.assertEqual(validate_brief(brief, "strict"), [])
        self.assertEqual(validate_matrix(matrix, "strict"), [])
        self.assertTrue((self.root / ".rubricodex/taskpacks/draft-strict/goal.md").is_file())
        self.assertEqual(lint_goal_file(self.root, "draft-strict", mode="strict")["status"], "pass")

    def test_plan_draft_rejects_empty_goal(self) -> None:
        with self.assertRaises(ArtifactError) as context:
            draft_harness(self.root, "empty", " ")

        self.assertIn("goal must be non-empty", str(context.exception))

    def test_plan_draft_rejects_unsafe_run_id(self) -> None:
        for run_id in ("../escape", ""):
            with self.subTest(run_id=run_id):
                with self.assertRaises(ArtifactError) as context:
                    draft_harness(self.root, run_id, "관리자 dashboard page를 만들고 test evidence를 남겨줘.")

                self.assertIn("$.run_id", {issue.path for issue in context.exception.issues})
        self.assertFalse((self.root / ".rubricodex" / "escape" / "goal.md").exists())
        self.assertFalse((self.root / ".rubricodex" / "taskpacks" / "goal.md").exists())

    def test_plan_draft_rejects_existing_locked_contract(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")

        with self.assertRaises(ArtifactError) as context:
            draft_harness(self.root, "example-v1.0", "관리자 dashboard page를 만들고 test evidence를 남겨줘.")

        self.assertIn("$.run_id", {issue.path for issue in context.exception.issues})
        self.assertIn("example-v0.1", str(context.exception))
        self.assertEqual(verify_matrix_lock(self.root, "example-v0.1")["status"], "pass")
        self.assertFalse((self.root / ".rubricodex" / "taskpacks" / "example-v1.0").exists())

    def test_request_readiness_records_assumptions_without_raw_fields(self) -> None:
        readiness = assess_request_readiness("대시보드를 만들어줘", "standard")

        self.assertIn(readiness["status"], {"needs_assumption", "needs_clarification"})
        self.assertTrue(readiness["assumptions"])
        self.assertNotIn("raw_transcript", str(readiness))

    def test_request_readiness_does_not_treat_sentence_period_as_context(self) -> None:
        readiness = assess_request_readiness("Add an API.", "standard")

        checks = {check["id"]: check for check in readiness["checks"]}
        self.assertFalse(checks["context"]["passed"])

    def test_request_readiness_accepts_file_or_path_context(self) -> None:
        for goal in ("Update README.md evidence.", "Fix src/server.js endpoint."):
            with self.subTest(goal=goal):
                readiness = assess_request_readiness(goal, "standard")
                checks = {check["id"]: check for check in readiness["checks"]}

                self.assertTrue(checks["context"]["passed"])

    def test_mode_classifier_uses_lowest_sufficient_mode(self) -> None:
        self.assertEqual(classify_mode("오타 문구 수정", "auto"), "micro")
        self.assertEqual(classify_mode("작은 버그 수정", "auto"), "quick")
        self.assertEqual(classify_mode("권한 migration을 안전하게 수정", "auto"), "strict")
        self.assertEqual(classify_mode("현재 diff review", "auto"), "audit")
        self.assertEqual(classify_mode("Implement authentication middleware with tests", "auto"), "strict")
        self.assertEqual(classify_mode("Fix user permissions bug", "auto"), "strict")
        self.assertEqual(classify_mode("Implement payments dashboard", "auto"), "strict")
        self.assertEqual(classify_mode("review and fix auth bug", "auto"), "strict")
        self.assertEqual(classify_mode("Review and improve authentication middleware with tests", "auto"), "strict")
        self.assertEqual(classify_mode("Review and improve dashboard UI with tests", "auto"), "standard")
        self.assertEqual(classify_mode("review and delete old auth route", "auto"), "strict")
        self.assertEqual(classify_mode("review and remove old route", "auto"), "strict")
        self.assertEqual(classify_mode("보안 삭제 리뷰", "auto"), "strict")
        self.assertEqual(classify_mode("리뷰 반영해서 작은 버그 수정", "auto"), "quick")
        self.assertEqual(classify_mode("관리자 대시보드를 만들어줘", "auto"), "standard")

    def test_mode_classifier_uses_word_boundaries_for_english_keywords(self) -> None:
        self.assertEqual(classify_mode("Create copyright page", "auto"), "standard")
        self.assertEqual(classify_mode("Add prefix handling", "auto"), "standard")
        self.assertEqual(classify_mode("Preview page", "auto"), "standard")

    def test_audit_draft_includes_audit_specific_criterion(self) -> None:
        draft_harness(self.root, "audit-draft", "현재 diff review", mode="audit")

        matrix = read_json(matrix_path(self.root))

        self.assertIn("Audit objectivity", {criterion["name"] for criterion in matrix["criteria"]})

    def test_v10_all_modes_draft_and_orchestrate(self) -> None:
        mode_goals = {
            "micro": "오타 문구 수정",
            "quick": "작은 버그 수정",
            "standard": "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            "strict": "결제 권한 migration 위험을 고려해서 API endpoint를 수정하고 test evidence를 남겨줘.",
            "audit": "현재 diff를 review하고 findings report evidence를 남겨줘.",
        }
        for mode, goal in mode_goals.items():
            with self.subTest(mode=mode):
                root = self.root / mode
                run_id = f"{mode}-fixture"
                draft = draft_harness(root, run_id, goal, mode=mode)
                matrix = read_json(matrix_path(root))
                write_json(run_dir(root, run_id) / "evidence.json", sample_evidence(matrix, run_id=run_id))
                result = orchestrate_run(root, run_id, mode=mode, parallel=1)
                status = orchestrate_status(root, run_id)

                self.assertEqual(draft["status"], "pass")
                self.assertEqual(result["status"], "pass")
                self.assertEqual(status["status"], "complete")
                self.assertEqual(status["decision"], "pass")

    def test_cli_plan_draft_command(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "plan",
                    "draft",
                    "--run-id",
                    "cli-draft",
                    "--mode",
                    "quick",
                    "--goal",
                    "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"mode": "quick"', stdout.getvalue())
        self.assertIn('"status": "pass"', stdout.getvalue())
        self.assertTrue((self.root / ".rubricodex/taskpacks/cli-draft/goal.md").is_file())

    def test_cli_plan_draft_honors_global_mode(self) -> None:
        old_cwd = Path.cwd()
        try:
            os.chdir(self.root)
            with redirect_stdout(StringIO()) as stdout:
                exit_code = cli_main(
                    [
                        "--root",
                        "plan",
                        "--mode",
                        "strict",
                        "plan",
                        "draft",
                        "--run-id",
                        "global-mode-draft",
                        "--goal",
                        "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                    ]
                )
        finally:
            os.chdir(old_cwd)

        self.assertEqual(exit_code, 0)
        self.assertIn('"mode": "strict"', stdout.getvalue())
        matrix = read_json(matrix_path(self.root / "plan"))
        self.assertEqual(len(matrix["criteria"]), 6)

    def test_cli_plan_draft_explicit_auto_overrides_global_mode(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "--mode",
                    "strict",
                    "plan",
                    "draft",
                    "--run-id",
                    "explicit-auto-draft",
                    "--mode",
                    "auto",
                    "--goal",
                    "작은 버그 수정",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"mode": "quick"', stdout.getvalue())
        matrix = read_json(matrix_path(self.root))
        self.assertEqual(len(matrix["criteria"]), 3)

    def test_cli_followup_commands_infer_drafted_mode(self) -> None:
        with redirect_stdout(StringIO()):
            draft_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "plan",
                    "draft",
                    "--run-id",
                    "quick-draft",
                    "--goal",
                    "작은 버그 수정",
                ]
            )
        matrix = read_json(matrix_path(self.root))
        write_json(run_dir(self.root, "quick-draft") / "evidence.json", sample_evidence(matrix, run_id="quick-draft"))

        with redirect_stdout(StringIO()) as stdout:
            run_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "orchestrate",
                    "run",
                    "--run-id",
                    "quick-draft",
                    "--parallel",
                    "1",
                ]
            )

        self.assertEqual(draft_exit, 0)
        self.assertEqual(run_exit, 0)
        self.assertIn('"status": "pass"', stdout.getvalue())

    def test_cli_followup_commands_infer_explicit_matrix_file_mode(self) -> None:
        write_json(intent_path(self.root), sample_brief(mode="quick"))
        write_json(matrix_path(self.root), sample_matrix(mode="quick", count=3, hard_ids={1}))
        standard_brief = self.root / "standard-brief.json"
        standard_matrix = self.root / "standard-matrix.json"
        write_json(standard_brief, sample_brief(mode="standard"))
        write_json(standard_matrix, sample_matrix(mode="standard", count=5, hard_ids={1, 2}))

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "goal",
                    "compile",
                    "--run-id",
                    "standard-alt",
                    "--brief",
                    str(standard_brief),
                    "--matrix",
                    str(standard_matrix),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "pass"', stdout.getvalue())

    def test_cli_matrix_validate_rejects_unknown_artifact_mode(self) -> None:
        matrix = sample_matrix()
        matrix["mode"] = "nonsense"
        matrix_file = self.root / "matrix.json"
        write_json(matrix_file, matrix)

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(["matrix", "validate", "--file", str(matrix_file)])

        self.assertEqual(exit_code, 1)
        self.assertIn("$.mode", stdout.getvalue())

    def test_cli_matrix_validate_rejects_non_string_artifact_mode(self) -> None:
        matrix = sample_matrix()
        matrix["mode"] = ["standard"]
        matrix_file = self.root / "matrix.json"
        write_json(matrix_file, matrix)

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(["matrix", "validate", "--mode", "standard", "--file", str(matrix_file)])

        self.assertEqual(exit_code, 1)
        self.assertIn("$.mode", stdout.getvalue())
        self.assertNotIn("Traceback", stdout.getvalue())

    def test_goal_compile_writes_adapter_input_goal_and_lock(self) -> None:
        self.write_default_contract()
        paths = compile_goal(self.root, "example-v0.1")
        for path in paths.values():
            self.assertTrue(path.is_file())
        self.assertIn("brief_sha256", read_json(paths["lock"]))
        self.assertIn("guidance_sha256", read_json(paths["lock"]))
        self.assertIn("locked_criteria", read_json(paths["lock"]))

    def test_goal_compile_does_not_use_target_json(self) -> None:
        self.write_default_contract()
        write_json(self.root / ".rubricodex" / "target.json", {"invalid": True})
        paths = compile_goal(self.root, "example-v0.1")
        adapter = read_json(paths["adapter_input"])
        self.assertNotIn("target.json", str(adapter))

    def test_matrix_lock_passes_when_unchanged(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["issues"], [])

    def test_matrix_lock_detects_deleted_criterion(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        matrix["criteria"] = matrix["criteria"][1:]
        write_json(matrix_path(self.root), matrix)
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")
        self.assertIn("criterion was removed", str(result["issues"]))

    def test_matrix_lock_detects_hard_gate_weakening(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        matrix["criteria"][0]["hard_gate"] = False
        write_json(matrix_path(self.root), matrix)
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")
        self.assertIn("hard gate was weakened", str(result["issues"]))

    def test_matrix_lock_detects_evidence_required_removal(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][0]["evidence_required"].append("Second required evidence")
        self.write_default_contract(matrix=matrix)
        compile_goal(self.root, "example-v0.1")
        matrix["criteria"][0]["evidence_required"] = matrix["criteria"][0]["evidence_required"][:1]
        write_json(matrix_path(self.root), matrix)
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")
        self.assertIn("evidence_required was removed", str(result["issues"]))

    def test_matrix_lock_detects_scope_drift_standard(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        brief = sample_brief()
        brief["blocks"]["scope_in"].append("pagination")
        write_json(intent_path(self.root), brief)
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")
        self.assertIn("scope changed", str(result["issues"]))

    def test_matrix_lock_warns_for_scope_drift_micro(self) -> None:
        self.write_default_contract(matrix=sample_matrix(mode="micro", count=1, hard_ids={1}))
        write_json(intent_path(self.root), sample_brief(mode="micro"))
        compile_goal(self.root, "example-v0.1", mode="micro")
        brief = sample_brief(mode="micro")
        brief["blocks"]["scope_in"].append("copy tweak")
        write_json(intent_path(self.root), brief)
        result = verify_matrix_lock(self.root, "example-v0.1", mode="micro")
        self.assertEqual(result["status"], "pass")
        self.assertIn("warning", str(result["issues"]))

    def test_matrix_lock_requires_criterion_in_evaluation_section(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        matrix["criteria"].append(criterion(6))
        write_json(matrix_path(self.root), matrix)
        goal = self.root / ".rubricodex" / "taskpacks" / "example-v0.1" / "goal.md"
        goal.write_text(
            goal.read_text(encoding="utf-8") + "\nC-06 is mentioned outside the evaluation section.\n",
            encoding="utf-8",
        )
        result = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")
        self.assertIn("goal.md is missing criterion C-06", str(result["issues"]))

    def test_matrix_lock_approved_safe_revision_writes_new_lock(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        old_lock = read_json(goal_lock_path(self.root, "example-v0.1"))
        matrix["criteria"].append(criterion(6))
        write_json(matrix_path(self.root), matrix)

        failed = verify_matrix_lock(self.root, "example-v0.1")
        self.assertEqual(failed["status"], "fail")

        goal = self.root / ".rubricodex" / "taskpacks" / "example-v0.1" / "goal.md"
        goal_text = goal.read_text(encoding="utf-8")
        goal.write_text(
            goal_text.replace(
                "\n## Evidence\n",
                "\n- C-06 (supporting): Does criterion 6 have summarized evidence? Evidence: Evidence summary for C-06\n\n## Evidence\n",
            ),
            encoding="utf-8",
        )
        approved = verify_matrix_lock(self.root, "example-v0.1", revision_reason="Add report quality criterion.")
        self.assertEqual(approved["status"], "pass")
        self.assertTrue(approved["revision_approved"])
        new_lock = read_json(goal_lock_path(self.root, "example-v0.1"))
        self.assertNotEqual(old_lock["matrix_sha256"], new_lock["matrix_sha256"])
        self.assertEqual(new_lock["revision"]["reason"], "Add report quality criterion.")

    def test_goal_md_contains_required_sections(self) -> None:
        self.write_default_contract()
        paths = compile_goal(self.root, "example-v0.1")
        text = paths["goal"].read_text(encoding="utf-8")
        for heading in GOAL_HEADINGS:
            self.assertIn(f"## {heading}", text)

    def test_prompt_lint_missing_include_or_exclude_fails(self) -> None:
        self.write_default_contract()
        paths = compile_goal(self.root, "example-v0.1")
        text = paths["goal"].read_text(encoding="utf-8").replace("## Include\n", "## Missing include\n")
        paths["goal"].write_text(text, encoding="utf-8")
        result = lint_goal_file(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")

    def test_prompt_lint_missing_evaluation_fails(self) -> None:
        self.write_default_contract()
        paths = compile_goal(self.root, "example-v0.1")
        text = paths["goal"].read_text(encoding="utf-8").replace("## Evaluation\n", "## Missing evaluation\n")
        paths["goal"].write_text(text, encoding="utf-8")
        result = lint_goal_file(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")

    def test_prompt_lint_missing_completion_rule_fails_standard(self) -> None:
        self.write_default_contract()
        paths = compile_goal(self.root, "example-v0.1")
        text = paths["goal"].read_text(encoding="utf-8").replace("## Completion rule\n", "## Missing completion\n")
        paths["goal"].write_text(text, encoding="utf-8")
        result = lint_goal_file(self.root, "example-v0.1")
        self.assertEqual(result["status"], "fail")

    def test_evidence_valid_passes(self) -> None:
        matrix = sample_matrix()
        self.assertEqual(validate_evidence(sample_evidence(matrix), matrix), [])

    def test_evidence_raw_output_stored_true_fails(self) -> None:
        matrix = sample_matrix()
        evidence = sample_evidence(matrix)
        evidence["raw_output_stored"] = True
        self.assertTrue(validate_evidence(evidence, matrix))

    def test_evidence_unknown_criterion_id_fails(self) -> None:
        matrix = sample_matrix()
        evidence = sample_evidence(matrix)
        evidence["evidence_items"][0]["criterion_id"] = "C-999"
        self.assertTrue(validate_evidence(evidence, matrix))

    def test_run_local_requires_prompt_lint_pass(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")

        with self.assertRaises(ArtifactError) as context:
            run_local(self.root, "example-v0.1")

        self.assertIn("prompt-lint.json", str(context.exception))

    def test_run_local_dry_run_writes_manifest_without_raw_output(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        result = run_local(
            self.root,
            "example-v0.1",
            result_summary="Prepared Codex CLI handoff without execution.",
            verification_commands=["python3 -m unittest discover -s tests"],
            changed_files=["rubricodex/artifacts.py", "rubricodex/cli.py"],
        )

        manifest = read_json(run_manifest_path(self.root, "example-v0.1"))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(manifest["artifact_type"], RUN_MANIFEST_TYPE)
        self.assertEqual(manifest["execution_mode"], "dry_run")
        self.assertFalse(manifest["raw_output_stored"])
        self.assertEqual(validate_run_manifest(manifest), [])
        self.assertNotIn("stdout", str(manifest).lower())
        self.assertNotIn("stderr", str(manifest).lower())

    def test_run_local_creates_missing_evidence_when_absent(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        run_local(self.root, "example-v0.1")

        evidence = read_json(run_dir(self.root, "example-v0.1") / "evidence.json")
        self.assertEqual(validate_evidence(evidence, matrix), [])
        self.assertEqual(
            {item["status"] for item in evidence["evidence_items"]},
            {"missing_evidence"},
        )
        self.assertIn(
            ".rubricodex/runs/example-v0.1/run-manifest.json",
            evidence["runner_manifest_path"],
        )

    def test_run_local_execute_reports_nonzero_exit_without_raw_output(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        result = run_local(self.root, "example-v0.1", execute=True, codex_bin="false")

        manifest = read_json(run_manifest_path(self.root, "example-v0.1"))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(manifest["command_results"][0]["exit_code"], 1)
        self.assertEqual(validate_run_manifest(manifest), [])
        self.assertNotIn("stdout", str(manifest).lower())
        self.assertNotIn("stderr", str(manifest).lower())

    def test_cli_run_local_accepts_summary_and_writes_manifest(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "run",
                    "local",
                    "--run-id",
                    "example-v0.1",
                    "--summary",
                    "Dry-run handoff verified.",
                    "--verification-command",
                    "python3 -m unittest discover -s tests",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn("run-manifest.json", output)
        manifest = read_json(run_manifest_path(self.root, "example-v0.1"))
        self.assertEqual(manifest["result_summary"], "Dry-run handoff verified.")

    def test_run_manifest_rejects_raw_output_fields(self) -> None:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": RUN_MANIFEST_TYPE,
            "rubricodex_version": "0.1.0",
            "created_at": "2026-05-11T00:00:00Z",
            "mode": "standard",
            "run_id": "example-v0.1",
            "executor": "codex-cli-local",
            "execution_mode": "dry_run",
            "raw_output_stored": False,
            "result_summary": "Prepared handoff.",
            "command_results": [
                {"command": "codex exec", "exit_code": None, "stdout": "raw"},
            ],
            "changed_files": [],
            "verification_commands": [],
        }
        self.assertTrue(validate_run_manifest(manifest))

    def test_app_session_and_cards_validate_without_raw_transcript(self) -> None:
        session = sample_app_session()
        cards = sample_app_cards()
        self.assertEqual(validate_app_session(session), [])
        self.assertEqual(validate_app_cards(cards, session), [])

        session["raw_transcript_stored"] = True
        cards["raw_transcript"] = "do not store this"
        self.assertTrue(validate_app_session(session))
        self.assertTrue(validate_app_cards(cards))

    def test_app_session_and_cards_reject_path_segment_ids(self) -> None:
        for unsafe in ("nested/session", "../session", "/tmp/session", "nested\\session"):
            session = sample_app_session()
            cards = sample_app_cards()
            session["session_id"] = unsafe
            session["run_id"] = unsafe
            cards["session_id"] = unsafe
            cards["run_id"] = unsafe

            session_issues = validate_app_session(session)
            cards_issues = validate_app_cards(cards)

            self.assertIn("$.session_id", {issue.path for issue in session_issues})
            self.assertIn("$.run_id", {issue.path for issue in session_issues})
            self.assertIn("$.session_id", {issue.path for issue in cards_issues})
            self.assertIn("$.run_id", {issue.path for issue in cards_issues})

    def test_app_session_import_writes_shared_run_reference(self) -> None:
        source = self.root / "incoming" / "app-session.json"
        write_json(source, sample_app_session())

        result = import_app_session(self.root, source)

        self.assertEqual(result["status"], "pass")
        self.assertTrue(app_session_path(self.root, "example-session").is_file())
        imported = read_json(run_dir(self.root, "example-v0.1") / "app-session-import.json")
        self.assertFalse(imported["raw_transcript_stored"])
        self.assertIn("app-session.json", imported["app_session_path"])

    def test_app_collect_links_cards_to_report_and_retune(self) -> None:
        matrix = self.write_default_contract()
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        result = collect_app_artifacts(self.root, "example-v0.1")

        collection = read_json(app_collection_path(self.root, "example-v0.1"))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(collection["artifact_type"], APP_COLLECTION_TYPE)
        self.assertEqual(collection["card_count"], 4)
        self.assertEqual(validate_app_collection(collection), [])

    def test_app_collect_reports_missing_cards_as_artifact_error(self) -> None:
        write_json(app_session_path(self.root, "example-session"), sample_app_session())

        with self.assertRaises(ArtifactError) as context:
            collect_app_artifacts(self.root, "example-v0.1")

        self.assertIn("cards.json is missing", str(context.exception))

    def test_app_collect_rejects_stale_report_and_retune_card_refs(self) -> None:
        matrix = self.write_default_contract()
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        cards = sample_app_cards()
        cards["cards"][2]["artifact_refs"] = [".rubricodex/runs/other/report.md"]
        cards["cards"][3]["artifact_refs"] = [".rubricodex/runs/other/retune_goal.md"]
        write_json(app_cards_path(self.root, "example-session"), cards)
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        with self.assertRaises(ArtifactError) as context:
            collect_app_artifacts(self.root, "example-v0.1")

        message = str(context.exception)
        self.assertIn("report card must reference", message)
        self.assertIn("retune card must reference", message)

    def test_orchestrate_run_and_status_complete_shared_flow(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(
            run_dir(self.root, "example-v0.1") / "evidence.json",
            sample_evidence(matrix, {"C-05": "partial"}),
        )
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())

        result = orchestrate_run(self.root, "example-v0.1", parallel=2)
        status = orchestrate_status(self.root, "example-v0.1")

        orchestrator = read_json(orchestrator_path(self.root, "example-v0.1"))
        self.assertEqual(result["status"], "needs_retune")
        self.assertEqual(status["status"], "complete")
        self.assertEqual(orchestrator["artifact_type"], ORCHESTRATOR_TYPE)
        self.assertEqual(validate_orchestrator(orchestrator), [])
        self.assertTrue(app_collection_path(self.root, "example-v0.1").is_file())

    def test_orchestrate_status_requires_current_app_collection_for_app_session(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        orchestrate_run(self.root, "example-v0.1", parallel=2)

        app_collection = app_collection_path(self.root, "example-v0.1")
        app_collection.unlink()
        missing_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(missing_status["status"], "incomplete")
        self.assertIn("app_collection", missing_status["missing"])

        collection = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": APP_COLLECTION_TYPE,
            "rubricodex_version": "0.1.0",
            "created_at": "2026-05-11T00:00:00Z",
            "mode": "standard",
            "run_id": "example-v0.1",
            "session_id": "example-session",
            "app_session_path": ".rubricodex/app/sessions/example-session/app-session.json",
            "cards_path": ".rubricodex/app/sessions/example-session/cards.json",
            "report_path": ".rubricodex/runs/other/report.md",
            "retune_goal_path": ".rubricodex/runs/example-v0.1/retune_goal.md",
            "card_count": 4,
            "raw_transcript_stored": False,
        }
        write_json(app_collection, collection)
        stale_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(stale_status["status"], "fail")
        self.assertIn(
            "$.app_collection.report_path",
            {issue["path"] for issue in stale_status["issues"]},
        )

    def test_orchestrate_status_rejects_stale_app_collection_session_refs(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        orchestrate_run(self.root, "example-v0.1", parallel=2)

        collection = read_json(app_collection_path(self.root, "example-v0.1"))
        collection["session_id"] = "other-session"
        collection["app_session_path"] = ".rubricodex/app/sessions/other-session/app-session.json"
        collection["cards_path"] = ".rubricodex/app/sessions/other-session/cards.json"
        collection["card_count"] = 999
        write_json(app_collection_path(self.root, "example-v0.1"), collection)

        status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(status["status"], "fail")
        issue_paths = {issue["path"] for issue in status["issues"]}
        self.assertIn("$.app_collection.session_id", issue_paths)
        self.assertIn("$.app_collection.app_session_path", issue_paths)
        self.assertIn("$.app_collection.cards_path", issue_paths)
        self.assertIn("$.app_collection.card_count", issue_paths)

    def test_orchestrate_status_revalidates_source_app_artifacts(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        orchestrate_run(self.root, "example-v0.1", parallel=2)

        session = sample_app_session()
        session["raw_transcript_stored"] = True
        session["raw_transcript"] = "do not store this"
        write_json(app_session_path(self.root, "example-session"), session)
        session_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(session_status["status"], "fail")
        self.assertIn("$.raw_transcript", {issue["path"] for issue in session_status["issues"]})

        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        cards = sample_app_cards()
        cards["raw_transcript"] = "do not store this"
        write_json(app_cards_path(self.root, "example-session"), cards)
        cards_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(cards_status["status"], "fail")
        self.assertIn("$.raw_transcript", {issue["path"] for issue in cards_status["issues"]})

    def test_orchestrate_status_rechecks_current_card_report_refs(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        orchestrate_run(self.root, "example-v0.1", parallel=2)

        cards = sample_app_cards()
        cards["cards"][2]["artifact_refs"] = [".rubricodex/runs/other/report.md"]
        cards["cards"][3]["artifact_refs"] = [".rubricodex/runs/other/retune_goal.md"]
        write_json(app_cards_path(self.root, "example-session"), cards)

        status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(status["status"], "fail")
        issue_paths = {issue["path"] for issue in status["issues"]}
        self.assertIn("$.cards.report.artifact_refs", issue_paths)
        self.assertIn("$.cards.retune.artifact_refs", issue_paths)

    def test_orchestrate_status_reports_malformed_current_cards(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        orchestrate_run(self.root, "example-v0.1", parallel=2)

        cards = sample_app_cards()
        del cards["cards"][0]["card_type"]
        write_json(app_cards_path(self.root, "example-session"), cards)

        missing_card_type_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(missing_card_type_status["status"], "fail")
        self.assertIn("$.cards[0].card_type", {issue["path"] for issue in missing_card_type_status["issues"]})

        cards = sample_app_cards()
        del cards["cards"]
        write_json(app_cards_path(self.root, "example-session"), cards)

        missing_cards_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(missing_cards_status["status"], "fail")
        self.assertIn("$.cards", {issue["path"] for issue in missing_cards_status["issues"]})

        cards = sample_app_cards()
        cards["cards"][2]["artifact_refs"] = [[".rubricodex/runs/example-v0.1/report.md"]]
        write_json(app_cards_path(self.root, "example-session"), cards)

        malformed_refs_status = orchestrate_status(self.root, "example-v0.1")

        self.assertEqual(malformed_refs_status["status"], "fail")
        self.assertIn("$.cards[2].artifact_refs[0]", {issue["path"] for issue in malformed_refs_status["issues"]})

    def test_orchestrate_run_fails_when_app_collection_is_invalid(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        write_json(app_session_path(self.root, "example-session"), sample_app_session())
        cards = sample_app_cards()
        cards["cards"] = cards["cards"][:3]
        write_json(app_cards_path(self.root, "example-session"), cards)

        result = orchestrate_run(self.root, "example-v0.1", parallel=2)

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["run_status"]["status"], "fail")
        self.assertEqual(result["steps"][-1], {"name": "app_collect", "status": "fail"})

    def test_orchestrate_run_fails_when_probe_execution_fails(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        counter = self.root / "fake-codex-count"
        fake_codex = self.root / "fake-codex"
        fake_codex.write_text(
            "#!/bin/sh\n"
            f"count_file='{counter}'\n"
            "count=0\n"
            "[ -f \"$count_file\" ] && count=$(cat \"$count_file\")\n"
            "count=$((count + 1))\n"
            "echo \"$count\" > \"$count_file\"\n"
            "[ \"$count\" -eq 1 ] && exit 0\n"
            "exit 1\n",
            encoding="utf-8",
        )
        fake_codex.chmod(0o755)

        result = orchestrate_run(self.root, "example-v0.1", execute=True, codex_bin=str(fake_codex))

        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["run_status"]["status"], "fail")
        self.assertIn({"name": "probe_run", "status": "fail"}, result["steps"])

    def test_orchestrate_run_rerun_recomputes_manifest_summary(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))

        failed = orchestrate_run(self.root, "example-v0.1", execute=True, codex_bin="false")
        rerun = orchestrate_run(self.root, "example-v0.1")
        manifest = read_json(run_manifest_path(self.root, "example-v0.1"))

        self.assertEqual(failed["status"], "fail")
        self.assertEqual(rerun["status"], "pass")
        self.assertEqual(manifest["execution_mode"], "dry_run")
        self.assertEqual(
            manifest["result_summary"],
            "Prepared Codex CLI local runner handoff without executing external commands.",
        )

    def test_cli_app_and_orchestrate_commands(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        source = self.root / "incoming" / "app-session.json"
        write_json(source, sample_app_session())

        with redirect_stdout(StringIO()) as import_stdout:
            import_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "app",
                    "session",
                    "import",
                    "--from",
                    str(source),
                ]
            )
        write_json(app_cards_path(self.root, "example-session"), sample_app_cards())
        with redirect_stdout(StringIO()) as run_stdout:
            run_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "orchestrate",
                    "run",
                    "--run-id",
                    "example-v0.1",
                    "--parallel",
                    "2",
                ]
            )
        with redirect_stdout(StringIO()) as status_stdout:
            status_exit = cli_main(["--root", str(self.root), "orchestrate", "status", "--run", "example-v0.1"])

        self.assertEqual(import_exit, 0)
        self.assertEqual(run_exit, 0)
        self.assertEqual(status_exit, 0)
        self.assertIn("app-session-import.json", import_stdout.getvalue())
        self.assertIn("orchestrator.json", run_stdout.getvalue())
        self.assertIn("complete", status_stdout.getvalue())

    def test_probe_plan_selects_hard_gates_and_skips_supporting(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        result = plan_probes(self.root, "example-v0.1")

        plan = read_json(probe_plan_path(self.root, "example-v0.1"))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(plan["artifact_type"], PROBE_PLAN_TYPE)
        self.assertEqual([probe["criterion_id"] for probe in plan["selected_probes"]], ["C-01", "C-02"])
        self.assertEqual({item["criterion_id"] for item in plan["skipped_probes"]}, {"C-03", "C-04", "C-05"})
        self.assertTrue(all(item["skip_reason"] for item in plan["skipped_probes"]))
        self.assertEqual(validate_probe_plan(plan), [])

        prompt = probe_prompt_path(self.root, "example-v0.1", "C-01").read_text(encoding="utf-8")
        self.assertIn("read-only", prompt.lower())
        self.assertIn("Do not modify files", prompt)

    def test_probe_plan_includes_explicit_supporting_criterion(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        plan_probes(self.root, "example-v0.1", criterion_ids=["C-05"])

        plan = read_json(probe_plan_path(self.root, "example-v0.1"))
        self.assertEqual(
            [probe["criterion_id"] for probe in plan["selected_probes"]],
            ["C-01", "C-02", "C-05"],
        )

    def test_probe_run_dry_run_writes_normalized_results_without_raw_output(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        plan_probes(self.root, "example-v0.1")

        result = run_probes(self.root, "example-v0.1", parallel=2)

        probe_result = read_json(probe_result_path(self.root, "example-v0.1", "C-01"))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(probe_result["artifact_type"], PROBE_RESULT_TYPE)
        self.assertEqual(probe_result["status"], "probe_skipped")
        self.assertTrue(probe_result["read_only"])
        self.assertFalse(probe_result["raw_output_stored"])
        self.assertEqual(validate_probe_result(probe_result), [])
        self.assertNotIn("stdout", str(probe_result).lower())
        self.assertNotIn("stderr", str(probe_result).lower())

    def test_probe_run_execute_nonzero_is_probe_error(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        plan_probes(self.root, "example-v0.1", criterion_ids=["C-01"])

        result = run_probes(self.root, "example-v0.1", execute=True, codex_bin="false")

        probe_result = read_json(probe_result_path(self.root, "example-v0.1", "C-01"))
        self.assertEqual(result["status"], "fail")
        self.assertEqual(probe_result["status"], "probe_error")
        self.assertEqual(probe_result["exit_code"], 1)
        self.assertEqual(validate_probe_result(probe_result), [])

    def test_probe_result_rejects_raw_output_fields(self) -> None:
        probe_result = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": PROBE_RESULT_TYPE,
            "rubricodex_version": "0.1.0",
            "created_at": "2026-05-11T00:00:00Z",
            "mode": "standard",
            "run_id": "example-v0.1",
            "criterion_id": "C-01",
            "status": "probe_failure",
            "summary": "Probe found missing evidence.",
            "read_only": True,
            "raw_output_stored": False,
            "stdout": "raw",
        }
        self.assertTrue(validate_probe_result(probe_result))

    def test_cli_probe_plan_and_run_write_results(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        with redirect_stdout(StringIO()) as plan_stdout:
            plan_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "probe",
                    "plan",
                    "--run-id",
                    "example-v0.1",
                    "--criterion-id",
                    "C-05",
                ]
            )
        with redirect_stdout(StringIO()) as run_stdout:
            run_exit = cli_main(
                [
                    "--root",
                    str(self.root),
                    "probe",
                    "run",
                    "--run-id",
                    "example-v0.1",
                    "--parallel",
                    "2",
                ]
            )

        self.assertEqual(plan_exit, 0)
        self.assertEqual(run_exit, 0)
        self.assertIn("probe-plan.json", plan_stdout.getvalue())
        self.assertIn("probe_results", run_stdout.getvalue())
        self.assertTrue(probe_result_path(self.root, "example-v0.1", "C-05").is_file())

    def test_scorecard_pass_all_pass(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        scorecard = compute_scorecard(self.root, "example-v0.1")
        self.assertEqual(scorecard["decision"], "pass")
        self.assertEqual(scorecard["counts"]["pass"], 5)

    def test_scorecard_pass_with_warnings_nonhard_partial(self) -> None:
        matrix = self.write_default_contract()
        evidence = sample_evidence(matrix, {"C-05": "partial"})
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", evidence)
        scorecard = compute_scorecard(self.root, "example-v0.1")
        self.assertEqual(scorecard["decision"], "pass_with_warnings")

    def test_scorecard_needs_retune_missing_hard_gate_evidence(self) -> None:
        matrix = self.write_default_contract()
        evidence = sample_evidence(matrix, {"C-01": "omit"})
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", evidence)
        scorecard = compute_scorecard(self.root, "example-v0.1")
        self.assertEqual(scorecard["decision"], "needs_retune")

    def test_scorecard_fail_scope_out_drift(self) -> None:
        matrix = self.write_default_contract()
        evidence = sample_evidence(matrix, {"C-05": "fail"}, scope_out_drift="C-05")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", evidence)
        scorecard = compute_scorecard(self.root, "example-v0.1")
        self.assertEqual(scorecard["decision"], "fail")

    def test_scorecard_rejects_total_score_in_v01(self) -> None:
        scorecard = {
            "schema_version": SCHEMA_VERSION,
            "artifact_type": SCORECARD_TYPE,
            "rubricodex_version": "0.1.0",
            "mode": "standard",
            "run_id": "example-v0.1",
            "created_at": "2026-05-11T00:00:00Z",
            "scoring_model": "counts-v0.1",
            "decision": "pass",
            "counts": {"pass": 1, "partial": 0, "missing_evidence": 0, "fail": 0},
            "results": [],
            "total_score": 1.0,
        }
        self.assertTrue(validate_scorecard(scorecard))

    def test_report_writes_required_headings(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        paths = write_report(self.root, "example-v0.1")
        text = paths["report"].read_text(encoding="utf-8")
        for heading in ("# Rubricodex Report", "## Summary", "## Criteria", "## Next action", "## App actions"):
            self.assertIn(heading, text)
        self.assertIn("Retune targets: C-05", text)
        self.assertIn("Preserved pass criteria: C-01, C-02, C-03, C-04", text)
        self.assertIn("Reason:", text)
        self.assertIn("retune_failed_criteria", text)

    def test_report_highlights_failed_hard_gate(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-01": "fail"}))
        compute_scorecard(self.root, "example-v0.1")

        paths = write_report(self.root, "example-v0.1")

        text = paths["report"].read_text(encoding="utf-8")
        self.assertIn("Hard gate alert: C-01 Endpoint contract is fail", text)
        self.assertIn("Hard gate blocked", text)

    def test_report_includes_probe_skip_reasons(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        plan_probes(self.root, "example-v0.1")
        run_probes(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        compute_scorecard(self.root, "example-v0.1")

        paths = write_report(self.root, "example-v0.1")

        text = paths["report"].read_text(encoding="utf-8")
        self.assertIn("## Probes", text)
        self.assertIn("C-03 skipped", text)
        self.assertIn("supporting criterion skipped", text)
        self.assertIn("C-01: probe_skipped", text)

    def test_retune_goal_targets_only_failed_partial_or_missing_criteria(self) -> None:
        matrix = self.write_default_contract()
        write_json(
            run_dir(self.root, "example-v0.1") / "evidence.json",
            sample_evidence(matrix, {"C-03": "missing_evidence", "C-04": "fail", "C-05": "partial"}),
        )
        compute_scorecard(self.root, "example-v0.1")
        paths = write_report(self.root, "example-v0.1")
        text = paths["retune"].read_text(encoding="utf-8")
        include = text.split("## Include", 1)[1].split("## Exclude", 1)[0]
        exclude = text.split("## Exclude", 1)[1].split("## Working rules", 1)[0]
        self.assertIn("C-03", include)
        self.assertIn("C-04", include)
        self.assertIn("C-05", include)
        self.assertNotIn("C-01", include)
        self.assertIn("C-01", exclude)

    def test_retune_goal_passes_prompt_lint_and_stays_short(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")

        paths = write_report(self.root, "example-v0.1")

        text = paths["retune"].read_text(encoding="utf-8")
        self.assertEqual(lint_goal_text(text), [])
        self.assertLess(len(text), 2400)

    def test_report_handles_legacy_scorecard_without_reason(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        scorecard = compute_scorecard(self.root, "example-v0.1")
        for result in scorecard["results"]:
            result.pop("reason", None)
        write_json(run_dir(self.root, "example-v0.1") / "scorecard.json", scorecard)

        paths = write_report(self.root, "example-v0.1")

        text = paths["retune"].read_text(encoding="utf-8")
        self.assertIn("No reason recorded", text)
        self.assertEqual(lint_goal_text(text), [])

    def test_legacy_fixture_target_matrix_harness_plan_not_canonical(self) -> None:
        fixture = REPO_ROOT / "examples/source-code-endpoint/.rubricodex"
        self.assertFalse((fixture / "target.json").exists())
        self.assertFalse((fixture / "matrix.json").exists())
        self.assertFalse((fixture / "harness-plan.json").exists())

    def test_source_code_endpoint_fixture_full_flow(self) -> None:
        source = REPO_ROOT / "examples/source-code-endpoint"
        fixture = self.root / "fixture"
        shutil.copytree(source, fixture)
        brief = read_json(intent_path(fixture))
        matrix = read_json(matrix_path(fixture))
        evidence = read_json(run_dir(fixture, "example-v0.1") / "evidence.json")
        self.assertEqual(validate_brief(brief), [])
        self.assertEqual(validate_matrix(matrix), [])
        self.assertEqual(validate_evidence(evidence, matrix), [])
        compile_goal(fixture, "example-v0.1")
        lint = lint_goal_file(fixture, "example-v0.1")
        self.assertEqual(lint["status"], "pass")
        run_result = run_local(fixture, "example-v0.1")
        self.assertEqual(run_result["status"], "pass")
        manifest = read_json(run_manifest_path(fixture, "example-v0.1"))
        self.assertEqual(validate_run_manifest(manifest), [])
        probe_plan = plan_probes(fixture, "example-v0.1")
        self.assertEqual(probe_plan["status"], "pass")
        probe_run = run_probes(fixture, "example-v0.1", parallel=2)
        self.assertEqual(probe_run["status"], "pass")
        scorecard = compute_scorecard(fixture, "example-v0.1")
        self.assertIn(scorecard["decision"], {"pass", "pass_with_warnings"})
        paths = write_report(fixture, "example-v0.1")
        self.assertTrue(paths["report"].is_file())
        self.assertTrue(paths["retune"].is_file())


if __name__ == "__main__":
    unittest.main()
