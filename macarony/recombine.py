"""Step 3: glue fragments from different languages into one fake word.

The rule is positional.  A three-part word takes its *prefix* from one
language, its *middle* from a second and its *suffix* from a third::

    de "vogel" -> "vog"  +  pl "ptak" -> "ta"  +  sv "fagel" -> "gel"
                                  = "vogtagel"

A two-part word is just prefix + suffix.  Every part must come from a
different language, so the result belongs to none of them.
"""

from __future__ import annotations

import itertools
import random
import statistics

from macarony.fragments import (
    MAX_FRAGMENT,
    MIDDLE,
    MIN_FRAGMENT,
    PREFIX,
    SUFFIX,
    VOWELS,
    extract_fragments,
    group_by_role,
)

#: How many prefix/middle/suffix combinations to enumerate before switching to
#: seeded random sampling.  Keeps a request fast when many languages are used.
SAMPLE_CAP = 50_000

# Weights of the three score components.  They sum to 1, so a score reads as a
# rough 0..1 quality.  Many candidates score identically; ties are broken by a
# seeded random value rather than alphabetically, which stops the top of the
# list filling up with ten words that share a first fragment.
W_LENGTH = 0.45
W_PRONOUNCEABLE = 0.40
W_BALANCE = 0.15

#: Filtering strictness, tried hardest-first so a result always comes back.
_STRICT, _MEDIUM, _LOOSE = 2, 1, 0


def build_pools(normalized: dict[str, str], min_frag: int = MIN_FRAGMENT,
                max_frag: int = MAX_FRAGMENT) -> dict[str, dict[str, list[dict]]]:
    """``{lang: {role: [fragment, ...]}}`` for every non-empty translation."""
    pools: dict[str, dict[str, list[dict]]] = {}
    for lang, word in normalized.items():
        if not word:
            continue
        pools[lang] = group_by_role(extract_fragments(word, lang, min_frag, max_frag))
    return pools


def _roles_for(parts: int) -> tuple[str, ...]:
    return (PREFIX, MIDDLE, SUFFIX) if parts >= 3 else (PREFIX, SUFFIX)


def _usable_orders(pools: dict, langs: list[str], roles: tuple[str, ...],
                   language_order: list[str] | None) -> list[tuple[str, ...]]:
    """Ordered language tuples that can actually fill every role."""
    if language_order:
        wanted = tuple(language_order[:len(roles)])
        if len(wanted) != len(roles) or len(set(wanted)) != len(wanted):
            return []
        candidates = [wanted]
    else:
        candidates = list(itertools.permutations(langs, len(roles)))

    usable = []
    for order in candidates:
        if any(lang not in pools for lang in order):
            continue
        if all(pools[lang][role] for lang, role in zip(order, roles)):
            usable.append(order)
    return usable


def _runs(word: str) -> list[tuple[int, int]]:
    """Maximal same-kind (vowel or consonant) runs as ``(start, length)``."""
    runs: list[tuple[int, int]] = []
    if not word:
        return runs
    start = 0
    kind = word[0] in VOWELS
    for index in range(1, len(word) + 1):
        current = word[index] in VOWELS if index < len(word) else None
        if current != kind:
            runs.append((start, index - start))
            start, kind = index, current
    return runs


def _pronounceability(word: str, seams: list[int]) -> float:
    """Penalize long vowel/consonant pile-ups, hardest where fragments meet."""
    penalty = 0.0
    for start, length in _runs(word):
        if length < 3:
            continue
        excess = length - 2
        crosses_seam = any(start < seam < start + length for seam in seams)
        penalty += excess * (1.5 if crosses_seam else 1.0)
    return max(0.0, 1.0 - 0.25 * penalty)


def _balance(lengths: list[int]) -> float:
    total = sum(lengths)
    if total <= 0 or len(lengths) < 2:
        return 1.0
    return 1.0 - (max(lengths) - min(lengths)) / total


def _length_score(length: int, median: float) -> float:
    if median <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(length - median) / median)


def _acceptable(word: str, forbidden: set[str], median: float, strictness: int) -> bool:
    """Is this string gibberish enough to be worth showing?"""
    if not word or word in forbidden:
        return False
    if strictness >= _MEDIUM:
        # A fragment of a real translation is not a new word.
        if any(word in real for real in forbidden):
            return False
        if not 0.6 * median <= len(word) <= 1.6 * median:
            return False
    if strictness >= _STRICT:
        # Nor is anything that swallows a real translation whole.
        if any(real in word for real in forbidden if len(real) >= 3):
            return False
    return True


def _assemble(order: tuple[str, ...], roles: tuple[str, ...],
              picks: tuple[dict, ...]) -> tuple[str, list[dict]]:
    word = "".join(piece["text"] for piece in picks)
    parts = [
        {"text": piece["text"], "lang": lang, "role": role}
        for piece, lang, role in zip(picks, order, roles)
    ]
    return word, parts


