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

from glyphsLib import classes, to_glyphs, to_ufos
from glyphsLib.builder.multi_language import expand_multi_language_statements

GLYPH_NAMES = ["i", "idotaccent", "Scedilla", "Scommaaccent", "Lcommaaccent"]

LANGUAGE_SYSTEMS = "languagesystem DFLT dflt;\nlanguagesystem latn dflt;\n" + "".join(
    f"languagesystem latn {tag};\n"
    for tag in ("AZE", "CRT", "KAZ", "TAT", "TRK", "ROM", "MOL")
)


def parse(fea):
    """Parse the feature text, raising on anything feaLib does not accept."""
    feature_file = io.StringIO(LANGUAGE_SYSTEMS + fea)
    return Parser(feature_file, glyphNames=GLYPH_NAMES).parse()


def check(source, expected):
    """Expand the source, assert the whole output, then parse it."""
    fea = expand_multi_language_statements(dedent(source))
    assert fea == dedent(expected)
    parse(fea)


def test_bare_rules_are_repeated():
    check(
        """\
        feature locl {
        script latn;
        language ROM MOL;
        sub Scedilla by Scommaaccent;
        } locl;
        """,
        """\
        feature locl {
        script latn;
        language ROM;
        sub Scedilla by Scommaaccent;
        language MOL;
        sub Scedilla by Scommaaccent;
        } locl;
        """,
    )


def test_named_lookup_is_defined_once_and_referenced():
    check(
        """\
        feature locl {
        script latn;
        language AZE CRT KAZ;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
        } locl;
        """,
        """\
        feature locl {
        script latn;
        language AZE;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
        language CRT;
        lookup idotaccent;
        language KAZ;
        lookup idotaccent;
        } locl;
        """,
    )


def test_lookup_with_use_extension_is_referenced():
    check(
        """\
        feature locl {
        language AZE CRT;
        lookup idot useExtension {
            sub i by idotaccent;
        } idot;
        } locl;
        """,
        """\
        feature locl {
        language AZE;
        lookup idot useExtension {
            sub i by idotaccent;
        } idot;
        language CRT;
        lookup idot;
        } locl;
        """,
    )


def test_lookup_with_brace_on_the_next_line_is_referenced():
    check(
        """\
        feature locl {
        language AZE CRT;
        lookup idot
        {
            sub i by idotaccent;
        } idot;
        } locl;
        """,
        """\
        feature locl {
        language AZE;
        lookup idot
        {
            sub i by idotaccent;
        } idot;
        language CRT;
        lookup idot;
        } locl;
        """,
    )


def test_glyph_class_is_not_redefined():
    check(
        """\
        feature locl {
        language ROM MOL;
        @Cedillas = [Scedilla];
        sub @Cedillas by Scommaaccent;
        } locl;
        """,
        """\
        feature locl {
        language ROM;
        @Cedillas = [Scedilla];
        sub @Cedillas by Scommaaccent;
        language MOL;
        sub @Cedillas by Scommaaccent;
        } locl;
        """,
    )


def test_multi_line_glyph_class_is_dropped_whole():
    check(
        """\
        feature locl {
        language ROM MOL;
        @Ced = [Scedilla
                Lcommaaccent];
        sub @Ced by Scommaaccent;
        } locl;
        """,
        """\
        feature locl {
        language ROM;
        @Ced = [Scedilla
                Lcommaaccent];
        sub @Ced by Scommaaccent;
        language MOL;
        sub @Ced by Scommaaccent;
        } locl;
        """,
    )


def test_mark_class_is_not_redefined():
    check(
        """\
        feature test {
        language ROM MOL;
        markClass [Scedilla] <anchor 0 0> @MC;
        pos base i <anchor 0 0> mark @MC;
        } test;
        """,
        """\
        feature test {
        language ROM;
        markClass [Scedilla] <anchor 0 0> @MC;
        pos base i <anchor 0 0> mark @MC;
        language MOL;
        pos base i <anchor 0 0> mark @MC;
        } test;
        """,
    )


def test_closing_brace_in_a_comment_does_not_truncate_the_body():
    """It would otherwise bind the rules to the last tag only, and parse
    cleanly while doing so."""
    check(
        """\
        feature locl {
        language AZE CRT;
        # see the } sign
        sub i by idotaccent;
        } locl;
        """,
        """\
        feature locl {
        language AZE;
        # see the } sign
        sub i by idotaccent;
        language CRT;
        # see the } sign
        sub i by idotaccent;
        } locl;
        """,
    )


