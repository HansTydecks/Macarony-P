"""Macarony - build fake "mixed-language" words out of real translations.

The package is pure standard library.  Three steps:

1. :mod:`macarony.pipeline` splits a sentence into tokens so words can be picked.
2. :mod:`macarony.translate` translates a picked word into several languages and
   :mod:`macarony.fragments` cuts each translation into character fragments.
3. :mod:`macarony.recombine` glues fragments from different languages back
   together into something that looks like a word but belongs to no language.
"""

__version__ = "1.0.0"

from macarony.pipeline import process, tokenize

__all__ = ["__version__", "process", "tokenize"]
