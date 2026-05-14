from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any


def extract_json_payload(text: str) -> Any:
    stripped = text.strip()
    if not stripped:
        raise ValueError("subagent response was empty")
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL | re.IGNORECASE)
    if fence:
        return json.loads(fence.group(1).strip())

    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            payload, _ = decoder.raw_decode(stripped[index:])
            return payload
        except json.JSONDecodeError:
            continue
    raise ValueError("subagent response did not contain JSON")


def run_read_only_json(
    root: Path,
    prompt: str,
    *,
    timeout: int = 60,
    codex_bin: str = "codex",
) -> Any | None:
    with tempfile.TemporaryDirectory(prefix="rubricodex-subagent-") as tmpdir:
        output_path = Path(tmpdir) / "last-message.txt"
        try:
            completed = subprocess.run(
                [
                    codex_bin,
                    "exec",
                    "--sandbox",
                    "read-only",
                    "--ephemeral",
                    "--cd",
                    str(root),
                    "--output-last-message",
                    str(output_path),
                    "-",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if completed.returncode != 0:
            return None
        if output_path.exists():
            text = output_path.read_text(encoding="utf-8")
        else:
            text = completed.stdout
        try:
            return extract_json_payload(text)
        except (json.JSONDecodeError, ValueError, TypeError):
            return None
