"""deterministic text normalisation. any change here must bump PARSER_VERSION"""

import re
import unicodedata

_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SPACES = str.maketrans({" ": " ", " ": " ", " ": " ", " ": " ", "​": ""})


def normalize_line(line: str) -> str:
    line = unicodedata.normalize("NFKC", line).translate(_SPACES)
    line = _CONTROL.sub("", line.expandtabs(8))
    return line.rstrip()


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(normalize_line(line) for line in text.split("\n"))
