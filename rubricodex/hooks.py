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
    r"writes?|wrote|written|writing|persists?|persisted|persisting|records?|recorded|recording|"
    r"includes?|included|including|adds?|added|adding|pastes?|pasted|pasting|puts?|putting|"
    r"keeps?|kept|keeping)"
)
ENGLISH_STORAGE_GERUND_PATTERN_TEXT = r"(?:storing|saving|committing|writing|persisting|recording)"
BROAD_ENGLISH_STORAGE_ACTIONS = {"add", "include", "put", "keep"}
BARE_ENGLISH_STORAGE_ACTIONS = {"store", "save", "commit", "write", "persist", "record", "paste"}
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
ENGLISH_RAW_REFERENCE_ACTION_PATTERN_TEXT = (
    r"(?:"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"|includes?|included|including|adds?|added|adding|pastes?|pasted|pasting|puts?|putting|keeps?|kept|keeping)"
)
NEGATED_ENGLISH_ACTION_PREFIX_PATTERN = re.compile(
    r"(?:please\s+)?(?:do\s+not|don't|must\s+not|mustn't|should\s+not|shouldn't|"
    r"can\s+not|cannot|can't|may\s+not|never|not|not\s+to\s+be|not\s+to|"
    r"not\s+allowed\s+to|forbidden\s+to|prohibited\s+to|prohibited\s+from\s+being|without|"
    r"forbid(?:s|ding)?|prohibit(?:s|ed|ing)?|ban(?:s|ned|ning)?|from\s+being|"
    r"blocks?|blocking|prevents?|preventing|rejects?|rejecting|disallows?|disallowing)"
    r"(?:\s+ever)?(?:\s+be)?\s+$",
    re.IGNORECASE,
)
NEGATED_STORAGE_BEFORE_RAW_PATTERN = re.compile(
    r"(?:do\s+not|don't|must\s+not|mustn't|should\s+not|shouldn't|never|not\s+allowed\s+to|"
    r"forbidden\s+to|prohibited\s+to)(?:\s+ever)?\s+"
    + ENGLISH_RAW_REFERENCE_ACTION_PATTERN_TEXT
    + r"\b(?P<body>[^.!?;；]{0,120})$"
    + r"|without\s+"
    + r"(?:" + ENGLISH_STORAGE_GERUND_PATTERN_TEXT + r"|including|adding|pasting|putting|keeping)"
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
ENGLISH_DETACHED_POST_RAW_NEGATION_PATTERN = re.compile(
    r"(?:,|\band\b|\bthen\b|\bbut\b|\bhowever\b|\bexcept\b|\binstead\b)",
    re.IGNORECASE,
)
ENGLISH_TRAILING_CAVEAT_PATTERN = re.compile(
    r"\b(?:although|though|even\s+though|while|because|since|as)\b",
    re.IGNORECASE,
)
KOREAN_NEGATED_STORAGE_AFTER_RAW_PATTERN = re.compile(
    r"(?:저장|커밋|기록)(?:을|를|도|이|가|은|는)?\s*"
    r"(?:하지|하지\s+않|하지\s+마|말고|없이|금지|허용하지|안\s*하|막|방지)"
)
KOREAN_NEGATED_STORAGE_ACTION_PATTERN = re.compile(
    r"^(?:저장|커밋|기록)(?:을|를|도|이|가|은|는)?\s*"
    r"(?:하지|하지\s+않|하지\s+마|말고|없이|금지|허용하지|안\s*하|막|방지)"
)
ENGLISH_NEGATED_STORAGE_AFTER_RAW_PATTERN = re.compile(
    r"(?:(?:must|should|may|can)\s+not|mustn't|shouldn't|can't|cannot|do\s+not|don't|never|"
    r"not(?:\s+ever)?\s+to\s+be|not\s+to\s+be|not)"
    r"(?:\s+ever)?\s+(?:be\s+)?"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b"
    + r"|(?:is|are|was|were|be)\s+(?:not\s+allowed|forbidden|prohibited)\s+to\s+be\s+"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b"
    + r"|(?:is|are|was|were|be)\s+prohibited\s+from\s+being\s+"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\b"
    + r"|(?:is|are|was|were|be)\s+(?:not\s+allowed|forbidden|prohibited|disallowed)"
    + r"\b"
    + r"|(?:is|are|was|were|be|being)\s+(?:blocked|rejected|prevented|excluded)"
    + r"\b"
    + r"|(?:is|are|was|were|be)\s+"
    + ENGLISH_STORAGE_ACTION_PATTERN_TEXT
    + r"\s+nowhere\b",
    re.IGNORECASE,
)
ENGLISH_ACTION_NOWHERE_PATTERN = re.compile(
    r"^" + ENGLISH_STORAGE_ACTION_PATTERN_TEXT + r"\b\s+nowhere\b",
    re.IGNORECASE,
)
KOREAN_RAW_STORAGE_REQUEST_PATTERN = re.compile(
    r"(?P<action>"
    + "|".join(KOREAN_STORAGE_ACTIONS)
    + r")(?:을|를|도|이|가|은|는)?\s*(?P<form>해야\s*합니다|해야합니다|해도\s*(?:됩니다|돼요|되요|된다|됨|괜찮습니다|좋습니다|가능합니다)|합니다|하십시오|합시다|해주시고|해주고|해줘|해주세요|하세요|하라|해라|해서|해야|해 주세요|해|부탁|하고\s*나서|하고|한\s*다음|한\s*뒤|한\s*후|후|"
    r"할\s*것|하는|할|하도록|하게|하기|된|되는|되도록)?"
    r"\s*(?:$|[.!?。:：]|\s)",
)
KOREAN_ATTRIBUTIVE_STORAGE_FORMS = {"하는", "할", "하도록", "하게", "하기", "된", "되는", "되도록"}
KOREAN_ATTRIBUTIVE_STORAGE_TARGET_PATTERN = re.compile(
    r"^\s*(?:코드|파일|스크립트|로직|기능|구현|함수|명령)"
    r"|(?:만들|구현|작성|생성|추가|수정|패치|적용|해줘|해주세요)"
)
REFERENCE_RAW_OBJECT_PATTERN = re.compile(r"\b(?:it|this|that|them|these|those|above|below|same)\b", re.IGNORECASE)
SAFE_SUMMARY_OBJECT_PATTERN = re.compile(
    r"\b(?:summary|summaries|summarized|summarised|redacted|sanitized|sanitised)\b",
    re.IGNORECASE,
)
AFFIRMATIVE_SUMMARY_OUTPUT_PATTERN = re.compile(
    r"\b(?:make|create|write|produce|include|add|store|save|record|persist)\b"
    r"[^.!?;；]{0,80}\b(?:a\s+|an\s+|the\s+)?"
    r"(?:summary|summaries|summarized|summarised|redacted|sanitized|sanitised)\b",
    re.IGNORECASE,
)
NEGATED_SUMMARY_OUTPUT_PATTERN = re.compile(
    r"\b(?:do\s+not|don't|must\s+not|mustn't|should\s+not|shouldn't|never)\b"
    r"[^.!?;；]{0,80}\b(?:summary|summaries)\b"
    r"|\b(?:no|without)\s+(?:a\s+|the\s+)?(?:summary|summaries)\b"
    r"|\b(?:summary|summaries)\b[^.!?;；]{0,40}\bnot\s+(?:needed|required|necessary)\b",
    re.IGNORECASE,
)
SUMMARY_TRANSFORM_PATTERN = re.compile(r"\b(?:summari[sz]e|redact|saniti[sz]e)\b|요약", re.IGNORECASE)
SUMMARY_TRANSFORM_VERB_PATTERN = re.compile(r"\b(?:summari[sz]e|redact|saniti[sz]e)\b", re.IGNORECASE)
NEGATED_SUMMARY_TRANSFORM_PREFIX_PATTERN = re.compile(
    r"(?:do\s+not|don't|must\s+not|mustn't|should\s+not|shouldn't|never|not)\s+$",
    re.IGNORECASE,
)
SUMMARY_SOURCE_CONNECTOR_PATTERN = re.compile(r"\b(?:of|from|about)\b", re.IGNORECASE)
RAW_INCLUSION_CONNECTOR_PATTERN = re.compile(
    r"\b(?:and|plus|with|alongside|including|containing)\b",
    re.IGNORECASE,
)
SUMMARY_ONLY_FORWARD_OBJECT_PATTERN = re.compile(
    r"^\s+(?:the\s+following\s+)?(?:a\s+|an\s+|the\s+|this\s+|that\s+|our\s+|my\s+)?"
    r"(?:summary|summaries|summarized|summarised|redacted|sanitized|sanitised)\b",
    re.IGNORECASE,
)
SAFE_FOLLOWUP_OBJECT_PATTERN = re.compile(
    r"^\s+(?:the\s+|a\s+|an\s+)?(?:tests?|test\s+cases?)\b",
    re.IGNORECASE,
)
SAFE_BROAD_ACTION_OBJECT_PATTERN = re.compile(
    r"^\s+(?:a\s+|an\s+|the\s+)?"
    r"(?:tests?|test\s+cases?|test\s+case|fixtures?|test\s+fixtures?|function|logic|validator|code|hook|"
    r"solution|note|section|docs?\s+section|policy|rules?)\b",
    re.IGNORECASE,
)
SAFE_BROAD_ACTION_LANGUAGE_PATTERN = re.compile(
    r"^\s+in\s+(?:korean|english|japanese|spanish|french|german)\b",
    re.IGNORECASE,
)
SAFE_KEEP_DIRECTION_PATTERN = re.compile(
    r"^\s+(?:it\s+)?(?:simple|small|focused)\b|^\s+the\s+solution\s+(?:simple|small|focused)\b",
    re.IGNORECASE,
)
SAFE_CROSS_STORAGE_OBJECT_PATTERN = re.compile(
    r"^\s+(?:the\s+|a\s+|an\s+|this\s+|that\s+|our\s+|my\s+)?"
    r"(?:goal\s+lock|intent\s+brief|brief|summary|summaries|summarized\s+evidence|redacted\s+summary|"
    r"evidence(?:\.json)?|report|scorecard|matrix|taskpack|requirements|policy|docs?|documentation)\b",
    re.IGNORECASE,
)
RAW_PRESERVATION_QUALIFIER_PATTERN = re.compile(
    r"\b(?:verbatim|as[-\s]?is|unredacted|raw|unchanged|without\s+redaction)\b",
    re.IGNORECASE,
)
FORWARD_DELIMITER_PATTERN = re.compile(r"^\s*[:：]\s*$")
KOREAN_RAW_PRESERVATION_OBJECT_PATTERN = re.compile(r"(?:원문|원본|그대로|전문|전체|무가공|무편집)")
KEEP_OUT_PATTERN = re.compile(r"\b(?:out\s+of|outside|away\s+from)\b", re.IGNORECASE)
POLICY_DOC_DESTINATION_PATTERN = re.compile(
    r"\b(?:policy|policies|docs?|documentation|rules?|guidelines?|agents\.md)\b|do-not-store",
    re.IGNORECASE,
)
POLICY_PROHIBITION_CONTEXT_PATTERN = re.compile(
    r"\b(?:disallowed|forbidden|prohibited|not\s+allowed|do-not-store|do\s+not\s+store|must\s+not|"
    r"should\s+not|never|no)\b|금지|허용하지|저장하지",
    re.IGNORECASE,
)
POLICY_EXCEPTION_UNSAFE_DESTINATION_PATTERN = re.compile(
    r"(?:\b(?:and|also|then|plus|along\s+with|as\s+well\s+as)\b|[&/])[^.!?;；]{0,80}"
    r"(?:\bevidence(?:\.json)?\b|\breport(?:\.md)?\b|\brepo(?:sitory)?\b|\.rubricodex|\.json|\.md)",
    re.IGNORECASE,
)
POLICY_PROHIBITION_BEFORE_RAW_PATTERN = re.compile(
    r"(?:"
    r"(?:do\s+not|don't|must\s+not|mustn't|should\s+not|shouldn't|never)\s+"
    r"(?:ever\s+)?(?:store|save|commit|write|persist|record|include|add)\s+(?:the\s+)?"
    r"|(?:forbid(?:s|ding)?|prohibit(?:s|ed|ing)?|disallow(?:s|ed|ing)?|ban(?:s|ned|ning)?)\s+"
    r"(?:storing\s+|storage\s+of\s+)?(?:the\s+)?"
    r")$",
    re.IGNORECASE,
)
POLICY_PROHIBITION_AFTER_RAW_PATTERN = re.compile(
    r"^s?(?:"
    r"\s+(?:is|are|be)\s+(?:not\s+allowed|forbidden|prohibited|disallowed)"
    r"|\s+(?:must|should|may|can)\s+not\b"
    r"|\s+(?:mustn't|shouldn't|can't|cannot)\b"
    r"|[^.!?;；]{0,60}\bas\s+(?:disallowed|forbidden|prohibited)\b"
    r"|[^.!?;；]{0,60}\bdo-not-store\b"
    r")",
    re.IGNORECASE,
)
UNSAFE_ARTIFACT_DESTINATION_PATTERN = re.compile(
    r"\bevidence(?:\.json)?\b|\breport(?:\.md)?\b|\brepo(?:sitory)?\b|\.rubricodex|\.json|\.md",
    re.IGNORECASE,
)
LOOSE_ARTIFACT_DESTINATION_PATTERN = re.compile(
    r"evidence(?:\.json)?|report(?:\.md)?|repo(?:sitory)?|\.rubricodex|\.json|\.md",
    re.IGNORECASE,
)
DERIVED_TRANSFORM_VERB_PATTERN = re.compile(
    r"\b(?:extract|derive|summari[sz]e|redact|saniti[sz]e|analy[sz]e|review)\b|요약",
    re.IGNORECASE,
)
DERIVED_OUTPUT_OBJECT_PATTERN = re.compile(
    r"\b(?:requirements?|summar(?:y|ies)|redacted|sanitized|sanitised|evidence|findings?|criteria|tasks?|"
    r"goal\s+lock|brief)\b",
    re.IGNORECASE,
)
DERIVED_REFERENCE_OBJECT_PATTERN = re.compile(r"\b(?:it|them|these|those)\b", re.IGNORECASE)
DESTINATION_STORAGE_PREFIX_PATTERN = re.compile(r"^\s+(?:to|into|in|inside|under|onto|within)\b", re.IGNORECASE)
FORWARD_STORAGE_OBJECT_PATTERN = re.compile(
    r"\b(?:everything\s+(?:below|above|that\s+follows)|the\s+following|"
    r"following\s+(?:content|input|text|transcript|output)|"
    r"(?:the\s+)?(?:content|input|text|details)\s+below|"
    r"all\s+(?:of\s+)?(?:this|the\s+following|content|input|text|details|below)|"
    r"this|that|below|above)\b",
    re.IGNORECASE,
)
KOREAN_FORWARD_STORAGE_OBJECT_PATTERN = re.compile(
    r"(?:아래|다음|이|해당)\s*(?:내용|텍스트|입력|전문|출력)|(?:내용|텍스트|입력|전문|출력)\s*(?:아래|다음)|아래"
)
KOREAN_REFERENCE_RAW_OBJECT_PATTERN = re.compile(r"(?:그걸|그것|그거|이를|이걸|이것|해당|원문)")


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
    if lowered.startswith("includ"):
        return "include"
    if lowered.startswith("add"):
        return "add"
    if lowered.startswith("past"):
        return "paste"
    if lowered.startswith("put"):
        return "put"
    if lowered.startswith("keep") or lowered == "kept":
        return "keep"
    return lowered


def _has_contradicting_storage_after_raw(text: str, raw_start: int) -> bool:
    suffix = text[raw_start : raw_start + 120]
    boundary_match = ENGLISH_DETACHED_POST_RAW_NEGATION_PATTERN.search(suffix)
    if boundary_match is None:
        return False
    after_boundary = suffix[boundary_match.end() :]
    for storage_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(after_boundary):
        if _is_negated_english_action(after_boundary, storage_match.start()):
            continue
        storage_suffix = after_boundary[storage_match.end() : storage_match.end() + 80]
        if SAFE_SUMMARY_OBJECT_PATTERN.search(storage_suffix) is not None:
            continue
        if REFERENCE_RAW_OBJECT_PATTERN.search(storage_suffix) is not None:
            return True
    return False


def _has_affirmative_storage_after_post_raw_negation(suffix: str, negation_end: int) -> bool:
    after_negation = suffix[negation_end : negation_end + 120]
    boundary_match = ENGLISH_DETACHED_POST_RAW_NEGATION_PATTERN.search(after_negation)
    if boundary_match is None:
        return False
    after_boundary = after_negation[boundary_match.end() :]
    for storage_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(after_boundary):
        if _is_negated_english_action(after_boundary, storage_match.start()):
            continue
        storage_prefix = after_boundary[max(0, storage_match.start() - 60) : storage_match.start()]
        storage_suffix = after_boundary[storage_match.end() : storage_match.end() + 80]
        if SAFE_SUMMARY_OBJECT_PATTERN.search(storage_prefix) is not None:
            continue
        if _is_safe_summary_storage_suffix(storage_suffix):
            continue
        return True
    return False


def _is_negated_raw_reference(text: str, raw_start: int) -> bool:
    prefix = text[max(0, raw_start - 120) : raw_start]
    if BARE_NEGATED_RAW_PREFIX_PATTERN.search(prefix) is not None:
        return True
    match = NEGATED_STORAGE_BEFORE_RAW_PATTERN.search(prefix)
    if match is None:
        return False
    if _has_contradicting_storage_after_raw(text, raw_start):
        return False
    body = match.groupdict().get("body") or match.groupdict().get("without_body") or ""
    if re.search(r",|\b(?:but|however|except|instead)\b", body, re.IGNORECASE) is not None:
        return False
    summary_match = SAFE_SUMMARY_OBJECT_PATTERN.search(body)
    if summary_match is not None and SUMMARY_SOURCE_CONNECTOR_PATTERN.search(body[summary_match.end() :]) is not None:
        return False
    return ENGLISH_NEGATION_BOUNDARY_PATTERN.search(body) is None


def _is_negated_korean_raw_reference(text: str, raw_end: int) -> bool:
    suffix = text[raw_end : raw_end + 120]
    match = KOREAN_NEGATED_STORAGE_AFTER_RAW_PATTERN.search(suffix)
    if match is None:
        return False
    after_negation = suffix[match.end() : match.end() + 120]
    boundary_match = re.search(r"(?:말고|대신|하지만|그러나|그리고|,)", after_negation)
    if boundary_match is not None:
        after_boundary = after_negation[boundary_match.end() :]
        for storage_match in KOREAN_RAW_STORAGE_REQUEST_PATTERN.finditer(after_boundary):
            action_start = storage_match.start("action")
            if _is_negated_korean_action(after_boundary, action_start) or _is_safe_korean_summary_action(
                after_boundary,
                action_start,
            ):
                continue
            if not _raw_category_matches(after_boundary[:action_start]):
                return False
            break
    return not _has_affirmative_korean_storage_action(suffix[: match.start()])


def _is_negated_korean_action(text: str, action_start: int) -> bool:
    suffix = text[action_start : action_start + 80]
    return KOREAN_NEGATED_STORAGE_ACTION_PATTERN.search(suffix) is not None


def _is_safe_korean_summary_action(text: str, action_start: int) -> bool:
    window = text[max(0, action_start - 80) : action_start]
    summary_index = window.rfind("요약")
    if summary_index < 0:
        return False
    summary_context = window[summary_index:]
    if re.search(r"요약\s*(?:하지|말고|없이)|요약하지", summary_context) is not None:
        return False
    if KOREAN_RAW_PRESERVATION_OBJECT_PATTERN.search(summary_context) is not None:
        return False
    return not _raw_category_matches(summary_context)


def _has_affirmative_korean_storage_action(text: str) -> bool:
    for storage_match in KOREAN_RAW_STORAGE_REQUEST_PATTERN.finditer(text):
        if not _is_negated_korean_action(text, storage_match.start("action")) and not _is_safe_korean_summary_action(
            text,
            storage_match.start("action"),
        ):
            return True
    return False


def _is_negated_english_raw_reference_after(text: str, raw_end: int) -> bool:
    suffix = text[raw_end : raw_end + 160]
    match = ENGLISH_NEGATED_STORAGE_AFTER_RAW_PATTERN.search(suffix)
    if match is None:
        return False
    before_negation = suffix[: match.start()]
    if ENGLISH_NEGATION_BOUNDARY_PATTERN.search(before_negation) is not None:
        return False
    if ENGLISH_DETACHED_POST_RAW_NEGATION_PATTERN.search(before_negation) is not None:
        return False
    if ENGLISH_TRAILING_CAVEAT_PATTERN.search(before_negation) is not None:
        return False
    if _has_affirmative_storage_after_post_raw_negation(suffix, match.end()):
        return False
    return not _has_affirmative_storage_action(before_negation)


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
    if prefix.rstrip().endswith(("do-not-", "do_not_", "must-not-", "should-not-")):
        return True
    if NEGATED_ENGLISH_ACTION_PREFIX_PATTERN.search(prefix) is not None:
        return True
    suffix = text[action_start : action_start + 40]
    return ENGLISH_ACTION_NOWHERE_PATTERN.search(suffix) is not None


def _has_affirmative_storage_action(text: str) -> bool:
    for storage_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(text):
        if not _is_negated_english_action(text, storage_match.start()):
            return True
    return False


def _has_safe_summary_transform_before(text: str) -> bool:
    for transform_match in SUMMARY_TRANSFORM_VERB_PATTERN.finditer(text):
        prefix = text[max(0, transform_match.start() - 40) : transform_match.start()]
        if NEGATED_SUMMARY_TRANSFORM_PREFIX_PATTERN.search(prefix) is None:
            return True
    return False


def _has_safe_derived_output_before(text: str) -> bool:
    for transform_match in DERIVED_TRANSFORM_VERB_PATTERN.finditer(text):
        prefix = text[max(0, transform_match.start() - 40) : transform_match.start()]
        if NEGATED_SUMMARY_TRANSFORM_PREFIX_PATTERN.search(prefix) is not None:
            continue
        following = text[transform_match.start() :]
        if DERIVED_OUTPUT_OBJECT_PATTERN.search(following) is not None:
            return True
    return False


def _has_safe_analysis_reference_before(text: str) -> bool:
    for transform_match in re.finditer(r"\banaly[sz]e\b", text, re.IGNORECASE):
        prefix = text[max(0, transform_match.start() - 40) : transform_match.start()]
        if NEGATED_SUMMARY_TRANSFORM_PREFIX_PATTERN.search(prefix) is not None:
            continue
        following = text[transform_match.end() :]
        if REFERENCE_RAW_OBJECT_PATTERN.search(following) is not None or _raw_category_matches(following):
            return True
    return False


def _has_safe_analysis_destination_before(prefix: str, suffix: str) -> bool:
    return (
        _has_safe_analysis_reference_before(prefix)
        and REFERENCE_RAW_OBJECT_PATTERN.search(suffix) is None
        and DERIVED_OUTPUT_OBJECT_PATTERN.search(suffix) is not None
    )


def _is_policy_doc_reference_action(action: str, suffix: str) -> bool:
    if action not in {"include", "add", "write", "save", "commit", "persist", "record"}:
        return False
    first_policy_markers: list[int] = []
    for pattern in (POLICY_DOC_DESTINATION_PATTERN, POLICY_PROHIBITION_CONTEXT_PATTERN):
        match = pattern.search(suffix)
        if match is not None:
            first_policy_markers.append(match.start())
    if first_policy_markers:
        policy_start = min(first_policy_markers)
        if UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix[:policy_start]) is not None:
            return False
    raw_matches = _raw_category_matches(suffix)
    if action not in {"include", "add", "write"} and first_policy_markers:
        policy_start = min(first_policy_markers)
        if raw_matches and all(int(match["start"]) < policy_start for match in raw_matches):
            return False
    return (
        POLICY_DOC_DESTINATION_PATTERN.search(suffix) is not None
        and raw_matches
        and any(_has_policy_prohibition_context_for_raw(suffix, match) for match in raw_matches)
        and POLICY_EXCEPTION_UNSAFE_DESTINATION_PATTERN.search(suffix) is None
    )


