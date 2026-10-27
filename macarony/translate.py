"""Step 2a: turn one word into translations in several languages.

Two translators share an interface::

    translator.translate(word, langs) -> {lang: result}

where ``result`` is ``{"lang", "text", "romanized", "error"}``.  ``text`` is the
translation in its own script; ``romanized`` is a Latin-script spelling when the
translation is not written in the Latin alphabet (and ``None`` otherwise).
"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

GOOGLE_URL = "https://translate.googleapis.com/translate_a/single"
DEFAULT_TIMEOUT = 8.0
_USER_AGENT = "Mozilla/5.0 (compatible; Macarony/1.0)"
_MAX_WORKERS = 8

#: Languages offered by the UI.  The eight defaults are all Latin-script, which
#: keeps the fragments readable without romanization.
DEFAULT_LANGUAGES = ["de", "fr", "es", "it", "pt", "nl", "sv", "pl"]

LANGUAGE_NAMES = {
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "nl": "Dutch",
    "sv": "Swedish",
    "pl": "Polish",
    "da": "Danish",
    "no": "Norwegian",
    "fi": "Finnish",
    "is": "Icelandic",
    "cs": "Czech",
    "sk": "Slovak",
    "hu": "Hungarian",
    "ro": "Romanian",
    "hr": "Croatian",
    "lt": "Lithuanian",
    "lv": "Latvian",
    "et": "Estonian",
    "tr": "Turkish",
    "ca": "Catalan",
    "gl": "Galician",
    "eu": "Basque",
    "cy": "Welsh",
    "ga": "Irish",
    "la": "Latin",
    "eo": "Esperanto",
    "id": "Indonesian",
    "ms": "Malay",
    "sw": "Swahili",
    "vi": "Vietnamese",
    "ru": "Russian",
    "uk": "Ukrainian",
    "bg": "Bulgarian",
    "sr": "Serbian",
    "el": "Greek",
    "he": "Hebrew",
    "ar": "Arabic",
    "fa": "Persian",
    "hi": "Hindi",
    "ja": "Japanese",
    "ko": "Korean",
    "zh-CN": "Chinese",
    "th": "Thai",
}


def language_name(lang: str) -> str:
    """Human-readable name for a language code, falling back to the code."""
    return LANGUAGE_NAMES.get(lang, lang)


def _result(lang: str, text: str = "", romanized: str | None = None,
            error: str | None = None) -> dict:
    return {"lang": lang, "text": text, "romanized": romanized, "error": error}


def _parse_google(payload) -> tuple[str, str | None]:
    """Pull the translation and its romanization out of a gtx response.

    The interesting part is ``payload[0]``, a list of chunks.  A text chunk is
    ``[translated, original, ...]``; the romanization chunk has ``None`` in the
    first slot and the Latin-script spelling of the *target* in slot 2.
    """
    text_parts: list[str] = []
    rom_parts: list[str] = []
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        return "", None
    for chunk in payload[0]:
        if not isinstance(chunk, list) or not chunk:
            continue
        if chunk[0]:
            text_parts.append(str(chunk[0]))
        elif len(chunk) > 2 and chunk[2]:
            rom_parts.append(str(chunk[2]))
    romanized = "".join(rom_parts).strip() or None
    return "".join(text_parts).strip(), romanized


class GoogleTranslator:
    """Free ``translate_a/single`` endpoint, queried in parallel and cached.

    No API key is involved, so the endpoint can rate-limit or disappear.  Every
    failure is reported per language in the result rather than raised, which
    lets the pipeline carry on with whatever languages did answer.
    """

    name = "google"

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout
        self._cache: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()

    def _fetch(self, word: str, lang: str) -> dict:
        params = [
            ("client", "gtx"),
            ("sl", "en"),
            ("tl", lang),
            ("dt", "t"),
            ("dt", "rm"),
            ("q", word),
        ]
        url = f"{GOOGLE_URL}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            return _result(lang, error=f"HTTP {exc.code} from the translation endpoint")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return _result(lang, error=f"could not reach the translation endpoint ({exc})")
        except (ValueError, json.JSONDecodeError):
            return _result(lang, error="unreadable response from the translation endpoint")

        text, romanized = _parse_google(payload)
        if not text:
            return _result(lang, error="empty translation")
        return _result(lang, text=text, romanized=romanized)

    def translate(self, word: str, langs: list[str]) -> dict[str, dict]:
        wanted: list[str] = []
        out: dict[str, dict] = {}
        with self._lock:
            for lang in langs:
                cached = self._cache.get((word, lang))
                if cached is None:
                    wanted.append(lang)
                else:
                    out[lang] = dict(cached)

        if wanted:
            workers = min(_MAX_WORKERS, len(wanted))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                fetched = list(pool.map(lambda lang: self._fetch(word, lang), wanted))
            with self._lock:
                for lang, result in zip(wanted, fetched):
                    # Only successes are cached; a transient failure should be
                    # retried on the next request.
                    if result["error"] is None:
                        self._cache[(word, lang)] = dict(result)
                    out[lang] = result

        return {lang: out[lang] for lang in langs if lang in out}


class OfflineTranslator:
    """Small bundled dictionary, used as a fallback and by the tests."""

    name = "offline"

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else Path(__file__).with_name("data") / "offline_dict.json"
        with open(self.path, encoding="utf-8") as handle:
            self._words: dict[str, dict[str, str]] = json.load(handle)

    @property
    def words(self) -> list[str]:
        """Every English word the bundled dictionary knows, sorted."""
        return sorted(self._words)

    @property
    def languages(self) -> list[str]:
        seen: list[str] = []
        for entry in self._words.values():
            for lang in entry:
                if lang not in seen:
                    seen.append(lang)
        return seen

    def translate(self, word: str, langs: list[str]) -> dict[str, dict]:
        entry = self._words.get(word.lower())
        out: dict[str, dict] = {}
        for lang in langs:
            if entry is None:
                out[lang] = _result(lang, error=f"'{word}' is not in the offline dictionary")
            elif lang not in entry:
                out[lang] = _result(lang, error=f"{language_name(lang)} is not in the offline dictionary")
            else:
                out[lang] = _result(lang, text=entry[lang])
        return out
