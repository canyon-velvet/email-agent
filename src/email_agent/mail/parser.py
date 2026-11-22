"""Turn raw RFC 2822 email bytes into plain-text headers and a readable body.

Shared by every mail provider: the fixture files and Gmail's raw format are the
same bytes, so both go through this one parser.
"""

from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser


@dataclass(frozen=True)
class ParsedMessage:
    """The parts of a raw email that come from the email itself (not provider metadata)."""

    sender: str
    to: str
    date: str
    subject: str
    body: str


def parse_message(raw_bytes: bytes) -> ParsedMessage:
    """Parse a raw email: decode its headers and pick a readable body.

    The body is the text/plain part if there is one, else the text/html part
    converted to text, else empty. Transfer encodings and charsets are decoded.
    """
    msg = BytesParser(policy=policy.default).parsebytes(raw_bytes)

    sender = str(msg.get('From', ''))
    to = str(msg.get('To', ''))
    date = str(msg.get('Date', ''))
    subject = str(msg.get('Subject', ''))

    part = msg.get_body(preferencelist=('plain', 'html'))

    if part is None:
        body = ''
    else:
        text = part.get_content()
        if part.get_content_type() == 'text/html':
            body = html_to_text(text)
        else:
            body = text
    return ParsedMessage(sender, to, date, subject, body)


BLOCK_TAGS = {'p', 'br', 'div', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li', 'tr'}
SKIP_TAGS = {'script', 'style'}


class TextExtractor(HTMLParser):
    """Collects the visible text of an HTML document as `HTMLParser` reads it.

    Text inside <script> and <style> is skipped, and block tags add line breaks so
    paragraphs stay on separate lines. Entities like `&amp;` arrive already decoded.
    """

    def __init__(self) -> None:
        super().__init__()
        self.pieces: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.pieces.append('\n')

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self.pieces.append('\n')

    def handle_data(self, data: str) -> None:
        if self.skip_depth == 0:
            self.pieces.append(data)


def html_to_text(html: str) -> str:
    """Convert HTML to readable text: one line per block, single spaces, no blank lines."""
    extractor = TextExtractor()
    extractor.feed(html)
    extractor.close()
    text = ''.join(extractor.pieces)

    lines: list[str] = []
    for line in text.splitlines():
        line = ' '.join(line.split())
        if line:
            lines.append(line)
    return '\n'.join(lines)
