"""Turn raw RFC 2822 email bytes into plain-text headers and a readable body.

Shared by every mail provider: the fixture files and Gmail's raw format are the
same bytes, so both go through this one parser.
"""

from dataclasses import dataclass
from email import policy
from email.headerregistry import BaseHeader, HeaderRegistry
from email.message import MIMEPart
from email.parser import BytesParser
from html.parser import HTMLParser

_PLAIN_HEADERS = HeaderRegistry(use_default_map=False)  # every header as unstructured text


class _LenientHeaderRegistry(HeaderRegistry):
    """Builds header objects like the default registry, but never raises.

    Python's header parsers crash on some malformed values, common in spam, wherever a
    header is read: even mid-parse, which reads Content-Type. A header that fails is
    rebuilt from less: a Content-* header from its main value alone, so MIME handling
    still sees e.g. `text/plain`; any other header as plain text.
    """

    def __call__(self, name: str, value: str) -> BaseHeader:
        try:
            return super().__call__(name, value)
        except Exception:  # the stdlib parsers fail in many ways, not one error type
            pass
        if name.lower().startswith('content-'):
            try:
                return super().__call__(name, value.split(';', 1)[0])  # drop the parameters
            except Exception:
                return super().__call__(name, '')
        return _PLAIN_HEADERS(name, value)


# Parse every message with this, so reading a header can never raise.
LENIENT_POLICY = policy.default.clone(header_factory=_LenientHeaderRegistry())


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
    msg = BytesParser(policy=LENIENT_POLICY).parsebytes(raw_bytes)

    sender = header_text(msg, 'From')
    to = header_text(msg, 'To')
    date = header_text(msg, 'Date')
    subject = header_text(msg, 'Subject')

    part = msg.get_body(preferencelist=('plain', 'html'))

    if part is None:
        body = ''
    else:
        text = _decode_text(part)
        if part.get_content_type() == 'text/html':
            body = html_to_text(text)
        else:
            # CRLF (Gmail's raw format) and bare CR to \n; nothing else counts as a break.
            body = text.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n')
    return ParsedMessage(sender, to, date, subject, body)


def header_text(msg: MIMEPart, name: str) -> str:
    """Return a header as one line of decoded plain text, or '' if missing.

    `msg` must come from `LENIENT_POLICY`, so a malformed value can't raise; it comes
    back as plain text instead. Every whitespace run becomes one space, including line
    breaks encoded as `=0D=0A`, so a value can never start a forged header line.
    """
    return ' '.join(str(msg.get(name, '')).split())


def _decode_text(part: MIMEPart) -> str:
    """Decode a text part to str. Unknown or undeclared charsets fall back to UTF-8.

    Python assumes ASCII when no charset is declared, which garbles UTF-8 text. It
    raises LookupError on charset names it doesn't know (e.g. `unknown-8bit`), and
    UnicodeError (a ValueError) on codecs that can't decode text, like `idna`.
    """
    payload = part.get_payload(decode=True)  # undoes base64 / quoted-printable
    if not isinstance(payload, bytes):  # only a multipart or rfc822 part gives non-bytes
        payload = b''
    charset = part.get_content_charset() or 'utf-8'
    try:
        return payload.decode(charset, 'replace')
    except (LookupError, ValueError):
        return payload.decode('utf-8', 'replace')


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
