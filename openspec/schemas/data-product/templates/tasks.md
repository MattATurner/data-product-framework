## 1. Specs

- [ ] 1.1 Update the BRD/TDD deltas and verify `openspec validate --all --strict` passes

## 2. Design

- [ ] 2.1 Update products/<product>/product.yaml and SQL bodies and verify `dpf check <product> --gate G1` passes

## 3. Build

- [ ] 3.1 Run `dpf generate <product>` and review the diff of generated/<product>/
- [ ] 3.2 Refresh golden fixtures if the change is intended (`dpf generate <product> --update-golden`) and verify `dpf generate --all --check` passes

## 4. Test

- [ ] 4.1 Run `dpf test plan <product>` and verify every changed requirement maps to a test
- [ ] 4.2 Deploy to a sandbox and record evidence with `dpf test run <product> --live`

## 5. Gates

- [ ] 5.1 Verify `dpf check <product> --gate G3` passes
- [ ] 5.2 Verify `dpf check <product> --gate G4` passes against the recorded evidence
