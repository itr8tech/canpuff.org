# CanPUFF conformance fixtures

Small, purposeful vaults that pin down what the spec means at its edges. They are the testable contract between implementations: a validator is checked against the expected verdicts; an importer or exporter is checked against the vaults themselves.

## Layout

```
fixtures/
  run-fixtures.py          runs a validator over every fixture and compares verdicts
  valid/<name>/            vaults a conforming writer could produce
  invalid/<name>/          vaults a conforming writer must never produce
    vault/                 the fixture vault itself
    expected.json          the reference validator's verdict for it
```

`expected.json` records the outcome of `tools/validate-vault.py`:

```json
{ "verdict": "PASS" | "FAIL", "errors": ["…"], "warnings": ["…"] }
```

The contract, enforced by `run-fixtures.py`: the verdict must match, the error and warning **counts** must match exactly, and each listed string must appear (substring match) in a distinct reported message of its category. The runner also re-validates one fixture as a `.canpuff.zip` to prove archive input behaves identically (Core §8).

```
python3 run-fixtures.py                 # everything, against ../tools/validate-vault.py
python3 run-fixtures.py valid/tombstones
python3 run-fixtures.py --validator path/to/your-validator.py
python3 run-fixtures.py --update        # maintainers: rewrite expected.json after an
                                        # intentional validator change; review the diff
```

## The fixtures

| Fixture | Asserts | Spec |
|---|---|---|
| `valid/empty-vault` | The minimal conforming vault: a manifest plus empty `journal/` and `catalog/` directories. | §3 |
| `valid/tombstones` | Tombstones in both tiers validate against the tombstone schema; a reference to a tombstoned id resolves (it is not dangling). | §2, §8 |
| `valid/dangling-refs` | Dangling references — supply, method, brand, shop, taxes, attachment — are warnings, never errors. | §2, §7 |
| `valid/extensions` | `ext` blocks, dotted extension journal types, unrecognized journal types, unknown `catalog/` directories, the `apps/` area, and unknown top-level directories are all tolerated. | §9, §3, §5 |
| `valid/attachments` | Content-addressed storage resolves; an unreferenced attachment is a GC candidate, not an error. | §7 |
| `invalid/missing-manifest` | No `manifest.json` — not a CanPUFF vault; readers must refuse rather than guess. | §3.1 |
| `invalid/bad-manifest` | A manifest whose `format` is not `"canpuff"` is refused. | §3.1 |
| `invalid/schema-violations` | One violation per record: missing `name`, `cost` without `currency`, missing `at`, `rating` out of range, malformed uuid. | §2, §4.1, §5.1 |
| `invalid/duplicate-id` | An id reused across tiers violates vault-wide uniqueness. | §2 |
| `invalid/misplaced` | Wrong monthly file for `at`, non-zero-padded month filename, type/directory mismatch, filename ≠ id. | §3 |
| `invalid/malformed-files` | Unparseable JSONL line; `.md` without/with unterminated frontmatter; non-mapping frontmatter; empty-string `notes`. | §6.1, §6.2 |
| `invalid/bad-attachments` | Non-hash filename stem, wrong shard directory, content/stem hash mismatch, duplicate stem. | §7 |

## Using them to test an implementation

**A validator** should reproduce every verdict. Wording may differ from `expected.json` (those strings are the reference validator's); what must agree is which vaults pass, which fail, and what each failure is about.

**An importer** must ingest every `valid/` fixture without error — including the empty vault — resolving the tombstone semantics, tolerating every dangling reference, and preserving `ext` content and `apps/` files it does not understand. For `invalid/` fixtures, refusal is always acceptable; note that several (e.g. `misplaced`) are *writer* violations that Core §3 encourages readers to repair — an importer that salvages them with a warning is conforming, one that silently mis-reads them is not.

**An exporter** must never produce anything resembling `invalid/`. Feeding an exporter's output to `tools/validate-vault.py` (0 errors) and round-tripping it through `tools/diff-vaults.py` (EQUIVALENT) is the fastest conformance check.

When two implementations are ever observed to disagree about a vault, the resolution is a new fixture here — that is this directory's reason to exist.
