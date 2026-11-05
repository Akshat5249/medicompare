# AI and OCR design

**Principle: software proposes, a person decides.** No score, model or rule can verify a medicine.

## Pipeline
1. **Intake:** type is decided from magic bytes. Size, page and pixel limits apply. Images are re-encoded from pixels, which removes EXIF and GPS data. PDF metadata, named objects and open actions are removed, and pages are rendered to pixels.
2. **Pre-processing (`imaging.py`):** applies EXIF orientation, detects the page region, deskews small angles, upscales small pages, denoises and enhances contrast.
3. **OCR (`ocr.py`):** the `OcrEngine` protocol returns text spans with a box and quality. Spans are grouped into lines. Engines: Tesseract and RapidOCR.
4. **Extraction (`extraction.py`):** deterministic, schema-validated, input-derived.
5. **Matching (`matcher.py`):** deterministic, explainable candidates.
6. **Confidence (`confidence.py`):** separate OCR and match scores change a label only.
7. **Human verification:** image beside fields, correct, confirm, reject or mark unresolved.
8. **Gate (`safety/gate.py`):** prices and options require `status=verified`, a medicine and a verifier type. A database constraint backs this up.

## Extraction schema
Defined as `EXTRACTION_SCHEMA`. Each field has a value and a state:

| State | Meaning | Value |
|---|---|---|
| `visible` | Read from the document | The fragment as written |
| `unclear` | Something is there but is not reliable | `null` |
| `unknown` | Not found | `null` |

Fields: `name`, `strength`, `form`, `frequency`, `duration`, plus `source_text`. Lines below a quality of 0.45 become `unclear`. **Nothing is inferred**, including dose, frequency, route or strength.

## Line filtering, before any parsing
| Line type | Handling |
|---|---|
| Instruction-like text | Dropped and counted (`safety/injection.py`) |
| Personal details (doctor, patient, phone, date, address) | Dropped and counted, never stored as text |
| Headings and vitals (`Rx`, `BP`) | Ignored |
| No form word and no strength | Ignored |

**Limit:** this filter uses patterns. Unusual layouts can leak a name into `source_text`, and the image itself still shows personal details, so it is private and short-lived.

## Matching rules
- Name similarity must reach 0.75 (Jaro-Winkler against brand, or per-ingredient against all ingredients), then contributes 70% of the score.
- A single-ingredient query cannot strongly match an FDC, or the reverse.
- Strength: match +0.20, conflict −0.25, absent adds nothing.
- Form: match +0.05, conflict −0.10.
- Release marker: match +0.05, conflict −0.15. A special-release product with no written marker: −0.05.
- Candidates need 0.62 or more. At most five are returned.
- Look-alike hits add a warning and force an acknowledgement at the API.

**Maximum score without a readable strength is 0.75**, so a missing strength can never look like a strong match.

## Equivalence rules
`equivalence.compare()` requires matching ingredients, salt form (stated on both), canonical strength, dosage form, route and release type. Names are never an input.

## Confidence
Thresholds come only from measured validation results, in `thresholds.json`. Without that file, every item is labelled "not calibrated". With it, an item is labelled "possible match" or "low confidence". **Status stays `needs_verification` either way.** See [EVALUATION.md](EVALUATION.md).

## Safety checks at verification
| Attempt | Result |
|---|---|
| Medicine is not a candidate | `422 not_a_candidate` |
| Look-alike not acknowledged | `409 lasa_review_required` |
| Readable strength conflicts | `409 strength_conflict` |
| Text corrected after verification | Verification cleared, rematched |

## Optional LLM adapter (`llm.py`)
- **Off by default,** and **not connected to the pipeline in this build.** It is a tested module for later evaluation.
- **Uses** the official Anthropic SDK, structured outputs, default model `claude-opus-5-5` with server-side refusal fallback, and `LLM_MODEL` to change the model.
- **Input:** only lines that already passed filtering, inside a delimited block labelled untrusted.
- **Output:** must pass the same schema, and any fragment not found verbatim in the input becomes `unclear`.
- **Never** chooses a match or gives advice.
- **Logs** model, tokens and estimated cost, never content.
- **Tested** with a fake client only. It has not been run against the live API.

## Prompt injection
The deterministic pipeline has no way to take instructions. The worst an injected line can do is appear as text. Tests render injection text into images and PDFs and confirm that nothing changes. See `test_prompt_injection_*`.

## Emergency detection
`safety/emergency.py` matches English, Hindi and Tamil patterns in searches, manual entry and OCR text. It is deliberately over-inclusive, and the pattern list needs [native-speaker review](OPEN_ITEMS.md). A pattern match cannot catch every way a person might describe an emergency, so the 112 message also stays in the footer.
