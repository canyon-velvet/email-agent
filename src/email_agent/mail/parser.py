from email import policy
from email.parser import BytesParser
from dataclasses import dataclass
from html.parser import HTMLParser

@dataclass(frozen=True)
class ParsedMessage:
    sender: str
    to: str
    date: str
    subject: str
    body: str


def parse_message(raw_bytes):
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
    def __init__(self) -> None:
        super().__init__()
        self.pieces: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
        elif tag in BLOCK_TAGS:
            self.pieces.append('\n')

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
        elif tag in BLOCK_TAGS:
            self.pieces.append('\n')

    def handle_data(self, data):
        if self.skip_depth == 0:
            self.pieces.append(data)

def html_to_text(html):
    extractor = TextExtractor()
    extractor.feed(html)
    extractor.close()
    text = ''.join(extractor.pieces)

    lines = []
    for line in text.splitlines():
        line = ' '.join(line.split())
        if line:
            lines.append(line)
    return '\n'.join(lines)
