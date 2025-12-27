from __future__ import annotations

from compendiumscribe.compendium.text_utils import format_html_text


def test_format_html_text_with_plain_text():
    text = "Hello world"
    assert format_html_text(text) == "Hello world"


def test_format_html_text_escapes_special_chars():
    text = "User <user>"
    assert format_html_text(text) == "User &lt;user&gt;"


def test_format_html_text_converts_backticks_to_code():
    text = "Use `print()` function"
    assert format_html_text(text) == "Use <code>print()</code> function"


def test_format_html_text_converts_backticks_with_html_chars():
    text = "Check `x < y` logic"
    assert format_html_text(text) == "Check <code>x &lt; y</code> logic"


def test_format_html_text_handles_multiple_code_blocks():
    text = "Use `foo` and `bar`"
    assert format_html_text(text) == "Use <code>foo</code> and <code>bar</code>"


def test_format_html_text_with_links_and_code():
    # Verify processing of inline code within markdown link labels.
    text = "Click [`here`](https://example.com) now"
    expected = 'Click <a href="https://example.com"><code>here</code></a> now'
    assert format_html_text(text) == expected


def test_format_html_text_handles_bold():
    text = "This is **bold** text"
    assert format_html_text(text) == "This is <strong>bold</strong> text"


def test_format_html_text_handles_italic_stars():
    text = "This is *italic* text"
    assert format_html_text(text) == "This is <em>italic</em> text"


def test_format_html_text_handles_italic_underscores():
    text = "This is _italic_ text"
    # Assuming we treat _ underscores same as stars
    # Usually Markdown allows _italic_
    assert format_html_text(text) == "This is <em>italic</em> text"


def test_format_html_text_handles_mixed_emphasis():
    text = "**Bold** and *Italic*"
    assert format_html_text(text) == "<strong>Bold</strong> and <em>Italic</em>"


def test_format_html_text_handles_nested_bold_italic():
    text = "**Bold *and* Italic**"
    # Expect: <strong>Bold <em>and</em> Italic</strong>
    assert format_html_text(text) == "<strong>Bold <em>and</em> Italic</strong>"


def test_format_html_text_does_not_emphasize_code():
    text = "`*code*` inside"
    # Current code block keeps content raw/escaped but not emphasized
    assert format_html_text(text) == "<code>*code*</code> inside"


def test_format_html_text_ignores_bold_inside_code():
    text = "Code `**not bold**` block"
    assert format_html_text(text) == "Code <code>**not bold**</code> block"


def test_format_html_text_ignores_underscore_inside_code():
    text = "Code `_not italic_` block"
    assert format_html_text(text) == "Code <code>_not italic_</code> block"
