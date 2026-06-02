#!/usr/bin/env python3
"""
local_ocr.py — verbatim handwriting/scan transcription via a local LM Studio server.

Renders each page of a PDF to an image, sends them ONE AT A TIME to a
vision-capable model served at localhost:1234 (OpenAI-compatible API), and
concatenates the results into a single Markdown file.

Usage:
    python local_ocr.py scan.pdf
    python local_ocr.py scan.pdf -o out.md --dpi 250 --model qwen/qwen3-vl-30b

Requires:
    pip install pymupdf requests
"""

import argparse
import base64
import sys
import time
from pathlib import Path

import requests

try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("Missing dependency: pip install pymupdf")


SYSTEM_PROMPT = """\
You are a verbatim transcription engine. Your only job is to convert an image of
handwritten (or typed) pages into Markdown that reproduces the source EXACTLY as
written. You are not an editor, proofreader, or assistant. Accuracy to the
original — including its mistakes — is the only thing that matters.

## Core rule
Transcribe what is ACTUALLY ON THE PAGE, not what the writer meant. Never
"fix," "improve," "complete," or "normalize" anything.

## Preserve exactly
- Spelling errors and typos — copy them letter-for-letter (e.g. "definately",
  "teh", "recieve"). Do NOT correct them.
- Grammar, punctuation, and capitalization as written, including missing or
  doubled punctuation and random capitals.
- The writer's original line breaks and paragraph breaks.
- Numbers, dates, and abbreviations exactly as written (don't expand "Jan." to
  "January" or reformat dates).
- Spacing quirks only where meaningful (e.g. indentation, hanging text); collapse
  ordinary multiple spaces to one.

## Markdown conventions for handwriting features
- Crossed-out / struck-through text: wrap in ~~strikethrough~~.
- Inserted text (carets, words squeezed above the line): place inline where
  inserted and mark as ^[inserted: word].
- Underlined text: render as **bold**.
- Margin notes / annotations: put on their own line as `> [margin: ...]`.
- Headings, titles, or clearly larger text: use # / ## as appropriate.
- Lists: use - or 1. only if the original is visibly a list.
- Tables: use Markdown tables only if the original is laid out as a grid.

## Uncertainty and gaps
- A word you cannot confidently read: [unclear: best-guess].
- Completely illegible word(s): [illegible].
- Whole illegible line/region: [illegible line].
- Blank fields/lines left empty by the writer: [blank].
- A page or word cut off at the edge: [cut off].
Never invent or guess to fill a gap. When unsure, mark it — do not silently
choose the "sensible" word.

## Output
- Output ONLY the transcription as Markdown. No preamble, no summary, no
  explanation, no "Here is the transcription," no commentary about legibility.
- If the image contains no readable text at all, output exactly: [no text found]
"""


def render_pages(pdf_path: Path, dpi: int):
    """Yield (page_number, png_bytes) for each page of the PDF."""
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc, start=1):
            pix = page.get_pixmap(dpi=dpi)
            yield i, pix.tobytes("png")
    finally:
        doc.close()


def strip_fences(text: str) -> str:
    """Remove a wrapping ```markdown ... ``` fence if the model added one."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    return t


def transcribe_page(png_bytes: bytes, args) -> str:
    b64 = base64.b64encode(png_bytes).decode("ascii")
    data_uri = f"data:image/png;base64,{b64}"
    payload = {
        "model": args.model,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "Transcribe this page verbatim."},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ],
            },
        ],
    }
    headers = {"Content-Type": "application/json"}
    if args.api_key:
        headers["Authorization"] = f"Bearer {args.api_key}"

    resp = requests.post(
        f"{args.url.rstrip('/')}/chat/completions",
        json=payload,
        headers=headers,
        timeout=args.timeout,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return strip_fences(content)


def main():
    p = argparse.ArgumentParser(description="Verbatim PDF transcription via a local vision model.")
    p.add_argument("file", help="Input PDF file")
    p.add_argument("-o", "--output", help="Output Markdown file (default: <input>.md)")
    p.add_argument("--url", default="http://localhost:1234/v1",
                   help="OpenAI-compatible base URL (default: %(default)s)")
    p.add_argument("--model", default="local-model",
                   help="Model id loaded in the server (default: %(default)s)")
    p.add_argument("--dpi", type=int, default=200,
                   help="Render resolution; bump to 250-300 for dense handwriting (default: %(default)s)")
    p.add_argument("--temperature", type=float, default=0.1,
                   help="Sampling temperature; keep low to avoid 'autocompleting' handwriting (default: %(default)s)")
    p.add_argument("--max-tokens", type=int, default=4096, dest="max_tokens",
                   help="Max output tokens per page (default: %(default)s)")
    p.add_argument("--timeout", type=int, default=600, help="Per-request timeout in seconds (default: %(default)s)")
    p.add_argument("--api-key", default="lm-studio", help="Bearer token if your server requires one")
    args = p.parse_args()

    pdf_path = Path(args.file)
    if not pdf_path.is_file():
        sys.exit(f"File not found: {pdf_path}")

    out_path = Path(args.output) if args.output else pdf_path.with_suffix(".md")

    pages = list(render_pages(pdf_path, args.dpi))
    total = len(pages)
    if total == 0:
        sys.exit("No pages found in PDF.")
    print(f"{pdf_path.name}: {total} page(s) at {args.dpi} DPI -> {out_path}", file=sys.stderr)

    sections = []
    for num, png in pages:
        t0 = time.time()
        try:
            text = transcribe_page(png, args)
        except Exception as e:  # keep going; mark the failed page
            text = f"[transcription failed: {e}]"
            print(f"  page {num}/{total}: ERROR {e}", file=sys.stderr)
        else:
            print(f"  page {num}/{total}: {len(text)} chars in {time.time()-t0:.1f}s", file=sys.stderr)
        sections.append(text)

    full = "\n\n---\n\n".join(sections) + "\n"
    out_path.write_text(full, encoding="utf-8")
    print(f"Wrote {out_path} ({len(full)} chars).", file=sys.stderr)


if __name__ == "__main__":
    main()
