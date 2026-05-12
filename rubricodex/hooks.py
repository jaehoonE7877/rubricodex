from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .artifacts import (
    ArtifactError,
    DEFAULT_MODE,
    artifact_root,
    goal_lock_path,
    intent_path,
    matrix_path,
    orchestrate_status,
    read_json,
    run_dir,
    taskpack_dir,
    validate_evidence,
    validate_matrix,
    validate_run_manifest,
    validate_scorecard,
    verify_matrix_lock,
)


RAW_STORAGE_TERMS = (
    "raw transcript",
    "raw chat transcript",
    "raw task log",
    "raw codex log",
    "raw command output",
    "unredacted command output",
)
STORE_TERMS = ("store", "save", "commit", "write", "persist", "record", "저장", "커밋", "기록")
IMPLEMENT_TERMS = ("implement", "handoff", "start coding", "start implementation", "begin implementation", "구현")
ENGLISH_COMPLETION_TERMS = ("complete", "completed")
KOREAN_COMPLETION_TERMS = ("완료", "준비", "통과")
EXECUTE_CONTEXT_PATTERN = re.compile(
    r"\b(?:execute|proceed)\b[^\n.!?]{0,60}\b(?:task|work|implementation|change|changes|feature|fix|goal)\b"
    r"|\b(?:task|work|implementation|change|changes|feature|fix|goal)\b[^\n.!?]{0,60}\b(?:execute|proceed)\b",
    re.IGNORECASE,
)
KOREAN_IMPLEMENTATION_CONTEXT_PATTERN = re.compile(r"(?:작업|개발|변경)[^\n.!?]{0,20}(?:진행|실행)")
COMPLETION_TERM_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in ENGLISH_COMPLETION_TERMS) + r")\b",
    re.IGNORECASE,
)
DONE_PASSED_COMPLETION_PATTERN = re.compile(
    r"\b(?:rubricodex|task|work|implementation|pr|branch|changes?)\b[^\n.!?]{0,80}\b(?:done|passed)\b"
    r"|\b(?:done|passed)\b[^\n.!?]{0,80}\b(?:rubricodex|task|work|implementation|pr|branch|changes?)\b"
    r"|\ball\s+tests\s+passed\b",
    re.IGNORECASE,
)
PROGRESS_CONTINUATION_PATTERN = re.compile(
    r"\b(?:continuing|continue|remaining|still|next|then\s+i\s+will|before\s+i\s+continue)\b",
    re.IGNORECASE,
)
READY_COMPLETION_PATTERN = re.compile(
    r"\b(?:rubricodex|task|implementation|work|pr|branch|changes?)\b[^\n.!?]{0,80}\bready\b"
    r"|\bready\b\s+(?:for\s+(?:review|merge|release|pr)|to\s+(?:ship|merge|release|submit))\b",
    re.IGNORECASE,
)


def _cwd(payload: dict[str, Any]) -> Path:
    cwd = payload.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return _project_root(Path(cwd))
    return _project_root(Path.cwd())


def _project_root(cwd: Path) -> Path:
    root = cwd.expanduser().resolve()
    for candidate in (root, *root.parents):
        if artifact_root(candidate).exists():
            return candidate
    return root


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def _is_rubricodex_prompt(text: str) -> bool:
    lowered = text.lower()
    return "@rubricodex" in lowered or "rubricodex" in lowered


def _is_implementation_handoff(text: str) -> bool:
    return (
        _contains_any(text, IMPLEMENT_TERMS)
        or EXECUTE_CONTEXT_PATTERN.search(text) is not None
        or KOREAN_IMPLEMENTATION_CONTEXT_PATTERN.search(text) is not None
    )


def _has_done_or_passed_completion(text: str) -> bool:
    if PROGRESS_CONTINUATION_PATTERN.search(text):
        return False
    return DONE_PASSED_COMPLETION_PATTERN.search(text) is not None


def _is_completion_claim(text: str) -> bool:
    return (
        COMPLETION_TERM_PATTERN.search(text) is not None
        or _has_done_or_passed_completion(text)
        or READY_COMPLETION_PATTERN.search(text) is not None
        or _contains_any(text, KOREAN_COMPLETION_TERMS)
    )


def _additional_context(event_name: str, message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": event_name,
            "additionalContext": message,
        }
    }


def _block(reason: str) -> dict[str, str]:
    return {"decision": "block", "reason": reason}