def _has_policy_prohibition_context_for_raw(suffix: str, raw_match: dict[str, Any]) -> bool:
    raw_start = int(raw_match["start"])
    raw_end = int(raw_match["end"])
    before = suffix[max(0, raw_start - 100) : raw_start]
    after = suffix[raw_end : raw_end + 100]
    return (
        POLICY_PROHIBITION_BEFORE_RAW_PATTERN.search(before) is not None
        or POLICY_PROHIBITION_AFTER_RAW_PATTERN.search(after) is not None
    )


def _is_policy_negation_clause(clause: str, raw_matches: list[dict[str, Any]]) -> bool:
    return (
        POLICY_DOC_DESTINATION_PATTERN.search(clause) is not None
        and any(_has_policy_prohibition_context_for_raw(clause, match) for match in raw_matches)
    )


def _is_safe_summary_storage_suffix(suffix: str) -> bool:
    summary_match = SAFE_SUMMARY_OBJECT_PATTERN.search(suffix)
    if summary_match is None:
        return False
    raw_matches = _active_raw_category_matches(suffix)
    if not raw_matches:
        return True
    for raw_match in raw_matches:
        raw_start = int(raw_match["start"])
        if int(summary_match.start()) >= raw_start:
            return False
        connector = suffix[summary_match.end() : raw_start]
        if (
            SUMMARY_SOURCE_CONNECTOR_PATTERN.search(connector) is None
            or RAW_INCLUSION_CONNECTOR_PATTERN.search(connector) is not None
        ):
            return False
    return True


