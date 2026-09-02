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

_language_re = re.compile(r"^([ \t]*)language[ \t]+([^;]+);[ \t]*$")
# A `language` or `script` statement closes the block opened by the previous one.
_delimiter_re = re.compile(r"^[ \t]*(?:language|script)[ \t]+[^;]+;[ \t]*$")
_lookup_open_re = re.compile(r"^([ \t]*)lookup[ \t]+([A-Za-z_][A-Za-z0-9_.]*)[ \t]*\{")
_class_def_re = re.compile(r"^[ \t]*@[A-Za-z0-9_.]+[ \t]*=")
_tag_re = re.compile(r"^[A-Za-z0-9_]{1,4}$")


def expand_multi_language_statements(fea):
    """Rewrite multi-tag ``language`` statements as one statement per tag.

    The block is emitted once for the first tag and then repeated for every
    remaining one. Named lookups cannot simply be duplicated -- that would
    redefine them -- so the repeats reference the lookup defined under the
    first tag, and glyph class definitions are likewise emitted only once::

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
    out = []
    changed = False
    i = 0
    while i < len(lines):
        line = lines[i]
        match = _language_re.match(line)
        tags, keywords = _split_tokens(match.group(2)) if match else (None, None)
        if not tags or len(tags) < 2:
            out.append(line)
            i += 1
            continue
        indent = match.group(1)
        body, i = _collect_body(lines, i + 1)
        items = _parse_body(body)
        out.append(_statement(indent, tags[0], keywords))
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


def _statement(indent, tag, keywords):
    return "{}language {};".format(indent, " ".join([tag] + keywords))


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
        elif keywords or not _tag_re.match(token):
            # A tag after a keyword, or a token that is not a tag at all.
            return None, None
        else:
            tags.append(token)
    return tags, keywords


def _collect_body(lines, start):
    """Collect the lines governed by a ``language`` statement.

    That is everything up to the next ``language``/``script`` statement or the
    end of the enclosing block, whichever comes first. Returns the lines and
    the index of the first line not taken.
    """
    body = []
    depth = 0
    i = start
    while i < len(lines):
        line = lines[i]
        if depth == 0 and _delimiter_re.match(line):
            break
        new_depth = depth + line.count("{") - line.count("}")
        if new_depth < 0:
            # The line closes the block we are nested in (`} locl;`).
            break
        body.append(line)
        depth = new_depth
        i += 1
    return body, i


def _parse_body(body):
    """Split the body into ``(kind, name, lines)`` items.

    ``kind`` is ``lookup`` for a named lookup block, ``class`` for a glyph
    class definition and ``line`` for anything else.
    """
    items = []
    i = 0
    while i < len(body):
        line = body[i]
        match = _lookup_open_re.match(line)
        if match:
            depth = line.count("{") - line.count("}")
            block = [line]
            i += 1
            while i < len(body) and depth > 0:
                block.append(body[i])
                depth += body[i].count("{") - body[i].count("}")
                i += 1
            items.append(("lookup", match.groups(), block))
            continue
        kind = "class" if _class_def_re.match(line) else "line"
        items.append((kind, None, [line]))
        i += 1
    return items


def _replay(items):
    """Render the body again for a repeated tag.

    Lookups become references, class definitions are dropped, the rest is
    repeated as is.
    """
    out = []
    for kind, name, block in items:
        if kind == "lookup":
            indent, lookup_name = name
            out.append(f"{indent}lookup {lookup_name};")
        elif kind != "class":
            out.extend(block)
    return out
