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


RAW_STORAGE_CATEGORIES = {
    "raw_transcript": ("raw transcript", "raw chat transcript"),
    "raw_task_log": ("raw task log", "raw codex log"),
    "raw_command_output": ("raw command output", "unredacted command output"),
}
ENGLISH_STORAGE_ACTION_PATTERN_TEXT = (
    r"(?:stores?|stored|storing|saves?|saved|saving|commits?|committed|committing|"
    r"writes?|wrote|written|writing|persists?|persisted|persisting|records?|recorded|recording)"
)
ENGLISH_STORAGE_GERUND_PATTERN_TEXT = r"(?:storing|saving|committing|writing|persisting|recording)"
KOREAN_STORAGE_ACTIONS = ("저장", "커밋", "기록")
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
READY_COMPLETION_PATTERN = re.compile(
    r"\b(?:rubricodex|task|implementation|work|pr|branch|changes?)\b[^\n.!?]{0,80}\bready\b"
    r"|\bready\b\s+(?:for\s+(?:review|merge|release|pr)|to\s+(?:ship|merge|release|submit))\b",
    re.IGNORECASE,
)
PROMPT_CLAUSE_PATTERN = re.compile(r"[\n\r]+|(?<=[.!?])\s+|[;；]")
ENGLISH_STORAGE_ACTION_PATTERN = re.compile(r"\b(" + ENGLISH_STORAGE_ACTION_PATTERN_TEXT + r")\b", re.IGNORECASE)
NEGATED_ENGLISH_ACTION_PREFIX_PATTERN = re.compile(
    r"(?:do\s+not|don't|must\s+not(?:\s+be)?|should\s+not(?:\s+be)?|never(?:\s+be)?|not(?:\s+be)?|"
    r"not\s+allowed\s+to|forbidden\s+to|prohibited\s+to|without)\s+$",
    re.IGNORECASE,
)
NEGATED_STORAGE_BEFORE_RAW_PATTERN = re.compile(
    r"(?:do\s+not|don't|must\s+not|should\s+not|never|not\s+allowed\s+to|forbidden\s+to|prohibited\s+to)\s+"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b(?P<body>[^.!?;；]{0,120})$"
    + r"|without\s+"
    + ENGLISH_STORAGE_GERUND_PATTERN_TEXT
    + r"\b(?P<without_body>[^.!?;；]{0,120})$",
    re.IGNORECASE,
)
BARE_NEGATED_RAW_PREFIX_PATTERN = re.compile(r"(?:not|no)\s+$", re.IGNORECASE)
ENGLISH_NEGATION_BOUNDARY_PATTERN = re.compile(
    r"\b(?:but|however|except|instead)\b|(?:,|\band\b|\bthen\b)\s*(?:please\s+|then\s+)?"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b",
    re.IGNORECASE,
)
KOREAN_NEGATED_STORAGE_AFTER_RAW_PATTERN = re.compile(r"^[^.!?;；,\n\r]{0,80}저장\s*(?:하지|하지\s+않|금지|허용하지)")
ENGLISH_NEGATED_STORAGE_AFTER_RAW_PATTERN = re.compile(
    r"^[^.!?;；]{0,120}(?:(?:must|should)\s+not|do\s+not|don't|never|not)\s+(?:be\s+)?"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b"
    + r"|^[^.!?;；]{0,120}(?:is|are|be)\s+(?:not\s+allowed|forbidden|prohibited)\s+to\s+be\s+"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b",
    re.IGNORECASE,
)
KOREAN_RAW_STORAGE_REQUEST_PATTERN = re.compile(
    r"(?P<action>"
    + "|".join(KOREAN_STORAGE_ACTIONS)
    + r")\s*(?:해줘|해주세요|하세요|하라|해라|해|해야|해 주세요|부탁)?\s*(?:$|[.!?。])",
)
REFERENCE_RAW_OBJECT_PATTERN = re.compile(r"\b(?:it|this|that|them|these|those|above|below|same)\b", re.IGNORECASE)
SAFE_SUMMARY_OBJECT_PATTERN = re.compile(
    r"\b(?:summary|summaries|summarized|summarised|redacted|sanitized|sanitised)\b",
    re.IGNORECASE,
)
SUMMARY_TRANSFORM_PATTERN = re.compile(r"\b(?:summari[sz]e|redact|saniti[sz]e)\b|요약", re.IGNORECASE)
SUMMARY_SOURCE_CONNECTOR_PATTERN = re.compile(r"\b(?:of|from|about)\b", re.IGNORECASE)
RAW_INCLUSION_CONNECTOR_PATTERN = re.compile(
    r"\b(?:and|plus|with|alongside|including|containing)\b",
    re.IGNORECASE,
)
SAFE_CROSS_STORAGE_OBJECT_PATTERN = re.compile(
    r"^\s+(?:the\s+|a\s+|an\s+|this\s+|that\s+|our\s+|my\s+)?"
    r"(?:goal\s+lock|intent\s+brief|brief|summary|summaries|summarized\s+evidence|redacted\s+summary|"
    r"evidence(?:\.json)?|report|scorecard|matrix|taskpack|requirements|policy|docs?|documentation)\b",
    re.IGNORECASE,
)
FORWARD_STORAGE_OBJECT_PATTERN = re.compile(
    r"\b(?:everything\s+(?:below|above|that\s+follows)|the\s+following|"
    r"following\s+(?:content|input|text|transcript|output)|"
    r"all\s+(?:of\s+)?(?:this|the\s+following|content|input|text|details|below))\b",
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


def _raw_category_matches(text: str) -> list[dict[str, Any]]:
    lowered = text.lower()
    matches: list[dict[str, Any]] = []
    for category, terms in RAW_STORAGE_CATEGORIES.items():
        for term in terms:
            start = 0
            while True:
                index = lowered.find(term, start)
                if index < 0:
                    break
                matches.append({"category": category, "start": index, "end": index + len(term)})
                start = index + 1
    return sorted(matches, key=lambda item: item["start"])


def _unique_categories(matches: list[dict[str, Any]]) -> list[str]:
    categories: list[str] = []
    for match in matches:
        category = str(match["category"])
        if category not in categories:
            categories.append(category)
    return categories


def _canonical_english_storage_action(action: str) -> str:
    lowered = action.lower()
    if lowered.startswith("stor"):
        return "store"
    if lowered.startswith("sav"):
        return "save"
    if lowered.startswith("commit"):
        return "commit"
    if lowered in {"write", "writes", "wrote", "written", "writing"}:
        return "write"
    if lowered.startswith("persist"):
        return "persist"
    if lowered.startswith("record"):
        return "record"
    return lowered


def _is_negated_raw_reference(text: str, raw_start: int) -> bool:
    prefix = text[max(0, raw_start - 120) : raw_start]
    if BARE_NEGATED_RAW_PREFIX_PATTERN.search(prefix) is not None:
        return True
    match = NEGATED_STORAGE_BEFORE_RAW_PATTERN.search(prefix)
    if match is None:
        return False
    body = match.groupdict().get("body") or match.groupdict().get("without_body") or ""
    return ENGLISH_NEGATION_BOUNDARY_PATTERN.search(body) is None


def _is_negated_korean_raw_reference(text: str, raw_end: int) -> bool:
    suffix = text[raw_end : raw_end + 120]
    return KOREAN_NEGATED_STORAGE_AFTER_RAW_PATTERN.search(suffix) is not None


def _is_negated_english_raw_reference_after(text: str, raw_end: int) -> bool:
    suffix = text[raw_end : raw_end + 160]
    return ENGLISH_NEGATED_STORAGE_AFTER_RAW_PATTERN.search(suffix) is not None


def _active_raw_category_matches(text: str) -> list[dict[str, Any]]:
    return [
        match
        for match in _raw_category_matches(text)
        if not _is_negated_raw_reference(text, int(match["start"]))
        and not _is_negated_english_raw_reference_after(text, int(match["end"]))
        and not _is_negated_korean_raw_reference(text, int(match["end"]))
    ]


def _active_raw_categories(text: str) -> list[str]:
    return _unique_categories(_active_raw_category_matches(text))


def _is_negated_english_action(text: str, action_start: int) -> bool:
    prefix = text[max(0, action_start - 32) : action_start].lower()
    return NEGATED_ENGLISH_ACTION_PREFIX_PATTERN.search(prefix) is not None


def _is_safe_summary_storage_suffix(suffix: str) -> bool:
    summary_match = SAFE_SUMMARY_OBJECT_PATTERN.search(suffix)
    if summary_match is None:
        return False
    raw_matches = _active_raw_category_matches(suffix)
    if not raw_matches:
        return True
    first_raw_start = min(int(match["start"]) for match in raw_matches)
    if int(summary_match.start()) >= first_raw_start:
        return False
    connector = suffix[summary_match.end() : first_raw_start]
    return (
        SUMMARY_SOURCE_CONNECTOR_PATTERN.search(connector) is not None
        and RAW_INCLUSION_CONNECTOR_PATTERN.search(connector) is None
    )


def _same_clause_english_storage_match(clause: str) -> dict[str, str] | None:
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 120]
        prefix_categories = _active_raw_categories(clause[max(0, english_match.start() - 120) : english_match.start()])
        suffix_categories = _active_raw_categories(suffix)
        if (
            (
                _is_safe_summary_storage_suffix(suffix)
                and (not prefix_categories or SUMMARY_TRANSFORM_PATTERN.search(clause[: english_match.start()]) is not None)
            )
            or (
                not suffix_categories
                and SUMMARY_TRANSFORM_PATTERN.search(clause[: english_match.start()]) is not None
                and REFERENCE_RAW_OBJECT_PATTERN.search(suffix) is not None
            )
        ):
            continue
        window = clause[max(0, english_match.start() - 120) : english_match.end() + 120]
        window_categories = _active_raw_categories(window)
        if window_categories:
            return {
                "matched_categories": ",".join(window_categories),
                "matched_action": _canonical_english_storage_action(english_match.group(1)),
            }
    return None


