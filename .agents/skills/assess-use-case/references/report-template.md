# Use-case assessment: <UC-ID> <title>

| | |
|---|---|
| Verdict | **<Ready for scoring, Ready with fixes or Not ready>** |
| Input | `<path>` |
| Assessed against | `templates/src/use-case.form.yaml`, `templates/scoring.yaml` <version>, `registry/brd-vocabulary.yaml` |
| Date | <YYYY-MM-DD> |
| Findings | <n> blocking · <n> should fix · <n> suggestions |

<One or two sentences: the main reason for the verdict and what happens next. If the input has
illustrative answers (a worked example), say once that they count as answered.>

## Findings

<Blocking findings first, then should fix, then suggestions. Keep the id (M1, M2 ...) of each
mechanical finding from checks.json; number judgement findings J1, J2 .... Quote the sponsor's
words when there are any (not for an empty answer); never rewrite them.>

| # | Severity | Section | Finding | Question for the sponsor |
|---|---|---|---|---|
| M1 | Blocking | Business questions | Row 1 gives no decision. | For row 1, which decision will the answer support? |

## Section by section

<One row per section in checks.json `sections`, in that order. Red: a blocking finding.
Amber: a should-fix finding. Green: neither.>

| Section | Status | Note |
|---|---|---|
| Control | Green | |

## Evidence for the scorecard

<One row per criterion in checks.json `evidence`, in that order. Say in a few words what a
scorer would rely on, or "No evidence: <ask_sponsor>". Never suggest a score.>

| Criterion | Axis (weight) | What a scorer would rely on |
|---|---|---|
| Supports corporate strategy | Value (5) | |

## Next step

- **Not ready** or **Ready with fixes**: send the questions above to <proposed by>, then assess
  the use case again.
- **Ready for scoring**: add it to the scorecard (`templates/define/2-scorecard.pdf`).
