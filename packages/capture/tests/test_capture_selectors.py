"""Unit tests for nexcoder_capture.web.selectors."""

from __future__ import annotations

from nexcoder_capture.web.selectors import DOMParser, ElementNode, SelectorExtractor


def test_dom_parser_hierarchy() -> None:
    html = """
    <html>
      <body>
        <div id="container">
          <button id="btn1">First</button>
          <button id="btn2">Second</button>
        </div>
      </body>
    </html>
    """
    parser = DOMParser()
    parser.feed(html)

    # Check root and children
    root = parser.root
    assert root.tag == "document"
    assert len(root.children) == 1  # html
    assert len(parser.elements) > 0


def test_element_node_properties() -> None:
    node = ElementNode(
        tag="input",
        attrs={"id": "email-input", "data-testid": "email-field", "type": "text", "placeholder": "Enter email"},
    )
    assert node.tag == "input"
    assert node.id_val == "email-input"
    assert node.test_id == "email-field"
    assert node.role == "textbox"
    assert node.accessible_name == "Enter email"


def test_test_id_strategy_attributes() -> None:
    extractor = SelectorExtractor()

    for attr in ("data-testid", "data-test", "data-cy", "data-qa", "data-test-id"):
        html = f'<button {attr}="action-submit">Submit</button>'
        selectors = extractor.extract_from_html(html)
        assert len(selectors) == 1
        sel = selectors[0]
        assert sel.strategy == "test_id"
        assert sel.confidence == 1.0
        assert sel.primary == "getByTestId('action-submit')"
        assert sel.css == f"[{attr}='action-submit']"
        assert sel.test_id == "action-submit"


def test_id_strategy() -> None:
    extractor = SelectorExtractor()
    html = '<button id="checkout-button">Proceed to Checkout</button>'
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 1
    sel = selectors[0]
    assert sel.strategy == "id"
    assert sel.confidence == 0.95
    assert sel.primary == "#checkout-button"
    assert sel.css == "#checkout-button"
    assert sel.xpath == "//*[@id='checkout-button']"


def test_invalid_dynamic_id_fallback() -> None:
    extractor = SelectorExtractor()
    # Dynamic ids like :r1: or numeric prefixes or long trailing numbers should not use "id" strategy
    html = '<button id=":r1:">Click me</button>'
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 1
    # Falls back to text or role_name
    assert selectors[0].strategy != "id"


def test_role_and_name_strategy() -> None:
    extractor = SelectorExtractor()
    html = '<div role="button" aria-label="Close menu">X</div>'
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 1
    sel = selectors[0]
    assert sel.strategy == "role_name"
    assert sel.confidence == 0.90
    assert sel.primary == "getByRole('button', name='Close menu')"
    assert "[aria-label='Close menu']" in sel.css


def test_text_strategy_for_buttons_and_links() -> None:
    extractor = SelectorExtractor()
    html = '<button class="btn primary">Save Changes</button>'
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 1
    sel = selectors[0]
    # If no test-id, no id, and no role+aria-label, text strategy applies
    assert sel.confidence >= 0.85
    assert sel.name == "Save Changes"


def test_css_path_fallback() -> None:
    extractor = SelectorExtractor()
    # Element without text, test_id, id, role or aria attributes
    html = "<div><form><input></form></div>"
    selectors = extractor.extract_from_html(html)
    assert len(selectors) >= 1
    input_sel = next(s for s in selectors if s.tag == "input")
    assert input_sel.strategy in ("css_path", "role_name")
    assert input_sel.confidence > 0.0


def test_non_candidate_elements_ignored() -> None:
    extractor = SelectorExtractor()
    html = """
    <div>
      <p>Plain paragraph without interactive elements</p>
      <span>Plain span</span>
      <section>Regular container</section>
    </div>
    """
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 0


def test_tabindex_makes_element_candidate() -> None:
    extractor = SelectorExtractor()
    html = '<div tabindex="0">Custom focusable widget</div>'
    selectors = extractor.extract_from_html(html)
    assert len(selectors) == 1
    assert selectors[0].tag == "div"


def test_void_elements_do_not_parent_siblings() -> None:
    html = """
    <form id="login-form">
      <input type="text" id="username" placeholder="User">
      <input type="password" id="password" placeholder="Pass">
      <button type="submit" id="submit-btn">Login</button>
    </form>
    """
    parser = DOMParser()
    parser.feed(html)

    form_node = next(el for el in parser.elements if el.tag == "form")
    input_nodes = [el for el in parser.elements if el.tag == "input"]
    button_node = next(el for el in parser.elements if el.tag == "button")

    # Void inputs must have 0 children
    for inp in input_nodes:
        assert len(inp.children) == 0

    # Form node must be parent of inputs and button
    assert button_node.parent == form_node
    assert len(form_node.children) == 3


def test_xpath_inside_id_container_has_no_triple_slashes() -> None:
    html = """
    <form id="login-form">
      <input type="text">
    </form>
    """
    extractor = SelectorExtractor()
    selectors = extractor.extract_from_html(html)
    input_sel = next(s for s in selectors if s.tag == "input")
    assert not input_sel.xpath.startswith("///")
    assert input_sel.xpath.startswith("//*[@id='login-form']/input")