def _run_id_from_prompt(prompt: str, root: Path) -> str | None:
    match = re.search(r"--run-id(?:=|\s+)([A-Za-z0-9_.-]+)", prompt)
    if match:
        return match.group(1)
    taskpacks = artifact_root(root) / "taskpacks"
    if not taskpacks.exists():
        return None
    locks = sorted(taskpacks.glob("*/goal.lock.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if locks:
        return locks[0].parent.name
    goals = sorted(taskpacks.glob("*/goal.md"), key=lambda path: path.stat().st_mtime, reverse=True)
    return goals[0].parent.name if goals else None


def _latest_run_id(root: Path) -> str | None:
    runs = artifact_root(root) / "runs"
    if not runs.exists():
        return None
    candidates = [path for path in runs.iterdir() if path.is_dir()]
    if not candidates:
        return None
    candidates.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return candidates[0].name


def _matrix_lock_mode(root: Path, run_id: str) -> str:
    for path in (matrix_path(root), goal_lock_path(root, run_id)):
        mode = read_json(path).get("mode")
        if isinstance(mode, str) and mode.strip():
            return mode
    return DEFAULT_MODE


def _summarize_status(status: dict[str, Any]) -> str:
    parts: list[str] = []
    missing = status.get("missing")
    if isinstance(missing, list) and missing:
        parts.append("missing: " + ", ".join(str(item) for item in missing[:6]))
    issues = status.get("issues")
    if isinstance(issues, list) and issues:
        issue_paths = [str(item.get("path", "$")) for item in issues if isinstance(item, dict)]
        parts.append("issues: " + ", ".join(issue_paths[:6]))
    return "; ".join(parts) or f"status: {status.get('status')}"


def evaluate_intake_boundary(payload: dict[str, Any]) -> dict[str, Any]:
    root = _cwd(payload)
    prompt = str(payload.get("prompt") or "")
    if not _is_rubricodex_prompt(prompt):
        return {}
    if _contains_any(prompt, RAW_STORAGE_TERMS) and _contains_any(prompt, STORE_TERMS):
        return _block(
            "Rubricodex must not store raw transcripts, raw task logs, or unredacted command output."
        )
    return _additional_context(
        "UserPromptSubmit",
        "Rubricodex intake boundary: classify mode, write intent brief, keep explicit scope_in/scope_out, and store only summarized evidence.",
    )


def evaluate_matrix_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    root = _cwd(payload)
    prompt = str(payload.get("prompt") or "")
    if not artifact_root(root).exists() or not _is_rubricodex_prompt(prompt):
        return {}
    if not _is_implementation_handoff(prompt):
        return {}

    run_id = _run_id_from_prompt(prompt, root)
    if run_id is None:
        return _block("Rubricodex matrix readiness requires a taskpack run id and matrix lock before implementation.")
    required = [
        intent_path(root),
        matrix_path(root),
        taskpack_dir(root, run_id) / "goal.md",
        taskpack_dir(root, run_id) / "prompt-lint.json",
        goal_lock_path(root, run_id),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return _block("Rubricodex matrix readiness missing matrix lock artifacts: " + ", ".join(missing))
    try:
        lock = verify_matrix_lock(root, run_id, mode=_matrix_lock_mode(root, run_id))
    except ArtifactError as error:
        details = ", ".join(issue.path for issue in error.issues[:6])
        return _block("Rubricodex matrix readiness failed: " + details)
    if lock["status"] != "pass":
        details = ", ".join(issue.get("path", "$") for issue in lock.get("issues", [])[:6])
        return _block("Rubricodex matrix readiness failed: " + details)
    return {}


def evaluate_completion_claim(payload: dict[str, Any]) -> dict[str, Any]:
    root = _cwd(payload)
    message = str(payload.get("last_assistant_message") or "")
    if not artifact_root(root).exists() or not _is_completion_claim(message):
        return {}
    run_id = _latest_run_id(root)
    if run_id is None:
        return {}

    try:
        status = orchestrate_status(root, run_id)
    except ArtifactError as error:
        details = ", ".join(issue.path for issue in error.issues[:6])
        return _block(f"Rubricodex completion gate failed for {run_id}: {details}")
    if status["status"] != "complete":
        return _block("Rubricodex completion gate failed for " + run_id + ": " + _summarize_status(status))

    try:
        matrix = read_json(matrix_path(root))
        evidence = read_json(run_dir(root, run_id) / "evidence.json")
        manifest = read_json(run_dir(root, run_id) / "run-manifest.json")
        scorecard = read_json(run_dir(root, run_id) / "scorecard.json")
    except (ArtifactError, FileNotFoundError, json.JSONDecodeError) as error:
        return _block(f"Rubricodex completion gate could not read summarized artifacts for {run_id}: {error}")

    issues = []
    issues.extend(validate_matrix(matrix))
    issues.extend(validate_evidence(evidence, matrix))
    issues.extend(validate_run_manifest(manifest))
    issues.extend(validate_scorecard(scorecard))
    if issues:
        details = ", ".join(issue.path for issue in issues[:6])
        return _block("Rubricodex completion gate found invalid artifacts: " + details)
    return {}


def evaluate_gate(gate: str, payload: dict[str, Any]) -> dict[str, Any]:
    if gate == "intake-boundary":
        return evaluate_intake_boundary(payload)
    if gate == "matrix-readiness":
        return evaluate_matrix_readiness(payload)
    if gate == "completion-claim":
        return evaluate_completion_claim(payload)
    raise KeyError(f"unknown Rubricodex hook gate: {gate}")
