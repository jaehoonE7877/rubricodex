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
RUN_ID_PATTERN = re.compile(r"--run-id(?:=|\s+)([A-Za-z0-9_.-]+)")
DIRECT_RUBRICODEX_LINE_PATTERN = re.compile(r"(?im)^\s*(?:[-*+]\s*)?@rubricodex\b[^\n]*")
ENGLISH_COMPLETION_TERMS = ("complete", "completed")
EXECUTE_CONTEXT_PATTERN = re.compile(
    r"\b(?:execute|proceed)\b[^\n.!?]{0,60}\b(?:task|work|implementation|change|changes|feature|fix|goal)\b"
    r"|\b(?:task|work|implementation|change|changes|feature|fix|goal)\b[^\n.!?]{0,60}\b(?:execute|proceed)\b",
    re.IGNORECASE,
)
KOREAN_IMPLEMENTATION_CONTEXT_PATTERN = re.compile(r"(?:작업|개발|변경)[^\n.!?]{0,20}(?:진행|실행)")
VALIDATION_RUN_PATTERN = re.compile(
    r"\b(?:run|execute)\s+(?:tests?|checks?|verification|validation)\b|테스트\s*실행",
    re.IGNORECASE,
)
COMPLETION_TERM_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(term) for term in ENGLISH_COMPLETION_TERMS) + r")\b",
    re.IGNORECASE,
)
DONE_PASSED_COMPLETION_PATTERN = re.compile(
    r"\b(?:rubricodex|task|work|implementation|pr|branch|changes?)\b[^\n.!?]{0,80}\b(?:done|passed)\b"
    r"|\b(?:done|passed)\b[^\n.!?]{0,80}\b(?:rubricodex|task|work|implementation|pr|branch|changes?)\b",
    re.IGNORECASE,
)
READY_COMPLETION_PATTERN = re.compile(
    r"\b(?:rubricodex|task|implementation|work|pr|branch|changes?)\b[^\n.!?]{0,80}\bready\b"
    r"|\bready\b\s+(?:for\s+(?:review|merge|release|pr)|to\s+(?:ship|merge|release|submit))\b",
    re.IGNORECASE,
)
KOREAN_COMPLETION_PATTERN = re.compile(
    r"(?:Rubricodex|작업|구현|변경|PR)[^\n.!?]{0,40}(?:완료|준비|통과)"
    r"|(?:완료|준비|통과)[^\n.!?]{0,40}(?:Rubricodex|작업|구현|변경|PR)",
    re.IGNORECASE,
)
POLICY_PROMPT_MARKERS = (
    "agents.md instructions",
    "<instructions>",
    "--- project-doc ---",
    "## source of truth",
    "## change rules",
    "## ask first",
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


def _has_explicit_run_id(text: str) -> bool:
    return RUN_ID_PATTERN.search(text) is not None


def _is_validation_run_prompt(text: str) -> bool:
    return VALIDATION_RUN_PATTERN.search(text) is not None


def _has_direct_rubricodex_handoff(text: str) -> bool:
    for match in DIRECT_RUBRICODEX_LINE_PATTERN.finditer(text):
        line = match.group(0)
        if _is_validation_run_prompt(line):
            continue
        if _is_implementation_handoff(line):
            return True
    return False


def _is_explicit_handoff_prompt(text: str) -> bool:
    if _has_direct_rubricodex_handoff(text):
        return True
    if DIRECT_RUBRICODEX_LINE_PATTERN.search(text):
        return False
    return _has_explicit_run_id(text) and _is_implementation_handoff(text)


def _has_done_or_passed_completion(text: str) -> bool:
    return DONE_PASSED_COMPLETION_PATTERN.search(text) is not None


def _is_completion_claim(text: str) -> bool:
    return (
        COMPLETION_TERM_PATTERN.search(text) is not None
        or _has_done_or_passed_completion(text)
        or READY_COMPLETION_PATTERN.search(text) is not None
        or KOREAN_COMPLETION_PATTERN.search(text) is not None
    )


def _is_policy_document_prompt(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in POLICY_PROMPT_MARKERS)


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
    match = RUN_ID_PATTERN.search(prompt)
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
    prompt = str(payload.get("prompt") or "")
    if not _is_rubricodex_prompt(prompt):
        return {}
    if _contains_any(prompt, RAW_STORAGE_TERMS) and _contains_any(prompt, STORE_TERMS):
        return _additional_context(
            "UserPromptSubmit",
            "Rubricodex guidance: raw_artifact_storage_request detected. Continue the run, store summarized evidence and references only, and let artifact validators reject forbidden raw artifacts.",
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
    explicit_handoff = _is_explicit_handoff_prompt(prompt)
    if _is_policy_document_prompt(prompt) and not explicit_handoff:
        return {}
    if not explicit_handoff and not _is_implementation_handoff(prompt):
        return {}

    run_id = _run_id_from_prompt(prompt, root)
    if run_id is None:
        return {}
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