def _is_safe_broad_storage_action(action: str, suffix: str) -> bool:
    if action not in BROAD_ENGLISH_STORAGE_ACTIONS:
        return False
    if action == "keep" and SAFE_KEEP_DIRECTION_PATTERN.search(suffix) is not None:
        return True
    if SAFE_BROAD_ACTION_LANGUAGE_PATTERN.search(suffix) is not None:
        return True
    raw_matches = _raw_category_matches(suffix)
    has_policy_context = (
        POLICY_PROHIBITION_CONTEXT_PATTERN.search(suffix) is not None
        or re.search(r"\b(?:blocked|rejected|prevented|excluded)\b", suffix, re.IGNORECASE) is not None
    )
    raw_policy_context = any(
        _has_policy_prohibition_context_for_raw(suffix, match)
        or re.search(
            r"\b(?:the\s+)?(?:forbidden|disallowed|rejected|blocked|prevented|excluded)\s+(?:list|items?)\b",
            suffix[int(match["end"]) : int(match["end"]) + 100],
            re.IGNORECASE,
        )
        is not None
        for match in raw_matches
    )
    if SAFE_BROAD_ACTION_OBJECT_PATTERN.search(suffix) is not None:
        if has_policy_context or UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix) is None:
            return True
    if raw_policy_context and UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix) is None:
        return True
    return False


