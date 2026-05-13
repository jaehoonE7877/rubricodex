from __future__ import annotations

import os
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from rubricodex import __version__
from rubricodex.hooks import evaluate_gate
from rubricodex.schemas import load_schema, schema_index, schema_path
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

    def hook_context(self, result: dict[str, Any]) -> str:
        output = result.get("hookSpecificOutput", {})
        if isinstance(output, dict):
            context = output.get("additionalContext")
            if isinstance(context, str):
                return context
        return str(result.get("reason", ""))

    def assert_advised_categories(self, result: dict[str, Any], categories: str) -> None:
        context = self.hook_context(result)
        self.assertIn("matched_categories=", context)
        for category in categories.split(","):
            self.assertIn(category, context)

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

    def test_hook_intake_advises_raw_storage_prompt(self) -> None:
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex store the raw transcript and raw command output in the repo.",
                "cwd": str(self.root),
            },
        )

        self.assertNotEqual(result.get("decision"), "block")
        self.assertIn("intake-boundary advisory", self.hook_context(result))
        self.assertIn("matched_categories=raw_transcript,raw_command_output", self.hook_context(result))
        self.assertIn("matched_action=store", self.hook_context(result))
        self.assertNotIn("reason", result)
        self.assertNotIn("store the raw transcript", self.hook_context(result))

    def test_hook_intake_allows_first_rubricodex_prompt(self) -> None:
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex 우리 서비스에 POST /api/widgets endpoint를 추가해줘. 기본 테스트까지.",
                "cwd": str(self.root),
            },
        )

        self.assertNotEqual(result.get("decision"), "block")
        self.assertIn("intake-boundary advisory", self.hook_context(result))

    def test_hook_intake_advises_explicit_korean_raw_storage_prompt(self) -> None:
        cases = [
            ("@Rubricodex raw transcript를 repo에 저장해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript repo에 저장", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하고 요약도 작성해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해주시고 요약도 해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장도 하고 요약도 해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하고나서 요약해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해서 요약해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장한 다음 요약해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장한 뒤 요약도 작성해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장이 필요합니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장은 필요합니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하고 요약은 저장하지 마.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript를 요약하지 말고 저장해줘.", "raw_transcript", "저장"),
            ("@Rubricodex 요약도 작성하고 raw transcript 저장해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하는 코드를 만들어줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장할 파일을 만들어줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하도록 구현해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해도 됩니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해주십시오.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해주시기 바랍니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장하시오.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장되게 해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw command output 기록해도 돼요.", "raw_command_output", "기록"),
            ("@Rubricodex raw task log 커밋해도 됩니다.", "raw_task_log", "커밋"),
            ("@Rubricodex raw transcript를 저장합니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장해야합니다.", "raw_transcript", "저장"),
            ("@Rubricodex raw transcript 저장을 해줘.", "raw_transcript", "저장"),
            ("@Rubricodex raw task log 기록", "raw_task_log", "기록"),
            ("@Rubricodex raw task log 기록하는 파일을 만들어줘.", "raw_task_log", "기록"),
            ("@Rubricodex raw command output 커밋", "raw_command_output", "커밋"),
            ("@Rubricodex raw command output 커밋을 해줘.", "raw_command_output", "커밋"),
            ("@Rubricodex raw command output 커밋하는 스크립트를 만들어줘.", "raw_command_output", "커밋"),
        ]

        for prompt, category, action in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)
                self.assertIn(f"matched_action={action}", self.hook_context(result))

    def test_hook_intake_advises_unredacted_command_output_without_raw_word(self) -> None:
        for prompt in (
            "@Rubricodex store unredacted command output in the repo.",
            "@Rubricodex write unredacted command output to .rubricodex/runs/foo/evidence.json.",
        ):
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assertIn("matched_categories=raw_command_output", self.hook_context(result))

    def test_hook_intake_advises_inflected_raw_storage_actions(self) -> None:
        cases = [
            (
                "@Rubricodex create a file that stores the raw transcript.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex raw transcript should be stored in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex raw transcript should be saved alongside a summary.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex keep storing raw command output in evidence.",
                "raw_command_output",
                "keep",
            ),
            (
                "@Rubricodex add the raw transcript to evidence.json.",
                "raw_transcript",
                "add",
            ),
            (
                "@Rubricodex include raw command output in the report.",
                "raw_command_output",
                "include",
            ),
            (
                "@Rubricodex paste raw transcript into the repo.",
                "raw_transcript",
                "paste",
            ),
            (
                "@Rubricodex put raw task log in .rubricodex.",
                "raw_task_log",
                "put",
            ),
            (
                "@Rubricodex keep raw command output in evidence.",
                "raw_command_output",
                "keep",
            ),
        ]

        for prompt, category, action in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)
                self.assertIn(f"matched_action={action}", self.hook_context(result))

    def test_hook_intake_advises_raw_containing_document_writes(self) -> None:
        for prompt in (
            "@Rubricodex write docs with the raw transcript.",
            "@Rubricodex write documentation containing raw command output.",
            "@Rubricodex write an AGENTS policy with the raw transcript.",
            "@Rubricodex Write raw transcript to evidence.json and to the do-not-store policy.",
            "@Rubricodex Add raw transcript to evidence.json and to the do-not-store policy.",
            "@Rubricodex Include raw command output in evidence.json and in the do-not-store policy.",
            "@Rubricodex add raw transcript to the do-not-store policy as well as evidence.json.",
            "@Rubricodex add raw transcript to the do-not-store policy plus evidence.json.",
            "@Rubricodex add raw transcript to the do-not-store policy / evidence.json.",
            "@Rubricodex add raw transcript to the do-not-store policy & evidence.json.",
            "@Rubricodex add raw transcript to the do-not-store policy along with evidence.json.",
            "@Rubricodex write docs with the raw transcript and do not store summaries.",
            "@Rubricodex write a policy with the raw transcript and never persist summaries.",
            "@Rubricodex include raw transcript in docs and do not store summaries.",
            "@Rubricodex Here is the raw transcript. Write docs with it.",
            "@Rubricodex Here is raw command output. Save documentation with it.",
            "@Rubricodex Here is the raw transcript. Save the summary and it to evidence.json.",
        ):
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assertIn("intake-boundary advisory", self.hook_context(result))

    def test_hook_intake_advises_mixed_negative_and_raw_storage_prompt(self) -> None:
        cases = [
            (
                "@Rubricodex do not store raw transcript but store raw command output.",
                "raw_command_output",
            ),
            (
                "@Rubricodex do not store raw transcript but store it in evidence.json.",
                "raw_transcript",
            ),
            (
                "@Rubricodex do not store raw transcript, store it in evidence.json.",
                "raw_transcript",
            ),
            (
                "@Rubricodex do not store raw transcript. Save it to repo.",
                "raw_transcript",
            ),
            (
                "@Rubricodex do not store raw transcript and store it in evidence.json.",
                "raw_transcript",
            ),
            (
                "@Rubricodex raw transcript should not be stored then save it in repo.",
                "raw_transcript",
            ),
            (
                "@Rubricodex raw transcript 저장하지 마. 그걸 저장해줘.",
                "raw_transcript",
            ),
            (
                "@Rubricodex raw transcript 저장하지 마. repo에 저장해줘.",
                "raw_transcript",
            ),
            (
                "@Rubricodex raw transcript should not be stored but should be saved in repo.",
                "raw_transcript",
            ),
            (
                "@Rubricodex raw transcript는 저장하지 말고 raw command output은 저장해줘.",
                "raw_command_output",
            ),
            (
                "@Rubricodex raw transcript 저장하지 말고 커밋해줘.",
                "raw_transcript",
            ),
        ]

        for prompt, category in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)

    def test_hook_intake_advises_storage_request_with_unrelated_negation(self) -> None:
        cases = [
            ("@Rubricodex don't redact anything, store the raw transcript in the repo.", "raw_transcript"),
            ("@Rubricodex store the raw transcript without storing summaries.", "raw_transcript"),
            ("@Rubricodex don't save anything else and store raw transcript.", "raw_transcript"),
            ("@Rubricodex do not summarize the raw transcript, save it as-is.", "raw_transcript"),
            ("@Rubricodex do not summarize raw transcript, store it in repo.", "raw_transcript"),
            ("@Rubricodex store raw transcript in repo but never persist summaries.", "raw_transcript"),
            ("@Rubricodex store raw transcript and do not store summaries.", "raw_transcript"),
            ("@Rubricodex do not store summary, raw transcript should be stored.", "raw_transcript"),
            ("@Rubricodex raw transcript should be stored in repo and never persisted elsewhere.", "raw_transcript"),
            ("@Rubricodex save raw command output to evidence but never store transcripts.", "raw_command_output"),
            ("@Rubricodex summarize the raw transcript and store it verbatim.", "raw_transcript"),
            ("@Rubricodex summarize the raw transcript and store it as-is.", "raw_transcript"),
            ("@Rubricodex summarize the raw transcript and store it unredacted.", "raw_transcript"),
            ("@Rubricodex analyze raw command output and save it to evidence.json.", "raw_command_output"),
            ("@Rubricodex Here is raw command output. Analyze it and save it to evidence.json.", "raw_command_output"),
            ("@Rubricodex do not store a summary of the raw transcript, save it verbatim.", "raw_transcript"),
            ("@Rubricodex Here is raw transcript. Save verbatim to evidence.json.", "raw_transcript"),
            ("@Rubricodex Here is raw transcript. Save as-is to evidence.json.", "raw_transcript"),
            ("@Rubricodex store the summary and raw transcript in evidence.json.", "raw_transcript"),
            ("@Rubricodex save a redacted summary plus raw command output.", "raw_command_output"),
            ("@Rubricodex raw transcript 요약하고 원문도 저장해줘.", "raw_transcript"),
            ("@Rubricodex raw transcript 요약하고 그대로 저장해줘.", "raw_transcript"),
            ("@Rubricodex raw transcript 요약 말고 저장해줘.", "raw_transcript"),
            ("@Rubricodex raw transcript 요약 없이 저장해줘.", "raw_transcript"),
            ("@Rubricodex store raw transcript although it is not allowed.", "raw_transcript"),
            ("@Rubricodex store raw transcript even though it is not allowed.", "raw_transcript"),
            ("@Rubricodex store raw transcript while it is not allowed.", "raw_transcript"),
            ("@Rubricodex store raw transcript because it is not allowed.", "raw_transcript"),
            (
                "@Rubricodex store a summary of raw transcript alongside raw command output.",
                "raw_transcript,raw_command_output",
            ),
        ]

        for prompt, category in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)

    def test_hook_intake_advises_cross_sentence_raw_storage_request(self) -> None:
        cases = [
            (
                "@Rubricodex Store everything below in .rubricodex. raw transcript: hello",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Save to evidence.json:\nraw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Write to evidence.json:\nraw command output: hello",
                "raw_command_output",
                "write",
            ),
            (
                "@Rubricodex 저장해줘:\nraw task log: hello",
                "raw_task_log",
                "저장",
            ),
            (
                "@Rubricodex Store everything below, including a summary. raw transcript: hello",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Store everything below in .rubricodex. Do not include raw transcripts. raw command output: hello",
                "raw_command_output",
                "store",
            ),
            (
                "@Rubricodex Save everything below to evidence.json. Include a summary. raw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Save everything below to evidence.json. Include a redacted summary. raw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Save this to evidence.json. Summary: TBD. raw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Save the following to evidence.json. raw command output: hello",
                "raw_command_output",
                "save",
            ),
            (
                "@Rubricodex Save the following to evidence.json: "
                + ("filler " * 30)
                + "raw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Save this to evidence.json:\nraw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Save the content below to evidence.json:\nraw transcript: hello",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex 아래 내용을 저장해줘. raw transcript: hello",
                "raw_transcript",
                "저장",
            ),
            (
                "@Rubricodex Here is the raw transcript. Store it in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex The raw command output is below. Please save it to evidence.json.",
                "raw_command_output",
                "save",
            ),
            (
                "@Rubricodex raw transcript는 아래에 있어요. repo에 저장해줘.",
                "raw_transcript",
                "저장",
            ),
            (
                "@Rubricodex Here is the raw transcript. Please review it carefully. Store it in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. Do not make a summary. Store it in repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. No summary. Store it in repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. Summary is not needed. Store it in repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. Store in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex do not store raw transcript; store it in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. Write to .rubricodex/runs/foo/evidence.json.",
                "raw_transcript",
                "write",
            ),
            (
                "@Rubricodex The raw command output is below. Write to evidence.json.",
                "raw_command_output",
                "write",
            ),
            (
                "@Rubricodex raw transcript는 아래에 있어요. write to repo.",
                "raw_transcript",
                "write",
            ),
            (
                "@Rubricodex Here is the raw transcript. It should be stored in the repo.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. It should be stored.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex Here is the raw transcript. This should be committed.",
                "raw_transcript",
                "commit",
            ),
            (
                "@Rubricodex Here is the raw transcript. Add it to the do-not-store policy and to evidence.json.",
                "raw_transcript",
                "add",
            ),
            (
                "@Rubricodex Here is the raw transcript. Extract requirements and save to evidence.json as-is.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex Here is the raw transcript. Extract requirements. Save verbatim to evidence.json.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex raw transcript: hello. Save.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex raw command output: hello. Record.",
                "raw_command_output",
                "record",
            ),
            (
                "@Rubricodex raw task log: hello. Commit.",
                "raw_task_log",
                "commit",
            ),
            (
                "@Rubricodex raw transcript. Please save.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex raw transcript: hello. Save everything.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex raw command output: hello. Save all.",
                "raw_command_output",
                "save",
            ),
            (
                "@Rubricodex raw task log: hello. Save all of it.",
                "raw_task_log",
                "save",
            ),
            (
                "@Rubricodex raw command output: hello. Save the output to evidence.json.",
                "raw_command_output",
                "save",
            ),
            (
                "@Rubricodex raw transcript: hello. Save the transcript to evidence.json.",
                "raw_transcript",
                "save",
            ),
            (
                "@Rubricodex raw task log: hello. Commit the log to repo.",
                "raw_task_log",
                "commit",
            ),
        ]

        for prompt, category, action in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)
                self.assertIn(f"matched_action={action}", self.hook_context(result))

    def test_hook_intake_advises_long_inline_raw_storage_request(self) -> None:
        prompt = "@Rubricodex raw transcript: " + ("line " * 80) + "store it in the repo."
        result = evaluate_gate(
            "intake-boundary",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": prompt,
                "cwd": str(self.root),
            },
        )

        self.assertNotEqual(result.get("decision"), "block")
        self.assertIn("matched_categories=raw_transcript", self.hook_context(result))
        self.assertIn("matched_action=store", self.hook_context(result))

    def test_hook_intake_advises_delayed_same_clause_raw_storage_request(self) -> None:
        cases = [
            (
                "@Rubricodex store the provided session bundle with metadata, context refs, "
                "decision notes, agent messages, tool messages, screenshots, attachments, "
                "and the raw transcript in evidence.json.",
                "raw_transcript",
                "store",
            ),
            (
                "@Rubricodex save the provided session bundle with metadata, context refs, "
                "decision notes, agent messages, tool messages, screenshots, attachments, "
                "and raw command output to evidence.json.",
                "raw_command_output",
                "save",
            ),
        ]

        for prompt, category, action in cases:
            with self.subTest(prompt=prompt):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")
                self.assert_advised_categories(result, category)
                self.assertIn(f"matched_action={action}", self.hook_context(result))

    def test_hook_intake_allows_policy_and_agents_prompts(self) -> None:
        cases = [
            "@Rubricodex follow this policy: raw transcript는 repo에 저장하지 않습니다.",
            "@Rubricodex do not store raw transcripts or raw command output.",
            "@Rubricodex store summarized evidence, not raw transcripts.",
            "@Rubricodex write docs that say do not store raw transcripts.",
            "@Rubricodex write docs forbidding raw transcripts.",
            "@Rubricodex write docs that prohibit storing raw transcripts.",
            "@Rubricodex write AGENTS.md to forbid storing raw transcripts.",
            "@Rubricodex commit AGENTS.md with a rule forbidding raw transcripts.",
            "@Rubricodex write docs to ban raw transcripts from being stored.",
            "@Rubricodex write docs to prohibit raw transcripts from being stored.",
            "@Rubricodex add a rule that bans raw transcripts from being stored.",
            "@Rubricodex persist a policy listing raw transcripts as disallowed.",
            "@Rubricodex write a policy listing raw transcripts as disallowed.",
            "@Rubricodex write docs listing raw command output as forbidden.",
            "@Rubricodex include raw transcripts in the policy as disallowed items.",
            "@Rubricodex add raw transcript to the do-not-store policy.",
            "@Rubricodex add tests for raw transcript policy.",
            "@Rubricodex add tests for storing raw transcripts being blocked.",
            "@Rubricodex fix the hook so storing raw transcripts is blocked.",
            "@Rubricodex add support for rejecting raw transcript storage.",
            "@Rubricodex add support for blocking raw command output storage.",
            "@Rubricodex include raw transcript in the forbidden list.",
            "@Rubricodex put raw transcript on the disallowed list.",
            "@Rubricodex write an AGENTS policy: do not store raw transcripts or raw command output.",
            "@Rubricodex write an AGENTS policy: raw transcripts must not be stored in repo.",
            "@Rubricodex write docs: raw transcripts are not allowed to be stored.",
            "@Rubricodex raw transcript should not be stored in the repo.",
            "@Rubricodex do not ever store raw transcripts.",
            "@Rubricodex raw transcripts shouldn't be stored in repo.",
            "@Rubricodex raw transcripts can't be stored in repo.",
            "@Rubricodex write docs: raw transcripts can't be stored in repo.",
            "@Rubricodex raw command output은 커밋 금지입니다.",
            "@Rubricodex write docs: raw transcripts should not ever be stored in repo.",
            "@Rubricodex write docs: raw transcripts are not to be stored.",
            "@Rubricodex write docs: raw transcripts are disallowed.",
            "@Rubricodex raw transcript is stored nowhere; write summary only.",
            "@Rubricodex keep raw command output out of the repo.",
            "@Rubricodex raw transcript is below. Keep it out of evidence.json.",
            "@Rubricodex Store everything below in .rubricodex. Do not include raw transcripts.",
            "@Rubricodex Store everything below in .rubricodex. Do not include raw transcripts. raw transcript: hello",
            "@Rubricodex store the summary of the raw transcript in evidence.json.",
            "@Rubricodex store a summary of the raw transcript and add it to evidence.json.",
            "@Rubricodex store the summary of the raw transcript and add it to evidence.json.",
            "@Rubricodex save a redacted summary of raw command output.",
            "@Rubricodex save a redacted summary of raw command output and put it in evidence.json.",
            "@Rubricodex save a redacted summary of raw command output. Put it in evidence.json.",
            "@Rubricodex summarize the raw transcript and store the summary in evidence.json.",
            "@Rubricodex summarize the raw transcript and store it in evidence.json.",
            "@Rubricodex summarize the raw transcript and store it in evidence.json and add tests.",
            "@Rubricodex summarize the raw transcript. Save it to evidence.json.",
            "@Rubricodex summarize the raw transcript. Store it in evidence.json.",
            "@Rubricodex store the summary of the raw transcript; add it to evidence.json.",
            "@Rubricodex raw transcript는 요약해서 저장해줘.",
            "@Rubricodex raw transcript의 요약을 저장해줘.",
            "@Rubricodex redact raw command output and save the redacted summary in evidence.json.",
            "@Rubricodex Here is the raw transcript. Extract requirements. Save the goal lock.",
            "@Rubricodex Here is the raw transcript. Review it and write a summary.",
            "@Rubricodex Here is the raw transcript. Extract requirements from it and add tests.",
            "@Rubricodex Here is the raw transcript. Extract requirements from it. Save them to evidence.json.",
            "@Rubricodex Here is the raw transcript. Extract requirements. Save them to evidence.json.",
            "@Rubricodex Here is the raw transcript. Extract requirements and save them to evidence.json.",
            "@Rubricodex Here is the raw transcript. Extract requirements from it and save to evidence.json.",
            "@Rubricodex Here is raw command output. Analyze it and write to summary.md.",
            "@Rubricodex analyze raw command output and write to summary.md.",
            "@Rubricodex Here is raw command output. Analyze it and write a summary.",
            "@Rubricodex Use the raw transcript to write a summary.",
            "@Rubricodex extract requirements from raw transcript and save the requirements.",
            "@Rubricodex derive tasks from raw transcript and save tasks.",
            "@Rubricodex analyze raw command output and save findings to evidence.json.",
            "@Rubricodex Extract requirements and save them to evidence.json. raw transcript: hello",
            "@Rubricodex Redact command output and save it to evidence.json. raw command output: hello",
            "@Rubricodex Here is raw transcript: user asks for endpoint. Keep the solution simple.",
            "@Rubricodex Here is raw transcript. Keep it simple.",
            "@Rubricodex Here is raw transcript. Add in Korean.",
            "@Rubricodex Here is raw transcript. Include in Korean.",
            "@Rubricodex raw transcript는 아래에 있어요. 저장 하지 말고 요약만 해줘.",
            "@Rubricodex raw transcript 저장 말고 요약해줘.",
            "@Rubricodex raw transcript 저장 없이 요약해줘.",
            "@Rubricodex raw transcript는 아래에 있어요. 저장 금지이고 요약만 해줘.",
            "@Rubricodex raw transcript 저장을 막는 로직을 구현해줘.",
            "@Rubricodex raw transcript 저장 방지 코드를 작성해줘.",
            "@Rubricodex raw transcript 저장 안 하게 해줘.",
            "@Rubricodex raw transcript 저장 안되게 해줘.",
            "@Rubricodex raw transcript 저장 안 되게 해줘.",
            "@Rubricodex raw transcript 저장 필요 없어.",
            "@Rubricodex raw transcript 저장 필요 없습니다.",
            "@Rubricodex write docs that say do not store raw transcripts. Save them to repo.",
            "@Rubricodex write AGENTS.md to forbid storing raw transcripts. Commit it.",
            "@Rubricodex add a rule that bans raw transcripts from being stored. Save it to AGENTS.md.",
            "@Rubricodex write docs that say do not store raw transcripts and save them to repo.",
            "@Rubricodex write AGENTS.md to forbid storing raw transcripts and commit it.",
            "@Rubricodex add a rule that bans raw transcripts from being stored and save it to AGENTS.md.",
            "@Rubricodex do not store raw transcript; write a summary.",
            "@Rubricodex write docs about the repository policy and implementation guidance that raw transcripts are not stored in repo.",
            (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        ]

        for prompt in cases:
            with self.subTest(prompt=prompt[:80]):
                result = evaluate_gate(
                    "intake-boundary",
                    {
                        "hook_event_name": "UserPromptSubmit",
                        "prompt": prompt,
                        "cwd": str(self.root),
                    },
                )

                self.assertNotEqual(result.get("decision"), "block")

    def test_hook_matrix_readiness_blocks_implementation_without_lock(self) -> None:
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

        self.assertEqual(result["decision"], "block")
        self.assertIn("matrix lock", result["reason"])

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

    def test_hook_matrix_readiness_allows_first_rubricodex_prompt_without_artifacts(self) -> None:
        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex implement a small endpoint with tests.",
                "cwd": str(self.root),
            },
        )

        self.assertEqual(result, {})

    def test_hook_matrix_readiness_ignores_validation_run_prompt(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())

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

    def test_hook_matrix_readiness_blocks_clear_execute_handoff(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())

        for prompt in ("@Rubricodex execute the task now", "@Rubricodex 작업 진행해줘"):
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

    def test_hook_matrix_readiness_resolves_project_root_from_subdirectory(self) -> None:
        init_project(self.root)
        write_json(intent_path(self.root), sample_brief())
        write_json(matrix_path(self.root), sample_matrix())
        child = self.root / "src"
        child.mkdir()

        result = evaluate_gate(
            "matrix-readiness",
            {
                "hook_event_name": "UserPromptSubmit",
                "prompt": "@Rubricodex implement the task now.",
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

    def test_hook_completion_blocks_done_or_passed_claims(self) -> None:
        init_project(self.root)
        run_dir(self.root, "example-v0.1").mkdir(parents=True)

        for message in (
            "Rubricodex is done.",
            "All tests passed.",
            "All tests passed. Next steps: open a PR.",
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

    def test_artifact_validators_reject_raw_storage_fields(self) -> None:
        brief = sample_brief()
        brief["raw_task_log"] = "do not store this"
        self.assertIn("$.raw_task_log", {issue.path for issue in validate_brief(brief)})

        matrix = sample_matrix()
        evidence = sample_evidence(matrix)
        evidence["unredacted_command_output"] = "do not store this"
        self.assertIn("$.unredacted_command_output", {issue.path for issue in validate_evidence(evidence, matrix)})

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
