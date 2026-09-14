"""Pin the markup contract consumed by the executable page-test doubles."""

import pytest

from tests import html_tree


def test_text_chunks_preserve_whitespace_unicode_and_entity_decoding():
    page = html_tree.TextPageTree()
    for chunk in ("<p>", " \nÉtiquette ", "𐐀\t", "&amp;", " e\u0301\u00a0 ", "</p>"):
        page.feed(chunk)
    page.close()

    assert page.root["children"][0]["text"] == " \nÉtiquette 𐐀\t& e\u0301\u00a0 "
    assert "text" not in page.root


def test_nested_text_belongs_only_to_its_current_node():
    page = html_tree.TextPageTree()
    page.feed("outside<section>before<b>bold<i>inner</i>tail</b>after</section>end")
    page.close()

    assert page.root == {
        "tag": "document",
        "attrs": {},
        "text": "outsideend",
        "children": [
            {
                "tag": "section",
                "attrs": {},
                "text": "beforeafter",
                "children": [
                    {
                        "tag": "b",
                        "attrs": {},
                        "text": "boldtail",
                        "children": [
                            {
                                "tag": "i",
                                "attrs": {},
                                "text": "inner",
                                "children": [],
                            }
                        ],
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize("parser_name", ["PageTree", "TextPageTree"])
def test_element_order_ancestry_attributes_and_empty_nodes(parser_name):
    page = getattr(html_tree, parser_name)()
    page.feed(
        '<div id="outer"><span title="É &amp; 𐐀"></span><br><input disabled></div>'
    )
    page.close()

    assert page.root == {
        "tag": "document",
        "attrs": {},
        "children": [
            {
                "tag": "div",
                "attrs": {"id": "outer"},
                "children": [
                    {"tag": "span", "attrs": {"title": "É & 𐐀"}, "children": []},
                    {"tag": "br", "attrs": {}, "children": []},
                    {"tag": "input", "attrs": {"disabled": None}, "children": []},
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    "tag",
    [
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    ],
)
def test_void_elements_do_not_take_following_text_or_siblings(tag):
    page = html_tree.TextPageTree()
    page.feed(f'<div>before<{tag} id="void">after<span>child</span>end</div>')
    page.close()

    parent = page.root["children"][0]
    assert parent["text"] == "beforeafterend"
    assert parent["children"] == [
        {"tag": tag, "attrs": {"id": "void"}, "children": []},
        {"tag": "span", "attrs": {}, "text": "child", "children": []},
    ]


def test_structure_only_parser_does_not_add_text_fields():
    page = html_tree.PageTree()
    page.feed('outside<div id="outer"> \nÉ 𐐀 <span>nested</span>&amp; tail</div>end')
    page.close()

    assert page.root == {
        "tag": "document",
        "attrs": {},
        "children": [
            {
                "tag": "div",
                "attrs": {"id": "outer"},
                "children": [{"tag": "span", "attrs": {}, "children": []}],
            }
        ],
    }
