
"""
Extract 3D virtual tour links from OSF Portfolio content.
"""

from html.parser import HTMLParser
from urllib.parse import urlparse

from app.utils.google_maps import normalize_map_project_name


ALLOWED_TOUR_HOSTS = {
    "3d.virtualhomes.in",
    "danube.discoverin360.com",
    "view.propvr.tech",
    "virtualtour.farcomtrento.com",
}


def safe_tour_url(value):
    """Accept valid HTTPS URLs from approved tour providers."""

    if not isinstance(value, str):
        return None

    url = value.strip()

    try:
        parsed = urlparse(url)

        if (
            parsed.scheme != "https"
            or parsed.hostname not in ALLOWED_TOUR_HOSTS
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (None, 443)
        ):
            return None

        return url

    except ValueError:
        return None


class VirtualTourParser(HTMLParser):
    """Find virtual tour links in OSF HTML content."""

    TOUR_LABELS = (
        "virtual tour",
        "3d tour",
        "360 tour",
        "360° tour",
        "360 virtual tour",
    )

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.current_href = dict(attrs).get("href")
            self.current_text = []

    def handle_data(self, data):
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag):
        if tag.lower() != "a" or self.current_href is None:
            return

        label = " ".join(self.current_text).casefold()

        if any(
            keyword in label
            for keyword in self.TOUR_LABELS
        ):
            url = safe_tour_url(self.current_href)

            if url:
                self.links.append(url)

        self.current_href = None
        self.current_text = []


def extract_virtual_tour_url(content):
    """Extract the first valid tour URL from project HTML."""

    if not isinstance(content, str) or not content.strip():
        return None

    parser = VirtualTourParser()
    parser.feed(content)

    return parser.links[0] if parser.links else None


def build_project_tour_lookup(portfolio):
    """
    Build:
        normalized_project_name -> virtual_tour_url

    Uses OSF Portfolio title and HTML content.
    """

    lookup = {}
    ambiguous = set()

    if not isinstance(portfolio, list):
        return lookup

    for item in portfolio:
        if not isinstance(item, dict):
            continue

        title = item.get("title")
        content = item.get("content")

        tour_url = extract_virtual_tour_url(content)

        if not tour_url:
            continue

        key = normalize_map_project_name(title)

        if not key:
            continue

        if key in lookup and lookup[key] != tour_url:
            ambiguous.add(key)
        else:
            lookup[key] = tour_url

    for key in ambiguous:
        lookup.pop(key, None)

    return lookup
