# Macarony

Macarony builds words that sound like they *ought* to mean something and don't.

You give it a sentence and point at the words you want mangled. For each one it
fetches translations in several languages, cuts those translations into
character fragments, and glues fragments from *different* languages back
together. The result belongs to no language at all:

```
bird  →  de "vogel"   prefix  vo
         pt "passaro" middle    sa
         nl "vogel"   suffix      el
                              = vosael

The bird sings in the garden.  →  The vosael sings in the girden.
```

(The name is from *macaronic* verse — text that mixes languages on purpose.)

## Quick start

No dependencies, no install. Python 3.9 or newer:

```bash
python -m macarony
```

That serves <http://127.0.0.1:8000/> and opens a browser. Type a sentence, click
the words you want, press **Generate**.

```
python -m macarony --port 8765      # a different port
python -m macarony --no-browser     # don't open a browser
python -m macarony --offline        # never call the network (see below)
python -m macarony --host 0.0.0.0   # reachable from the network
```

The page binds to `127.0.0.1` by default; it is a local tool with no
authentication, so only pass `--host 0.0.0.0` on a network you trust.

## How it works

**Step 1 — pick words.** The sentence is split into words and the spacing and
punctuation between them. Everything is kept, so the sentence can be rebuilt
exactly with the invented words dropped into place. Clicking a word chip in the
page selects or deselects it.

**Step 2 — translate and cut.** Each picked word is translated into every
selected language at once. Each translation is then normalized — lowercased,
reduced to its longest word so articles fall away (`der Vogel` → `vogel`), and
optionally stripped of accents (`fågel` → `fagel`). A translation written in a
non-Latin script is romanized first (`птица` → `ptitsa`), since Cyrillic and
Latin letters don't mix into a pronounceable word.

Every substring between the minimum and maximum fragment length becomes a
candidate fragment, tagged with where it sat in the word:

| role | where it sits | from `vogel` |
| --- | --- | --- |
| prefix | starts at the first letter | `vo`, `vog`, `voge` |
| middle | strictly inside | `og`, `oge`, `ge` |
| suffix | ends at the last letter | `ogel`, `gel`, `el` |

The whole word is never a fragment — a prefix has to leave something for
another language to supply.

A translation that is identical to the English word (`warm` is `warm` in German
and Dutch) contributes nothing to a mixed word, so it is skipped as long as
enough other languages remain.

**Step 3 — recombine.** The rule is positional: a three-part word takes its
prefix from one language, its middle from a second and its suffix from a third,
and all three must differ. Two-part mode is just prefix + suffix. Every
combination is enumerated — or, past about 50 000, sampled with a seeded
generator so a run stays fast and still repeats exactly.

Results are then filtered to stay gibberish: nothing that equals a real
translation or the English word, nothing that is merely a piece of one, nothing
that swallows one whole, and nothing far off the median translation length. If
that leaves nothing at all, the filter relaxes a step at a time rather than
returning an empty list.

What survives is scored on three things — closeness to the median translation
length, pronounceability (runs of three or more consonants or vowels are
penalized, harder where two fragments meet), and how evenly the fragments share
the word. Ties break on a seeded random value, so the top of the list isn't ten
variations on one prefix. At most two results come from any one language
triple.

Every step is visible in the page: the translations, the fragments colored by
language, and the candidate words with their parts underlined in the color of
the language they came from. Click any candidate to swap it into the sentence.

## Settings

| setting | what it does |
| --- | --- |
| Parts | 3 (prefix + middle + suffix) or 2 (prefix + suffix) |
| Fragment length | how many letters a fragment may have (default 2–4) |
| Results per word | how many candidates to show (default 10) |
| Seed | change it for a different set of results; the same seed always gives the same ones |
| Strip accents | `fågel` → `fagel` before cutting |
| Offline dictionary only | never call the network |
| Use the language order below | fix which language supplies which part, in the order you ticked them |
| Languages | 45 to choose from; the eight Latin-script defaults are ticked |

## Translation

Translations come from Google's free `translate_a/single` endpoint. It needs no
API key, which also means it can rate-limit or change without warning. If it
cannot be reached for a word, Macarony falls back to a small bundled dictionary
(55 common English words × 8 languages) and says so in the page.

`--offline`, or the checkbox, uses that dictionary and nothing else. It is also
what the tests run against, so they need no network.

## HTTP API

The page is a client of a small JSON API, which is usable on its own:

```bash
curl -X POST http://127.0.0.1:8000/api/process \
  -H 'Content-Type: application/json' \
  -d '{"sentence":"The bird sings in the garden.",
       "selected":[2,10],
       "options":{"count":5,"parts":3}}'
```

| route | purpose |
| --- | --- |
| `GET /` | the page |
| `GET /api/languages` | language list, defaults, and the offline word list |
| `POST /api/tokenize` | `{sentence}` → tokens, for drawing the word chips |
| `POST /api/process` | `{sentence, selected, options}` → translations, fragments, candidates and the rebuilt sentence |

`selected` holds token indices as returned by `/api/tokenize`. `options` takes
`languages`, `parts`, `language_order`, `min_frag`, `max_frag`, `count`,
`seed`, `ascii_only` and `offline`; anything omitted falls back to its default,
and out-of-range values are clamped rather than rejected.

## Using it as a library

```python
from macarony import process

result = process("The bird sings in the garden.", selected=[2, 10],
                 options={"count": 5, "offline": True})
print(result["sentence_out"])
```

## Tests

```bash
python -m unittest discover -s tests
```

93 tests covering fragment extraction, the recombination rules and scoring, the
tokenizer round-trip, option handling and the translator layer. They use the
offline dictionary and a fixed seed, so they are deterministic and offline.

## Layout

```
macarony/
  __main__.py     the python -m entry point
  translate.py    step 2a: Google and offline translators
  fragments.py    step 2b: normalization and fragment extraction
  recombine.py    step 3:  positional recombination, filtering, scoring
  pipeline.py     step 1 tokenizing, and the orchestration of 2 and 3
  server.py       the local web server and JSON API
  web/index.html  the page (inline CSS and JS, light and dark)
  data/           the offline dictionary
tests/
```
