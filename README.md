# local_ocr

Many new "small" language models, such as recent Qwen and Gemma models, are very good at OCR, even on handwriting. Not best for every use case, but preferable to traditional solutions in messy circumstances. This script leverages that to allow the creation of accessible, machine readable text without needing to use a cloud service, which is preferable for privacy sensitive applications.

### Install dependencies
Script assumes you have an LMStudio instance running on default localhost:1234.
You also need the following python libraries installed:

```
pip install pymupdf requests
```

### Usage
```
python3 local_ocr.py <path/filename.pdf>
```

By default markdown version will be filename.md in same directory. You can change this if you want to using the -o (output) flag.

```
python3 local_ocr.py /imports/file.pdf -o /exports/file.md
```

### Handling blank pages (retries & heuristics)
Vision models occasionally return nothing for a page — sometimes the page really is blank, sometimes the model just choked on it. The script tells these apart instead of silently dropping text.

For each page it:

1. **Measures ink.** A fast low-resolution grayscale pass counts dark pixels. If the page is essentially white, a blank response is accepted as `[no text found]` and no time is wasted retrying.
2. **Retries pages that have writing but came back empty.** Each retry re-renders at a higher DPI (`+--dpi-step` per attempt) and nudges the temperature up slightly. Refusal-style replies (e.g. "I'm unable to…", "appears to be blank") are treated as failures and retried too.
3. **Falls back to Tesseract** (optional, on by default) only after retries are exhausted on a page that clearly has content. Tesseract is a printed-text engine and is poor at handwriting, so its output is clearly marked in the Markdown with an HTML comment — it is a last resort, not a peer of the model.

At the end it prints a summary like `Pages — ok:5 recovered:2 blank:1 failed:0`.

Relevant flags (all optional):

| Flag | Default | Purpose |
|------|---------|---------|
| `--retries N` | `2` | Retries for a blank/failed page before giving up. |
| `--dpi N` | `200` | Base render resolution. Raise for dense or faint handwriting. |
| `--dpi-step N` | `50` | DPI added on each retry. |
| `--blank-ink-threshold F` | `0.004` | Min dark-pixel fraction for a page to count as "has content". Lower it if real pages are wrongly called blank; raise it if truly blank pages keep getting retried. The per-page ink fraction is printed to the log so you can calibrate. |
| `--temperature F` | `0.1` | Base sampling temperature. Kept low so the model doesn't "autocomplete" handwriting into plausible-but-wrong words. |
| `--max-tokens N` | `4096` | Max output tokens per page. |
| `--no-tesseract` | (fallback on) | Disable the Tesseract fallback entirely. |

The Tesseract fallback is best-effort — if its libraries aren't installed it is silently skipped. To enable it:

```
pip install pytesseract pillow
# plus the tesseract binary, e.g. on Debian/Ubuntu:
sudo apt install tesseract-ocr
```

### Prompt
This is the system prompt the script uses by default. Begins on line 43 of the script if you want to tweak it.

```
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
```