def _is_bare_english_storage_imperative(action: str, prefix: str, suffix: str) -> bool:
    if action not in BARE_ENGLISH_STORAGE_ACTIONS:
        return False
    if re.fullmatch(r"\s*(?:please\s+|then\s+)?", prefix, re.IGNORECASE) is None:
        return False
    return re.fullmatch(r"\s*[.!?。]*\s*", suffix) is not None


def _same_clause_english_storage_match(clause: str) -> dict[str, str] | None:
    safe_summary_antecedent = False
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        action = _canonical_english_storage_action(english_match.group(1))
        suffix = clause[english_match.end() : english_match.end() + 120]
        if action == "keep" and KEEP_OUT_PATTERN.search(suffix) is not None:
            continue
        if _is_policy_doc_reference_action(action, suffix):
            continue
        if _is_safe_broad_storage_action(action, suffix):
            continue
        prefix_categories = _active_raw_categories(clause[max(0, english_match.start() - 120) : english_match.start()])
        full_prefix_categories = _active_raw_categories(clause[: english_match.start()])
        suffix_categories = _active_raw_categories(suffix)
        suffix_raw_reference = REFERENCE_RAW_OBJECT_PATTERN.search(suffix) is not None
        suffix_preserves_raw = RAW_PRESERVATION_QUALIFIER_PATTERN.search(suffix) is not None
        has_destination_prefix = DESTINATION_STORAGE_PREFIX_PATTERN.search(suffix) is not None
        prefix = clause[: english_match.start()]
        safe_derived_before = _has_safe_derived_output_before(prefix) or _has_safe_analysis_destination_before(
            prefix,
            suffix,
        )
        safe_summary_action = _is_safe_summary_storage_suffix(suffix) and (
            not prefix_categories or action == "write" or _has_safe_summary_transform_before(prefix)
        )
        safe_summary_reference_action = (
            not suffix_categories
            and _has_safe_summary_transform_before(clause[: english_match.start()])
            and suffix_raw_reference
            and not suffix_preserves_raw
        )
        safe_followup_action = (
            not suffix_categories
            and not suffix_raw_reference
            and SAFE_FOLLOWUP_OBJECT_PATTERN.search(suffix) is not None
        )
        safe_summary_pronoun_action = (
            safe_summary_antecedent and not suffix_categories and suffix_raw_reference and not suffix_preserves_raw
        )
        safe_derived_pronoun_action = (
            safe_derived_before
            and not suffix_categories
            and (DERIVED_REFERENCE_OBJECT_PATTERN.search(suffix) is not None or has_destination_prefix)
            and not suffix_preserves_raw
        )
        if safe_summary_action or safe_summary_reference_action:
            safe_summary_antecedent = True
            continue
        if safe_followup_action or safe_summary_pronoun_action or safe_derived_pronoun_action:
            continue
        window = clause[max(0, english_match.start() - 120) : english_match.end() + 120]
        window_categories = _active_raw_categories(window)
        if window_categories:
            return {
                "matched_categories": ",".join(window_categories),
                "matched_action": action,
            }
        if full_prefix_categories and (suffix_raw_reference or has_destination_prefix):
            return {
                "matched_categories": ",".join(full_prefix_categories),
                "matched_action": action,
            }
    return None


