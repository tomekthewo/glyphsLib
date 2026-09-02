#
# Copyright 2026 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Expand Glyphs' multiple languages syntax into plain FEA.

Glyphs lets a single ``language`` statement carry several tags and applies
everything that follows to each of them::

    language AZE CRT KAZ TAT TRK;
    lookup idotaccent {
        sub i by idotaccent;
    } idotaccent;

The FEA spec allows exactly one tag per statement, so feaLib rejects this with
``Expected ';'`` at the second tag. See
https://handbook.glyphsapp.com/layout/multiple-languages-syntax/ and
https://github.com/googlefonts/glyphsLib/issues/1109.
"""

import logging
import re

logger = logging.getLogger(__name__)

# Keywords the FEA spec allows after the tag of a `language` statement.
_LANGUAGE_KEYWORDS = frozenset(("exclude_dflt", "include_dflt", "required"))

# Comment | "string": blanked out before anything below is matched, so that a
# brace, a semicolon or a keyword inside one is never taken for code.
_skip_re = re.compile(r"#[^\n]*|\"[^\"\n]*\"")

_language_re = re.compile(r"^([ \t]*)language[ \t]+([^;]+);[ \t]*$")
# A `language` or `script` statement closes the block opened by the previous one.
_delimiter_re = re.compile(r"^[ \t]*(?:language|script)[ \t]+[^;]+;[ \t]*$")
# `lookup NAME [useExtension] {`, with the brace allowed on a following line.
# A reference (`lookup NAME;`) matches neither branch and stays a plain rule.
_lookup_def_re = re.compile(
    r"^([ \t]*)lookup[ \t]+([A-Za-z_][A-Za-z0-9_.]*)[ \t]*"
    r"(?:useExtension[ \t]*)?(?:\{|$)"
)
# Definitions that name something: emitted once, dropped when replayed.
_definition_re = re.compile(r"^[ \t]*(?:@[A-Za-z0-9_.]+[ \t]*=|markClass[ \t(\[])")


def expand_multi_language_statements(fea):
    """Rewrite multi-tag ``language`` statements as one statement per tag.

    The block is emitted once for the first tag and then repeated for every
    remaining one. Named lookups cannot simply be duplicated -- that would
    redefine them -- so the repeats reference the lookup defined under the
    first tag, and glyph class and ``markClass`` definitions are likewise
    emitted only once::

        language AZE;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
        language CRT;
        lookup idotaccent;

    Everything else (bare rules, ``lookupflag``, ...) is repeated verbatim,
    which is what the shorthand means. A statement that is already
    spec-compliant, or that cannot be parsed with confidence, is left alone
    for feaLib to report.
    """
    lines = fea.splitlines()
    code = [_skip_re.sub(lambda m: " " * len(m.group(0)), line) for line in lines]
    out = []
    changed = False
    i = 0
    while i < len(lines):
        match = _language_re.match(code[i])
        tags, keywords = _split_tokens(match.group(2)) if match else (None, None)
        if not tags or len(tags) < 2:
            out.append(lines[i])
            i += 1
            continue
        indent = match.group(1)
        # Keep anything the original statement carried after the semicolon
        # (a trailing comment); the blanking above preserves column numbers.
        trailing = lines[i][code[i].index(";") + 1 :].strip()
        start = i + 1
        i = _body_end(code, start)
        body, body_code = lines[start:i], code[start:i]
        items = _parse_body(body, body_code)
        out.append(_statement(indent, tags[0], keywords, trailing))
        out.extend(body)
        for tag in tags[1:]:
            out.append(_statement(indent, tag, keywords))
            out.extend(_replay(items))
        logger.debug("Expanded 'language %s;'", " ".join(tags))
        changed = True

    if not changed:
        return fea
    expanded = "\n".join(out)
    if fea.endswith("\n"):
        expanded += "\n"
    return expanded


def _statement(indent, tag, keywords, trailing=""):
    statement = "{}language {};".format(indent, " ".join([tag] + keywords))
    return f"{statement} {trailing}" if trailing else statement


def _split_tokens(tokens):
    """Split a statement's contents into tags and trailing keywords.

    Returns ``(None, None)`` for anything unexpected, so that the caller
    leaves the statement alone rather than guessing at it.
    """
    tags = []
    keywords = []
    for token in tokens.split():
        if token in _LANGUAGE_KEYWORDS:
            keywords.append(token)
        elif keywords or not re.fullmatch(r"[A-Za-z0-9_]{1,4}", token):
            # A tag after a keyword, or a token that is not a tag at all.
            return None, None
        else:
            tags.append(token)
    return tags, keywords


def _body_end(code, start):
    """Return the index of the first line no longer governed by the statement.

    The body runs up to the next ``language``/``script`` statement or the end
    of the enclosing block, whichever comes first.
    """
    depth = 0
    i = start
    while i < len(code):
        if depth == 0 and _delimiter_re.match(code[i]):
            break
        new_depth = depth + code[i].count("{") - code[i].count("}")
        if new_depth < 0:
            # The line closes the block we are nested in (`} locl;`).
            break
        depth = new_depth
        i += 1
    return i


def _parse_body(body, code):
    """Split the body into ``(kind, name, lines)`` items.

    ``kind`` is ``lookup`` for a named lookup block, ``definition`` for a
    glyph class or ``markClass`` definition and ``line`` for anything else.
    """
    items = []
    i = 0
    while i < len(body):
        match = _lookup_def_re.match(code[i])
        if match:
            start, depth, opened = i, 0, False
            while i < len(body):
                depth += code[i].count("{") - code[i].count("}")
                opened = opened or depth > 0
                i += 1
                if opened and depth <= 0:
                    break
            items.append(("lookup", match.groups(), body[start:i]))
            continue
        if _definition_re.match(code[i]):
            start = i
            # A definition runs to its terminating semicolon.
            while i < len(body) and ";" not in code[i]:
                i += 1
            i = min(i + 1, len(body))
            items.append(("definition", None, body[start:i]))
            continue
        items.append(("line", None, [body[i]]))
        i += 1
    return items


def _replay(items):
    """Render the body again for a repeated tag.

    Lookups become references, definitions are dropped, the rest is repeated
    as is.
    """
    out = []
    for kind, name, block in items:
        if kind == "lookup":
            indent, lookup_name = name
            out.append(f"{indent}lookup {lookup_name};")
        elif kind != "definition":
            out.extend(block)
    return out
