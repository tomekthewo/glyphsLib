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

import io
from textwrap import dedent

from fontTools.feaLib.parser import Parser

from glyphsLib import classes, to_ufos
from glyphsLib.builder.multi_language import expand_multi_language_statements

GLYPH_NAMES = ["i", "idotaccent", "Scedilla", "Scommaaccent", "Lcommaaccent"]


def parse(fea, glyph_names=GLYPH_NAMES):
    """Parse the feature text, raising on anything feaLib does not accept."""
    header = "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n"
    header += "".join(
        f"languagesystem latn {tag};\n"
        for tag in ("AZE", "CRT", "KAZ", "TAT", "TRK", "ROM", "MOL")
    )
    return Parser(io.StringIO(header + fea), glyphNames=glyph_names).parse()


def test_named_lookup_is_defined_once_and_referenced():
    fea = expand_multi_language_statements(dedent("""\
        feature locl {
        script latn;

        language AZE CRT KAZ TAT TRK;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;

        } locl;
    """))

    lines = [line.strip() for line in fea.splitlines()]
    # Defined under the first tag only ...
    assert lines.count("lookup idotaccent {") == 1
    # ... and referenced under each of the remaining four.
    assert lines.count("lookup idotaccent;") == 4
    for tag in ("AZE", "CRT", "KAZ", "TAT", "TRK"):
        assert f"language {tag};" in lines
    parse(fea)


def test_bare_rules_are_repeated():
    fea = expand_multi_language_statements(dedent("""\
        feature locl {
        script latn;
        language ROM MOL;
        sub Scedilla by Scommaaccent;
        } locl;
    """))

    lines = [line.strip() for line in fea.splitlines()]
    assert lines.count("sub Scedilla by Scommaaccent;") == 2
    assert lines.count("language ROM;") == 1
    assert lines.count("language MOL;") == 1
    parse(fea)


def test_glyph_class_is_not_redefined():
    fea = expand_multi_language_statements(dedent("""\
        feature locl {
        language ROM MOL;
        @Cedillas = [Scedilla];
        sub @Cedillas by Scommaaccent;
        } locl;
    """))

    lines = [line.strip() for line in fea.splitlines()]
    assert lines.count("@Cedillas = [Scedilla];") == 1
    assert lines.count("sub @Cedillas by Scommaaccent;") == 2
    parse(fea)


def test_keywords_are_kept_on_every_tag():
    fea = expand_multi_language_statements(
        "language ROM MOL exclude_dflt;\nsub Scedilla by Scommaaccent;\n"
    )

    lines = [line.strip() for line in fea.splitlines()]
    assert "language ROM exclude_dflt;" in lines
    assert "language MOL exclude_dflt;" in lines


def test_single_tag_is_untouched():
    original = "script latn;\nlanguage TRK;\nsub i by idotaccent;\n"

    assert expand_multi_language_statements(original) == original


def test_unparseable_statement_is_untouched():
    """Leave it for feaLib to report rather than guess at it."""
    original = "language TOOLONGTAG OTHER;\nsub i by idotaccent;\n"

    assert expand_multi_language_statements(original) == original


def test_to_ufos_expands_feature_code(ufo_module):
    font = classes.GSFont()
    font.masters.append(classes.GSFontMaster())
    for name in ("i", "idotaccent"):
        glyph = classes.GSGlyph(name)
        glyph.layers.append(classes.GSLayer())
        glyph.layers[0].layerId = font.masters[0].id
        font.glyphs.append(glyph)

    prefix = classes.GSFeaturePrefix()
    prefix.name = "Languagesystems"
    prefix.code = "languagesystem latn AZE;\nlanguagesystem latn TRK;\n"
    font.featurePrefixes.append(prefix)

    feature = classes.GSFeature("locl")
    feature.code = dedent("""\
        script latn;
        language AZE TRK;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
    """)
    font.features.append(feature)

    (ufo,) = to_ufos(font, ufo_module=ufo_module)

    lines = [line.strip() for line in ufo.features.text.splitlines()]
    assert "language AZE TRK;" not in lines
    assert "language AZE;" in lines
    assert "language TRK;" in lines
    assert lines.count("lookup idotaccent;") == 1
    Parser(io.StringIO(ufo.features.text), glyphNames=GLYPH_NAMES).parse()
