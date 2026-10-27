"""Step 1 (tokenizing) plus the orchestration of steps 2 and 3."""

from __future__ import annotations

import re

from macarony.fragments import (
    MAX_FRAGMENT,
    MIN_FRAGMENT,
    ROLES,
    latin_form,
    normalize,
)
from macarony.recombine import recombine
from macarony.translate import (
    DEFAULT_LANGUAGES,
    GoogleTranslator,
    OfflineTranslator,
    language_name,
)

#: A word is a run of letters, optionally joined by an apostrophe or hyphen, so
#: "don't" and "well-known" stay single words.  Digits are not words.
_WORD_RE = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)

DEFAULT_OPTIONS = {
    "languages": list(DEFAULT_LANGUAGES),
    "parts": 3,
    "language_order": None,
    "min_frag": MIN_FRAGMENT,
    "max_frag": MAX_FRAGMENT,
    "count": 10,
    "seed": 0,
    "ascii_only": True,
    "offline": False,
}


def tokenize(sentence: str) -> list[dict]:
    """Split a sentence into words and the spacing/punctuation between them.

    Everything is kept, so ``"".join(t["text"] for t in tokens)`` rebuilds the
    input exactly.  ``index`` is the position in this list and is what the
    caller passes back to say which words it picked.
    """
    tokens: list[dict] = []
    cursor = 0

    def add(text: str, is_word: bool) -> None:
        if text:
            tokens.append({"index": len(tokens), "text": text, "is_word": is_word})

    for match in _WORD_RE.finditer(sentence or ""):
        add(sentence[cursor:match.start()], False)
        add(match.group(0), True)
        cursor = match.end()
    add((sentence or "")[cursor:], False)
    return tokens


