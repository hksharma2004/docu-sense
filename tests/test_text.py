import pytest

from docusense.ingest.normalize import normalize_line, normalize_text
from docusense.ingest.sections import match_heading_text
from docusense.store.blobs import BlobStore, sha256_hex


def test_blob_roundtrip(tmp_path):
    store = BlobStore(tmp_path)
    digest = store.put(b"hello")
    assert digest == sha256_hex(b"hello")
    assert store.put(b"hello") == digest
    assert store.get(digest) == b"hello"
    assert store.path_for(digest).parent.name == digest[:2]


def test_normalize():
    assert normalize_line("ﬁle name\t \r") == "file name"
    assert normalize_text("a\r\nb\rc  ") == "a\nb\nc"


@pytest.mark.parametrize("line, number, title, level", [
    ("4.5.3.1.6.  Text Line", "4.5.3.1.6", "Text Line", 5),
    ("2.1 Basic Structure", "2.1", "Basic Structure", 2),
    ("Appendix B.  Generating SMTP Commands", "B", "Generating SMTP Commands", 1),
    ("A. TCP Transport Service", "A", "TCP Transport Service", 1),
    ("D.1 A Typical SMTP Transaction Scenario", "D.1", "A Typical SMTP Transaction Scenario", 2),
    ("2.3.  0-RTT Data", "2.3", "0-RTT Data", 2),
    ("F.4.  #-literals", "F.4", "#-literals", 2),
    ("Status of This Memo", None, "Status of This Memo", 1),
])
def test_heading_detected(line, number, title, level):
    hm = match_heading_text(line)
    assert hm is not None
    assert (hm.number, hm.title, hm.level) == (number, title, level)


def test_heading_with_inline_body():
    hm = match_heading_text('1. MUST   This word, or the terms "REQUIRED" or "SHALL", mean that')
    assert hm.number == "1" and hm.title == "MUST" and hm.inline_body


@pytest.mark.parametrize("line", [
    "1. Introduction . . . . . . . . . . . . . 5",       # TOC entry
    "1.2.  History .......................... 6",       # TOC entry
    "3. The server sends a reply and the client then waits for the next command to arrive.",
    "1000 octets",
    "",
])
def test_not_a_heading(line):
    assert match_heading_text(line) is None
