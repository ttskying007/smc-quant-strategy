# -*- coding: utf-8 -*-
"""Test pure-Python PDF text extraction feasibility (no external libs).
Download a small announcement PDF and try zlib-based text extraction."""
import io, re, sys, urllib.request, zlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# a small announcement PDF (use a known small one - the test one from probe)
url = "https://pdf.dfcfw.com/pdf/H2_AN202608141827994407_1.pdf"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    print("PDF downloaded:", len(data), "bytes, header:", data[:8])
except Exception as e:
    print("download FAIL:", e)
    sys.exit(1)


def extract_text(pdf):
    """Minimal PDF text extraction: find streams, decompress flate, pull Tj/TJ text."""
    texts = []
    # find stream objects
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", pdf, re.S):
        raw = m.group(1)
        # try flate decode
        try:
            dec = zlib.decompress(raw)
        except Exception:
            continue
        # extract text from BT...ET blocks with Tj/TJ
        for tm in re.finditer(rb"\(([^()]*)\)\s*Tj", dec):
            texts.append(tm.group(1))
        for tm in re.finditer(rb"\[(.*?)\]\s*TJ", dec, re.S):
            parts = re.findall(rb"\(([^()]*)\)", tm.group(1))
            texts.append(b"".join(parts))
    return b"".join(texts)


txt = extract_text(data)
print("extracted bytes:", len(txt))
if txt:
    # decode with common encodings
    for enc in ("gbk", "utf-8", "latin-1"):
        try:
            s = txt.decode(enc)
            print(f"  [{enc}] sample:", s[:200].replace("\n", " "))
            break
        except Exception:
            continue
else:
    print("no text extracted (PDF may be scanned/image-based)")