def match_case(source: str, word: str) -> str:
    """Give the invented word the capitalization of the word it replaces."""
    if not word:
        return word
    if source.isupper() and len(source) > 1:
        return word.upper()
    if source[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def _merge_options(options: dict | None) -> dict:
    merged = dict(DEFAULT_OPTIONS)
    merged["languages"] = list(DEFAULT_OPTIONS["languages"])
    for key, value in (options or {}).items():
        if key in merged and value is not None:
            merged[key] = value

    merged["parts"] = 3 if int(merged["parts"]) >= 3 else 2
    merged["min_frag"] = max(1, min(6, int(merged["min_frag"])))
    merged["max_frag"] = max(merged["min_frag"], min(8, int(merged["max_frag"])))
    merged["count"] = max(1, min(60, int(merged["count"])))
    merged["seed"] = int(merged["seed"])
    merged["ascii_only"] = bool(merged["ascii_only"])
    merged["offline"] = bool(merged["offline"])

    languages = [str(lang) for lang in merged["languages"] if str(lang).strip()]
    # Keep the first occurrence of each language, preserving the caller's order.
    merged["languages"] = list(dict.fromkeys(languages)) or list(DEFAULT_LANGUAGES)

    order = merged["language_order"]
    if order:
        order = [lang for lang in order if lang in merged["languages"]]
        merged["language_order"] = order or None
    else:
        merged["language_order"] = None
    return merged


def _collect_translations(word: str, results: dict, options: dict) -> list[dict]:
    """Shape the raw translator output for display and for step 3."""
    source = normalize(word, options["ascii_only"])
    rows: list[dict] = []
    for lang in options["languages"]:
        result = results.get(lang) or {"lang": lang, "error": "no response"}
        latin = latin_form(result)
        rows.append({
            "lang": lang,
            "name": language_name(lang),
            "text": result.get("text") or "",
            "romanized": result.get("romanized"),
            "normalized": normalize(latin, options["ascii_only"]),
            "error": result.get("error"),
            "used": False,
            "dropped": None,
        })

    usable = [row for row in rows if row["normalized"]]
    # A translation identical to the English word contributes nothing to a
    # mixed-language word ("hotel" is "hotel" nearly everywhere), so drop those
    # -- but only while enough languages are left to fill every part.
    identical = [row for row in usable if row["normalized"] == source]
    needed = max(2, options["parts"])
    if identical and len(usable) - len(identical) >= needed:
        for row in identical:
            row["dropped"] = "same as the English word"

    for row in rows:
        row["used"] = bool(row["normalized"]) and row["dropped"] is None
    return rows


def _fragment_view(normalized: dict[str, str], options: dict) -> list[dict]:
    """Per-language fragment lists, for the step 2 panel in the UI."""
    from macarony.recombine import build_pools

    pools = build_pools(normalized, options["min_frag"], options["max_frag"])
    view: list[dict] = []
    for lang, buckets in pools.items():
        view.append({
            "lang": lang,
            "name": language_name(lang),
            "word": normalized[lang],
            "roles": {role: [f["text"] for f in buckets[role]] for role in ROLES},
        })
    return view


def _pick_translator(options: dict):
    if options["offline"]:
        return OfflineTranslator(), None
    return GoogleTranslator(), None


def process(sentence: str, selected: list[int] | None = None,
            options: dict | None = None, translator=None) -> dict:
    """Run the whole pipeline over a sentence and the words picked in it."""
    options = _merge_options(options)
    tokens = tokenize(sentence)
    wanted = sorted({
        int(index) for index in (selected or [])
        if 0 <= int(index) < len(tokens) and tokens[int(index)]["is_word"]
    })

    if translator is None:
        translator, _ = _pick_translator(options)
    notice = None

    words: list[dict] = []
    for index in wanted:
        source = tokens[index]["text"]
        results = translator.translate(source, options["languages"])

        # The free endpoint can rate-limit or vanish; fall back to the bundled
        # dictionary rather than returning an empty result.
        if (not options["offline"]
                and all(row.get("error") for row in results.values())):
            fallback = OfflineTranslator()
            fallback_results = fallback.translate(source, options["languages"])
            if any(not row.get("error") for row in fallback_results.values()):
                results = fallback_results
                translator = fallback
                notice = ("The online translator could not be reached; "
                          "using the bundled offline dictionary.")

        rows = _collect_translations(source, results, options)
        normalized = {row["lang"]: row["normalized"] for row in rows if row["used"]}
        candidates = recombine(
            source,
            normalized,
            parts=options["parts"],
            language_order=options["language_order"],
            min_frag=options["min_frag"],
            max_frag=options["max_frag"],
            count=options["count"],
            seed=options["seed"],
        )
        for candidate in candidates:
            candidate["display"] = match_case(source, candidate["word"])

        words.append({
            "index": index,
            "source": source,
            "translations": rows,
            "fragments": _fragment_view(normalized, options),
            "candidates": candidates,
            "error": None if candidates else _why_empty(rows, options),
        })

    replacements = {
        word["index"]: word["candidates"][0]["display"]
        for word in words if word["candidates"]
    }
    sentence_out = "".join(
        replacements.get(token["index"], token["text"]) for token in tokens
    )

    return {
        "sentence": sentence,
        "sentence_out": sentence_out,
        "tokens": tokens,
        "selected": wanted,
        "words": words,
        "options": options,
        "translator": getattr(translator, "name", "unknown"),
        "notice": notice,
    }


def _why_empty(rows: list[dict], options: dict) -> str:
    """A short explanation for a word that produced no mixed-language word."""
    usable = [row for row in rows if row["used"]]
    needed = max(2, options["parts"])
    if not usable:
        errors = [row["error"] for row in rows if row["error"]]
        if errors:
            return f"no translations available ({errors[0]})"
        return "no translations available"
    if len(usable) < needed:
        return (f"only {len(usable)} usable translation(s); "
                f"{needed} different languages are needed")
    return ("the translations are too short to cut into "
            f"{options['min_frag']}-letter fragments")
