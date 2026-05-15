from __future__ import annotations

import os
import json
import re
import shutil
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from rubricodex import __version__
from rubricodex.hooks import evaluate_gate
from rubricodex.schemas import load_schema, schema_index, schema_path
from rubricodex.artifacts import (
    APP_CARDS_TYPE,
    APP_COLLECTION_TYPE,
    APP_SESSION_TYPE,
    ArtifactError,
    GOAL_HEADINGS,
    GOAL_LOCK_TYPE,
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
    apply_retune,
    draft_harness,
    sketch_evidence,
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
    taskpack_dir,
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
            "deliverable_shape": "Small Node built-in HTTP endpoint plus node:test coverage.",
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

    def test_plugin_has_manifest_skill_and_hook_surface(self) -> None:
        plugin_root = REPO_ROOT / "plugins/rubricodex"
        self.assertTrue((plugin_root / ".codex-plugin/plugin.json").is_file())
        self.assertTrue((plugin_root / "skills/rubricodex/SKILL.md").is_file())
        self.assertTrue((plugin_root / "hooks/hooks.json").is_file())
        self.assertTrue((plugin_root / "HOOKS.md").is_file())
        self.assertFalse((plugin_root / ".mcp.json").exists())
        self.assertFalse((plugin_root / ".app.json").exists())
        self.assertFalse((plugin_root / "hooks.json").exists())

        manifest = json.loads((plugin_root / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["hooks"], "./hooks/hooks.json")
        hooks_config = json.loads((plugin_root / "hooks/hooks.json").read_text(encoding="utf-8"))
        self.assertIn("UserPromptSubmit", hooks_config["hooks"])
        self.assertIn("Stop", hooks_config["hooks"])
        serialized = json.dumps(hooks_config)
        self.assertIn("rubricodex hook gate intake-boundary", serialized)
        self.assertIn("rubricodex hook gate matrix-readiness", serialized)
        self.assertIn("rubricodex hook gate completion-claim", serialized)

    def test_core_artifact_schemas_are_available(self) -> None:
        schemas = schema_index()

        for artifact_type in (
            BRIEF_TYPE,
            MATRIX_TYPE,
            GOAL_LOCK_TYPE,
            EVIDENCE_TYPE,
            SCORECARD_TYPE,
            RUN_MANIFEST_TYPE,
            PROBE_PLAN_TYPE,
            PROBE_RESULT_TYPE,
            APP_SESSION_TYPE,
            APP_CARDS_TYPE,
            APP_COLLECTION_TYPE,
            ORCHESTRATOR_TYPE,
        ):
            with self.subTest(artifact_type=artifact_type):
                self.assertIn(artifact_type, schemas)
                self.assertTrue(schema_path(artifact_type).is_file())
                self.assertEqual(load_schema(artifact_type)["$id"], schemas[artifact_type])

    def test_goal_lock_schema_exposes_retune_metadata(self) -> None:
        properties = load_schema(GOAL_LOCK_TYPE)["properties"]

        for key in ("parent_run_id", "retune_depth", "preserved_pass_criteria", "retune_targets", "matrix_hash"):
            self.assertIn(key, properties)

    def test_matrix_schema_id_pattern_matches_path_safe_segment(self) -> None:
        properties = load_schema(MATRIX_TYPE)["properties"]
        pattern = re.compile(properties["criteria"]["items"]["properties"]["id"]["pattern"])

        for value in ("C-01", "C 01"):
            with self.subTest(value=value):
                self.assertTrue(pattern.fullmatch(value))
        for value in (" C-01", "C-01 ", "../../escaped", ".", "..", " ", "C-\x00"):
            with self.subTest(value=value):
                self.assertFalse(pattern.fullmatch(value))

    def test_committed_fixture_artifacts_have_schema_coverage(self) -> None:
        schemas = schema_index()
        fixture_root = REPO_ROOT / "examples" / "source-code-endpoint" / ".rubricodex"
        covered = []

        for path in fixture_root.rglob("*.json"):
            artifact = read_json(path)
            artifact_type = artifact.get("artifact_type")
            if artifact_type in schemas:
                covered.append(path)

        self.assertGreaterEqual(len(covered), 12)

    def test_cli_schema_list_and_show(self) -> None:
        with redirect_stdout(StringIO()) as list_stdout:
            list_exit = cli_main(["schema", "list"])
        with redirect_stdout(StringIO()) as show_stdout:
            show_exit = cli_main(["schema", "show", "--artifact-type", MATRIX_TYPE])

        self.assertEqual(list_exit, 0)
        self.assertEqual(show_exit, 0)
        self.assertIn(MATRIX_TYPE, list_stdout.getvalue())
        self.assertEqual(json.loads(show_stdout.getvalue())["title"], "Rubricodex Evaluation Matrix")

    def test_cli_schema_invalid_inputs_return_failure_json(self) -> None:
        cases = [
            ["schema", "show", "--artifact-type", "nope"],
            ["schema", "list", "--schema-version", "v0.2"],
        ]

        for argv in cases:
            with self.subTest(argv=argv):
                with redirect_stdout(StringIO()) as stdout:
                    exit_code = cli_main(argv)

                result = json.loads(stdout.getvalue())
                self.assertEqual(exit_code, 1)
                self.assertEqual(result["status"], "fail")
                self.assertIn("$.schema", {issue["path"] for issue in result["issues"]})

    def test_hook_intake_advises_without_blocking_raw_storage_prompt(self) -> None:
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex store the raw transcript and raw command output in the repo.",
                "cwd": str(self.root),
            },
        )

        self.assertNotIn("decision", result)
        context = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("raw_artifact_storage_request", context)
        self.assertIn("summarized evidence", context)
        self.assertNotIn("store the raw transcript", context)

    def test_hook_intake_allows_first_rubricodex_prompt(self) -> None:
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex 이 작업을 목표와 평가표로 정리해줘.",
                "cwd": str(self.root),
            },
        )

        self.assertNotIn("decision", result)
        self.assertIn("additionalContext", result["hookSpecificOutput"])

    def test_hook_intake_allows_agents_policy_prompt(self) -> None:
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
                "cwd": str(self.root),
            },
        )

        self.assertNotEqual(result.get("decision"), "block")

    def test_hook_matrix_readiness_ignores_first_run_without_taskpack(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex implement the task now.",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_untargeted_prompt_in_initialized_project(self) -> None:
        init_project(self.root)

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "run tests",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_validation_run_prompt(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")

        for prompt in ("@Rubricodex run tests", "@Rubricodex execute tests", "@Rubricodex 테스트 실행"):
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "matrix-readiness",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_read_only_run_id_prompt(self) -> None:
        init_project(self.root)
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex show status --run-id missing-lock",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_policy_context_with_read_only_run_id_prompt(self) -> None:
        init_project(self.root)
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")
        policy = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": policy + "\n\n@Rubricodex show status --run-id missing-lock",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_surrounding_implementation_context_with_read_only_command(self) -> None:
        init_project(self.root)
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "Before I implement this.\n@Rubricodex show status --run-id missing-lock",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_blocks_clear_execute_handoff_with_taskpack_state(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")

        for prompt in (
            "@Rubricodex execute the task now --run-id missing-lock",
            "@Rubricodex 작업 진행해줘 --run-id missing-lock",
        ):
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "matrix-readiness",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result["decision"], "block")
                self.assertIn("matrix lock", result["reason"])

    def test_hook_matrix_readiness_allows_agents_policy_prompt_with_taskpack_state(self) -> None:
        init_project(self.root)
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_blocks_mixed_policy_handoff_prompt(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")
        policy = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")

        for command in (
            "@Rubricodex implement the task now --run-id missing-lock",
            "@Rubricodex execute the task now",
            "@Rubricodex execute tests and implement the fix --run-id missing-lock",
        ):
            with self.subTest(command=command):
                result = evaluate_gate(
                    "matrix-readiness",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": policy + "\n\n" + command,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result["decision"], "block")
                self.assertIn("matrix lock", result["reason"])

    def test_hook_matrix_readiness_resolves_project_root_from_subdirectory(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())
        taskpack_dir(self.root, "missing-lock").mkdir(parents=True)
        (taskpack_dir(self.root, "missing-lock") / "goal.md").write_text("goal", encoding="utf-8")
        child = self.root / "src"
        child.mkdir()

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex implement the task now --run-id missing-lock.",
                "cwd": str(child),
            },
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("matrix lock", result["reason"])

    def test_hook_matrix_readiness_uses_taskpack_mode(self) -> None:
        draft = draft_harness(self.root, "micro-run", "오타 문구 수정", mode="micro")

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex implement --run-id micro-run",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(draft["mode"], "micro")
        self.assertEqual(result, {})

    def test_hook_completion_blocks_claim_with_missing_artifacts(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        result = evaluate_gate(
            "completion-claim",
            {
                "hook_event_name": "Stop",
                "last_assistant_message": "Rubricodex is complete and ready.",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result["decision"], "block")
        self.assertIn("missing", result["reason"])

    def test_hook_completion_ignores_non_completion_ready_phrases(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        for message in ("I am already investigating this.", "I am ready to investigate."):
            with self.subTest(message=message):
                result = evaluate_gate(
                    "completion-claim",
                    {
                        "hook_event_name": "Stop",
                        "last_assistant_message": message,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result, {})

    def test_hook_completion_ignores_final_non_completion_phrase(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        for message in (
            "One final thought before I continue.",
            "Tests passed; continuing with remaining artifacts.",
            "One setup step is done, then I will collect evidence.",
        ):
            with self.subTest(message=message):
                result = evaluate_gate(
                    "completion-claim",
                    {
                        "hook_event_name": "Stop",
                        "last_assistant_message": message,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result, {})

    def test_hook_completion_blocks_explicit_done_claims_with_missing_artifacts(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        for message in (
            "Rubricodex is done.",
            "The task is done. Next, I will open a PR.",
        ):
            with self.subTest(message=message):
                result = evaluate_gate(
                    "completion-claim",
                    {
                        "hook_event_name": "Stop",
                        "last_assistant_message": message,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result["decision"], "block")
                self.assertIn("missing", result["reason"])

    def test_hook_completion_ignores_generic_test_passed_phrase(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        for message in (
            "All tests passed.",
            "테스트 통과했습니다.",
            "테스트는 통과했고 남은 artifacts를 수집하겠습니다.",
        ):
            with self.subTest(message=message):
                result = evaluate_gate(
                    "completion-claim",
                    {
                        "hook_event_name": "Stop",
                        "last_assistant_message": message,
                        "cwd": str(self.root),
                    },
                )

                self.assertEqual(result, {})

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

    def test_brief_raw_transcript_marker_fails_in_allowed_field(self) -> None:
        for marker in ("RAW TRANSCRIPT: user said secret...", "- RAW TRANSCRIPT: user said secret..."):
            with self.subTest(marker=marker):
                brief = sample_brief()
                brief["blocks"]["reference_context"] = marker
                issues = validate_brief(brief)

                self.assertIn("$.blocks.reference_context", {issue.path for issue in issues})

    def test_matrix_valid_passes(self) -> None:
        self.assertEqual(validate_matrix(sample_matrix()), [])

    def test_matrix_duplicate_criterion_id_fails(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][1]["id"] = matrix["criteria"][0]["id"]
        self.assertTrue(validate_matrix(matrix))

    def test_matrix_path_unsafe_criterion_id_fails(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][0]["id"] = "../../escaped"

        issues = validate_matrix(matrix)

        self.assertIn("$.criteria[0].id", {issue.path for issue in issues})

    def test_matrix_control_character_criterion_id_fails(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][0]["id"] = "C-\x00"

        issues = validate_matrix(matrix)

        self.assertIn("$.criteria[0].id", {issue.path for issue in issues})

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

    def test_plan_draft_propose_accepts_valid_subagent_matrix(self) -> None:
        def proposer(**_: object) -> dict:
            matrix = sample_matrix()
            matrix["criteria"][0]["name"] = "Payment idempotency"
            matrix["criteria"][0]["claim"] = "Duplicate payment webhook events are idempotent."
            matrix["criteria"][0]["check_question"] = "Does the webhook keep one payment side effect per event id?"
            return matrix

        result = draft_harness(
            self.root,
            "proposed",
            "결제 webhook 중복 처리를 막고 test evidence를 남겨줘.",
            mode="standard",
            propose=True,
            proposal_runner=proposer,
        )

        matrix = read_json(matrix_path(self.root))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["matrix_source"], "codex-subagent")
        self.assertEqual(matrix["criteria"][0]["name"], "Payment idempotency")
        self.assertNotIn("raw", json.dumps(matrix).lower())

    def test_plan_draft_propose_parses_string_boolean_hard_gate(self) -> None:
        def proposer(**_: object) -> dict:
            matrix = sample_matrix()
            matrix["criteria"][0]["hard_gate"] = "true"
            matrix["criteria"][1]["hard_gate"] = "false"
            return matrix

        result = draft_harness(
            self.root,
            "string-booleans",
            "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            mode="standard",
            propose=True,
            proposal_runner=proposer,
        )

        matrix = read_json(matrix_path(self.root))
        self.assertEqual(result["matrix_source"], "codex-subagent")
        self.assertIs(matrix["criteria"][0]["hard_gate"], True)
        self.assertIs(matrix["criteria"][1]["hard_gate"], False)

    def test_plan_draft_propose_rewrites_path_unsafe_criterion_id(self) -> None:
        def proposer(**_: object) -> dict:
            matrix = sample_matrix(count=4)
            matrix["criteria"][0]["id"] = "../../escaped"
            return matrix

        result = draft_harness(
            self.root,
            "safe-ids",
            "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            mode="standard",
            propose=True,
            proposal_runner=proposer,
        )
        plan_probes(self.root, "safe-ids", include_supporting=True)

        matrix = read_json(matrix_path(self.root))
        self.assertEqual(result["matrix_source"], "codex-subagent")
        self.assertEqual(matrix["criteria"][0]["id"], "C-01")
        self.assertFalse((taskpack_dir(self.root, "escaped.md")).exists())

    def test_plan_draft_propose_falls_back_when_subagent_output_invalid(self) -> None:
        def proposer(**_: object) -> dict:
            return {"criteria": []}

        result = draft_harness(
            self.root,
            "fallback",
            "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            mode="standard",
            propose=True,
            proposal_runner=proposer,
        )

        matrix = read_json(matrix_path(self.root))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["matrix_source"], "deterministic-fallback")
        self.assertEqual(matrix["criteria"][0]["name"], "Intent alignment")

    def test_plan_draft_review_requires_noninteractive_confirmation_for_standard(self) -> None:
        with self.assertRaises(ArtifactError) as context:
            draft_harness(
                self.root,
                "review-needed",
                "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                mode="standard",
                review=True,
            )

        self.assertIn("$.review", {issue.path for issue in context.exception.issues})
        self.assertFalse((taskpack_dir(self.root, "review-needed") / "goal.lock.json").exists())

    def test_plan_draft_review_yes_locks_after_confirmation(self) -> None:
        result = draft_harness(
            self.root,
            "reviewed",
            "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            mode="standard",
            review=True,
            review_decision="yes",
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["review_status"], "confirmed")
        self.assertTrue((taskpack_dir(self.root, "reviewed") / "goal.lock.json").is_file())

    def test_plan_draft_review_confirmation_reuses_existing_reviewed_matrix(self) -> None:
        def proposer(name: str):
            def run(**_: object) -> dict:
                matrix = sample_matrix()
                matrix["criteria"][0]["name"] = name
                return {"criteria": matrix["criteria"]}

            return run

        with self.assertRaises(ArtifactError):
            draft_harness(
                self.root,
                "reviewed",
                "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                propose=True,
                review=True,
                proposal_runner=proposer("Reviewed matrix"),
            )

        result = draft_harness(
            self.root,
            "reviewed",
            "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
            propose=True,
            review=True,
            review_decision="yes",
            proposal_runner=proposer("Regenerated matrix"),
        )
        matrix = read_json(matrix_path(self.root))

        self.assertEqual(result["review_status"], "confirmed")
        self.assertEqual(result["matrix_source"], "existing-draft")
        self.assertEqual(matrix["criteria"][0]["name"], "Reviewed matrix")

    def test_plan_draft_review_confirmation_rejects_mismatched_existing_draft(self) -> None:
        with self.assertRaises(ArtifactError):
            draft_harness(
                self.root,
                "reviewed",
                "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                review=True,
            )

        with self.assertRaises(ArtifactError) as context:
            draft_harness(
                self.root,
                "reviewed",
                "다른 billing endpoint를 만들고 test evidence를 남겨줘.",
                review=True,
                review_decision="yes",
            )

        self.assertIn("$.review", {issue.path for issue in context.exception.issues})

    def test_plan_draft_review_confirmation_rejects_substring_goal_match(self) -> None:
        with self.assertRaises(ArtifactError):
            draft_harness(
                self.root,
                "reviewed",
                "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                mode="standard",
                review=True,
            )

        with self.assertRaises(ArtifactError) as context:
            draft_harness(
                self.root,
                "reviewed",
                "dashboard page",
                mode="standard",
                review=True,
                review_decision="yes",
            )

        self.assertIn("$.review", {issue.path for issue in context.exception.issues})

    def test_plan_draft_review_auto_accepts_micro_mode(self) -> None:
        result = draft_harness(
            self.root,
            "micro-reviewed",
            "오타 문구 수정",
            mode="micro",
            review=True,
        )

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["review_status"], "auto_accepted")

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

    def test_cli_plan_draft_propose_review_yes_uses_fallback_when_codex_fails(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "plan",
                    "draft",
                    "--run-id",
                    "cli-propose",
                    "--mode",
                    "standard",
                    "--goal",
                    "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                    "--propose",
                    "--codex-bin",
                    "false",
                    "--review",
                    "--yes",
                ]
            )

        self.assertEqual(exit_code, 0)
        output = stdout.getvalue()
        self.assertIn('"matrix_source": "deterministic-fallback"', output)
        self.assertIn('"review_status": "confirmed"', output)
        self.assertTrue((taskpack_dir(self.root, "cli-propose") / "goal.lock.json").is_file())

    def test_cli_plan_draft_rejects_conflicting_review_flags(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as context:
                cli_main(
                    [
                        "--root",
                        str(self.root),
                        "plan",
                        "draft",
                        "--run-id",
                        "conflict",
                        "--goal",
                        "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                        "--review",
                        "--yes",
                        "--no",
                    ]
                )

        self.assertEqual(context.exception.code, 2)
        self.assertFalse((taskpack_dir(self.root, "conflict") / "goal.lock.json").exists())

    def test_cli_plan_draft_no_implies_review_rejection(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "plan",
                    "draft",
                    "--run-id",
                    "reject-without-review",
                    "--goal",
                    "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                    "--no",
                ]
            )

        self.assertEqual(exit_code, 1)
        self.assertIn('"review_status": "rejected"', stdout.getvalue())
        self.assertFalse((taskpack_dir(self.root, "reject-without-review") / "goal.lock.json").exists())

    def test_cli_plan_draft_yes_implies_review_confirmation(self) -> None:
        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "plan",
                    "draft",
                    "--run-id",
                    "confirm-without-review",
                    "--goal",
                    "관리자 dashboard page를 만들고 test evidence를 남겨줘.",
                    "--yes",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"review_status": "confirmed"', stdout.getvalue())
        self.assertTrue((taskpack_dir(self.root, "confirm-without-review") / "goal.lock.json").is_file())

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

    def test_evidence_missing_status_fails(self) -> None:
        matrix = sample_matrix()
        evidence = sample_evidence(matrix)
        evidence["evidence_items"][0].pop("status")

        issues = validate_evidence(evidence, matrix)

        self.assertIn("$.evidence_items[0].status", {issue.path for issue in issues})

    def test_evidence_sketch_writes_draft_without_promoting_by_default(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        result = sketch_evidence(
            self.root,
            "example-v0.1",
            changed_files=["rubricodex/artifacts.py", "tests/test_rubricodex.py"],
            sketch_runner=lambda **_: sample_evidence(matrix),
        )

        draft_path = run_dir(self.root, "example-v0.1") / "evidence.draft.json"
        self.assertEqual(result["status"], "needs_confirmation")
        self.assertTrue(draft_path.is_file())
        self.assertFalse((run_dir(self.root, "example-v0.1") / "evidence.json").exists())
        self.assertEqual(validate_evidence(read_json(draft_path), matrix), [])

    def test_evidence_sketch_yes_promotes_confirmed_draft(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        result = sketch_evidence(
            self.root,
            "example-v0.1",
            changed_files=["rubricodex/artifacts.py"],
            review_decision="yes",
            sketch_runner=lambda **_: sample_evidence(matrix),
        )

        evidence_path = run_dir(self.root, "example-v0.1") / "evidence.json"
        self.assertEqual(result["status"], "pass")
        self.assertTrue(evidence_path.is_file())
        self.assertEqual(validate_evidence(read_json(evidence_path), matrix), [])

    def test_evidence_sketch_missing_status_falls_back_to_partial(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        sketch = sample_evidence(matrix)
        sketch["evidence_items"][0].pop("status")

        result = sketch_evidence(
            self.root,
            "example-v0.1",
            changed_files=["rubricodex/artifacts.py"],
            review_decision="yes",
            sketch_runner=lambda **_: sketch,
        )
        scorecard = compute_scorecard(self.root, "example-v0.1")
        evidence = read_json(run_dir(self.root, "example-v0.1") / "evidence.json")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["sketch_source"], "deterministic-fallback")
        self.assertEqual(evidence["evidence_items"][0]["status"], "partial")
        self.assertEqual(scorecard["decision"], "needs_retune")

    def test_evidence_sketch_requires_changed_files(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        subprocess.run(["git", "init"], cwd=self.root, capture_output=True, check=False)
        (self.root / "dirty.py").write_text("changed", encoding="utf-8")

        with self.assertRaises(ArtifactError) as context:
            sketch_evidence(self.root, "example-v0.1", changed_files=[])

        self.assertIn("$.changed_files", {issue.path for issue in context.exception.issues})

    def test_cli_evidence_sketch_rejects_conflicting_review_flags(self) -> None:
        with redirect_stderr(StringIO()):
            with self.assertRaises(SystemExit) as context:
                cli_main(["evidence", "sketch", "--run-id", "example-v0.1", "--yes", "--no"])

        self.assertEqual(context.exception.code, 2)

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

    def test_cli_evidence_sketch_yes_promotes_with_fallback(self) -> None:
        self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "evidence",
                    "sketch",
                    "--run-id",
                    "example-v0.1",
                    "--changed-file",
                    "rubricodex/artifacts.py",
                    "--codex-bin",
                    "false",
                    "--yes",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"status": "pass"', stdout.getvalue())
        self.assertTrue((run_dir(self.root, "example-v0.1") / "evidence.json").is_file())

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

    def test_run_manifest_rejects_raw_output_markers_in_summary_fields(self) -> None:
        for marker in (
            "STDOUT: raw output",
            "## STDOUT: raw output",
            "RAW OUTPUT: raw",
            "UNREDACTED OUTPUT: raw",
            "RAW LOG: raw",
            "RAW LOGS: raw",
        ):
            with self.subTest(marker=marker):
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
                        {"command": "codex exec", "exit_code": None, "summary": marker},
                    ],
                    "changed_files": [],
                    "verification_commands": [],
                }
                issues = validate_run_manifest(manifest)

                self.assertIn("$.command_results[0].summary", {issue.path for issue in issues})

    def test_app_session_and_cards_validate_without_raw_transcript(self) -> None:
        session = sample_app_session()
        cards = sample_app_cards()
        self.assertEqual(validate_app_session(session), [])
        self.assertEqual(validate_app_cards(cards, session), [])

        session["raw_transcript_stored"] = True
        cards["raw_transcript"] = "do not store this"
        self.assertTrue(validate_app_session(session))
        self.assertTrue(validate_app_cards(cards))

    def test_example_fixture_versions_match_package_version(self) -> None:
        fixture_root = REPO_ROOT / "examples" / "source-code-endpoint" / ".rubricodex"
        versioned_files = []

        for path in fixture_root.rglob("*.json"):
            artifact = read_json(path)
            if "rubricodex_version" not in artifact:
                continue
            versioned_files.append(path)
            self.assertEqual(
                artifact["rubricodex_version"],
                __version__,
                f"{path.relative_to(REPO_ROOT)} has stale rubricodex_version",
            )

        self.assertTrue(versioned_files)

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

    def test_scorecard_rejects_raw_output_label_keys(self) -> None:
        base = {
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
        }

        for key in ("stdout", "stderr", "Raw Transcript", "Raw Log", "raw-output"):
            with self.subTest(key=key):
                scorecard = dict(base)
                scorecard[key] = "do not store this"

                issues = validate_scorecard(scorecard)

                self.assertIn(f"$.{key}", {issue.path for issue in issues})

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

    def test_report_writer_rejects_raw_output_fields_in_scorecard(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        scorecard = compute_scorecard(self.root, "example-v0.1")
        scorecard["raw_command_output"] = "do not store this"
        write_json(run_dir(self.root, "example-v0.1") / "scorecard.json", scorecard)

        with self.assertRaises(ArtifactError):
            write_report(self.root, "example-v0.1")

    def test_report_writer_rejects_raw_output_label_keys_in_scorecard(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        scorecard = compute_scorecard(self.root, "example-v0.1")
        scorecard["stdout"] = "do not store this"
        write_json(run_dir(self.root, "example-v0.1") / "scorecard.json", scorecard)

        with self.assertRaises(ArtifactError):
            write_report(self.root, "example-v0.1")

    def test_report_writer_rejects_raw_output_markers_in_scorecard(self) -> None:
        matrix = self.write_default_contract()
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix))
        scorecard = compute_scorecard(self.root, "example-v0.1")
        scorecard["results"][0]["reason"] = "RAW COMMAND OUTPUT: secret shell output"
        write_json(run_dir(self.root, "example-v0.1") / "scorecard.json", scorecard)

        with self.assertRaises(ArtifactError):
            write_report(self.root, "example-v0.1")

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

    def test_retune_apply_creates_next_taskpack_with_preserved_passes(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        result = apply_retune(self.root, "example-v0.1")

        lock = read_json(goal_lock_path(self.root, "example-v0.1-r2"))
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["new_run_id"], "example-v0.1-r2")
        self.assertTrue((taskpack_dir(self.root, "example-v0.1-r2") / "goal.md").is_file())
        self.assertEqual(lock["parent_run_id"], "example-v0.1")
        self.assertEqual(lock["retune_depth"], 1)
        self.assertEqual(lock["retune_targets"], ["C-05"])
        self.assertIn("C-01", lock["preserved_pass_criteria"])
        locked_criteria = {item["id"]: item for item in lock["locked_criteria"]}
        self.assertEqual(locked_criteria["C-01"]["claim"], "Criterion 1 is satisfied.")
        child_goal = (taskpack_dir(self.root, "example-v0.1-r2") / "goal.md").read_text(encoding="utf-8")
        self.assertIn("/goal Retune Rubricodex run example-v0.1-r2", child_goal)
        self.assertIn("- Run id: example-v0.1-r2", child_goal)
        self.assertIn("- Parent run id: example-v0.1", child_goal)
        self.assertEqual(verify_matrix_lock(self.root, "example-v0.1-r2")["status"], "pass")

    def test_retune_child_scorecard_inherits_preserved_parent_pass_evidence(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")

        child_evidence = sample_evidence(matrix, {"C-05": "pass"}, run_id="example-v0.1-r2")
        child_evidence["evidence_items"] = [
            item for item in child_evidence["evidence_items"] if item["criterion_id"] == "C-05"
        ]
        write_json(run_dir(self.root, "example-v0.1-r2") / "evidence.json", child_evidence)

        scorecard = compute_scorecard(self.root, "example-v0.1-r2")

        self.assertEqual(scorecard["decision"], "pass")
        self.assertEqual(scorecard["counts"], {"pass": 5, "partial": 0, "missing_evidence": 0, "fail": 0})
        inherited = next(result for result in scorecard["results"] if result["criterion_id"] == "C-01")
        self.assertIn("Inherited pass evidence from parent run example-v0.1", inherited["reason"])

    def test_retune_evidence_sketch_fallback_limits_items_to_retune_targets(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")

        sketch_evidence(
            self.root,
            "example-v0.1-r2",
            changed_files=["src/server.js"],
            review_decision="yes",
            sketch_runner=lambda **_: None,
        )
        evidence = read_json(run_dir(self.root, "example-v0.1-r2") / "evidence.json")
        scorecard = compute_scorecard(self.root, "example-v0.1-r2")

        self.assertEqual({item["criterion_id"] for item in evidence["evidence_items"]}, {"C-05"})
        self.assertEqual(scorecard["counts"], {"pass": 4, "partial": 1, "missing_evidence": 0, "fail": 0})
        self.assertEqual(scorecard["decision"], "pass_with_warnings")

    def test_retune_chain_inherits_preserved_evidence_from_ancestor_runs(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")

        child_evidence = sample_evidence(matrix, {"C-05": "partial"}, run_id="example-v0.1-r2")
        child_evidence["evidence_items"] = [
            item for item in child_evidence["evidence_items"] if item["criterion_id"] == "C-05"
        ]
        write_json(run_dir(self.root, "example-v0.1-r2") / "evidence.json", child_evidence)
        compute_scorecard(self.root, "example-v0.1-r2")
        write_report(self.root, "example-v0.1-r2")
        apply_retune(self.root, "example-v0.1-r2")

        grandchild_evidence = sample_evidence(matrix, {"C-05": "pass"}, run_id="example-v0.1-r3")
        grandchild_evidence["evidence_items"] = [
            item for item in grandchild_evidence["evidence_items"] if item["criterion_id"] == "C-05"
        ]
        write_json(run_dir(self.root, "example-v0.1-r3") / "evidence.json", grandchild_evidence)

        scorecard = compute_scorecard(self.root, "example-v0.1-r3")

        self.assertEqual(scorecard["decision"], "pass")
        self.assertEqual(scorecard["counts"], {"pass": 5, "partial": 0, "missing_evidence": 0, "fail": 0})
        inherited = next(result for result in scorecard["results"] if result["criterion_id"] == "C-01")
        self.assertIn("example-v0.1", inherited["reason"])

    def test_cli_retune_apply_command(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        with redirect_stdout(StringIO()) as stdout:
            exit_code = cli_main(
                [
                    "--root",
                    str(self.root),
                    "retune",
                    "apply",
                    "--run-id",
                    "example-v0.1",
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertIn('"new_run_id": "example-v0.1-r2"', stdout.getvalue())
        self.assertTrue((taskpack_dir(self.root, "example-v0.1-r2") / "goal.md").is_file())

    def test_retune_apply_uses_next_available_revision_id(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")

        result = apply_retune(self.root, "example-v0.1", depth_warn=1)
        lock = read_json(goal_lock_path(self.root, "example-v0.1-r3"))

        self.assertEqual(result["new_run_id"], "example-v0.1-r3")
        self.assertEqual(result["retune_depth"], 2)
        self.assertEqual(lock["retune_depth"], 2)
        self.assertIn("retune depth 2", result["warning"])

    def test_retune_apply_skips_existing_run_artifact_directory(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        run_dir(self.root, "example-v0.1-r2").mkdir(parents=True)

        result = apply_retune(self.root, "example-v0.1")

        self.assertEqual(result["new_run_id"], "example-v0.1-r3")
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())
        self.assertTrue((taskpack_dir(self.root, "example-v0.1-r3") / "goal.md").is_file())

    def test_retune_apply_continues_two_digit_revision_ids(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1-r10")
        write_json(run_dir(self.root, "example-v0.1-r10") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1-r10")
        write_report(self.root, "example-v0.1-r10")

        result = apply_retune(self.root, "example-v0.1-r10")

        self.assertEqual(result["new_run_id"], "example-v0.1-r11")
        self.assertEqual(result["retune_depth"], 10)

    def test_retune_apply_custom_new_run_id_increments_parent_depth(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        result = apply_retune(self.root, "example-v0.1", new_run_id="fix-payment-retune")

        lock = read_json(goal_lock_path(self.root, "fix-payment-retune"))
        self.assertEqual(result["new_run_id"], "fix-payment-retune")
        self.assertEqual(result["retune_depth"], 1)
        self.assertEqual(lock["retune_depth"], 1)

    def test_retune_apply_rejects_custom_new_run_id_with_existing_run_artifacts(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        run_dir(self.root, "fix-payment-retune").mkdir(parents=True)

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1", new_run_id="fix-payment-retune")

        self.assertIn("$.new_run_id", {issue.path for issue in context.exception.issues})
        self.assertFalse(taskpack_dir(self.root, "fix-payment-retune").exists())

    def test_retune_apply_rejects_scorecard_targets_missing_from_matrix(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        matrix["criteria"] = [criterion for criterion in matrix["criteria"] if criterion["id"] != "C-05"]
        write_json(matrix_path(self.root), matrix)
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        self.assertEqual(verify_matrix_lock(self.root, "example-v0.1")["status"], "pass")

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.retune_targets", str(context.exception.issues))

    def test_retune_apply_rejects_stale_retune_goal_missing_target(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        retune_path = run_dir(self.root, "example-v0.1") / "retune_goal.md"
        text = retune_path.read_text(encoding="utf-8")
        retune_path.write_text(text.replace("- C-05", "- C-99"), encoding="utf-8")

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.goal.C-05", str(context.exception.issues))
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())

    def test_retune_apply_rejects_target_missing_from_include_only(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        retune_path = run_dir(self.root, "example-v0.1") / "retune_goal.md"
        before_exclude, after_exclude = retune_path.read_text(encoding="utf-8").split("## Exclude", 1)
        before_exclude = before_exclude.replace("- C-05", "- C-99", 1)
        retune_path.write_text(before_exclude + "## Exclude" + after_exclude, encoding="utf-8")

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.goal.include.C-05", str(context.exception.issues))
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())

    def test_retune_apply_rejects_preserved_pass_in_include(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        retune_path = run_dir(self.root, "example-v0.1") / "retune_goal.md"
        text = retune_path.read_text(encoding="utf-8")
        retune_path.write_text(
            text.replace("## Include\n", "## Include\n- C-01 Endpoint contract: pass. Do not retune.\n", 1),
            encoding="utf-8",
        )

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.goal.retune_scope.preserved_pass_criteria.C-01", str(context.exception.issues))
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())

    def test_retune_apply_rejects_target_in_exclude(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        retune_path = run_dir(self.root, "example-v0.1") / "retune_goal.md"
        text = retune_path.read_text(encoding="utf-8")
        retune_path.write_text(
            text.replace("## Working rules\n", "  - C-05 Maintainability\n## Working rules\n", 1),
            encoding="utf-8",
        )

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.goal.exclude.C-05", str(context.exception.issues))
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())

    def test_retune_apply_matches_exact_criterion_ids_without_prefix_collision(self) -> None:
        matrix = sample_matrix()
        matrix["criteria"][1]["id"] = "C-01-extra"
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), matrix)
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-01": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")

        result = apply_retune(self.root, "example-v0.1")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["retune_targets"], ["C-01"])
        self.assertIn("C-01-extra", result["preserved_pass_criteria"])

    def test_retune_apply_rejects_scorecard_missing_current_matrix_criteria(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        matrix["criteria"].append(criterion(6))
        write_json(matrix_path(self.root), matrix)
        compile_goal(self.root, "example-v0.1")
        lint_goal_file(self.root, "example-v0.1")
        self.assertEqual(verify_matrix_lock(self.root, "example-v0.1")["status"], "pass")

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.scorecard.results", str(context.exception.issues))
        self.assertFalse(taskpack_dir(self.root, "example-v0.1-r2").exists())

    def test_retune_apply_rejects_parent_lock_drift(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        matrix["criteria"][0]["evidence_required"] = ["changed evidence"]
        write_json(matrix_path(self.root), matrix)
        self.assertEqual(verify_matrix_lock(self.root, "example-v0.1")["status"], "fail")

        with self.assertRaises(ArtifactError) as context:
            apply_retune(self.root, "example-v0.1")

        self.assertIn("$.parent_lock", str(context.exception.issues))

    def test_retune_lock_blocks_preserved_pass_criteria_changes(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")

        matrix["criteria"][0]["evidence_required"] = ["weakened evidence"]
        write_json(matrix_path(self.root), matrix)
        result = verify_matrix_lock(self.root, "example-v0.1-r2")

        self.assertEqual(result["status"], "fail")
        self.assertIn("V-012", str(result["issues"]))

    def test_retune_lock_rejects_unknown_retune_targets(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        lock = read_json(goal_lock_path(self.root, "example-v0.1-r2"))
        lock["retune_targets"] = ["C-999"]
        write_json(goal_lock_path(self.root, "example-v0.1-r2"), lock)

        result = verify_matrix_lock(self.root, "example-v0.1-r2")

        self.assertEqual(result["status"], "fail")
        self.assertIn("$.retune_targets.C-999", str(result["issues"]))

    def test_retune_lock_revision_rejects_new_matrix_criteria_outside_scope(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        matrix["criteria"].append(criterion(6))
        write_json(matrix_path(self.root), matrix)

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve matrix refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("retune lock missing current matrix criteria", str(result["issues"]))

    def test_retune_lock_revision_rejects_preserved_claim_change(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        matrix["criteria"][0]["claim"] = "Changed preserved criterion meaning."
        write_json(matrix_path(self.root), matrix)

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve matrix refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("V-012", str(result["issues"]))

    def test_retune_lock_revision_rejects_missing_preserved_goal_guardrail(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        goal_path = taskpack_dir(self.root, "example-v0.1-r2") / "goal.md"
        goal_text = goal_path.read_text(encoding="utf-8")
        goal_path.write_text(goal_text.replace("  - C-01 Endpoint contract\n", ""), encoding="utf-8")

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve goal refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("$.goal.preserved_pass_criteria.C-01", str(result["issues"]))

    def test_retune_lock_revision_rejects_missing_retune_include_target(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        goal_path = taskpack_dir(self.root, "example-v0.1-r2") / "goal.md"
        before_exclude, after_exclude = goal_path.read_text(encoding="utf-8").split("## Exclude", 1)
        before_exclude = before_exclude.replace("- C-05", "- C-99", 1)
        goal_path.write_text(before_exclude + "## Exclude" + after_exclude, encoding="utf-8")

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve goal refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("$.goal.include.C-05", str(result["issues"]))

    def test_retune_lock_revision_rejects_preserved_pass_in_evaluation(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        goal_path = taskpack_dir(self.root, "example-v0.1-r2") / "goal.md"
        text = goal_path.read_text(encoding="utf-8")
        goal_path.write_text(
            text.replace("## Evaluation\n", "## Evaluation\n- C-01: should stay preserved.\n", 1),
            encoding="utf-8",
        )

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve goal refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("$.goal.retune_scope.preserved_pass_criteria.C-01", str(result["issues"]))

    def test_retune_lock_revision_rejects_target_in_exclude(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        goal_path = taskpack_dir(self.root, "example-v0.1-r2") / "goal.md"
        text = goal_path.read_text(encoding="utf-8")
        goal_path.write_text(
            text.replace("## Working rules\n", "  - C-05 Maintainability\n## Working rules\n", 1),
            encoding="utf-8",
        )

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve goal refresh")

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["revision_approved"])
        self.assertIn("$.goal.exclude.C-05", str(result["issues"]))

    def test_retune_lock_revision_preserves_retune_metadata(self) -> None:
        matrix = self.write_default_contract()
        compile_goal(self.root, "example-v0.1")
        write_json(run_dir(self.root, "example-v0.1") / "evidence.json", sample_evidence(matrix, {"C-05": "partial"}))
        compute_scorecard(self.root, "example-v0.1")
        write_report(self.root, "example-v0.1")
        apply_retune(self.root, "example-v0.1")
        goal_path = taskpack_dir(self.root, "example-v0.1-r2") / "goal.md"
        goal_path.write_text(goal_path.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        result = verify_matrix_lock(self.root, "example-v0.1-r2", revision_reason="approve whitespace-only goal refresh")
        lock = read_json(goal_lock_path(self.root, "example-v0.1-r2"))

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["revision_approved"])
        self.assertEqual(lock["parent_run_id"], "example-v0.1")
        self.assertEqual(lock["retune_targets"], ["C-05"])
        self.assertIn("C-01", lock["preserved_pass_criteria"])
        self.assertEqual(lock["matrix_hash"], lock["matrix_sha256"])

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
