from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from .artifacts import (
    APP_CARDS_TYPE,
    APP_COLLECTION_TYPE,
    APP_SESSION_TYPE,
    BRIEF_TYPE,
    EVIDENCE_TYPE,
    GOAL_LOCK_TYPE,
    MATRIX_TYPE,
    ORCHESTRATOR_TYPE,
    PROBE_PLAN_TYPE,
    PROBE_RESULT_TYPE,
    RUN_MANIFEST_TYPE,
    SCORECARD_TYPE,
)


SCHEMA_VERSION = "v0.1"

SCHEMA_FILES = {
    APP_CARDS_TYPE: "app-cards.schema.json",
    APP_COLLECTION_TYPE: "app-collection.schema.json",
    APP_SESSION_TYPE: "app-session.schema.json",
    BRIEF_TYPE: "intent-brief.schema.json",
    EVIDENCE_TYPE: "evidence.schema.json",
    GOAL_LOCK_TYPE: "goal-lock.schema.json",
    MATRIX_TYPE: "evaluation-matrix.schema.json",
    ORCHESTRATOR_TYPE: "orchestrator.schema.json",
    PROBE_PLAN_TYPE: "probe-plan.schema.json",
    PROBE_RESULT_TYPE: "probe-result.schema.json",
    RUN_MANIFEST_TYPE: "run-manifest.schema.json",
    SCORECARD_TYPE: "scorecard.schema.json",
}


def schema_dir(version: str = SCHEMA_VERSION) -> Path:
    if version != SCHEMA_VERSION:
        raise KeyError(f"unsupported schema version: {version}")
    return Path(resources.files("rubricodex").joinpath("schemas", version))


def schema_path(artifact_type: str, version: str = SCHEMA_VERSION) -> Path:
    try:
        filename = SCHEMA_FILES[artifact_type]
    except KeyError as error:
        raise KeyError(f"unknown artifact type: {artifact_type}") from error
    return schema_dir(version) / filename


def load_schema(artifact_type: str, version: str = SCHEMA_VERSION) -> dict[str, Any]:
    path = schema_path(artifact_type, version)
    with path.open("r", encoding="utf-8") as handle:
        schema = json.load(handle)
    if not isinstance(schema, dict):
        raise ValueError(f"schema must be a JSON object: {path}")
    return schema


def schema_index(version: str = SCHEMA_VERSION) -> dict[str, str]:
    index: dict[str, str] = {}
    for artifact_type in sorted(SCHEMA_FILES):
        index[artifact_type] = load_schema(artifact_type, version)["$id"]
    return index
