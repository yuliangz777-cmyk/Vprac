"""Pure text helpers for cleaning and stitching streaming transcripts.

Everything here is deliberately dependency-free and side-effect-free so it can
be unit tested without touching the network.
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

# Whisper-family models hallucinate stock phrases when handed near-silence.
# These are the ones that show up in practice on Mandarin and English lectures.
_SILENCE_ARTIFACT_SOURCES = frozenset(
    {
        "字幕由amara.org社群提供",
        "字幕由amara.org社区提供",
        "字幕志願者李宗盛",
        "中文字幕由玛丽提供",
        "請不吝點贊訂閱轉發打賞支持明鏡與點點欄目",
        "明鏡與點點欄目",
        "謝謝觀看",
        "謝謝大家",
        "感謝觀看",
        "下次再見",
        "我們下次再見",
        "多謝收睇",
        "字幕製作",
        "優優獨播劇場",
        "小編",
        "thanksforwatching",
        "thankyouforwatching",
        "thankyou",
        "subtitlesbytheamara.orgcommunity",
        "subtitlesbyamara.org",
        "youtube",
        "bye",
        "byebye",
        "seeyounexttime",
        "pleasesubscribe",
    }
)

_PUNCT_RE = re.compile(r"[\s　-〿＀-￯!-/:-@\[-`{-~]+")

_MIN_OVERLAP = 4
_MAX_OVERLAP = 120


def normalize_key(text: str) -> str:
    """Lowercase, drop punctuation and whitespace: a comparison key."""
    text = unicodedata.normalize("NFKC", text or "").lower()
    return _PUNCT_RE.sub("", text)


# The literal set above is written for readability; compare against the same
# normalised form the lookup key uses, so entries with punctuation still match.
_SILENCE_ARTIFACTS = frozenset(normalize_key(item) for item in _SILENCE_ARTIFACT_SOURCES)


def collapse_repeats(text: str, *, max_unit: int = 24, keep: int = 2) -> str:
    """Collapse runaway ASR loops such as ``的的的的的`` or a looping phrase."""
    if not text:
        return text

    # Single characters repeated many times in a row.
    text = re.sub(r"(.)\1{5,}", lambda m: m.group(1) * keep, text)

    # A multi-character unit repeated back to back at least four times.
    for unit in range(2, max_unit + 1):
        pattern = re.compile(r"(.{%d}?)\1{3,}" % unit, re.DOTALL)
        text = pattern.sub(lambda m: m.group(1) * keep, text)
    return text


def looks_like_silence_artifact(text: str) -> bool:
    """True when a transcript chunk carries no real speech."""
    key = normalize_key(text)
    if not key:
        return True
    if key in _SILENCE_ARTIFACTS:
        return True
    # A single repeated character ("嗯嗯嗯", "。。。") is not usable content.
    if len(set(key)) == 1 and len(key) <= 8:
        return True
    return False


def clean_transcript_chunk(text: str) -> str:
    """Normalise one transcription result; returns '' when it is unusable."""
    text = (text or "").strip()
    if not text:
        return ""
    text = collapse_repeats(text)
    text = re.sub(r"[ \t]{2,}", " ", text).strip()
    if looks_like_silence_artifact(text):
        return ""
    return text


def _compact(text: str) -> tuple[str, list[int]]:
    """Whitespace-free lowercase copy plus a map back to original indices."""
    chars: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char.lower())
            positions.append(index)
    return "".join(chars), positions


def _is_cjk(char: str) -> bool:
    code = ord(char)
    return (
        0x3040 <= code <= 0x30FF  # kana
        or 0x3400 <= code <= 0x4DBF  # CJK ext A
        or 0x4E00 <= code <= 0x9FFF  # CJK unified
        or 0xF900 <= code <= 0xFAFF  # compatibility
        or 0xFF00 <= code <= 0xFF65  # fullwidth forms
    )


def join_transcript(previous: str, addition: str) -> str:
    """Append ``addition`` to ``previous``, trimming any repeated overlap.

    Segments are cut on silence, but a forced cut mid-sentence deliberately
    carries a little audio overlap so no syllable is lost. That overlap comes
    back as duplicated text, which is what this removes.
    """
    addition = (addition or "").strip()
    if not addition:
        return previous
    previous = (previous or "").rstrip()
    if not previous:
        return addition

    tail = previous[-(_MAX_OVERLAP * 2):]
    tail_compact, _ = _compact(tail)
    add_compact, add_positions = _compact(addition)

    limit = min(_MAX_OVERLAP, len(tail_compact), len(add_compact))
    for size in range(limit, _MIN_OVERLAP - 1, -1):
        if tail_compact.endswith(add_compact[:size]):
            addition = addition[add_positions[size - 1] + 1:].lstrip()
            break

    if not addition:
        return previous

    separator = ""
    if not _is_cjk(previous[-1]) and not _is_cjk(addition[0]):
        separator = " "
    return previous + separator + addition


def clean_json_text(text: str) -> str:
    """Strip markdown fences and any prose around a JSON object."""
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        text = text[start : end + 1]
    return text.strip()


_NOTE_LIST_FIELDS = ("summary", "exam_points", "open_questions")


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            text = item.get("text") or item.get("point") or item.get("content")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def parse_notes(text: str) -> dict[str, Any]:
    """Parse a model reply into the notes shape, never raising."""
    empty: dict[str, Any] = {
        "summary": [],
        "concepts": [],
        "exam_points": [],
        "open_questions": [],
        "latest": "",
    }
    try:
        data = json.loads(clean_json_text(text))
    except (json.JSONDecodeError, TypeError):
        # Degrade to a single free-text bullet rather than losing the reply.
        stripped = (text or "").strip()
        return {**empty, "summary": [stripped] if stripped else []}
    if not isinstance(data, dict):
        return empty

    notes = {field: _as_str_list(data.get(field)) for field in _NOTE_LIST_FIELDS}

    concepts: list[dict[str, str]] = []
    raw_concepts = data.get("concepts")
    if isinstance(raw_concepts, list):
        for item in raw_concepts:
            if isinstance(item, dict):
                term = str(item.get("term") or "").strip()
                explanation = str(item.get("explanation") or "").strip()
                if term:
                    concepts.append({"term": term, "explanation": explanation})
            elif isinstance(item, str) and item.strip():
                concepts.append({"term": item.strip(), "explanation": ""})
    notes["concepts"] = concepts

    latest = data.get("latest")
    notes["latest"] = latest.strip() if isinstance(latest, str) else ""
    return notes
