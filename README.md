# CanPUFF — Cannabis Personal Use File Format

**Version 1.0-rc (July 2026)** · the core format is **frozen as a release candidate**, standing on a five-lens adversarial review (83 findings applied) and a proven lossless round-trip of real data — 1,752 records, 239 photos — between two independent implementations.

CanPUFF is an open, documented file format for **personal cannabis consumption records** — the data an individual creates when they track what they consume, what they have, where they got it, and how it affected them.

It is a format for *people*, not businesses. Seed-to-sale systems, dispensary point-of-sale, and regulatory traceability all have data standards. The person doing the consuming has none: every consumer tracking app keeps its records in an undocumented internal database, and the data dies with the app. CanPUFF exists so that this data can outlive any application — including the ones its authors write.

> **Think "RSS for personal cannabis data":** plain files you own, readable in any text editor, portable between apps, with no account, no API key, and no company that can take them away.

## The documents

| Document | Status | What it defines |
|---|---|---|
| [`canpuff-v1.md`](canpuff-v1.md) | **1.0-rc** | **The core format**: the vault layout, the journal (JSONL events), the catalog (Markdown + frontmatter cards), attachments, identifiers, units, and the extension mechanism. |
| [`canpuff-sealed-v1.md`](canpuff-sealed-v1.md) | Draft | **The sealed vault profile**: end-to-end encryption (age v1), the key hierarchy (BIP39 mnemonic root), and the synchronization repository layout + protocol for dumb file servers. |
| [`mapping-pufftab-ios.md`](mapping-pufftab-ios.md) | Draft | **Lossless mapping** from the PuffTab iOS app's data model (the first implementation) to CanPUFF, field by field. |
| [`schemas/`](schemas/) | 1.0-rc | JSON Schema (2020-12) for every object type. The schemas are normative for the JSON form. |
| [`examples/`](examples/) | 1.0-rc | A complete example plain vault, plus standalone JSON objects that validate against the schemas. |
| [`fixtures/`](fixtures/) | 1.0-rc | **Conformance fixtures**: edge-heavy valid vaults and deliberately broken ones, each with the reference validator's expected verdict, plus a runner. What makes a third-party implementation testable. |
| [`tools/`](tools/) | 1.0-rc | **Reference tooling**, standalone Python: `validate-vault.py` (conformance) and `diff-vaults.py` (semantic equivalence of two vaults — round-trip verification). Both accept a vault directory or a `.canpuff.zip`. |

## Design principles

1. **File over app.** The format is the product. Applications — including PuffTab — are replaceable CRUD interfaces over it.
2. **Journal / catalog split.** *Journal* records (consumption events) are private by default and never leave the user's control unencrypted. *Catalog* records (products, shops, brands) contain nothing personal and are inherently shareable.
3. **Human-legible where a human might look.** Catalog cards are Markdown with YAML frontmatter — they open in any text editor and natively in Obsidian. The journal is JSONL — still greppable, built for machines.
4. **Machine-exact where machines interoperate.** The canonical data model is JSON, specified by JSON Schema. Interchange, QR payloads, and validation always use the JSON form.
5. **Private by architecture, not policy.** The companion sealed-vault profile makes end-to-end encryption a first-class part of the standard: anything that leaves a trusted device is ciphertext. Cannabis consumption records are health data and, in some jurisdictions, self-incriminating — the format treats that as a design input, not a disclaimer.
6. **Extensible without forking.** Unknown fields are ignored, one blessed extension mechanism exists (`ext` + `apps/`), and every object carries `type` and `version`.
7. **Boring on purpose.** UUIDs, RFC 3339 timestamps, SHA-256, JSON Schema, age encryption. No invented primitives.

## Status & governance

The core format is a **v1.0 release candidate**: frozen, with breaking changes now requiring a demonstrated interoperability failure; additive proposals target v1.1 per the versioning rules (Core §10). The sealed profile remains a draft under active development. The spec text and schemas are published under **CC0-1.0**, with an OWFa 1.0 patent non-assertion covering implementations. Two reference implementations exist and round-trip real data losslessly: the PuffTab iOS app (export/import) and the PuffTab web app (import/export); v1.0 **final** follows validation of the sealed profile.

Feedback, implementations, and proposals are welcome — the extension mechanism is the intended first stop for new needs; fields that prove themselves in `ext` are candidates for the next minor version.