def recombine(source_word: str, normalized: dict[str, str], *, parts: int = 3,
              language_order: list[str] | None = None, min_frag: int = MIN_FRAGMENT,
              max_frag: int = MAX_FRAGMENT, count: int = 10, seed: int = 0,
              max_per_order: int = 2, sample_cap: int = SAMPLE_CAP) -> list[dict]:
    """Build, filter, score and rank mixed-language words for one source word.

    ``normalized`` maps a language code to its cleaned translation.  The return
    value is a list of ``{word, score, parts, metrics}`` dicts, best first, with
    every part drawn from a different language.
    """
    pools = build_pools(normalized, min_frag, max_frag)
    langs = list(pools)
    roles = _roles_for(parts)
    if len(langs) < len(roles):
        return []

    orders = _usable_orders(pools, langs, roles, language_order)
    if not orders:
        return []

    lengths = [len(word) for word in normalized.values() if word]
    median = statistics.median(lengths) if lengths else 0.0
    forbidden = {word for word in normalized.values() if word}
    source_normalized = source_word.strip().lower()
    if source_normalized:
        forbidden.add(source_normalized)

    total = sum(
        _product(len(pools[lang][role]) for lang, role in zip(order, roles))
        for order in orders
    )

    def raw_stream():
        """A fresh pass over the candidate space.

        Each strictness attempt needs its own pass (a generator cannot be
        replayed) and its own identically seeded RNG, so relaxing the filter
        never changes which candidates were considered.
        """
        if total <= sample_cap:
            return _enumerate_all(pools, orders, roles)
        return _sample(
            pools, orders, roles,
            random.Random(f"{seed}:{source_normalized}:sample"), sample_cap,
        )

    # Strict first; relax only if nothing survives, so a result always comes back.
    for strictness in (_STRICT, _MEDIUM, _LOOSE):
        ranked = _rank(
            raw_stream(), forbidden, median, strictness,
            random.Random(f"{seed}:{source_normalized}:rank"), count, max_per_order,
        )
        if ranked:
            return ranked
    return []


def _product(values) -> int:
    total = 1
    for value in values:
        total *= value
    return total


def _enumerate_all(pools: dict, orders: list[tuple[str, ...]], roles: tuple[str, ...]):
    for order in orders:
        buckets = [pools[lang][role] for lang, role in zip(order, roles)]
        for picks in itertools.product(*buckets):
            yield order, _assemble(order, roles, picks)


def _sample(pools: dict, orders: list[tuple[str, ...]], roles: tuple[str, ...],
            rng: random.Random, draws: int):
    for _ in range(draws):
        order = rng.choice(orders)
        picks = tuple(
            rng.choice(pools[lang][role]) for lang, role in zip(order, roles)
        )
        yield order, _assemble(order, roles, picks)


def _rank(raw, forbidden: set[str], median: float, strictness: int,
          rng: random.Random, count: int, max_per_order: int) -> list[dict]:
    best: dict[str, dict] = {}
    for order, (word, parts) in raw:
        if not _acceptable(word, forbidden, median, strictness):
            continue
        if word in best:
            continue

        lengths = [len(part["text"]) for part in parts]
        seams: list[int] = []
        running = 0
        for length in lengths[:-1]:
            running += length
            seams.append(running)

        length_score = _length_score(len(word), median)
        pronounceable = _pronounceability(word, seams)
        balance = _balance(lengths)
        score = (
            W_LENGTH * length_score
            + W_PRONOUNCEABLE * pronounceable
            + W_BALANCE * balance
        )
        best[word] = {
            "word": word,
            "score": round(score, 3),
            "_tiebreak": rng.random(),
            "parts": parts,
            "order": list(order),
            "metrics": {
                "length": round(length_score, 3),
                "pronounceable": round(pronounceable, 3),
                "balance": round(balance, 3),
            },
        }

    ordered = sorted(
        best.values(), key=lambda item: (-item["score"], -item["_tiebreak"])
    )

    # Cap how many results any one language triple may contribute, so the list
    # shows a spread of language mixes rather than ten variants of the same one.
    picked: list[dict] = []
    used: dict[tuple[str, ...], int] = {}
    for candidate in ordered:
        key = tuple(candidate["order"])
        if used.get(key, 0) >= max_per_order:
            continue
        used[key] = used.get(key, 0) + 1
        picked.append(candidate)
        if len(picked) >= count:
            break

    # If the per-order cap left room, top up with the next best overall.
    if len(picked) < count:
        seen = {candidate["word"] for candidate in picked}
        for candidate in ordered:
            if candidate["word"] in seen:
                continue
            picked.append(candidate)
            seen.add(candidate["word"])
            if len(picked) >= count:
                break
        picked.sort(key=lambda item: (-item["score"], -item["_tiebreak"]))

    for candidate in picked:
        del candidate["_tiebreak"]
    return picked
