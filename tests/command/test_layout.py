"""REQ-OPS-004: one header row and three side by side panels."""

from html.parser import HTMLParser
import re

from src.command.dashboard import dashboard

# Tags that never have a closing tag, so they never contain other elements.
VOID_TAGS = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}


class Element:
    def __init__(self, tag, attrs, parent):
        self.tag = tag
        self.attrs = dict(attrs)
        self.parent = parent
        self.children = []
        self.text = ""

    @property
    def classes(self):
        return self.attrs.get("class", "").split()

    def all_text(self):
        return (self.text + "".join(child.all_text() for child in self.children)).strip()

    def walk(self):
        yield self
        for child in self.children:
            yield from child.walk()

    def ancestors(self):
        node = self.parent
        while node is not None:
            yield node
            node = node.parent


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.root = Element("document", [], None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        element = Element(tag, attrs, self.current)
        self.current.children.append(element)
        if tag not in VOID_TAGS:
            self.current = element

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.text += data


def page():
    parser = PageParser()
    parser.feed(dashboard())
    return parser.root


def by_id(root, element_id):
    matches = [node for node in root.walk() if node.attrs.get("id") == element_id]
    assert len(matches) == 1, f'expected exactly one id="{element_id}", found {len(matches)}'
    return matches[0]


def first(root, tag=None, cls=None):
    for node in root.walk():
        if (tag is None or node.tag == tag) and (cls is None or cls in node.classes):
            return node
    raise AssertionError(f"no <{tag or '*'} class={cls}>")


def css():
    return re.search(r"<style>(.*?)</style>", dashboard(), re.S).group(1)


def media_block(css_text, query):
    """The inside of one @media block, matched by its query text."""
    start = css_text.index(f"@media {query}")
    depth, i = 0, css_text.index("{", start)
    for j in range(i, len(css_text)):
        depth += {"{": 1, "}": -1}.get(css_text[j], 0)
        if depth == 0:
            return css_text[i + 1:j]
    raise AssertionError(f"unclosed @media {query}")


def track_count(columns):
    """How many columns a grid-template-columns value makes.

    "minmax(0, 1fr) 280px" is 2 columns: spaces inside parentheses don't split columns.
    "repeat(2, minmax(0, 1fr))" is also 2 columns: repeat(n, ...) counts as n.
    """
    tokens, depth, current = [], 0, ""
    for char in columns.strip():
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char.isspace() and depth == 0:
            if current:
                tokens.append(current)
            current = ""
        else:
            current += char
    if current:
        tokens.append(current)
    total = 0
    for token in tokens:
        repeat = re.match(r"repeat\(\s*(\d+)\s*,", token)
        total += int(repeat.group(1)) if repeat else 1
    return total


# --- header ----------------------------------------------------------------

def test_heading_is_the_demo_name():
    root = page()
    assert first(root, tag="h1").all_text() == "b-sharp ATC Midterm Demo"
    assert first(root, tag="title").all_text().startswith("b-sharp ATC Midterm Demo")


def test_airport_id_card_is_removed():
    root = page()
    assert not [node for node in root.walk() if node.attrs.get("id") == "airport-id"]
    labels = [node.all_text() for node in root.walk() if "metric-label" in node.classes]
    assert "Airport ID" not in labels


def test_header_row_shows_the_four_details_next_to_the_heading():
    root = page()
    heading = first(root, cls="heading")
    labels = [node.all_text() for node in heading.walk() if "metric-label" in node.classes]
    assert labels == ["Coordinates", "Perimeter", "Runways", "Latest record time"]
    for element_id in ["airport-coordinates", "airport-perimeter", "airport-runway-count", "airport-updated"]:
        assert heading in by_id(root, element_id).ancestors(), element_id


def test_header_values_use_the_agreed_formats():
    script = dashboard()
    coordinates = re.search(r"function formatCoordinates\(latitude, longitude\) \{(.*?)\n      \}", script, re.S)
    assert coordinates, "formatCoordinates() builds the 40.6413° N / 73.7781° W text"
    body = coordinates.group(1)
    assert "°" in body
    assert '"N" : "S"' in body and '"E" : "W"' in body  # hemisphere letters instead of minus signs
    assert "toFixed(4)" in body                          # 4 decimal places, like 40.6413
    assert "demo units" in script


# --- three panels ----------------------------------------------------------

def test_three_panels_in_order():
    root = page()
    grid = first(root, cls="content-grid")
    panels = [child.attrs.get("id") for child in grid.children if "panel" in child.classes]
    assert panels == ["map-panel", "runway-panel", "message-panel"]


def test_runway_availability_has_its_own_column():
    root = page()
    runway_list = by_id(root, "runway-list")
    assert by_id(root, "runway-panel") in runway_list.ancestors()
    assert by_id(root, "map-panel") not in runway_list.ancestors()
    assert by_id(root, "runway-panel") in by_id(root, "runway-summary").ancestors()
    assert by_id(root, "runway-panel").all_text().startswith("Runway availability")


def test_airport_id_stays_visible_on_the_map():
    root = page()
    assert by_id(root, "map-panel") in by_id(root, "map-label").ancestors()
    assert "airport.airport_id" in dashboard()  # the label is filled from the real airport ID


def test_tower_messages_are_the_third_column():
    root = page()
    panel = by_id(root, "message-panel")
    for element_id in ["message-list", "message-form"]:
        assert panel in by_id(root, element_id).ancestors(), element_id
    assert by_id(root, "send-button").all_text() == "Send to Tower"


# --- screen sizes ----------------------------------------------------------

def test_wide_screens_show_three_columns():
    rule = re.search(r"\.content-grid\s*\{([^}]*)\}", css()).group(1)
    columns = re.search(r"grid-template-columns:\s*([^;]+);", rule).group(1)
    assert track_count(columns) == 3


def test_medium_screens_put_the_map_on_top():
    medium = media_block(css(), "(max-width: 1180px)")
    columns = re.search(r"\.content-grid\s*\{[^}]*grid-template-columns:\s*([^;]+);", medium).group(1)
    assert track_count(columns) == 2
    assert re.search(r"\.map-panel\s*\{[^}]*grid-column:\s*1\s*/\s*-1", medium)


def test_phones_stack_everything():
    phone = media_block(css(), "(max-width: 720px)")
    columns = re.search(r"\.content-grid\s*\{[^}]*grid-template-columns:\s*([^;]+);", phone).group(1)
    assert track_count(columns) == 1
