# Golden fixtures

A golden fixture is `(BRD + TDD) -> expected artefacts`. The build must reproduce them
byte for byte.

This is what enforces the reproducibility requirement in `compose-pipeline`: delete
`generated/`, re-run the chain against an unchanged BRD and TDD, and diff. Any drift is
a defect — usually a skill smuggling in nondeterminism such as a timestamp or an
unordered set.
