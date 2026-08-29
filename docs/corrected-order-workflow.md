# Corrected Order Workflow

## Product behavior

The converter supports two order types:

- **New order** keeps the existing single-PDF conversion unchanged.
- **Corrected order** accepts an original PDF and a corrected PDF, generates the
  original workbook internally as a baseline, applies supported corrections,
  and returns one corrected workbook with a `Revision Report` worksheet.

Corrected orders automatically apply changes that are corroborated by both the
structured selection rows and the revision text. Ambiguous changes require an
explicit Apply or Ignore decision. When a correction implies a quantity change
that is not stated in the PDFs and cannot be derived from a configured rule, the
baseline quantity/formula is retained and the report records a warning. The LLM
must never invent purchasing quantities or directly edit workbook cells.

Classica corrected orders are enabled using the supplied lot 33 and lot 34
fixtures. The correction architecture supports builder-specific adapters, but
Saussy corrected orders remain disabled until a real original/revised Saussy
pair is available and passes the correction contract tests.

## Processing design

1. Parse both PDFs into normalized metadata, room/item rows, revision dates,
   selection text, and change-order text.
2. Reject identical documents, reversed revision dates, and mismatched order
   identities (project/permit/job).
3. Match rows using room, item type, product code, and occurrence. Compare the
   normalized snapshots and correlate differences with revision instructions.
4. Use deterministic logic for exact changes. Send only redacted unmatched
   change snippets and candidate rows to the OpenAI Responses API using strict
   structured output.
5. Classify confidence in application code. Exact corroborated targets are
   high-confidence; prose-only, conflicting, ambiguous, or quantity-implicit
   changes require review.
6. Generate the original workbook model, apply accepted typed actions to that
   model, preserve unstated quantities, and write the corrected workbook plus
   the audit report.

The OpenAI integration uses server-side `OPENAI_API_KEY`, defaults
`OPENAI_CORRECTION_MODEL` to `gpt-5.6-terra`, sets `store: false`, and degrades
to reviewable deterministic results on timeout, refusal, malformed output, or
missing credentials. Raw PDFs and identifying header fields are not sent to the
model.

## Interfaces

- Existing `POST /api/convert` remains unchanged.
- `POST /api/corrections/analyze` accepts multipart `original_pdf`,
  `corrected_pdf`, and `template`, returning document hashes, typed actions,
  warnings, and review requirements.
- `POST /api/corrections/generate` accepts the same PDFs plus the analyzed
  actions and user decisions, revalidates document hashes/evidence, and returns
  `{corrected-name}-Corrected.xlsx`.
- Each PDF retains the 4 MB limit; corrected requests also have a 4 MB combined
  limit to fit the current deployment envelope.
- History records gain backward-compatible order type, original/corrected
  filenames, applied-change count, and warning count fields. Uploaded PDFs and
  generated workbooks remain ephemeral.

## Revision action contract

Each action includes a stable ID, operation (`ADD`, `DELETE`, `CHANGE`, or
`CLARIFICATION`), room, item type, target field, before/after values, evidence
from both documents, confidence (`high` or `review`), quantity treatment, status,
and warnings. High-confidence actions are applied automatically. Every review
action must be explicitly applied or ignored before generation.

The `Revision Report` sheet records the same contract plus the LLM model and
prompt version. It must agree exactly with changes made to the workbook.

## Acceptance tests

- Lot 33 replaces the bedroom 2 corner shelf with a niche and updates the
  bedroom 3 corner-shelf color to CN13.
- Lot 34 applies the niche-material and grout clarifications, retains the
  baseline formula quantity where the numeric effect is unstated, and records a
  warning explaining the retained quantity.
- Validate identical/swapped/mismatched PDFs, no-change revisions, duplicate
  products, wrapped text, revised-header reflow, missing quantities, and
  conflicting instructions.
- Mock LLM success, refusal, malformed output, timeout, and missing API key.
- Confirm existing new-order behavior and legacy history decoding remain
  unchanged, and exercise corrected-mode keyboard, validation, loading, review,
  and focus behavior.