def _cross_clause_english_storage_match(
    clause: str,
    previous_categories: list[str],
    *,
    require_raw_reference: bool = False,
) -> dict[str, str] | None:
    if not previous_categories:
        return None
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 120]
        action = _canonical_english_storage_action(english_match.group(1))
        if action == "keep" and KEEP_OUT_PATTERN.search(suffix) is not None:
            continue
        if _is_policy_doc_reference_action(action, suffix):
            continue
        if _is_safe_broad_storage_action(action, suffix):
            continue
        has_raw_reference = REFERENCE_RAW_OBJECT_PATTERN.search(suffix) is not None
        has_destination_prefix = DESTINATION_STORAGE_PREFIX_PATTERN.search(suffix) is not None
        has_unsafe_destination = UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix) is not None
        has_storage_destination = has_unsafe_destination if action in BROAD_ENGLISH_STORAGE_ACTIONS else has_destination_prefix
        prefix = clause[: english_match.start()]
        has_prefix_raw_reference = REFERENCE_RAW_OBJECT_PATTERN.search(prefix) is not None
        safe_derived_pronoun_action = (
            (
                _has_safe_derived_output_before(prefix)
                or _has_safe_analysis_destination_before(prefix, suffix)
            )
            and (DERIVED_REFERENCE_OBJECT_PATTERN.search(suffix) is not None or has_storage_destination)
            and RAW_PRESERVATION_QUALIFIER_PATTERN.search(suffix) is None
        )
        if safe_derived_pronoun_action:
            continue
        if require_raw_reference and not has_raw_reference and not has_prefix_raw_reference:
            continue
        if SAFE_SUMMARY_OBJECT_PATTERN.search(suffix) is not None and not has_raw_reference and not has_storage_destination:
            continue
        if SAFE_FOLLOWUP_OBJECT_PATTERN.search(suffix) is not None and not has_raw_reference and not has_storage_destination:
            continue
        if SAFE_CROSS_STORAGE_OBJECT_PATTERN.search(suffix) is not None and not has_raw_reference and not has_storage_destination:
            continue
        if not has_raw_reference and not has_storage_destination and not has_prefix_raw_reference:
            if _is_bare_english_storage_imperative(action, prefix, suffix):
                return {
                    "matched_categories": ",".join(previous_categories),
                    "matched_action": action,
                }
            continue
        return {
            "matched_categories": ",".join(previous_categories),
            "matched_action": action,
        }
    return None