def _cross_clause_english_storage_match(clause: str, previous_categories: list[str]) -> dict[str, str] | None:
    if not previous_categories:
        return None
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 120]
        action = _canonical_english_storage_action(english_match.group(1))
        reference_window = clause[max(0, english_match.start() - 80) : english_match.end() + 120]
        has_raw_reference = REFERENCE_RAW_OBJECT_PATTERN.search(reference_window) is not None
        if SAFE_SUMMARY_OBJECT_PATTERN.search(suffix) is not None:
            continue
        if SAFE_CROSS_STORAGE_OBJECT_PATTERN.search(suffix) is not None and not has_raw_reference:
            continue
        if action != "write" or has_raw_reference:
            return {
                "matched_categories": ",".join(previous_categories),
                "matched_action": action,
            }
    return None


def _forward_english_storage_match(clause: str) -> dict[str, str] | None:
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 160]
        if SAFE_SUMMARY_OBJECT_PATTERN.search(suffix) is not None:
            continue
        if FORWARD_STORAGE_OBJECT_PATTERN.search(suffix) is None:
            continue
        return {
            "matched_action": _canonical_english_storage_action(english_match.group(1)),
        }
    return None


def _korean_storage_match(clause: str, categories: list[str]) -> dict[str, str] | None:
    if not categories:
        return None
    korean_match = KOREAN_RAW_STORAGE_REQUEST_PATTERN.search(clause)
    if korean_match is None:
        return None
    return {
        "matched_categories": ",".join(categories),
        "matched_action": korean_match.group("action"),
    }


