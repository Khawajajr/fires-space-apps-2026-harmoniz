"""English and Arabic text. One file, web/i18n/strings.json, holds every string of the web app ("ui.*") and every
sentence the API writes ("api.*"); the API formats its sentences in the requested language (?lang=en|ar).
Numbers and dates stay in Western digits in both languages."""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Literal

from godseye.config import get_config

Lang = Literal["en", "ar"]
FSI, PDI = "\u2068", "\u2069"     # first-strong isolate: a date or number range keeps its order inside Arabic text


def isolate(value) -> str:
    return f"{FSI}{value}{PDI}"


@lru_cache
def strings() -> dict[str, dict[str, str]]:
    return json.loads((get_config().web_dir / "i18n" / "strings.json").read_text(encoding="utf-8"))


def t(lang: str, key: str, default: str | None = None, **params) -> str:
    """The string for `key` in `lang` (falling back to English, then to `default`), with {params} filled in."""
    s = strings()
    text = s.get(lang, {}).get(key) or s["en"].get(key) or default
    if text is None:
        raise KeyError(f"no string {key!r} in web/i18n/strings.json")
    if lang == "ar":            # values inserted into right-to-left text: isolate them so "2026-11-14" isn't reordered
        params = {k: isolate(v) for k, v in params.items()}
    return text.format(**params)