def _cross_clause_raw_preserving_storage_match(
    clause: str,
    previous_source_categories: list[str],
) -> dict[str, str] | None:
    if not previous_source_categories:
        return None
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 120]
        if RAW_PRESERVATION_QUALIFIER_PATTERN.search(suffix) is None:
            continue
        if (
            REFERENCE_RAW_OBJECT_PATTERN.search(suffix) is None
            and DESTINATION_STORAGE_PREFIX_PATTERN.search(suffix) is None
            and UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix) is None
        ):
            continue
        return {
            "matched_categories": ",".join(previous_source_categories),
            "matched_action": _canonical_english_storage_action(english_match.group(1)),
        }
    return None


def _forward_english_storage_match(clause: str) -> dict[str, str] | None:
    for english_match in ENGLISH_STORAGE_ACTION_PATTERN.finditer(clause):
        if _is_negated_english_action(clause, english_match.start()):
            continue
        suffix = clause[english_match.end() : english_match.end() + 160]
        action = _canonical_english_storage_action(english_match.group(1))
        if action == "keep" and KEEP_OUT_PATTERN.search(suffix) is not None:
            continue
        if _is_policy_doc_reference_action(action, suffix):
            continue
        if SUMMARY_ONLY_FORWARD_OBJECT_PATTERN.search(suffix) is not None:
            continue
        has_forward_object = FORWARD_STORAGE_OBJECT_PATTERN.search(suffix) is not None
        has_destination = (
            DESTINATION_STORAGE_PREFIX_PATTERN.search(suffix) is not None
            or UNSAFE_ARTIFACT_DESTINATION_PATTERN.search(suffix) is not None
        )
        has_forward_delimiter = FORWARD_DELIMITER_PATTERN.search(suffix) is not None
        if not has_forward_object and not has_destination and not has_forward_delimiter:
            continue
        return {
            "matched_action": _canonical_english_storage_action(english_match.group(1)),
        }
    return None