def _explicit_raw_storage_request(prompt: str) -> dict[str, str] | None:
    previous_categories: list[str] = []
    pending_forward_storage: dict[str, str] | None = None
    for clause in PROMPT_CLAUSE_PATTERN.split(prompt):
        clause = clause.strip()
        if not clause:
            continue

        same_clause_match = _same_clause_english_storage_match(clause)
        if same_clause_match is not None:
            return same_clause_match

        categories = _active_raw_categories(clause)
        if categories and pending_forward_storage is not None:
            return {
                "matched_categories": ",".join(categories),
                "matched_action": pending_forward_storage["matched_action"],
            }

        korean_match = _korean_storage_match(clause, categories or previous_categories)
        if korean_match is not None:
            return korean_match

        cross_clause_match = _cross_clause_english_storage_match(clause, previous_categories)
        if cross_clause_match is not None:
            return cross_clause_match

        forward_storage_match = _forward_english_storage_match(clause)
        if forward_storage_match is not None:
            pending_forward_storage = forward_storage_match
            continue

        if categories:
            previous_categories = categories
        elif SAFE_SUMMARY_OBJECT_PATTERN.search(clause) is not None:
            previous_categories = []
            pending_forward_storage = None
    return None


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


def _intake_block_reason(match: dict[str, str]) -> str:
    return (
        "Rubricodex intake-boundary blocked: explicit raw artifact storage request detected; "
        f"matched_categories={match['matched_categories']}; matched_action={match['matched_action']}. "
        "Use summarized evidence instead."
    )


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
    raw_storage_request = _explicit_raw_storage_request(prompt)
    if raw_storage_request is not None:
        return _block(_intake_block_reason(raw_storage_request))
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
        return _block("Rubricodex matrix-readiness blocked: requires a taskpack run id and matrix lock before implementation.")
    required = [
        intent_path(root),
        matrix_path(root),
        taskpack_dir(root, run_id) / "goal.md",
        taskpack_dir(root, run_id) / "prompt-lint.json",
        goal_lock_path(root, run_id),
    ]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        return _block("Rubricodex matrix-readiness blocked: missing matrix lock artifacts: " + ", ".join(missing))
    try:
        lock = verify_matrix_lock(root, run_id, mode=_matrix_lock_mode(root, run_id))
    except ArtifactError as error:
        details = ", ".join(issue.path for issue in error.issues[:6])
        return _block("Rubricodex matrix-readiness blocked: matrix lock failed: " + details)
    if lock["status"] != "pass":
        details = ", ".join(issue.get("path", "$") for issue in lock.get("issues", [])[:6])
        return _block("Rubricodex matrix-readiness blocked: matrix lock failed: " + details)
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
        return _block(f"Rubricodex completion-claim blocked for {run_id}: {details}")
    if status["status"] != "complete":
        return _block("Rubricodex completion-claim blocked for " + run_id + ": " + _summarize_status(status))

    try:
        matrix = read_json(matrix_path(root))
        evidence = read_json(run_dir(root, run_id) / "evidence.json")
        manifest = read_json(run_dir(root, run_id) / "run-manifest.json")
        scorecard = read_json(run_dir(root, run_id) / "scorecard.json")
    except (ArtifactError, FileNotFoundError, json.JSONDecodeError) as error:
        return _block(f"Rubricodex completion-claim blocked: could not read summarized artifacts for {run_id}: {error}")

    issues = []
    issues.extend(validate_matrix(matrix))
    issues.extend(validate_evidence(evidence, matrix))
    issues.extend(validate_run_manifest(manifest))
    issues.extend(validate_scorecard(scorecard))
    if issues:
        details = ", ".join(issue.path for issue in issues[:6])
        return _block("Rubricodex completion-claim blocked: invalid artifacts: " + details)
    return {}


def evaluate_gate(gate: str, payload: dict[str, Any]) -> dict[str, Any]:
    if gate == "intake-boundary":
        return evaluate_intake_boundary(payload)
    if gate == "matrix-readiness":
        return evaluate_matrix_readiness(payload)
    if gate == "completion-claim":
        return evaluate_completion_claim(payload)
    raise KeyError(f"unknown Rubricodex hook gate: {gate}")
