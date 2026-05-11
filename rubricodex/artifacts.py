from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import __version__


SCHEMA_VERSION = "rubricodex.v0.1"
DEFAULT_MODE = "standard"
DEFAULT_EXECUTOR = "codex-cli-goal"

BRIEF_TYPE = "rubricodex.intent_brief"
MATRIX_TYPE = "rubricodex.evaluation_matrix"
EVIDENCE_TYPE = "rubricodex.evidence"
SCORECARD_TYPE = "rubricodex.scorecard"
GOAL_LOCK_TYPE = "rubricodex.goal_lock"
MATRIX_LOCK_RESULT_TYPE = "rubricodex.matrix_lock_result"
RUN_MANIFEST_TYPE = "rubricodex.run_manifest"
LOCAL_RUNNER_EXECUTOR = "codex-cli-local"
PROBE_PLAN_TYPE = "rubricodex.probe_plan"
PROBE_RESULT_TYPE = "rubricodex.probe_result"
APP_SESSION_TYPE = "rubricodex.app_session"
APP_CARDS_TYPE = "rubricodex.app_cards"
APP_COLLECTION_TYPE = "rubricodex.app_collection"
ORCHESTRATOR_TYPE = "rubricodex.orchestrator"
PROBE_RESULT_STATUSES = {"probe_pass", "probe_failure", "probe_error", "probe_skipped"}
APP_CARD_TYPES = {"harness_plan", "matrix", "report", "retune"}

REQUIRED_BRIEF_BLOCKS = (
    "purpose",
    "desired_outcome",
    "deliverable_shape",
    "reference_context",
    "scope_in",
    "scope_out",
    "working_rules",
    "evaluation_basis",
    "done_when",
)

MODE_CRITERIA_RANGE = {
    "micro": (1, 2),
    "quick": (2, 3),
    "standard": (4, 6),
    "strict": (6, 8),
    "audit": (3, 7),
}

MODE_DRAFT_CRITERIA_COUNT = {
    "micro": 2,
    "quick": 3,
    "standard": 5,
    "strict": 6,
    "audit": 3,
}

AUDIT_KEYWORDS = {
    "audit",
    "review",
    "검토",
    "리뷰",
    "감사",
    "분석",
}

STRICT_KEYWORDS = {
    "auth",
    "authorization",
    "billing",
    "delete",
    "migration",
    "payment",
    "permission",
    "privacy",
    "security",
    "결제",
    "권한",
    "개인정보",
    "마이그레이션",
    "삭제",
    "보안",
    "인증",
}

MICRO_KEYWORDS = {
    "copy",
    "rename",
    "typo",
    "wording",
    "문구",
    "오타",
    "이름",
}

QUICK_KEYWORDS = {
    "bug",
    "fix",
    "small",
    "간단",
    "버그",
    "수정",
}

FORBIDDEN_KEYS = {
    "raw_transcript",
    "raw_chat_transcript",
    "raw_task_log",
    "raw_codex_log",
    "raw_command_output",
    "unredacted_command_output",
}

GOAL_HEADINGS = (
    "Purpose",
    "Desired outcome",
    "Deliverable",
    "Context",
    "Include",
    "Exclude",
    "Working rules",
    "Evaluation",
    "Evidence",
    "Completion rule",
    "Report back",
)

STATUS_ORDER = {
    "pass": 0,
    "partial": 1,
    "missing_evidence": 2,
    "fail": 3,
}

RETUNE_STATUSES = {"partial", "missing_evidence", "fail"}
LIGHT_LOCK_MODES = {"micro", "quick"}


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    message: str
    severity: str = "error"

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message, "severity": self.severity}


class ArtifactError(Exception):
    def __init__(self, issues: list[ValidationIssue]):
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def artifact_root(root: Path | str) -> Path:
    return Path(root) / ".rubricodex"


def intent_path(root: Path | str) -> Path:
    return artifact_root(root) / "intent" / "brief.json"


def matrix_path(root: Path | str) -> Path:
    return artifact_root(root) / "matrix" / "evaluation-matrix.json"


def taskpack_dir(root: Path | str, run_id: str) -> Path:
    return artifact_root(root) / "taskpacks" / run_id


def goal_lock_path(root: Path | str, run_id: str) -> Path:
    return taskpack_dir(root, run_id) / "goal.lock.json"


def probe_dir(root: Path | str, run_id: str) -> Path:
    return taskpack_dir(root, run_id) / "probes"


def probe_plan_path(root: Path | str, run_id: str) -> Path:
    return taskpack_dir(root, run_id) / "probe-plan.json"


def probe_prompt_path(root: Path | str, run_id: str, criterion_id: str) -> Path:
    return probe_dir(root, run_id) / f"{criterion_id}.md"


def run_dir(root: Path | str, run_id: str) -> Path:
    return artifact_root(root) / "runs" / run_id


def run_manifest_path(root: Path | str, run_id: str) -> Path:
    return run_dir(root, run_id) / "run-manifest.json"


def probe_result_dir(root: Path | str, run_id: str) -> Path:
    return run_dir(root, run_id) / "probes"


def probe_result_path(root: Path | str, run_id: str, criterion_id: str) -> Path:
    return probe_result_dir(root, run_id) / f"{criterion_id}.json"


def app_session_dir(root: Path | str, session_id: str) -> Path:
    return artifact_root(root) / "app" / "sessions" / session_id


def app_session_path(root: Path | str, session_id: str) -> Path:
    return app_session_dir(root, session_id) / "app-session.json"


def app_cards_path(root: Path | str, session_id: str) -> Path:
    return app_session_dir(root, session_id) / "cards.json"


def app_collection_path(root: Path | str, run_id: str) -> Path:
    return run_dir(root, run_id) / "app-collection.json"


def orchestrator_path(root: Path | str, run_id: str) -> Path:
    return run_dir(root, run_id) / "orchestrator.json"


def read_json(path: Path | str) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ArtifactError([ValidationIssue("$", "artifact must be a JSON object")])
    return data