def _forward_korean_storage_match(clause: str) -> dict[str, str] | None:
    for korean_match in KOREAN_RAW_STORAGE_REQUEST_PATTERN.finditer(clause):
        action_start = korean_match.start("action")
        if _is_negated_korean_action(clause, action_start) or _is_safe_korean_summary_action(clause, action_start):
            continue
        window = clause[max(0, action_start - 80) : korean_match.end() + 80]
        if (
            KOREAN_FORWARD_STORAGE_OBJECT_PATTERN.search(window) is None
            and re.search(r"[:：]\s*$", korean_match.group(0)) is None
        ):
            continue
        return {
            "matched_action": korean_match.group("action"),
        }
    return None


def _korean_storage_match(clause: str, categories: list[str]) -> dict[str, str] | None:
    if not categories:
        return None
    for korean_match in KOREAN_RAW_STORAGE_REQUEST_PATTERN.finditer(clause):
        action_start = korean_match.start("action")
        form = korean_match.group("form")
        if form in KOREAN_ATTRIBUTIVE_STORAGE_FORMS:
            suffix = clause[korean_match.end() : korean_match.end() + 80]
            if KOREAN_ATTRIBUTIVE_STORAGE_TARGET_PATTERN.search(suffix) is None:
                continue
        if _is_negated_korean_action(clause, action_start) or _is_safe_korean_summary_action(clause, action_start):
            continue
        return {
            "matched_categories": ",".join(categories),
            "matched_action": korean_match.group("action"),
        }
    return None


