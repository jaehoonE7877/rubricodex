from __future__ import annotations

import hashlib
import json
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


def run_dir(root: Path | str, run_id: str) -> Path:
    return artifact_root(root) / "runs" / run_id


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
    lock = base_artifact("rubricodex.goal_lock", mode=mode, run_id=run_id)
    lock.update(
        {
            "executor": executor,
            "brief_sha256": stable_hash(brief),
            "matrix_sha256": stable_hash(matrix),
            "goal_sha256": stable_hash(goal_text),
        }
    )
    lock_path = write_json(task_dir / "goal.lock.json", lock)
    return {"goal": goal_path, "adapter_input": adapter_path, "lock": lock_path}


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
    report_lines = [
        "# Rubricodex Report",
        "",
        "## Summary",
        f"- Decision: {scorecard['decision']}",
        f"- Scoring model: {scorecard['scoring_model']}",
        f"- Counts: pass={scorecard['counts']['pass']}, partial={scorecard['counts']['partial']}, missing={scorecard['counts']['missing_evidence']}, fail={scorecard['counts']['fail']}",
        "",
        "## Criteria",
    ]
    retune_results = []
    for result in scorecard["results"]:
        report_lines.append(f"- {result['criterion_id']} {result['name']}: {result['status']}")
        if result["status"] != "pass":
            retune_results.append(result)
    report_lines.extend(["", "## Next action"])
    if retune_results:
        report_lines.append("Run the retune goal for the failed or partial criteria only.")
    else:
        report_lines.append("No retune instruction required.")
    report_path = write_text(run_dir(root_path, run_id) / "report.md", "\n".join(report_lines) + "\n")

    retune_lines = [
        "/goal Retune only the criteria listed below.",
        "",
        "## Failed or partial criteria",
    ]
    if retune_results:
        for result in retune_results:
            retune_lines.append(f"- {result['criterion_id']} {result['name']}: {result['status']}. {result['retune_hint']}")
    else:
        retune_lines.append("- None")
    retune_lines.extend(
        [
            "",
            "## Keep unchanged",
            "- Do not change criteria already marked pass.",
            "- Do not store raw transcripts, raw logs, or unredacted command output.",
            "",
            "## Required fix",
            "- Provide summarized evidence references for the criteria above.",
            "",
            "## Completion rule",
            "- Stop when the listed criteria pass or when a hard gate remains blocked.",
            "",
        ]
    )
    retune_path = write_text(run_dir(root_path, run_id) / "retune_goal.md", "\n".join(retune_lines))
    return {"report": report_path, "retune": retune_path}
