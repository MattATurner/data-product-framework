---
name: assess-use-case
description: >-
  Assess a filled use-case definition (templates/define/1-use-case.pdf or a use-case YAML)
  against the DPF template and say whether it is ready for scoring: every section complete,
  answers specific and in business language, and enough evidence for each scorecard criterion.
  Use when a sponsor submits a use case, before the scoring panel meets, or when asked to
  review, check or quality-assure a use case. Don't use to write a use case or to score it:
  the panel scores, in templates/define/2-scorecard.pdf.
metadata:
  # Workspace-only for now. Before moving this skill into skills/, add the platform capability
  # spec openspec/specs/platform/define-readiness: dpf validate requires it.
  dpf:
    skill_id: assess-use-case
    stage: define
    scope: product
    implements: define-readiness
    consumes: []
    produces: []
    tool_tier: 4
    tool: dpf-local
    owner: business-analyst
---

# Assess a use case

Check a filled use case against the Define template before the scoring panel sees it. The
standard is the workspace's own template, scoring model and vocabulary, read each time. Find
the gaps and ask the sponsor questions. Never write, improve or score the use case.

## 1. Run the mechanical checks

From the workspace root:

```bash
python3 .agents/skills/assess-use-case/scripts/check_use_case.py <filled 1-use-case.pdf or use-case.yaml> \
  --out-dir generated/define/<UC-ID>
```

- Use the workspace's Python (`.venv/bin/python` in the framework repository). A PDF needs
  pypdf: `pip install --require-hashes -r requirements/templates.txt`. YAML needs only PyYAML.
- It writes `checks.json` and `checks.md`: the answers in one shape whatever the input, the
  mechanical findings, the evidence for each scorecard criterion and a provisional verdict.
  Work from `checks.json`. Do not read the PDF yourself.
- If the use case has no ID, name the folder after the input file.
- Keep every mechanical finding. You may add context, but never drop or downgrade one.

## 2. Add the judgement checks

Read each answer in `checks.json` `answers`, with the hints in
`templates/src/use-case.form.yaml`. Add a finding wherever an answer is not good enough:

| Section | Good when |
|---|---|
| Control | Proposed by gives a name and a role. The status is true: Approved, Scored, Deferred or Rejected needs the record that says so. |
| Description | Two or three sentences a busy executive understands. Says what it is and who it is for. Describes the need, not a technology or a solution. |
| Justification | Each item comes from the organisation's SWOT, and each "how" is specific to this use case. |
| Classification | The ticked purposes match the description and the benefits. |
| Business questions | Each question can be answered from data, names who asks it, and supports a concrete decision. These become group A of the BRD or PRD. |
| Data landscape | Names the systems or data sets. Agrees with the velocity and the risks. Gives enough to score data readiness. |
| Organisational changes | Says what changes, not how to change it. |
| Customer and partner impact | Specific. Mentions data agreements when partners receive data. |
| Investment | The notes give a currency and the assumptions. The bands are plausible for the scope. |
| Benefits | Each measure can be observed. The type matches the benefit. |
| Risks and dependencies | Names dependencies and who owns them. Covers legal and privacy concerns whenever personal data appears anywhere in the use case. Every unknown names who can answer. |
| Submission | Signed by real people before it goes to the panel. |
| Whole form | Short sentences and business terms. No answer pre-empts the design. |

Severity of a judgement finding:

- **Blocking**: the panel could not score it, or it could not become a BRD as written. For
  example, the description does not say what the use case is, the use case is really a
  technology project, or no business question can be answered from data.
- **Should fix**: the panel can score it, but an answer is vague, inconsistent or misses what
  the hint asks for.
- **Suggestion**: wording and plain English.

For each finding give the section, what is wrong, a short quote of the answer and the question
to put to the sponsor. Do not repeat a mechanical finding.

## 3. Read the evidence for scoring

For each criterion in `checks.json` `evidence`, say in a few words what a scorer would rely on,
or "No evidence: <ask_sponsor>". A criterion with no evidence is information for the panel, not
a fault: a use case may simply not address a threat. It is a finding only when the section
that should hold the evidence is empty or vague. Never suggest a score.

## 4. Write the report

Write `generated/define/<UC-ID>/assessment.md` from
[the report template](references/report-template.md).

- **Verdict**: Not ready if any finding is blocking; Ready with fixes if any is should fix;
  otherwise Ready for scoring.
- **Section status**: red with a blocking finding, amber with a should-fix finding, otherwise
  green.
- Answers listed under `illustrative` (worked examples) count as answered. Say so once.
- In chat, give the verdict, the counts and the path of the report.

## Must

- Never fill in, rewrite or improve an answer, and never score. Quote the sponsor's words.
- Write questions to the sponsor in plain business English. When a question suggests a value,
  use only the form's own options (for example its statuses or investment bands).
- Never change the template, the scoring model or the vocabulary to make a use case pass.
- Never change the use case's status; report a status that the record does not support.

## Maintain

- The standard lives in `templates/src/use-case.form.yaml`, `templates/scoring.yaml` and
  `registry/brd-vocabulary.yaml`. [`references/evidence-map.yaml`](references/evidence-map.yaml)
  maps each scorecard criterion to the answers that evidence it; the script reports any
  criterion that is not mapped.
- After changing any of these, or this skill, run
  `python3 .agents/skills/assess-use-case/scripts/selftest.py`. It checks the fixtures in
  [`fixtures/expected.yaml`](fixtures/expected.yaml) and a PDF round trip.
- `fixtures/expected.yaml` also lists the judgement findings an agent run must produce. Use it
  to evaluate this skill when its instructions or the model change.