def _is_safe_output_clause(clause: str) -> bool:
    if NEGATED_SUMMARY_OUTPUT_PATTERN.search(clause) is not None:
        return False
    return (
        AFFIRMATIVE_SUMMARY_OUTPUT_PATTERN.search(clause) is not None
        or _has_safe_summary_transform_before(clause)
        or _has_safe_derived_output_before(clause)
    )


def _explicit_raw_storage_request(prompt: str) -> dict[str, str] | None:
    previous_categories: list[str] = []
    previous_negated_categories: list[str] = []
    previous_safe_source_categories: list[str] = []
    pending_forward_storage: dict[str, str] | None = None
    pending_forward_excluded_categories: list[str] = []
    for clause in PROMPT_CLAUSE_PATTERN.split(prompt):
        clause = clause.strip()
        if not clause:
            continue

        same_clause_match = _same_clause_english_storage_match(clause)
        if same_clause_match is not None:
            return same_clause_match

        raw_matches = _raw_category_matches(clause)
        raw_categories = _unique_categories(raw_matches)
        categories = _active_raw_categories(clause)
        if categories and pending_forward_storage is not None:
            categories = [category for category in categories if category not in pending_forward_excluded_categories]
        if categories and pending_forward_storage is not None:
            return {
                "matched_categories": ",".join(categories),
                "matched_action": pending_forward_storage["matched_action"],
            }

        korean_context_categories = categories or previous_categories
        if (
            not korean_context_categories
            and previous_negated_categories
            and (
                KOREAN_REFERENCE_RAW_OBJECT_PATTERN.search(clause) is not None
                or LOOSE_ARTIFACT_DESTINATION_PATTERN.search(clause) is not None
            )
        ):
            korean_context_categories = previous_negated_categories
        korean_match = _korean_storage_match(clause, korean_context_categories)
        if korean_match is not None:
            return korean_match

        raw_preserving_match = _cross_clause_raw_preserving_storage_match(
            clause,
            previous_safe_source_categories or previous_categories,
        )
        if raw_preserving_match is not None:
            return raw_preserving_match

        cross_clause_match = _cross_clause_english_storage_match(clause, previous_categories)
        if cross_clause_match is not None:
            return cross_clause_match

        negated_cross_clause_match = _cross_clause_english_storage_match(
            clause,
            previous_negated_categories,
            require_raw_reference=True,
        )
        if negated_cross_clause_match is not None:
            return negated_cross_clause_match

        safe_output_clause = _is_safe_output_clause(clause)
        if not (categories and safe_output_clause):
            forward_storage_match = _forward_english_storage_match(clause)
            if forward_storage_match is None:
                forward_storage_match = _forward_korean_storage_match(clause)
            if forward_storage_match is not None:
                if categories:
                    return {
                        "matched_categories": ",".join(categories),
                        "matched_action": forward_storage_match["matched_action"],
                    }
                pending_forward_storage = forward_storage_match
                pending_forward_excluded_categories = []
                continue

        if safe_output_clause:
            if categories or previous_categories:
                previous_safe_source_categories = categories or previous_categories
            previous_categories = []
            previous_negated_categories = []
        elif categories:
            if _is_policy_negation_clause(clause, raw_matches):
                previous_categories = []
                previous_negated_categories = []
            else:
                previous_categories = categories
                previous_negated_categories = []
            previous_safe_source_categories = []
        elif raw_categories:
            previous_negated_categories = [] if _is_policy_negation_clause(clause, raw_matches) else raw_categories
            for category in raw_categories:
                if category not in pending_forward_excluded_categories:
                    pending_forward_excluded_categories.append(category)
            previous_safe_source_categories = []
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
