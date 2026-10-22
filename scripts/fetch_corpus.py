"""Download the RFC corpus and write corpus/manifest.yaml.

Newer RFCs (v3 format, RFC 8650+) ship an official PDF, which is used as-is. Older RFCs are
published only as paginated .txt, so they are rendered to a fixed-width PDF; the .txt URL and
its SHA-256 are recorded in the manifest so the provenance chain stays intact.
"""

import sys
from pathlib import Path

import httpx
import yaml

from docusense.ingest.render import render_txt_pdf
from docusense.store.blobs import sha256_hex

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "corpus"
RAW = CORPUS / "raw"

# (document id, title, RFC numbers ordered old → new; each newer RFC obsoletes the previous)
RFC_DOCUMENTS = [
    ("smtp", "Simple Mail Transfer Protocol", [2821, 5321]),
    ("imf", "Internet Message Format", [2822, 5322]),
    ("uri", "Uniform Resource Identifier (URI): Generic Syntax", [2396, 3986]),
    ("tls", "The Transport Layer Security (TLS) Protocol", [5246, 8446]),
    ("bcp14", "Key words for use in RFCs to Indicate Requirement Levels", [2119]),
    ("bcp14-case", "Ambiguity of Uppercase vs Lowercase in RFC 2119 Key Words", [8174]),
    ("oauth2", "The OAuth 2.0 Authorization Framework", [6749]),
    ("oauth2-bearer", "The OAuth 2.0 Authorization Framework: Bearer Token Usage", [6750]),
    ("pkce", "Proof Key for Code Exchange by OAuth Public Clients", [7636]),
    ("oauth-security-bcp", "Best Current Practice for OAuth 2.0 Security", [9700]),
]

# (document id, title, [(label, file under corpus/synthetic)])
SYNTHETIC_DOCUMENTS = [
    ("mail-policy", "Example Org Mail Server Policy",
     [("v1", "mail-policy-v1.md"), ("v2", "mail-policy-v2.md")]),
    ("oauth-profile", "Example Org OAuth Deployment Profile",
     [("v1", "oauth-profile-v1.md")]),
]


def fetch_rfc(client: httpx.Client, number: int, title: str) -> dict:
    out = RAW / f"rfc{number}.pdf"
    pdf_url = f"https://www.rfc-editor.org/rfc/rfc{number}.pdf"
    resp = client.get(pdf_url)
    if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("application/pdf"):
        out.write_bytes(resp.content)
        return {"kind": "official-pdf", "url": pdf_url, "sha256": sha256_hex(resp.content)}

    txt_url = f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
    resp = client.get(txt_url)
    resp.raise_for_status()
    out.write_bytes(render_txt_pdf(resp.text, f"RFC {number}: {title}"))
    return {"kind": "rendered-from-txt", "url": txt_url, "sha256": sha256_hex(resp.content),
            "renderer": "docusense-render/0.1"}


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    documents = []
    with httpx.Client(follow_redirects=True, timeout=60) as client:
        for doc_id, title, numbers in RFC_DOCUMENTS:
            versions = []
            for number in numbers:
                origin = fetch_rfc(client, number, title)
                print(f"  rfc{number:<5} {origin['kind']}", file=sys.stderr)
                versions.append({"label": f"rfc{number}", "file": f"raw/rfc{number}.pdf", "origin": origin})
            documents.append({"id": doc_id, "title": title, "family": "rfc", "versions": versions})

    for doc_id, title, files in SYNTHETIC_DOCUMENTS:
        versions = []
        for label, name in files:
            path = CORPUS / "synthetic" / name
            if not path.exists():
                print(f"  missing synthetic doc: {path}", file=sys.stderr)
                continue
            versions.append({"label": label, "file": f"synthetic/{name}",
                             "origin": {"kind": "synthetic", "sha256": sha256_hex(path.read_bytes())}})
        documents.append({"id": doc_id, "title": title, "family": "synthetic", "versions": versions})

    manifest = CORPUS / "manifest.yaml"
    manifest.write_text(yaml.safe_dump({"documents": documents}, sort_keys=False, width=100))
    print(f"wrote {manifest}", file=sys.stderr)


if __name__ == "__main__":
    main()
