import ast
import json
import re
from collections.abc import Iterable
from typing import Any

_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def extract_json_object(text: str) -> dict[str, Any]:
    """Extract and parse the first valid JSON object found in text."""

    for fenced in _JSON_FENCE_PATTERN.findall(text):
        parsed = _try_parse_candidate(fenced)
        if parsed is not None:
            return parsed

    parsed = _try_parse_candidate(text)
    if parsed is not None:
        return parsed

    for candidate in _iter_balanced_json_chunks(text):
        parsed = _try_parse_candidate(candidate)
        if parsed is not None:
            return parsed

    raise ValueError("No valid JSON object found in model output.")


def extract_final_itinerary_json(
    conversation_log: Iterable[str],
    final_token: str,
) -> dict[str, Any]:
    """Find the final itinerary JSON from a sequence of conversation messages."""

    entries = list(conversation_log)
    for entry in reversed(entries):
        if final_token in entry:
            segment = entry.split(final_token, maxsplit=1)[1]
            try:
                return extract_json_object(segment)
            except ValueError:
                pass

        try:
            return extract_json_object(entry)
        except ValueError:
            continue

    combined = "\n".join(entries)
    return extract_json_object(combined)


def _try_parse_candidate(candidate: str) -> dict[str, Any] | None:
    candidate = _normalize_candidate(candidate)
    if not candidate:
        return None

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(candidate)
        except (SyntaxError, ValueError):
            return None

    if isinstance(parsed, dict):
        return {str(key): value for key, value in parsed.items()}
    return None


def _normalize_candidate(candidate: str) -> str:
    return (
        candidate.strip()
        .replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2019", "'")
        .replace("\u2018", "'")
    )


def _iter_balanced_json_chunks(text: str) -> Iterable[str]:
    start = -1
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if start == -1:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                yield text[start : index + 1]
                start = -1