def write_json(path: Path | str, data: dict[str, Any]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return target


def write_text(path: Path | str, text: str) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return target


def stable_hash(value: Any) -> str:
    if isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        payload = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def guidance_fingerprint(executor: str) -> dict[str, Any]:
    return {
        "executor": executor,
        "goal_headings": list(GOAL_HEADINGS),
        "schema_version": SCHEMA_VERSION,
    }


def scope_fingerprint(brief: dict[str, Any]) -> dict[str, Any]:
    blocks = brief.get("blocks", {})
    return {
        "scope_in": blocks.get("scope_in", []),
        "scope_out": blocks.get("scope_out", []),
    }


def criteria_fingerprint(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    criteria = matrix.get("criteria", [])
    if not isinstance(criteria, list):
        return []
    locked = []
    for criterion in criteria:
        if not isinstance(criterion, dict):
            continue
        evidence_required = criterion.get("evidence_required", [])
        locked.append(
            {
                "id": criterion.get("id"),
                "hard_gate": bool(criterion.get("hard_gate")),
                "evidence_required": list(evidence_required) if isinstance(evidence_required, list) else [],
            }
        )
    return locked


def base_artifact(artifact_type: str, mode: str = DEFAULT_MODE, run_id: str | None = None) -> dict[str, Any]:
    artifact: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": artifact_type,
        "rubricodex_version": __version__,
        "created_at": now_iso(),
        "mode": mode,
    }
    if run_id:
        artifact["run_id"] = run_id
    return artifact


def build_goal_lock(
    brief: dict[str, Any],
    matrix: dict[str, Any],
    goal_text: str,
    executor: str,
    mode: str,
    run_id: str,
    revision_reason: str | None = None,
) -> dict[str, Any]:
    guidance = guidance_fingerprint(executor)
    lock = base_artifact(GOAL_LOCK_TYPE, mode=mode, run_id=run_id)
    lock.update(
        {
            "lock_version": "matrix-lock-v0.5",
            "executor": executor,
            "brief_sha256": stable_hash(brief),
            "matrix_sha256": stable_hash(matrix),
            "goal_sha256": stable_hash(goal_text),
            "guidance_sha256": stable_hash(guidance),
            "locked_scope": scope_fingerprint(brief),
            "locked_criteria": criteria_fingerprint(matrix),
        }
    )
    if revision_reason is not None:
        lock["revision"] = {
            "reason": revision_reason,
            "approved_at": now_iso(),
        }
    return lock


def init_project(
    root: Path | str,
    mode: str = DEFAULT_MODE,
    executor: str = DEFAULT_EXECUTOR,
    force: bool = False,
) -> list[Path]:
    root_path = Path(root)
    base = artifact_root(root_path)
    paths = [
        base / "intent",
        base / "matrix",
        base / "taskpacks",
        base / "runs",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

    config_path = base / "config.json"
    if config_path.exists() and not force:
        return [config_path]

    config = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "rubricodex.config",
        "rubricodex_version": __version__,
        "default_mode": mode,
        "default_executor": executor,
        "canonical_artifacts": {
            "intent_brief": ".rubricodex/intent/brief.json",
            "evaluation_matrix": ".rubricodex/matrix/evaluation-matrix.json",
            "taskpacks": ".rubricodex/taskpacks/<run_id>/",
            "runs": ".rubricodex/runs/<run_id>/",
        },
        "raw_storage_policy": "never_store_raw_transcripts_logs_or_unredacted_command_output",
    }
    write_json(config_path, config)
    return [config_path]


def _contains_any(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def classify_mode(goal: str, requested_mode: str = "auto") -> str:
    mode = requested_mode.strip().lower() if requested_mode else "auto"
    if mode != "auto":
        return mode

    words = [word for word in goal.replace("\n", " ").split(" ") if word.strip()]
    if _contains_any(goal, AUDIT_KEYWORDS):
        return "audit"
    if _contains_any(goal, STRICT_KEYWORDS):
        return "strict"
    if len(words) <= 8 and _contains_any(goal, MICRO_KEYWORDS):
        return "micro"
    if len(words) <= 18 and _contains_any(goal, QUICK_KEYWORDS):
        return "quick"
    return DEFAULT_MODE


def assess_request_readiness(goal: str, mode: str) -> dict[str, Any]:
    text = goal.strip()
    lowered = text.lower()
    checks = [
        {
            "id": "outcome",
            "label": "Desired outcome",
            "passed": len(text) >= 12,
        },
        {
            "id": "deliverable",
            "label": "Deliverable shape",
            "passed": _contains_any(
                lowered,
                {
                    "api",
                    "app",
                    "cli",
                    "code",
                    "doc",
                    "endpoint",
                    "page",
                    "report",
                    "test",
                    "ui",
                    "문서",
                    "리포트",
                    "엔드포인트",
                    "코드",
                    "테스트",
                    "페이지",
                    "화면",
                },
            ),
        },
        {
            "id": "scope",
            "label": "Scope boundary",
            "passed": _contains_any(lowered, {"only", "except", "without", "제외", "범위"}),
        },
        {
            "id": "evidence",
            "label": "Evidence expectation",
            "passed": _contains_any(lowered, {"evidence", "test", "verify", "검증", "근거", "테스트"}),
        },
        {
            "id": "context",
            "label": "Reference context",
            "passed": "/" in text or "." in text or _contains_any(lowered, {"file", "repo", "기존", "파일", "레포"}),
        },
        {
            "id": "risk",
            "label": "Risk signal",
            "passed": mode in {"micro", "quick"} or _contains_any(lowered, STRICT_KEYWORDS | {"risk", "위험"}),
        },
    ]
    passed = sum(1 for check in checks if check["passed"])
    assumptions = []
    if not checks[1]["passed"]:
        assumptions.append("Treat the deliverable as a repository change unless context says otherwise.")
    if not checks[2]["passed"]:
        assumptions.append("Keep scope to the smallest useful version of the requested outcome.")
    if not checks[3]["passed"]:
        assumptions.append("Use summarized test, file, or review evidence instead of raw output.")
    if not assumptions:
        assumptions.append("No extra product scope is assumed beyond the stated goal.")
    questions = [
        f"Clarify {check['label']} if this assumption is wrong."
        for check in checks
        if not check["passed"]
    ][:3]
    if passed >= 5 or (mode in {"micro", "quick"} and passed >= 3):
        status = "ready"
    elif passed >= 2:
        status = "needs_assumption"
    else:
        status = "needs_clarification"
    return {
        "score": passed,
        "max_score": len(checks),
        "status": status,
        "checks": checks,
        "assumptions": assumptions,
        "clarification_questions": questions,
    }


def _draft_deliverable(goal: str, mode: str) -> str:
    if mode == "audit":
        return "A read-only review report with findings, evidence references, and residual risk."
    if mode == "micro":
        return "A minimal patch or content update with summarized verification evidence."
    if mode == "strict":
        return "A scoped implementation with tests, risk notes, and summarized verification evidence."
    return "A small implementation patch with tests or equivalent summarized verification evidence."


def draft_brief(goal: str, mode: str, task_kind: str = "implementation") -> dict[str, Any]:
    goal_summary = " ".join(goal.strip().split())
    readiness = assess_request_readiness(goal_summary, mode)
    brief = base_artifact(BRIEF_TYPE, mode=mode)
    brief.update(
        {
            "task_kind": task_kind,
            "request_readiness": readiness,
            "blocks": {
                "purpose": f"Complete the requested Rubricodex task: {goal_summary}",
                "desired_outcome": "A bounded result that satisfies the user's stated outcome and the generated evaluation matrix.",
                "deliverable_shape": _draft_deliverable(goal_summary, mode),
                "reference_context": [
                    "Current repository and user-provided context.",
                    "Notion Canonical SSoT when product or contract meaning is unclear.",
                ],
                "scope_in": [
                    goal_summary,
                    "Use the smallest implementation or review path that can satisfy the evaluation matrix.",
                ],
                "scope_out": [
                    "Unrequested product scope.",
                    "Raw transcript, raw task log, or unredacted command output storage.",
                ],
                "working_rules": [
                    "Prefer simple, explicit changes.",
                    "Keep evidence summarized and reference-based.",
                    "Do not change passed criteria during retune unless the user approves scope change.",
                ],
                "evaluation_basis": [
                    "Intent alignment.",
                    "Mode-appropriate completeness.",
                    "Evidence quality.",
                    "Raw storage policy compliance.",
                ],
                "done_when": [
                    "Hard gates pass or a retune instruction explains the remaining blocker.",
                    "Report and scorecard cite summarized evidence for every criterion.",
                ],
            },
        }
    )
    return brief


def _draft_criterion(index: int, name: str, claim: str, evidence: str, hard_gate: bool) -> dict[str, Any]:
    criterion_id = f"C-{index:02d}"
    return {
        "id": criterion_id,
        "name": name,
        "claim": claim,
        "check_question": f"Is {name.lower()} satisfied with summarized evidence?",
        "evidence_required": [evidence],
        "hard_gate": hard_gate,
        "levels": {
            "pass": "Summarized evidence proves this criterion.",
            "partial": "Evidence is present but incomplete.",
            "fail": "Evidence disproves this criterion or the criterion is not implemented.",
        },
        "retune_hint": f"Fix {criterion_id} without reworking criteria already marked pass.",
    }


def draft_matrix(goal: str, mode: str) -> dict[str, Any]:
    count = MODE_DRAFT_CRITERIA_COUNT.get(mode, MODE_DRAFT_CRITERIA_COUNT[DEFAULT_MODE])
    templates = [
        (
            "Intent alignment",
            "The result directly addresses the drafted user goal.",
            "Changed files, review notes, or report summary showing the goal is addressed.",
            True,
        ),
        (
            "Scope control",
            "The work stays inside scope_in and avoids scope_out.",
            "Summary of included and excluded scope, plus any deferred items.",
            mode in {"standard", "strict", "audit"},
        ),
        (
            "Evidence quality",
            "The run records enough summarized evidence to judge the result.",
            "Test, typecheck, review, or manual verification summary without raw output.",
            mode in {"strict", "audit"},
        ),
        (
            "Mode fit",
            "The harness effort matches the selected mode.",
            "Mode choice and why it is sufficient for the risk level.",
            False,
        ),
        (
            "Report and retune usability",
            "Report and retune instructions are clear and bounded.",
            "Scorecard/report/retune references with failed criteria isolated.",
            False,
        ),
        (
            "Risk and policy compliance",
            "High-risk or policy-sensitive work is handled conservatively.",
            "Risk notes and confirmation that raw transcript/log/output storage is absent.",
            mode == "strict",
        ),
        (
            "Regression protection",
            "Existing behavior relevant to the task remains intact.",
            "Focused regression test or review summary.",
            mode == "strict",
        ),
        (
            "Audit objectivity",
            "The audit reports findings before summaries and avoids speculative fixes.",
            "Finding list with evidence references and residual risk.",
            mode == "audit",
        ),
    ]
    selected = templates[:count]
    matrix = base_artifact(MATRIX_TYPE, mode=mode)
    matrix.update(
        {
            "method": "gqe-r-lite",
            "draft_goal": " ".join(goal.strip().split()),
            "criteria": [
                _draft_criterion(index, name, claim, evidence, hard_gate)
                for index, (name, claim, evidence, hard_gate) in enumerate(selected, start=1)
            ],
        }
    )
    return matrix


def draft_harness(
    root: Path | str,
    run_id: str,
    goal: str,
    mode: str = "auto",
    task_kind: str = "implementation",
    executor: str = DEFAULT_EXECUTOR,
) -> dict[str, Any]:
    goal_text = goal.strip()
    if not goal_text:
        raise ArtifactError([ValidationIssue("$.goal", "goal must be non-empty")])
    active_mode = classify_mode(goal_text, mode)
    if active_mode not in MODE_CRITERIA_RANGE:
        raise ArtifactError([ValidationIssue("$.mode", f"mode must be auto or one of {', '.join(MODE_CRITERIA_RANGE)}")])

    root_path = Path(root)
    init_project(root_path, mode=active_mode, executor=executor)
    brief = draft_brief(goal_text, active_mode, task_kind=task_kind)
    matrix = draft_matrix(goal_text, active_mode)
    assert_valid(validate_brief(brief, active_mode))
    assert_valid(validate_matrix(matrix, active_mode))
    write_json(intent_path(root_path), brief)
    write_json(matrix_path(root_path), matrix)
    paths = compile_goal(root_path, run_id, mode=active_mode, executor=executor)
    lint = lint_goal_file(root_path, run_id, mode=active_mode)
    lock = verify_matrix_lock(root_path, run_id, mode=active_mode)
    return {
        "status": "pass" if lint["status"] == "pass" and lock["status"] == "pass" else "fail",
        "mode": active_mode,
        "run_id": run_id,
        "readiness": brief["request_readiness"],
        "paths": {name: str(path) for name, path in paths.items()},
        "brief_path": str(intent_path(root_path)),
        "matrix_path": str(matrix_path(root_path)),
        "prompt_lint_status": lint["status"],
        "matrix_lock_status": lock["status"],
    }


def validate_forbidden_keys(value: Any, path: str = "$") -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text.lower() in FORBIDDEN_KEYS:
                issues.append(ValidationIssue(f"{path}.{key_text}", "raw transcript/log/output fields are not allowed"))
            issues.extend(validate_forbidden_keys(child, f"{path}.{key_text}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            issues.extend(validate_forbidden_keys(child, f"{path}[{index}]"))
    return issues


def _is_non_empty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return bool(value)
    return value is not None


def validate_brief(data: dict[str, Any], mode: str | None = None) -> list[ValidationIssue]:
    active_mode = mode or data.get("mode") or DEFAULT_MODE
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != BRIEF_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {BRIEF_TYPE}"))
    blocks = data.get("blocks")
    if not isinstance(blocks, dict):
        return issues + [ValidationIssue("$.blocks", "blocks must be an object")]

    for block in REQUIRED_BRIEF_BLOCKS:
        if block not in blocks:
            issues.append(ValidationIssue(f"$.blocks.{block}", "required brief block is missing"))
        elif not _is_non_empty(blocks[block]):
            issues.append(ValidationIssue(f"$.blocks.{block}", "brief block must not be empty"))

    if active_mode in {"standard", "strict"} and not _is_non_empty(blocks.get("scope_in")):
        issues.append(ValidationIssue("$.blocks.scope_in", "standard mode requires non-empty scope_in"))
    return issues


def validate_matrix(data: dict[str, Any], mode: str | None = None) -> list[ValidationIssue]:
    active_mode = mode or data.get("mode") or DEFAULT_MODE
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != MATRIX_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {MATRIX_TYPE}"))
    if data.get("method") != "gqe-r-lite":
        issues.append(ValidationIssue("$.method", "method must be gqe-r-lite"))

    criteria = data.get("criteria")
    if not isinstance(criteria, list):
        return issues + [ValidationIssue("$.criteria", "criteria must be a list")]

    minimum, maximum = MODE_CRITERIA_RANGE.get(active_mode, MODE_CRITERIA_RANGE[DEFAULT_MODE])
    if not minimum <= len(criteria) <= maximum:
        issues.append(
            ValidationIssue("$.criteria", f"{active_mode} mode requires {minimum}-{maximum} criteria")
        )

    seen: set[str] = set()
    has_hard_gate = False
    for index, criterion in enumerate(criteria):
        path = f"$.criteria[{index}]"
        if not isinstance(criterion, dict):
            issues.append(ValidationIssue(path, "criterion must be an object"))
            continue
        criterion_id = criterion.get("id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            issues.append(ValidationIssue(f"{path}.id", "criterion id is required"))
        elif criterion_id in seen:
            issues.append(ValidationIssue(f"{path}.id", f"duplicate criterion id {criterion_id}"))
        else:
            seen.add(criterion_id)

        for key in ("name", "claim", "check_question", "retune_hint"):
            if not isinstance(criterion.get(key), str) or not criterion[key].strip():
                issues.append(ValidationIssue(f"{path}.{key}", f"{key} is required"))

        evidence_required = criterion.get("evidence_required")
        if not isinstance(evidence_required, list) or not evidence_required:
            issues.append(ValidationIssue(f"{path}.evidence_required", "evidence_required must be non-empty"))

        if "hard_gate" not in criterion:
            issues.append(ValidationIssue(f"{path}.hard_gate", "hard_gate is required"))
        elif not isinstance(criterion["hard_gate"], bool):
            issues.append(ValidationIssue(f"{path}.hard_gate", "hard_gate must be boolean"))
        elif criterion["hard_gate"]:
            has_hard_gate = True

        levels = criterion.get("levels")
        if not isinstance(levels, dict):
            issues.append(ValidationIssue(f"{path}.levels", "levels must include pass, partial, and fail"))
        else:
            for level in ("pass", "partial", "fail"):
                if not isinstance(levels.get(level), str) or not levels[level].strip():
                    issues.append(ValidationIssue(f"{path}.levels.{level}", f"{level} level is required"))

    if active_mode in {"standard", "strict"} and not has_hard_gate:
        issues.append(ValidationIssue("$.criteria", "standard mode requires at least one hard_gate"))
    return issues


def validate_evidence(data: dict[str, Any], matrix: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != EVIDENCE_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {EVIDENCE_TYPE}"))
    if data.get("raw_output_stored") is not False:
        issues.append(ValidationIssue("$.raw_output_stored", "raw_output_stored must be false"))

    known_ids = {criterion["id"] for criterion in matrix.get("criteria", []) if isinstance(criterion, dict) and "id" in criterion}
    items = data.get("evidence_items")
    if not isinstance(items, list):
        return issues + [ValidationIssue("$.evidence_items", "evidence_items must be a list")]

    for index, item in enumerate(items):
        path = f"$.evidence_items[{index}]"
        if not isinstance(item, dict):
            issues.append(ValidationIssue(path, "evidence item must be an object"))
            continue
        criterion_id = item.get("criterion_id")
        if criterion_id not in known_ids:
            issues.append(ValidationIssue(f"{path}.criterion_id", f"unknown criterion id {criterion_id!r}"))
        if not isinstance(item.get("summary"), str) or not item["summary"].strip():
            issues.append(ValidationIssue(f"{path}.summary", "summary is required"))
        if item.get("status", "pass") not in STATUS_ORDER:
            issues.append(ValidationIssue(f"{path}.status", "status must be pass, partial, missing_evidence, or fail"))
        if item.get("artifact_refs") is not None and not isinstance(item["artifact_refs"], list):
            issues.append(ValidationIssue(f"{path}.artifact_refs", "artifact_refs must be a list when present"))
    return issues


def validate_scorecard(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != SCORECARD_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {SCORECARD_TYPE}"))
    if data.get("scoring_model") != "counts-v0.1":
        issues.append(ValidationIssue("$.scoring_model", "scoring_model must be counts-v0.1"))
    for key in ("total_score", "threshold"):
        if key in data:
            issues.append(ValidationIssue(f"$.{key}", f"{key} is not allowed in v0.1 scorecards"))
    return issues


def validate_run_manifest(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != RUN_MANIFEST_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {RUN_MANIFEST_TYPE}"))
    if data.get("executor") != LOCAL_RUNNER_EXECUTOR:
        issues.append(ValidationIssue("$.executor", f"executor must be {LOCAL_RUNNER_EXECUTOR}"))
    if data.get("execution_mode") not in {"dry_run", "execute"}:
        issues.append(ValidationIssue("$.execution_mode", "execution_mode must be dry_run or execute"))
    if data.get("raw_output_stored") is not False:
        issues.append(ValidationIssue("$.raw_output_stored", "raw_output_stored must be false"))
    if not isinstance(data.get("result_summary"), str) or not data["result_summary"].strip():
        issues.append(ValidationIssue("$.result_summary", "result_summary is required"))

    for key in ("changed_files", "verification_commands", "command_results"):
        if not isinstance(data.get(key), list):
            issues.append(ValidationIssue(f"$.{key}", f"{key} must be a list"))

    for index, result in enumerate(data.get("command_results", [])):
        path = f"$.command_results[{index}]"
        if not isinstance(result, dict):
            issues.append(ValidationIssue(path, "command result must be an object"))
            continue
        for forbidden in ("stdout", "stderr", "raw_output", "output"):
            if forbidden in result:
                issues.append(ValidationIssue(f"{path}.{forbidden}", "raw command output fields are not allowed"))
        if not isinstance(result.get("command"), str) or not result["command"].strip():
            issues.append(ValidationIssue(f"{path}.command", "command is required"))
        if "exit_code" not in result:
            issues.append(ValidationIssue(f"{path}.exit_code", "exit_code is required"))
        elif result["exit_code"] is not None and not isinstance(result["exit_code"], int):
            issues.append(ValidationIssue(f"{path}.exit_code", "exit_code must be an integer or null"))
        if not isinstance(result.get("summary"), str) or not result["summary"].strip():
            issues.append(ValidationIssue(f"{path}.summary", "summary is required"))
    return issues


def validate_probe_plan(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != PROBE_PLAN_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {PROBE_PLAN_TYPE}"))
    if data.get("executor") != LOCAL_RUNNER_EXECUTOR:
        issues.append(ValidationIssue("$.executor", f"executor must be {LOCAL_RUNNER_EXECUTOR}"))
    if data.get("raw_output_stored") is not False:
        issues.append(ValidationIssue("$.raw_output_stored", "raw_output_stored must be false"))
    if not isinstance(data.get("parallel"), int) or data["parallel"] < 1:
        issues.append(ValidationIssue("$.parallel", "parallel must be an integer greater than zero"))

    selected = data.get("selected_probes")
    skipped = data.get("skipped_probes")
    if not isinstance(selected, list):
        issues.append(ValidationIssue("$.selected_probes", "selected_probes must be a list"))
        selected = []
    if not isinstance(skipped, list):
        issues.append(ValidationIssue("$.skipped_probes", "skipped_probes must be a list"))
        skipped = []

    seen: set[str] = set()
    for index, probe in enumerate(selected):
        path = f"$.selected_probes[{index}]"
        if not isinstance(probe, dict):
            issues.append(ValidationIssue(path, "selected probe must be an object"))
            continue
        criterion_id = probe.get("criterion_id")
        if not isinstance(criterion_id, str) or not criterion_id.strip():
            issues.append(ValidationIssue(f"{path}.criterion_id", "criterion_id is required"))
        elif criterion_id in seen:
            issues.append(ValidationIssue(f"{path}.criterion_id", f"duplicate criterion id {criterion_id}"))
        else:
            seen.add(criterion_id)
        if probe.get("read_only") is not True:
            issues.append(ValidationIssue(f"{path}.read_only", "probe must be read-only"))
        if not isinstance(probe.get("prompt_path"), str) or not probe["prompt_path"].strip():
            issues.append(ValidationIssue(f"{path}.prompt_path", "prompt_path is required"))
        if not isinstance(probe.get("selection_reason"), str) or not probe["selection_reason"].strip():
            issues.append(ValidationIssue(f"{path}.selection_reason", "selection_reason is required"))

    for index, probe in enumerate(skipped):
        path = f"$.skipped_probes[{index}]"
        if not isinstance(probe, dict):
            issues.append(ValidationIssue(path, "skipped probe must be an object"))
            continue
        if not isinstance(probe.get("criterion_id"), str) or not probe["criterion_id"].strip():
            issues.append(ValidationIssue(f"{path}.criterion_id", "criterion_id is required"))
        if not isinstance(probe.get("skip_reason"), str) or not probe["skip_reason"].strip():
            issues.append(ValidationIssue(f"{path}.skip_reason", "skip_reason is required"))
    return issues


def validate_probe_result(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != PROBE_RESULT_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {PROBE_RESULT_TYPE}"))
    if not isinstance(data.get("criterion_id"), str) or not data["criterion_id"].strip():
        issues.append(ValidationIssue("$.criterion_id", "criterion_id is required"))
    if data.get("status") not in PROBE_RESULT_STATUSES:
        issues.append(ValidationIssue("$.status", "status must be probe_pass, probe_failure, probe_error, or probe_skipped"))
    if not isinstance(data.get("summary"), str) or not data["summary"].strip():
        issues.append(ValidationIssue("$.summary", "summary is required"))
    if data.get("read_only") is not True:
        issues.append(ValidationIssue("$.read_only", "read_only must be true"))
    if data.get("raw_output_stored") is not False:
        issues.append(ValidationIssue("$.raw_output_stored", "raw_output_stored must be false"))
    for forbidden in ("stdout", "stderr", "raw_output", "output"):
        if forbidden in data:
            issues.append(ValidationIssue(f"$.{forbidden}", "raw probe output fields are not allowed"))
    if "exit_code" in data and data["exit_code"] is not None and not isinstance(data["exit_code"], int):
        issues.append(ValidationIssue("$.exit_code", "exit_code must be an integer or null"))
    return issues


def _is_safe_path_segment(value: str) -> bool:
    return (
        value == value.strip()
        and value not in {".", ".."}
        and "/" not in value
        and "\\" not in value
    )


def validate_app_session(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != APP_SESSION_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {APP_SESSION_TYPE}"))
    for key in ("session_id", "run_id", "entrypoint", "mention", "mode", "user_goal_summary"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(ValidationIssue(f"$.{key}", f"{key} is required"))
    for key in ("session_id", "run_id"):
        if (
            isinstance(data.get(key), str)
            and data[key].strip()
            and not _is_safe_path_segment(data[key])
        ):
            issues.append(ValidationIssue(f"$.{key}", f"{key} must be a single path-safe segment"))
    selected_context_refs = data.get("selected_context_refs")
    if not isinstance(selected_context_refs, list):
        issues.append(ValidationIssue("$.selected_context_refs", "selected_context_refs must be a list"))
    else:
        for index, context_ref in enumerate(selected_context_refs):
            if not isinstance(context_ref, str) or not context_ref.strip():
                issues.append(ValidationIssue(f"$.selected_context_refs[{index}]", "context ref must be a non-empty string"))
    if not isinstance(data.get("approved_decisions_ref"), str) or not data["approved_decisions_ref"].strip():
        issues.append(ValidationIssue("$.approved_decisions_ref", "approved_decisions_ref is required"))
    if data.get("raw_transcript_stored") is not False:
        issues.append(ValidationIssue("$.raw_transcript_stored", "raw_transcript_stored must be false"))
    return issues


def validate_app_cards(data: dict[str, Any], session: dict[str, Any] | None = None) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != APP_CARDS_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {APP_CARDS_TYPE}"))
    for key in ("session_id", "run_id"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(ValidationIssue(f"$.{key}", f"{key} is required"))
    for key in ("session_id", "run_id"):
        if (
            isinstance(data.get(key), str)
            and data[key].strip()
            and not _is_safe_path_segment(data[key])
        ):
            issues.append(ValidationIssue(f"$.{key}", f"{key} must be a single path-safe segment"))
    if session:
        if data.get("session_id") != session.get("session_id"):
            issues.append(ValidationIssue("$.session_id", "cards session_id must match app-session.json"))
        if data.get("run_id") != session.get("run_id"):
            issues.append(ValidationIssue("$.run_id", "cards run_id must match app-session.json"))
    if data.get("raw_transcript_stored") is not False:
        issues.append(ValidationIssue("$.raw_transcript_stored", "raw_transcript_stored must be false"))

    cards = data.get("cards")
    if not isinstance(cards, list):
        return issues + [ValidationIssue("$.cards", "cards must be a list")]
    seen_types: set[str] = set()
    for index, card in enumerate(cards):
        path = f"$.cards[{index}]"
        if not isinstance(card, dict):
            issues.append(ValidationIssue(path, "card must be an object"))
            continue
        card_type = card.get("card_type")
        if card_type not in APP_CARD_TYPES:
            issues.append(
                ValidationIssue(f"{path}.card_type", "card_type must be harness_plan, matrix, report, or retune")
            )
        else:
            seen_types.add(str(card_type))
        for key in ("title", "summary"):
            if not isinstance(card.get(key), str) or not card[key].strip():
                issues.append(ValidationIssue(f"{path}.{key}", f"{key} is required"))
        artifact_refs = card.get("artifact_refs")
        if not isinstance(artifact_refs, list) or not artifact_refs:
            issues.append(ValidationIssue(f"{path}.artifact_refs", "artifact_refs must be a non-empty list"))
        else:
            for ref_index, artifact_ref in enumerate(artifact_refs):
                if not isinstance(artifact_ref, str) or not artifact_ref.strip():
                    issues.append(
                        ValidationIssue(
                            f"{path}.artifact_refs[{ref_index}]",
                            "artifact ref must be a non-empty string",
                        )
                    )
    missing = sorted(APP_CARD_TYPES - seen_types)
    if missing:
        issues.append(ValidationIssue("$.cards", "missing app card types: " + ", ".join(missing)))
    return issues


def validate_app_collection(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != APP_COLLECTION_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {APP_COLLECTION_TYPE}"))
    for key in ("session_id", "run_id", "app_session_path", "cards_path", "report_path", "retune_goal_path"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            issues.append(ValidationIssue(f"$.{key}", f"{key} is required"))
    if data.get("raw_transcript_stored") is not False:
        issues.append(ValidationIssue("$.raw_transcript_stored", "raw_transcript_stored must be false"))
    if not isinstance(data.get("card_count"), int) or data["card_count"] < 0:
        issues.append(ValidationIssue("$.card_count", "card_count must be a non-negative integer"))
    return issues


def validate_orchestrator(data: dict[str, Any]) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(data)
    if data.get("artifact_type") != ORCHESTRATOR_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {ORCHESTRATOR_TYPE}"))
    if data.get("executor") != LOCAL_RUNNER_EXECUTOR:
        issues.append(ValidationIssue("$.executor", f"executor must be {LOCAL_RUNNER_EXECUTOR}"))
    if data.get("raw_output_stored") is not False:
        issues.append(ValidationIssue("$.raw_output_stored", "raw_output_stored must be false"))
    if data.get("status") not in {"pass", "needs_retune", "fail"}:
        issues.append(ValidationIssue("$.status", "status must be pass, needs_retune, or fail"))
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        issues.append(ValidationIssue("$.steps", "steps must be a non-empty list"))
    else:
        for index, step in enumerate(steps):
            path = f"$.steps[{index}]"
            if not isinstance(step, dict):
                issues.append(ValidationIssue(path, "step must be an object"))
                continue
            for key in ("name", "status"):
                if not isinstance(step.get(key), str) or not step[key].strip():
                    issues.append(ValidationIssue(f"{path}.{key}", f"{key} is required"))
    return issues


def assert_valid(issues: list[ValidationIssue]) -> None:
    errors = [issue for issue in issues if issue.severity == "error"]
    if errors:
        raise ArtifactError(errors)


def _format_block(value: Any) -> str:
    if isinstance(value, list):
        return "\n".join(f"- {item}" for item in value)
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True)


def compile_goal(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    executor: str = DEFAULT_EXECUTOR,
    brief_file: Path | str | None = None,
    matrix_file: Path | str | None = None,
) -> dict[str, Path]:
    root_path = Path(root)
    brief = read_json(brief_file or intent_path(root_path))
    matrix = read_json(matrix_file or matrix_path(root_path))
    assert_valid(validate_brief(brief, mode))
    assert_valid(validate_matrix(matrix, mode))

    blocks = brief["blocks"]
    criteria_lines = []
    for criterion in matrix["criteria"]:
        hard_gate = "hard gate" if criterion.get("hard_gate") else "supporting"
        evidence = "; ".join(str(item) for item in criterion.get("evidence_required", []))
        criteria_lines.append(
            f"- {criterion['id']} ({hard_gate}): {criterion['check_question']} Evidence: {evidence}"
        )

    goal_text = f"""/goal Complete Rubricodex taskpack {run_id} using the bounded contract below.

## Purpose
{_format_block(blocks["purpose"])}

## Desired outcome
{_format_block(blocks["desired_outcome"])}

## Deliverable
{_format_block(blocks["deliverable_shape"])}

## Context
{_format_block(blocks["reference_context"])}

## Include
{_format_block(blocks["scope_in"])}

## Exclude
{_format_block(blocks["scope_out"])}

## Working rules
{_format_block(blocks["working_rules"])}

## Evaluation
{chr(10).join(criteria_lines)}

## Evidence
Store only summarized evidence references in `.rubricodex/runs/{run_id}/evidence.json`.
Do not store raw transcripts, raw task logs, or unredacted command output.

## Completion rule
Finish only when hard gates pass and the report can cite summarized evidence for every criterion.
If a hard gate is missing or fails, stop with a retune instruction instead of calling the task complete.

## Report back
Return the scorecard decision, evidence summary, and next retune instruction if any.
"""

    task_dir = taskpack_dir(root_path, run_id)
    goal_path = write_text(task_dir / "goal.md", goal_text)
    adapter_input = base_artifact("rubricodex.adapter_input", mode=mode, run_id=run_id)
    adapter_input.update(
        {
            "executor": executor,
            "brief_path": ".rubricodex/intent/brief.json",
            "matrix_path": ".rubricodex/matrix/evaluation-matrix.json",
            "goal_path": f".rubricodex/taskpacks/{run_id}/goal.md",
        }
    )
    adapter_path = write_json(task_dir / "adapter-input.json", adapter_input)
    lock_path = write_json(
        task_dir / "goal.lock.json",
        build_goal_lock(brief, matrix, goal_text, executor, mode, run_id),
    )
    return {"goal": goal_path, "adapter_input": adapter_path, "lock": lock_path}


def _lock_drift_severity(mode: str) -> str:
    return "warning" if mode in LIGHT_LOCK_MODES else "error"


def _locked_criteria_by_id(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    criteria = lock.get("locked_criteria")
    if not isinstance(criteria, list):
        return {}
    return {
        str(criterion.get("id")): criterion
        for criterion in criteria
        if isinstance(criterion, dict) and criterion.get("id")
    }


def _current_criteria_by_id(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    criteria = matrix.get("criteria")
    if not isinstance(criteria, list):
        return {}
    return {
        str(criterion.get("id")): criterion
        for criterion in criteria
        if isinstance(criterion, dict) and criterion.get("id")
    }


def validate_matrix_lock(
    lock: dict[str, Any],
    brief: dict[str, Any],
    matrix: dict[str, Any],
    goal_text: str,
    mode: str = DEFAULT_MODE,
) -> list[ValidationIssue]:
    issues = validate_forbidden_keys(lock)
    active_mode = mode or lock.get("mode") or matrix.get("mode") or DEFAULT_MODE
    drift_severity = _lock_drift_severity(active_mode)

    if lock.get("artifact_type") != GOAL_LOCK_TYPE:
        issues.append(ValidationIssue("$.artifact_type", f"artifact_type must be {GOAL_LOCK_TYPE}"))

    current_hashes = {
        "brief_sha256": stable_hash(brief),
        "matrix_sha256": stable_hash(matrix),
        "goal_sha256": stable_hash(goal_text),
        "guidance_sha256": stable_hash(guidance_fingerprint(str(lock.get("executor", DEFAULT_EXECUTOR)))),
    }
    for key, current_hash in current_hashes.items():
        if lock.get(key) != current_hash:
            issues.append(ValidationIssue(f"$.{key}", f"{key} changed after lock", drift_severity))

    locked_scope = lock.get("locked_scope")
    current_scope = scope_fingerprint(brief)
    if not isinstance(locked_scope, dict):
        issues.append(ValidationIssue("$.locked_scope", "lock is missing scope fingerprint", drift_severity))
    elif locked_scope != current_scope:
        issues.append(ValidationIssue("$.locked_scope", "scope changed after lock", drift_severity))

    locked_criteria = _locked_criteria_by_id(lock)
    current_criteria = _current_criteria_by_id(matrix)
    if not locked_criteria:
        issues.append(ValidationIssue("$.locked_criteria", "lock is missing criteria fingerprint", drift_severity))

    for criterion_id, locked in locked_criteria.items():
        current = current_criteria.get(criterion_id)
        if current is None:
            issues.append(ValidationIssue(f"$.locked_criteria.{criterion_id}", "criterion was removed after lock"))
            continue

        if locked.get("hard_gate") is True and current.get("hard_gate") is not True:
            issues.append(ValidationIssue(f"$.criteria.{criterion_id}.hard_gate", "hard gate was weakened after lock"))

        locked_evidence = {
            str(item)
            for item in locked.get("evidence_required", [])
            if str(item).strip()
        }
        current_evidence = {
            str(item)
            for item in current.get("evidence_required", [])
            if str(item).strip()
        }
        missing_evidence = sorted(locked_evidence - current_evidence)
        if missing_evidence:
            issues.append(
                ValidationIssue(
                    f"$.criteria.{criterion_id}.evidence_required",
                    "evidence_required was removed after lock: " + ", ".join(missing_evidence),
                )
            )

    evaluation_text = _section_content(goal_text, "Evaluation") or ""
    for criterion_id in current_criteria:
        if criterion_id not in evaluation_text:
            issues.append(ValidationIssue(f"$.goal.{criterion_id}", f"goal.md is missing criterion {criterion_id}"))
    return issues


def _is_unsafe_lock_issue(issue: ValidationIssue) -> bool:
    return issue.message.startswith(
        (
            "criterion was removed",
            "hard gate was weakened",
            "evidence_required was removed",
            "goal.md is missing criterion",
        )
    )


def verify_matrix_lock(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    revision_reason: str | None = None,
    brief_file: Path | str | None = None,
    matrix_file: Path | str | None = None,
    goal_file: Path | str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    lock_path = goal_lock_path(root_path, run_id)
    lock = read_json(lock_path)
    brief = read_json(brief_file or intent_path(root_path))
    matrix = read_json(matrix_file or matrix_path(root_path))
    goal_path = Path(goal_file) if goal_file else taskpack_dir(root_path, run_id) / "goal.md"
    goal_text = goal_path.read_text(encoding="utf-8")

    assert_valid(validate_brief(brief, mode))
    assert_valid(validate_matrix(matrix, mode))
    assert_valid(lint_goal_text(goal_text, mode))

    issues = validate_matrix_lock(lock, brief, matrix, goal_text, mode)
    errors = [issue for issue in issues if issue.severity == "error"]
    revision_reason = revision_reason.strip() if revision_reason else None
    revision_approved = False

    if errors and revision_reason and not any(_is_unsafe_lock_issue(issue) for issue in errors):
        executor = str(lock.get("executor", DEFAULT_EXECUTOR))
        updated_lock = build_goal_lock(brief, matrix, goal_text, executor, mode, run_id, revision_reason)
        write_json(lock_path, updated_lock)
        issues = []
        errors = []
        revision_approved = True

    result = base_artifact(MATRIX_LOCK_RESULT_TYPE, mode=mode, run_id=run_id)
    result.update(
        {
            "status": "pass" if not errors else "fail",
            "revision_approved": revision_approved,
            "lock_path": str(lock_path),
            "issues": [issue.as_dict() for issue in issues],
        }
    )
    return result


def _section_content(text: str, heading: str) -> str | None:
    lines = text.splitlines()
    marker = f"## {heading}"
    start: int | None = None
    for index, line in enumerate(lines):
        if line.strip() == marker:
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def lint_goal_text(text: str, mode: str = DEFAULT_MODE) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not text.lstrip().startswith("/goal"):
        issues.append(ValidationIssue("$", "goal prompt must start with /goal"))
    for heading in GOAL_HEADINGS:
        content = _section_content(text, heading)
        if content is None:
            issues.append(ValidationIssue(f"$.{heading}", f"missing section: {heading}"))
        elif not content:
            issues.append(ValidationIssue(f"$.{heading}", f"empty section: {heading}"))
    if mode in {"standard", "strict"} and _section_content(text, "Completion rule") in (None, ""):
        issues.append(ValidationIssue("$.Completion rule", "standard mode requires a completion rule"))
    return issues


def lint_goal_file(root: Path | str, run_id: str, mode: str = DEFAULT_MODE, goal_file: Path | str | None = None) -> dict[str, Any]:
    goal_path = Path(goal_file) if goal_file else taskpack_dir(root, run_id) / "goal.md"
    text = goal_path.read_text(encoding="utf-8")
    issues = lint_goal_text(text, mode)
    result = base_artifact("rubricodex.prompt_lint", mode=mode, run_id=run_id)
    result.update({"status": "pass" if not issues else "fail", "issues": [issue.as_dict() for issue in issues]})
    write_json(taskpack_dir(root, run_id) / "prompt-lint.json", result)
    return result


def _relative_artifact_path(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _assert_local_runner_ready(root: Path, run_id: str, mode: str) -> None:
    goal_path = taskpack_dir(root, run_id) / "goal.md"
    prompt_lint_path = taskpack_dir(root, run_id) / "prompt-lint.json"
    issues: list[ValidationIssue] = []
    if not goal_path.is_file():
        issues.append(ValidationIssue("$.goal", f"goal.md is missing at {goal_path}"))
    if not prompt_lint_path.is_file():
        issues.append(ValidationIssue("$.prompt_lint", f"prompt-lint.json is missing at {prompt_lint_path}"))
    if issues:
        raise ArtifactError(issues)

    prompt_lint = read_json(prompt_lint_path)
    if prompt_lint.get("status") != "pass":
        raise ArtifactError([ValidationIssue("$.prompt_lint.status", "prompt-lint.json must have status pass")])

    lock_result = verify_matrix_lock(root, run_id, mode=mode)
    if lock_result["status"] != "pass":
        raise ArtifactError(
            [
                ValidationIssue(
                    issue.get("path", "$.matrix_lock"),
                    issue.get("message", "matrix lock failed"),
                    issue.get("severity", "error"),
                )
                for issue in lock_result["issues"]
            ]
        )


def _summarize_changed_files(root: Path) -> list[str]:
    try:
        completed = subprocess.run(
            ["git", "status", "--short"],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    files: list[str] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        files.append(line[3:].strip())
    return files


def _missing_evidence(matrix: dict[str, Any], manifest_ref: str, mode: str, run_id: str) -> dict[str, Any]:
    evidence = base_artifact(EVIDENCE_TYPE, mode=mode, run_id=run_id)
    evidence.update(
        {
            "executor": LOCAL_RUNNER_EXECUTOR,
            "raw_output_stored": False,
            "runner_manifest_path": manifest_ref,
            "runner_summary": "Local runner prepared the Codex CLI handoff; criterion evidence still needs implementation verification.",
            "evidence_items": [
                {
                    "id": f"E-{criterion['id']}",
                    "criterion_id": criterion["id"],
                    "kind": "runner",
                    "summary": "Local runner created the handoff manifest; explicit verification evidence is still missing.",
                    "artifact_refs": [manifest_ref],
                    "status": "missing_evidence",
                    "confidence": 0.0,
                }
                for criterion in matrix.get("criteria", [])
                if isinstance(criterion, dict) and criterion.get("id")
            ],
        }
    )
    return evidence


def run_local(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    execute: bool = False,
    codex_bin: str = "codex",
    result_summary: str | None = None,
    verification_commands: list[str] | None = None,
    changed_files: list[str] | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    _assert_local_runner_ready(root_path, run_id, mode)

    matrix = read_json(matrix_path(root_path))
    assert_valid(validate_matrix(matrix, mode))
    manifest_path = run_manifest_path(root_path, run_id)
    manifest_ref = _relative_artifact_path(manifest_path, root_path)
    execution_mode = "execute" if execute else "dry_run"
    command = f"{codex_bin} exec --cd <project-root> -"
    command_result: dict[str, Any]
    status = "pass"

    if execute:
        goal_text = (taskpack_dir(root_path, run_id) / "goal.md").read_text(encoding="utf-8")
        completed = subprocess.run(
            [codex_bin, "exec", "--cd", str(root_path), "-"],
            input=goal_text,
            capture_output=True,
            text=True,
            check=False,
        )
        command_result = {
            "command": command,
            "exit_code": completed.returncode,
            "summary": f"Codex CLI exited with code {completed.returncode}; raw output discarded.",
        }
        default_summary = f"Codex CLI local execution exited with code {completed.returncode}."
        changed_files = changed_files or _summarize_changed_files(root_path)
        if completed.returncode != 0:
            status = "fail"
    else:
        command_result = {
            "command": command,
            "exit_code": None,
            "summary": "Dry-run only; Codex CLI was not executed and goal.md remains the fallback handoff.",
        }
        default_summary = "Prepared Codex CLI local runner handoff without executing external commands."

    manifest = base_artifact(RUN_MANIFEST_TYPE, mode=mode, run_id=run_id)
    manifest.update(
        {
            "executor": LOCAL_RUNNER_EXECUTOR,
            "execution_mode": execution_mode,
            "goal_path": f".rubricodex/taskpacks/{run_id}/goal.md",
            "prompt_lint_path": f".rubricodex/taskpacks/{run_id}/prompt-lint.json",
            "matrix_lock_path": f".rubricodex/taskpacks/{run_id}/goal.lock.json",
            "raw_output_stored": False,
            "result_summary": result_summary or default_summary,
            "command_results": [command_result],
            "changed_files": changed_files or [],
            "verification_commands": verification_commands or [],
            "fallback_goal_exported": not execute,
        }
    )
    assert_valid(validate_run_manifest(manifest))
    write_json(manifest_path, manifest)

    evidence_path = run_dir(root_path, run_id) / "evidence.json"
    if evidence_path.exists():
        evidence = read_json(evidence_path)
        evidence["runner_manifest_path"] = manifest_ref
        evidence["runner_summary"] = manifest["result_summary"]
        evidence["raw_output_stored"] = False
    else:
        evidence = _missing_evidence(matrix, manifest_ref, mode, run_id)
    assert_valid(validate_evidence(evidence, matrix))
    write_json(evidence_path, evidence)

    return {
        "status": status,
        "execution_mode": execution_mode,
        "manifest_path": str(manifest_path),
        "evidence_path": str(evidence_path),
    }


def _criterion_lookup(matrix: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(criterion["id"]): criterion
        for criterion in matrix.get("criteria", [])
        if isinstance(criterion, dict) and criterion.get("id")
    }


def _probe_prompt(run_id: str, criterion: dict[str, Any]) -> str:
    evidence = "\n".join(f"- {item}" for item in criterion.get("evidence_required", []))
    return f"""/goal Read-only Rubricodex probe for {criterion['id']} in taskpack {run_id}.

## Criterion
- ID: {criterion['id']}
- Name: {criterion['name']}
- Check: {criterion['check_question']}

## Required evidence
{evidence}

## Read-only policy
Do not modify files.
Do not run destructive commands.
Do not store raw transcripts, raw task logs, stdout, stderr, or unredacted command output.

## Report back
Return a concise summary, one of probe_pass/probe_failure/probe_error, and summarized evidence references only.
"""


def plan_probes(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    criterion_ids: list[str] | None = None,
    include_supporting: bool = False,
    parallel: int = 4,
) -> dict[str, Any]:
    root_path = Path(root)
    _assert_local_runner_ready(root_path, run_id, mode)
    matrix = read_json(matrix_path(root_path))
    assert_valid(validate_matrix(matrix, mode))

    requested = {criterion_id for criterion_id in (criterion_ids or []) if criterion_id.strip()}
    criteria_by_id = _criterion_lookup(matrix)
    unknown = sorted(requested - set(criteria_by_id))
    if unknown:
        raise ArtifactError([ValidationIssue("$.criterion_ids", "unknown criterion ids: " + ", ".join(unknown))])

    selected: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for criterion in matrix["criteria"]:
        criterion_id = criterion["id"]
        hard_gate = bool(criterion.get("hard_gate"))
        should_select = include_supporting or hard_gate or criterion_id in requested
        if should_select:
            prompt_path = probe_prompt_path(root_path, run_id, criterion_id)
            write_text(prompt_path, _probe_prompt(run_id, criterion))
            selected.append(
                {
                    "criterion_id": criterion_id,
                    "prompt_path": _relative_artifact_path(prompt_path, root_path),
                    "selection_reason": "hard_gate" if hard_gate else "explicit_request" if criterion_id in requested else "include_supporting",
                    "read_only": True,
                }
            )
        else:
            skipped.append(
                {
                    "criterion_id": criterion_id,
                    "skip_reason": "supporting criterion skipped by default selective policy",
                }
            )

    plan = base_artifact(PROBE_PLAN_TYPE, mode=mode, run_id=run_id)
    plan.update(
        {
            "executor": LOCAL_RUNNER_EXECUTOR,
            "parallel": parallel,
            "raw_output_stored": False,
            "selected_probes": selected,
            "skipped_probes": skipped,
        }
    )
    assert_valid(validate_probe_plan(plan))
    plan_path = write_json(probe_plan_path(root_path, run_id), plan)
    return {
        "status": "pass",
        "probe_plan_path": str(plan_path),
        "selected": [probe["criterion_id"] for probe in selected],
        "skipped": [probe["criterion_id"] for probe in skipped],
    }


def _probe_result(
    root: Path,
    run_id: str,
    mode: str,
    criterion_id: str,
    status: str,
    summary: str,
    exit_code: int | None = None,
) -> dict[str, Any]:
    result = base_artifact(PROBE_RESULT_TYPE, mode=mode, run_id=run_id)
    result.update(
        {
            "criterion_id": criterion_id,
            "status": status,
            "summary": summary,
            "read_only": True,
            "raw_output_stored": False,
            "prompt_path": _relative_artifact_path(probe_prompt_path(root, run_id, criterion_id), root),
        }
    )
    if exit_code is not None:
        result["exit_code"] = exit_code
    return result


def run_probes(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    parallel: int = 4,
    execute: bool = False,
    codex_bin: str = "codex",
) -> dict[str, Any]:
    root_path = Path(root)
    if parallel < 1:
        raise ArtifactError([ValidationIssue("$.parallel", "parallel must be greater than zero")])
    plan = read_json(probe_plan_path(root_path, run_id))
    assert_valid(validate_probe_plan(plan))

    status = "pass"
    result_paths: list[str] = []
    for probe in plan["selected_probes"]:
        criterion_id = probe["criterion_id"]
        if execute:
            prompt = probe_prompt_path(root_path, run_id, criterion_id).read_text(encoding="utf-8")
            completed = subprocess.run(
                [codex_bin, "exec", "--cd", str(root_path), "-"],
                input=prompt,
                capture_output=True,
                text=True,
                check=False,
            )
            if completed.returncode == 0:
                probe_result = _probe_result(
                    root_path,
                    run_id,
                    mode,
                    criterion_id,
                    "probe_pass",
                    "Probe command exited successfully; raw output discarded.",
                    exit_code=0,
                )
            else:
                status = "fail"
                probe_result = _probe_result(
                    root_path,
                    run_id,
                    mode,
                    criterion_id,
                    "probe_error",
                    f"Probe command exited with code {completed.returncode}; raw output discarded.",
                    exit_code=completed.returncode,
                )
        else:
            probe_result = _probe_result(
                root_path,
                run_id,
                mode,
                criterion_id,
                "probe_skipped",
                "Dry-run only; read-only probe prompt was generated but not executed.",
            )
        assert_valid(validate_probe_result(probe_result))
        path = write_json(probe_result_path(root_path, run_id, criterion_id), probe_result)
        result_paths.append(str(path))

    return {
        "status": status,
        "parallel": parallel,
        "probe_results": result_paths,
    }


def _criterion_reason(criterion: dict[str, Any], status: str, items: list[dict[str, Any]]) -> str:
    if not items:
        reason = "No summarized evidence item was recorded for this criterion."
    else:
        summaries = "; ".join(str(item["summary"]) for item in items if str(item.get("summary", "")).strip())
        if status == "pass":
            reason = "Summarized evidence satisfies the criterion."
        elif status == "partial":
            reason = "Evidence is present but incomplete."
        elif status == "missing_evidence":
            reason = "Required evidence is missing or explicitly marked missing."
        else:
            reason = "Evidence indicates the criterion failed."
        if summaries:
            reason = f"{reason} Evidence summary: {summaries}"
    if criterion.get("hard_gate") and status != "pass":
        reason = f"Hard gate blocked. {reason}"
    return reason


def compute_scorecard(
    root: Path | str,
    run_id: str,
    evidence_file: Path | str | None = None,
    matrix_file: Path | str | None = None,
) -> dict[str, Any]:
    root_path = Path(root)
    matrix = read_json(matrix_file or matrix_path(root_path))
    evidence = read_json(evidence_file or run_dir(root_path, run_id) / "evidence.json")
    assert_valid(validate_matrix(matrix, matrix.get("mode")))
    assert_valid(validate_evidence(evidence, matrix))

    items_by_criterion: dict[str, list[dict[str, Any]]] = {}
    for item in evidence["evidence_items"]:
        items_by_criterion.setdefault(item["criterion_id"], []).append(item)

    counts = {"pass": 0, "partial": 0, "missing_evidence": 0, "fail": 0}
    results: list[dict[str, Any]] = []
    hard_gate_problem = False
    scope_out_drift = False
    non_hard_partial = False
    non_hard_fail = False

    for criterion in matrix["criteria"]:
        items = items_by_criterion.get(criterion["id"], [])
        if not items:
            status = "missing_evidence"
        else:
            status = max((item.get("status", "pass") for item in items), key=lambda item_status: STATUS_ORDER[item_status])
        counts[status] += 1

        if any(item.get("scope_out_drift") is True for item in items):
            scope_out_drift = True
        if criterion.get("hard_gate") and status != "pass":
            hard_gate_problem = True
        elif status == "partial":
            non_hard_partial = True
        elif status in {"missing_evidence", "fail"}:
            non_hard_fail = True

        results.append(
            {
                "criterion_id": criterion["id"],
                "name": criterion["name"],
                "hard_gate": bool(criterion.get("hard_gate")),
                "status": status,
                "evidence_refs": [
                    ref
                    for item in items
                    for ref in item.get("artifact_refs", [])
                ],
                "evidence_summaries": [
                    item["summary"]
                    for item in items
                    if isinstance(item.get("summary"), str) and item["summary"].strip()
                ],
                "reason": _criterion_reason(criterion, status, items),
                "retune_hint": criterion["retune_hint"],
            }
        )

    if scope_out_drift:
        decision = "fail"
    elif hard_gate_problem or non_hard_fail:
        decision = "needs_retune"
    elif non_hard_partial:
        decision = "pass_with_warnings"
    else:
        decision = "pass"

    scorecard = base_artifact(SCORECARD_TYPE, mode=matrix.get("mode", DEFAULT_MODE), run_id=run_id)
    scorecard.update(
        {
            "scoring_model": "counts-v0.1",
            "decision": decision,
            "counts": counts,
            "results": results,
        }
    )
    assert_valid(validate_scorecard(scorecard))
    write_json(run_dir(root_path, run_id) / "scorecard.json", scorecard)
    return scorecard


def write_report(root: Path | str, run_id: str) -> dict[str, Path]:
    root_path = Path(root)
    scorecard = read_json(run_dir(root_path, run_id) / "scorecard.json")
    assert_valid(validate_scorecard(scorecard))
    retune_results = [result for result in scorecard["results"] if result["status"] in RETUNE_STATUSES]
    passed_results = [result for result in scorecard["results"] if result["status"] == "pass"]
    hard_gate_results = [result for result in retune_results if result.get("hard_gate")]
    retune_ids = ", ".join(result["criterion_id"] for result in retune_results) or "none"
    passed_ids = ", ".join(result["criterion_id"] for result in passed_results) or "none"
    report_lines = [
        "# Rubricodex Report",
        "",
        "## Summary",
        f"- Decision: {scorecard['decision']}",
        f"- Scoring model: {scorecard['scoring_model']}",
        f"- Counts: pass={scorecard['counts']['pass']}, partial={scorecard['counts']['partial']}, missing={scorecard['counts']['missing_evidence']}, fail={scorecard['counts']['fail']}",
        f"- Retune targets: {retune_ids}",
        f"- Preserved pass criteria: {passed_ids}",
    ]
    if hard_gate_results:
        report_lines.append(
            "- Hard gate alert: "
            + "; ".join(f"{result['criterion_id']} {result['name']} is {result['status']}" for result in hard_gate_results)
        )
    else:
        report_lines.append("- Hard gate alert: none")
    report_lines.extend(
        [
            "",
            "## Criteria",
        ]
    )
    for result in scorecard["results"]:
        line = f"- {result['criterion_id']} {result['name']}: {result['status']}. Reason: {result.get('reason', 'No reason recorded.')}"
        if result.get("evidence_refs"):
            line += " Evidence: " + ", ".join(str(ref) for ref in result["evidence_refs"])
        if result["status"] in RETUNE_STATUSES:
            line += f" Retune: {result['retune_hint']}"
        report_lines.append(line)

    probe_plan_file = probe_plan_path(root_path, run_id)
    if probe_plan_file.exists():
        probe_plan = read_json(probe_plan_file)
        assert_valid(validate_probe_plan(probe_plan))
        report_lines.extend(["", "## Probes"])
        if probe_plan["selected_probes"]:
            for probe in probe_plan["selected_probes"]:
                criterion_id = probe["criterion_id"]
                result_file = probe_result_path(root_path, run_id, criterion_id)
                if result_file.exists():
                    probe_result = read_json(result_file)
                    assert_valid(validate_probe_result(probe_result))
                    report_lines.append(f"- {criterion_id}: {probe_result['status']}")
                else:
                    report_lines.append(f"- {criterion_id}: planned")
        else:
            report_lines.append("- No probes selected.")
        for probe in probe_plan["skipped_probes"]:
            report_lines.append(f"- {probe['criterion_id']} skipped: {probe['skip_reason']}")

    report_lines.extend(["", "## Next action"])
    if retune_results:
        report_lines.append("Run the retune goal for failed, partial, or missing-evidence criteria only.")
    else:
        report_lines.append("No retune instruction required.")
    report_lines.extend(
        [
            "",
            "## App actions",
            "- retune_failed_criteria: use retune_goal.md for the listed targets only.",
            "- review_current_diff: inspect the current implementation before changing preserved pass criteria.",
            "- mark_manual_evidence: attach summarized evidence without storing raw output.",
        ]
    )
    report_path = write_text(run_dir(root_path, run_id) / "report.md", "\n".join(report_lines) + "\n")

    retune_lines = [
        f"/goal Retune Rubricodex run {run_id} by fixing only the listed criteria.",
        "",
        "## Purpose",
        "Fix only criteria marked failed, partial, or missing_evidence in the current Rubricodex scorecard.",
        "",
        "## Desired outcome",
        "The listed criteria gain summarized evidence while criteria already marked pass remain unchanged.",
        "",
        "## Deliverable",
        "A small patch or evidence update plus refreshed evidence, scorecard, report, and retune artifacts.",
        "",
        "## Context",
        f"- Run id: {run_id}",
        f"- Current decision: {scorecard['decision']}",
        f"- Retune targets: {retune_ids}",
        "",
        "## Include",
    ]
    if retune_results:
        for result in retune_results:
            retune_lines.append(f"- {result['criterion_id']} {result['name']}: {result['status']}. {result['retune_hint']}")
    else:
        retune_lines.append("- No criteria require retune.")
    retune_lines.extend(
        [
            "",
            "## Exclude",
            "- Do not rework criteria already marked pass:",
        ]
    )
    if passed_results:
        retune_lines.extend(f"  - {result['criterion_id']} {result['name']}" for result in passed_results)
    else:
        retune_lines.append("  - None")
    retune_lines.extend(
        [
            "- Do not store raw transcripts, raw logs, or unredacted command output.",
            "",
            "## Working rules",
            "- Keep the retune patch limited to the Include criteria.",
            "- Preserve existing behavior that supports Exclude criteria.",
            "- Store only summarized evidence references.",
            "",
            "## Evaluation",
        ]
    )
    if retune_results:
        for result in retune_results:
            retune_lines.append(f"- {result['criterion_id']}: {result.get('reason', 'No reason recorded.')}")
    else:
        retune_lines.append("- No failed, partial, or missing_evidence criteria remain.")
    retune_lines.extend(
        [
            "",
            "## Evidence",
            "- Update summarized evidence references for the Include criteria only.",
            "- Do not store raw command output, raw task logs, or chat transcripts.",
            "",
            "## Completion rule",
            "- Stop when every Include criterion passes or when a hard gate remains blocked with a clear reason.",
            "",
            "## Report back",
            "- Summarize changed files, evidence references, remaining blockers, and preserved pass criteria.",
            "",
        ]
    )
    retune_text = "\n".join(retune_lines)
    assert_valid(lint_goal_text(retune_text, scorecard.get("mode", DEFAULT_MODE)))
    retune_path = write_text(run_dir(root_path, run_id) / "retune_goal.md", retune_text)
    return {"report": report_path, "retune": retune_path}


def _find_app_session_for_run(root: Path, run_id: str) -> tuple[dict[str, Any], Path]:
    sessions_dir = artifact_root(root) / "app" / "sessions"
    if not sessions_dir.exists():
        raise ArtifactError([ValidationIssue("$.app.sessions", "app sessions directory is missing")])
    matches: list[tuple[dict[str, Any], Path]] = []
    for path in sorted(sessions_dir.glob("*/app-session.json")):
        session = read_json(path)
        if session.get("run_id") == run_id:
            matches.append((session, path))
    if not matches:
        raise ArtifactError([ValidationIssue("$.run_id", f"no app session found for run_id {run_id}")])
    if len(matches) > 1:
        raise ArtifactError([ValidationIssue("$.run_id", f"multiple app sessions found for run_id {run_id}")])
    return matches[0]


def import_app_session(root: Path | str, source_file: Path | str, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    root_path = Path(root)
    source = Path(source_file)
    session = read_json(source)
    assert_valid(validate_app_session(session))
    run_id = str(session["run_id"])
    target = app_session_path(root_path, str(session["session_id"]))
    if source.resolve() != target.resolve():
        write_json(target, session)
    import_artifact = base_artifact("rubricodex.app_session_import", mode=mode, run_id=run_id)
    import_artifact.update(
        {
            "session_id": session["session_id"],
            "app_session_path": _relative_artifact_path(target, root_path),
            "raw_transcript_stored": False,
        }
    )
    import_path = write_json(run_dir(root_path, run_id) / "app-session-import.json", import_artifact)
    return {
        "status": "pass",
        "run_id": run_id,
        "session_id": session["session_id"],
        "app_session_path": str(target),
        "import_path": str(import_path),
    }


def _validate_app_card_shared_refs(
    cards: dict[str, Any],
    report_ref: str,
    retune_ref: str,
) -> list[ValidationIssue]:
    card_items = cards.get("cards")
    if not isinstance(card_items, list):
        return []
    card_refs: dict[str, set[str]] = {}
    for card in card_items:
        if not isinstance(card, dict):
            continue
        card_type = card.get("card_type")
        artifact_refs = card.get("artifact_refs")
        if not isinstance(card_type, str) or not isinstance(artifact_refs, list):
            continue
        card_refs[card_type] = {artifact_ref for artifact_ref in artifact_refs if isinstance(artifact_ref, str)}
    issues: list[ValidationIssue] = []
    if report_ref not in card_refs.get("report", set()):
        issues.append(ValidationIssue("$.cards.report.artifact_refs", f"report card must reference {report_ref}"))
    if retune_ref not in card_refs.get("retune", set()):
        issues.append(ValidationIssue("$.cards.retune.artifact_refs", f"retune card must reference {retune_ref}"))
    return issues


def collect_app_artifacts(root: Path | str, run_id: str, mode: str = DEFAULT_MODE) -> dict[str, Any]:
    root_path = Path(root)
    session, session_file = _find_app_session_for_run(root_path, run_id)
    assert_valid(validate_app_session(session))
    cards_file = app_cards_path(root_path, str(session["session_id"]))
    if not cards_file.is_file():
        raise ArtifactError([ValidationIssue("$.cards_path", f"cards.json is missing at {cards_file}")])
    cards = read_json(cards_file)
    assert_valid(validate_app_cards(cards, session))

    report = run_dir(root_path, run_id) / "report.md"
    retune = run_dir(root_path, run_id) / "retune_goal.md"
    report_ref = _relative_artifact_path(report, root_path)
    retune_ref = _relative_artifact_path(retune, root_path)
    link_issues = _validate_app_card_shared_refs(cards, report_ref, retune_ref)
    if link_issues:
        raise ArtifactError(link_issues)

    missing = [str(path) for path in (report, retune) if not path.exists()]
    if missing:
        raise ArtifactError([ValidationIssue("$.app_collection", "missing shared artifacts: " + ", ".join(missing))])

    collection = base_artifact(APP_COLLECTION_TYPE, mode=mode, run_id=run_id)
    collection.update(
        {
            "session_id": session["session_id"],
            "app_session_path": _relative_artifact_path(session_file, root_path),
            "cards_path": _relative_artifact_path(cards_file, root_path),
            "report_path": report_ref,
            "retune_goal_path": retune_ref,
            "card_count": len(cards["cards"]),
            "raw_transcript_stored": False,
        }
    )
    assert_valid(validate_app_collection(collection))
    path = write_json(app_collection_path(root_path, run_id), collection)
    return {
        "status": "pass",
        "app_collection_path": str(path),
        "card_count": collection["card_count"],
        "report_path": str(report),
        "retune_goal_path": str(retune),
    }


def _artifact_exists(root: Path, relative_path: str) -> bool:
    return (root / relative_path).exists()


def orchestrate_status(root: Path | str, run_id: str) -> dict[str, Any]:
    root_path = Path(root)
    required = {
        "goal": f".rubricodex/taskpacks/{run_id}/goal.md",
        "prompt_lint": f".rubricodex/taskpacks/{run_id}/prompt-lint.json",
        "matrix_lock": f".rubricodex/taskpacks/{run_id}/goal.lock.json",
        "run_manifest": f".rubricodex/runs/{run_id}/run-manifest.json",
        "evidence": f".rubricodex/runs/{run_id}/evidence.json",
        "scorecard": f".rubricodex/runs/{run_id}/scorecard.json",
        "report": f".rubricodex/runs/{run_id}/report.md",
        "retune_goal": f".rubricodex/runs/{run_id}/retune_goal.md",
        "orchestrator": f".rubricodex/runs/{run_id}/orchestrator.json",
    }
    app_session_required = False
    app_session: dict[str, Any] | None = None
    app_session_file: Path | None = None
    app_cards_file: Path | None = None
    app_card_count: int | None = None
    status_issues: list[ValidationIssue] = []
    if (artifact_root(root_path) / "app" / "sessions").exists():
        try:
            session, session_file = _find_app_session_for_run(root_path, run_id)
            app_session_required = True
            app_session = session
            app_session_file = session_file
            required["app_collection"] = f".rubricodex/runs/{run_id}/app-collection.json"
            status_issues.extend(validate_app_session(session))
            cards_file = app_cards_path(root_path, str(session.get("session_id", "")))
            app_cards_file = cards_file
            if cards_file.is_file():
                cards = read_json(cards_file)
                status_issues.extend(validate_app_cards(cards, session))
                card_items = cards.get("cards")
                if isinstance(card_items, list):
                    app_card_count = len(card_items)
                status_issues.extend(
                    _validate_app_card_shared_refs(
                        cards,
                        required["report"],
                        required["retune_goal"],
                    )
                )
            else:
                status_issues.append(ValidationIssue("$.cards_path", f"cards.json is missing at {cards_file}"))
        except ArtifactError as error:
            no_session = any(
                issue.path == "$.run_id" and issue.message.startswith("no app session")
                for issue in error.issues
            )
            if not no_session:
                status_issues.extend(error.issues)
    missing = [name for name, path in required.items() if not _artifact_exists(root_path, path)]
    decision = None
    orchestration_status = None
    if "scorecard" not in missing:
        scorecard = read_json(run_dir(root_path, run_id) / "scorecard.json")
        assert_valid(validate_scorecard(scorecard))
        decision = scorecard.get("decision")
    if "orchestrator" not in missing:
        orchestration = read_json(orchestrator_path(root_path, run_id))
        assert_valid(validate_orchestrator(orchestration))
        orchestration_status = orchestration.get("status")
    if app_session_required and "app_collection" not in missing:
        app_collection = read_json(app_collection_path(root_path, run_id))
        status_issues.extend(validate_app_collection(app_collection))
        if app_collection.get("report_path") != required["report"]:
            status_issues.append(
                ValidationIssue("$.app_collection.report_path", f"app collection must reference {required['report']}")
            )
        if app_collection.get("retune_goal_path") != required["retune_goal"]:
            status_issues.append(
                ValidationIssue(
                    "$.app_collection.retune_goal_path",
                    f"app collection must reference {required['retune_goal']}",
                )
            )
        if app_session is not None and app_collection.get("session_id") != app_session.get("session_id"):
            status_issues.append(
                ValidationIssue(
                    "$.app_collection.session_id",
                    f"app collection session_id must match {app_session.get('session_id')}",
                )
            )
        if app_session_file is not None:
            expected_session_path = _relative_artifact_path(app_session_file, root_path)
            if app_collection.get("app_session_path") != expected_session_path:
                status_issues.append(
                    ValidationIssue(
                        "$.app_collection.app_session_path",
                        f"app collection must reference {expected_session_path}",
                    )
                )
        if app_cards_file is not None:
            expected_cards_path = _relative_artifact_path(app_cards_file, root_path)
            if app_collection.get("cards_path") != expected_cards_path:
                status_issues.append(
                    ValidationIssue(
                        "$.app_collection.cards_path",
                        f"app collection must reference {expected_cards_path}",
                    )
                )
        if app_card_count is not None and app_collection.get("card_count") != app_card_count:
            status_issues.append(
                ValidationIssue(
                    "$.app_collection.card_count",
                    f"app collection card_count must be {app_card_count}",
                )
            )
    if orchestration_status == "fail" or status_issues:
        status = "fail"
    elif missing:
        status = "incomplete"
    else:
        status = "complete"
    return {
        "status": status,
        "run_id": run_id,
        "decision": decision,
        "orchestration_status": orchestration_status,
        "missing": missing,
        "issues": [issue.as_dict() for issue in status_issues],
        "report_path": required["report"],
        "retune_goal_path": required["retune_goal"],
        "app_collection_path": str(app_collection_path(root_path, run_id)),
        "orchestrator_path": str(orchestrator_path(root_path, run_id)),
    }


def orchestrate_run(
    root: Path | str,
    run_id: str,
    mode: str = DEFAULT_MODE,
    backend: str = LOCAL_RUNNER_EXECUTOR,
    parallel: int = 4,
    execute: bool = False,
    codex_bin: str = "codex",
) -> dict[str, Any]:
    if backend != LOCAL_RUNNER_EXECUTOR:
        raise ArtifactError([ValidationIssue("$.backend", f"backend must be {LOCAL_RUNNER_EXECUTOR}")])
    root_path = Path(root)
    steps: list[dict[str, str]] = []

    lock = verify_matrix_lock(root_path, run_id, mode=mode)
    steps.append({"name": "matrix_lock", "status": lock["status"]})
    if lock["status"] != "pass":
        status = "fail"
    else:
        run_result = run_local(
            root_path,
            run_id,
            mode=mode,
            execute=execute,
            codex_bin=codex_bin,
        )
        steps.append({"name": "run_local", "status": run_result["status"]})
        if run_result["status"] != "pass":
            status = "fail"
        else:
            probe_plan = plan_probes(root_path, run_id, mode=mode, parallel=parallel)
            steps.append({"name": "probe_plan", "status": probe_plan["status"]})
            probe_run = run_probes(
                root_path,
                run_id,
                mode=mode,
                parallel=parallel,
                execute=execute,
                codex_bin=codex_bin,
            )
            steps.append({"name": "probe_run", "status": probe_run["status"]})
            probe_failed = probe_run["status"] != "pass"
            scorecard = compute_scorecard(root_path, run_id)
            steps.append({"name": "score_compute", "status": "pass"})
            write_report(root_path, run_id)
            steps.append({"name": "report", "status": "pass"})

            app_collect_failed = False
            if (artifact_root(root_path) / "app" / "sessions").exists():
                try:
                    collect_app_artifacts(root_path, run_id, mode=mode)
                    steps.append({"name": "app_collect", "status": "pass"})
                except ArtifactError as error:
                    no_session = any(
                        issue.path == "$.run_id" and issue.message.startswith("no app session")
                        for issue in error.issues
                    )
                    steps.append({"name": "app_collect", "status": "skipped" if no_session else "fail"})
                    app_collect_failed = not no_session

            if probe_failed or app_collect_failed:
                status = "fail"
            elif scorecard["decision"] == "pass":
                status = "pass"
            elif scorecard["decision"] in {"pass_with_warnings", "needs_retune"}:
                status = "needs_retune"
            else:
                status = "fail"

    orchestration = base_artifact(ORCHESTRATOR_TYPE, mode=mode, run_id=run_id)
    orchestration.update(
        {
            "executor": backend,
            "status": status,
            "parallel": parallel,
            "raw_output_stored": False,
            "steps": steps,
            "report_path": f".rubricodex/runs/{run_id}/report.md",
            "retune_goal_path": f".rubricodex/runs/{run_id}/retune_goal.md",
        }
    )
    assert_valid(validate_orchestrator(orchestration))
    path = write_json(orchestrator_path(root_path, run_id), orchestration)
    return {
        "status": status,
        "orchestrator_path": str(path),
        "steps": steps,
        "run_status": orchestrate_status(root_path, run_id),
    }