def test_opening_brace_in_a_comment_does_not_swallow_the_closing_brace():
    check(
        """\
        feature locl {
        language AZE CRT;
        # an opening { sign
        sub i by idotaccent;
        } locl;
        """,
        """\
        feature locl {
        language AZE;
        # an opening { sign
        sub i by idotaccent;
        language CRT;
        # an opening { sign
        sub i by idotaccent;
        } locl;
        """,
    )


def test_trailing_comment_on_a_delimiter_ends_the_body():
    check(
        """\
        feature locl {
        language AZE CRT;
        sub i by idotaccent;
        language TRK; # Turkish
        sub Scedilla by Scommaaccent;
        } locl;
        """,
        """\
        feature locl {
        language AZE;
        sub i by idotaccent;
        language CRT;
        sub i by idotaccent;
        language TRK; # Turkish
        sub Scedilla by Scommaaccent;
        } locl;
        """,
    )


def test_trailing_comment_on_the_statement_is_kept():
    check(
        """\
        feature locl {
        script latn;
        language AZE CRT; # Turkic
        sub i by idotaccent;
        } locl;
        """,
        """\
        feature locl {
        script latn;
        language AZE; # Turkic
        sub i by idotaccent;
        language CRT;
        sub i by idotaccent;
        } locl;
        """,
    )


def test_keywords_are_kept_on_every_tag():
    check(
        """\
        feature locl {
        script latn;
        language ROM MOL exclude_dflt;
        sub Scedilla by Scommaaccent;
        } locl;
        """,
        """\
        feature locl {
        script latn;
        language ROM exclude_dflt;
        sub Scedilla by Scommaaccent;
        language MOL exclude_dflt;
        sub Scedilla by Scommaaccent;
        } locl;
        """,
    )


def test_single_tag_is_untouched():
    original = "script latn;\nlanguage TRK;\nsub i by idotaccent;\n"

    assert expand_multi_language_statements(original) == original


def test_unparseable_statement_is_untouched():
    """Leave it for feaLib to report rather than guess at it."""
    original = "language TOOLONGTAG OTHER;\nsub i by idotaccent;\n"

    assert expand_multi_language_statements(original) == original


def make_font():
    font = classes.GSFont()
    font.masters.append(classes.GSFontMaster())
    for name in ("i", "idotaccent"):
        glyph = classes.GSGlyph(name)
        glyph.layers.append(classes.GSLayer())
        glyph.layers[0].layerId = font.masters[0].id
        font.glyphs.append(glyph)

    prefix = classes.GSFeaturePrefix()
    prefix.name = "Languagesystems"
    prefix.code = "languagesystem latn AZE;\nlanguagesystem latn TRK;"
    font.featurePrefixes.append(prefix)

    feature = classes.GSFeature("locl")
    feature.code = dedent("""\
        script latn;
        language AZE TRK;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;""")
    font.features.append(feature)
    return font


def test_to_ufos_expands_feature_code(ufo_module):
    (ufo,) = to_ufos(make_font(), ufo_module=ufo_module)

    assert ufo.features.text == dedent("""\
        # Prefix: Languagesystems
        languagesystem latn AZE;
        languagesystem latn TRK;

        feature locl {
        script latn;
        language AZE;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
        language TRK;
        lookup idotaccent;
        } locl;
        """)
    Parser(io.StringIO(ufo.features.text), glyphNames=GLYPH_NAMES).parse()


def test_expansion_does_not_round_trip(ufo_module):
    """The expansion is one-way: the shorthand is not restored.

    Going back to Glyphs yields the expanded form rather than the original
    statement. UFO -> Glyphs -> UFO is unaffected, because the original
    feature text is recovered from ORIGINAL_FEATURE_CODE_KEY.
    """
    (ufo,) = to_ufos(make_font(), ufo_module=ufo_module)

    (feature,) = to_glyphs([ufo]).features
    assert feature.code == dedent("""\
        script latn;
        language AZE;
        lookup idotaccent {
            sub i by idotaccent;
        } idotaccent;
        language TRK;
        lookup idotaccent;""")
