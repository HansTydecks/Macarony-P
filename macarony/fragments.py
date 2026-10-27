"""Step 2b: normalize a translation and cut it into candidate fragments."""

from __future__ import annotations

import unicodedata

MIN_FRAGMENT = 2
MAX_FRAGMENT = 4

#: Roles a fragment can play in the recombined word.
PREFIX = "prefix"
MIDDLE = "middle"
SUFFIX = "suffix"
ROLES = (PREFIX, MIDDLE, SUFFIX)

VOWELS = set("aeiouyáàâäãåéèêëíìîïóòôöõúùûüýøæœœ")


def strip_diacritics(text: str) -> str:
    """"fågel" -> "fagel".  German eszett and the Nordic slashed o need help."""
    text = text.replace("ß", "ss").replace("ø", "o").replace("Ø", "O")
    text = text.replace("æ", "ae").replace("Æ", "Ae")
    text = text.replace("œ", "oe").replace("Œ", "Oe")
    text = text.replace("ł", "l").replace("Ł", "L")
    text = text.replace("đ", "d").replace("ð", "d").replace("þ", "th")
    decomposed = unicodedata.normalize("NFD", text)
    return unicodedata.normalize(
        "NFC", "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    )


def latin_form(result: dict) -> str:
    """The spelling of a translation that can be cut into letters.

    Non-Latin scripts cannot be mixed into a pronounceable word, so a
    romanization is used instead when the translator supplied one.
    """
    text = (result.get("text") or "").strip()
    romanized = (result.get("romanized") or "").strip()
    if not text:
        return romanized
    if romanized and not _is_latin(text):
        return romanized
    return text


def _is_latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return False
    return all("LATIN" in unicodedata.name(ch, "") for ch in letters)


def normalize(text: str, ascii_only: bool = False) -> str:
    """Reduce a translation to one lowercase run of letters.

    Multi-word translations keep only their longest word, which drops articles
    and particles ("der Vogel" -> "vogel", "l'oiseau" -> "oiseau").
    """
    if not text:
        return ""
    cleaned = text.strip().lower()
    if ascii_only:
        cleaned = strip_diacritics(cleaned)

    # Split on anything that is not a letter, then keep the longest piece.
    pieces: list[str] = []
    current: list[str] = []
    for ch in cleaned:
        if ch.isalpha():
            current.append(ch)
        elif current:
            pieces.append("".join(current))
            current = []
    if current:
        pieces.append("".join(current))
    if not pieces:
        return ""
    return max(pieces, key=len)


def extract_fragments(word: str, lang: str, min_len: int = MIN_FRAGMENT,
                      max_len: int = MAX_FRAGMENT) -> list[dict]:
    """Every substring of ``word`` between ``min_len`` and ``max_len`` letters.

    Each fragment records where it came from, which is what step 3 recombines
    by: a *prefix* starts at the first letter, a *suffix* ends at the last one,
    a *middle* sits strictly inside.  The whole word is not a fragment -- a
    prefix has to leave something out for another language to supply.
    """
    min_len = max(1, min_len)
    max_len = max(min_len, max_len)
    n = len(word)
    fragments: list[dict] = []
    for start in range(n):
        for end in range(start + min_len, min(n, start + max_len) + 1):
            if start == 0 and end == n:
                continue
            if start == 0:
                role = PREFIX
            elif end == n:
                role = SUFFIX
            else:
                role = MIDDLE
            fragments.append({
                "text": word[start:end],
                "lang": lang,
                "start": start,
                "end": end,
                "role": role,
            })
    return fragments


def group_by_role(fragments: list[dict]) -> dict[str, list[dict]]:
    """Fragments bucketed into prefix / middle / suffix, duplicates dropped."""
    grouped: dict[str, list[dict]] = {role: [] for role in ROLES}
    seen: set[tuple[str, str]] = set()
    for fragment in fragments:
        key = (fragment["role"], fragment["text"])
        if key in seen:
            continue
        seen.add(key)
        grouped[fragment["role"]].append(fragment)
    return grouped
