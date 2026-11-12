"""
Extract project FAQs from OSF Portfolio project records.

OSF field (per project):
    danube_faqs_title_and_content: [
        {"danube_faqs_title": "<question>",
         "danube_faqs_content": "<answer as HTML>"},
        ...
    ]

The answer HTML comes from a CMS and is never rendered as-is.
It is converted into plain-text blocks (paragraphs and bullet
lists) which the template escapes on output.
"""

import re
from html.parser import HTMLParser


FAQ_FIELD = "danube_faqs_title_and_content"
FAQ_TITLE_KEY = "danube_faqs_title"
FAQ_CONTENT_KEY = "danube_faqs_content"

MAX_FAQS = 50
MAX_QUESTION_CHARS = 300
MAX_BLOCK_CHARS = 2000

_WHITESPACE = re.compile(r"\s+")


def _clean_text(value: str) -> str:
    #   is &nbsp; after entity conversion.
    return _WHITESPACE.sub(
        " ",
        str(value or "").replace(" ", " "),
    ).strip()


class _FAQContentParser(HTMLParser):
    """
    Convert FAQ answer HTML into blocks:
        {"type": "paragraph", "text": "..."}
        {"type": "list", "items": ["...", "..."]}

    All tags and attributes are dropped; only text is kept.
    Script/style content is discarded entirely.
    """

    BLOCK_TAGS = {
        "p", "div", "br", "h1", "h2", "h3",
        "h4", "h5", "h6", "section", "article",
    }
    LIST_TAGS = {"ul", "ol"}
    SKIP_TAGS = {"script", "style", "noscript", "template"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks = []
        self._text = []
        self._list_items = None
        self._item_text = None
        self._skip_depth = 0

    # -- helpers ---------------------------------------------------

    def _flush_paragraph(self):
        text = _clean_text("".join(self._text))
        self._text = []

        if text:
            self.blocks.append({
                "type": "paragraph",
                "text": text[:MAX_BLOCK_CHARS],
            })

    def _flush_item(self):
        if self._item_text is None:
            return

        text = _clean_text("".join(self._item_text))
        self._item_text = None

        if text and self._list_items is not None:
            self._list_items.append(text[:MAX_BLOCK_CHARS])

    # -- parser callbacks -------------------------------------------

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return

        if self._skip_depth:
            return

        if tag in self.LIST_TAGS:
            self._flush_paragraph()
            if self._list_items is None:
                self._list_items = []

        elif tag == "li":
            self._flush_item()
            self._item_text = []

        elif tag in self.BLOCK_TAGS:
            if self._item_text is not None:
                self._item_text.append(" ")
            else:
                self._flush_paragraph()

    def handle_endtag(self, tag):
        tag = tag.lower()

        if tag in self.SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return

        if self._skip_depth:
            return

        if tag == "li":
            self._flush_item()

        elif tag in self.LIST_TAGS:
            self._flush_item()
            if self._list_items:
                self.blocks.append({
                    "type": "list",
                    "items": self._list_items,
                })
            self._list_items = None

        elif tag in self.BLOCK_TAGS:
            if self._item_text is None:
                self._flush_paragraph()

    def handle_data(self, data):
        if self._skip_depth:
            return

        if self._item_text is not None:
            self._item_text.append(data)
        else:
            self._text.append(data)

    def close(self):
        super().close()
        self._flush_item()

        if self._list_items:
            self.blocks.append({
                "type": "list",
                "items": self._list_items,
            })
            self._list_items = None

        self._flush_paragraph()


def html_to_blocks(content) -> list[dict]:
    """Convert CMS answer HTML into safe text blocks."""

    if not isinstance(content, str) or not content.strip():
        return []

    parser = _FAQContentParser()

    try:
        parser.feed(content)
        parser.close()
    except Exception:
        # Malformed HTML: fall back to a single text paragraph.
        text = _clean_text(re.sub(r"<[^>]*>", " ", content))
        return (
            [{"type": "paragraph", "text": text[:MAX_BLOCK_CHARS]}]
            if text
            else []
        )

    return parser.blocks


def html_to_text(value) -> str:
    """Plain text from a short HTML/entity string (FAQ titles)."""

    blocks = html_to_blocks(value)
    parts = []

    for block in blocks:
        if block["type"] == "paragraph":
            parts.append(block["text"])
        else:
            parts.extend(block["items"])

    return _clean_text(" ".join(parts))


def find_faq_entries(project_item) -> list:
    """
    Locate the raw FAQ list on an OSF project record.

    Checked on the project itself first, then under "meta"
    (where OSF keeps other custom fields such as "aminities").
    """

    if not isinstance(project_item, dict):
        return []

    for container in (
        project_item,
        project_item.get("meta"),
    ):
        if not isinstance(container, dict):
            continue

        entries = container.get(FAQ_FIELD)

        if isinstance(entries, list):
            return entries

    return []


def extract_project_faqs(project_items) -> list[dict]:
    """
    Build the FAQ list for one project.

    project_items: OSF records matched to the project (usually one).

    Returns:
        [{"question": str, "answer": [blocks]}, ...]

    Entries without a question or without an answer are skipped,
    and duplicate questions are removed (first one kept).
    """

    faqs = []
    seen = set()

    for item in project_items or []:

        for entry in find_faq_entries(item):

            if not isinstance(entry, dict):
                continue

            question = html_to_text(
                entry.get(FAQ_TITLE_KEY)
            )[:MAX_QUESTION_CHARS]

            answer = html_to_blocks(
                entry.get(FAQ_CONTENT_KEY)
            )

            if not question or not answer:
                continue

            key = question.casefold()

            if key in seen:
                continue

            seen.add(key)
            faqs.append({
                "question": question,
                "answer": answer,
            })

            if len(faqs) >= MAX_FAQS:
                return faqs

    return faqs
