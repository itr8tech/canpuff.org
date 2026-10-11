# CanPUFF Edibles Profile

**Version 1.0 — DRAFT r1 (2026-10-10)** · Companion to [CanPUFF Core v1](canpuff-v1.md)

This profile defines how a CanPUFF vault records **edibles**: cannabis products that are eaten, counted in pieces, and measured in milligrams, rather than inhaled and weighed (Core §1.2). It adds fields to existing Core objects. It adds no object types, no directories and no files.

Implementing this profile is OPTIONAL, and no application implements it yet; it is published so that one can. Its fields are ordinary unknown fields to a Core reader, which ignores them and preserves them on write-back (Core §2). To such a reader an edible dose is a consumption event with no amount, which contributes 0 grams (Core §4.1.1): nothing breaks, and nothing is counted.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

---

## 1. Scope

This revision covers products **counted in pieces**, each with a labelled amount of cannabinoid in milligrams: gummies, chocolates, hard candies, capsules, mints, baked goods.

It does not cover products dosed by volume (beverages, tinctures, oils) or applied to the skin; §7 lists what later additive revisions may add. Inhaled products of every form, including pre-rolls and infused pre-rolls, are weighed and belong to Core (Core §5.1.1).

An edible is not a mass-based supply with a different label. It is dosed by the piece, its potency is stated per piece, and it is already activated, so there is no as-sold/total split. That is why it has fields of its own instead of reusing `grams` and mg/g concentrations: no gram-based total, limit or chart can then mistake pieces for grams.

## 2. Fields

### 2.1 `supply`

| Field | Type | Meaning |
|---|---|---|
| `category` | string | `edible` marks the supply as an edible. (`category` is defined in Core §5.1.1; this profile defines the value `edible`.) |
| `format` | string | OPTIONAL free text (Core §5.1.1), e.g. "gummy", "chocolate", "hard candy", "capsule". |
| `unit` | string | OPTIONAL. `g` (default) or `each`: the measurement basis of the package. An edible SHOULD use `each`. |
| `quantity`, `quantityStart` | number | Pieces remaining and at acquisition; at most two decimal places. Used **only** with `unit: each`. |

Rules:

- With `unit: each`, `grams` and `gramsStart` MUST be absent (one source of truth), and `quantity` is authoritative on the same terms as `grams` (Core §5.1): applications MUST NOT recompute it from the event history except as an explicitly user-invoked repair. Without `unit: each`, `quantity` and `quantityStart` MUST be absent.
- `category: edible` without `unit: each` is a warning, not an error.

### 2.2 `supply.cannabinoids[].mgPerUnit`

For a `unit: each` supply, potency is stated per piece. An entry of the supply's `cannabinoids` array (Core §5.1) MAY carry `mgPerUnit`: the milligrams of that cannabinoid in one piece, 0–10000, at most four decimal places.

- The as-sold/total split does not apply: infused products are already activated. mg/g readings on a count-based supply, and `mgPerUnit` on a mass-based one, are warnings.
- Missing means unknown, not zero. An explicit zero is a reading (a CBD-free gummy records `{ "name": "CBD", "mgPerUnit": 0 }`) and MUST NOT be treated as missing.
- The package total is `mgPerUnit × quantityStart`. It is derived and never stored.

### 2.3 `consumption.serving`

For a `unit: each` supply the dose is a number of pieces, not grams. The event records it as `serving` instead of `amount`. Only the common fields and `at` are REQUIRED (Core §4.1); `method` is optional, so an edible can be logged without choosing a way of consuming it:

```json
{ "type": "consumption", "version": 1, "id": "…", "at": "2026-10-08T19:00:00-07:00",
  "supply": "…", "serving": { "unit": "each", "value": 0.5 } }
```

- `serving.value` is a number of pieces greater than 0, at most two decimal places (half and quarter pieces are normal). `serving.unit` is `each`.
- A writer MUST NOT write both `amount` and `serving` on one event. A reader that implements this profile and finds both MUST treat the event as invalid; a validator reports an error.
- Writing `serving` and omitting `amount` is deliberate: a Core reader sees an event with no `amount`, which Core §4.1.1 defines as contributing 0 grams. It neither rejects nor corrupts the event, and it MUST preserve the unknown field (Core §2).
- A `serving` against a mass-based supply, or an `amount` against a `unit: each` supply, is a warning, not an error: the event is preserved and its dose is simply not computable.

### 2.4 `method.defaultServing`

A `method` MAY carry `defaultServing` (`{ "unit": "each", "value": n }`), the typical dose it implies for count-based supplies. It is a hint for user interfaces. Core's `categories` (Core §5.1.1) can limit a method to edibles: `"categories": ["edible"]`.

## 3. Derived values (normative)

None of these is stored.

**The user's own serving.** Core §4.1.1 applies unchanged with pieces in place of grams, including its rule for an unresolved supply and its precision rule:

```
userServing = shared.gift ? (supply.sharedSupply ? serving.value : 0)
                          : serving.value / persons          # persons as in Core §4.1.1
```

**Depletion.** A writer SHOULD decrement the supply's `quantity` by `serving.value` (floored at 0) in the same logical operation, and reverse or adjust the decrement when the event is edited or deleted, exactly as Core §4.1 does for `grams`. A supply with `sharedSupply: true` SHOULD NOT be decremented by default.

**THC.** `thcMg = userServing × mgPerUnit` for the THC entry, and `thcUnits = thcMg / 5` (Core §4.1.2: 1 unit = 5 mg Δ9-THC). A missing `mgPerUnit` leaves the dose unknown; it is not zero.

## 4. Privacy

The journal rules of Core §1.1 and §11 apply unchanged: events that carry `serving` are journal-tier and private. Privacy-trimmed sharing of a catalog card (Core §11) treats `quantity` and `quantityStart` exactly as it treats `grams` and `gramsStart`: omit them unless the user opts in to sharing purchase details. `category`, `format` and `mgPerUnit` describe the product, not the person, and are shareable.

## 5. Working with Core and with other applications

- **Writers** keep edibles out of the gram fields: an edible carries no `grams`, `gramsStart` or `amount`, so no Core reader misreads it as a weighed product.
- **Edible-only applications are possible.** Core requires only the common `type`, `version` and `id`, a supply's `name` and an event's `at`. No method, variety, gram quantity or brand is required, and a vault that holds only edibles is a valid CanPUFF vault. An application infers that a vault is edible-focused from its data (supplies with `category` or `unit`, events with `serving`), never from a vault-level flag; there is none.
- **One vault, several applications.** An edibles application and an application for inhaled cannabis can read and write the same vault. Each preserves what it does not understand (Core §2): the one without this profile shows an edible supply with no gram quantity and an edible event with no amount, and writes both back untouched.
- **No manifest declaration.** The manifest does not list profiles. A reader recognizes the profile's use by its fields: a supply with `unit: each`, an event with `serving`.
- **Application-specific edible data** (onset and duration estimates, effect timelines, notes on a home infusion) belongs in `ext.<app-id>` (Core §9.1) until a revision of this profile standardizes it.

## 6. Schemas, validation and fixtures

- **Overlay schemas** are published at `https://canpuff.org/schemas/edibles/v1/{supply,consumption,method}.json`. A record validates against its Core schema **and** its overlay; an overlay constrains only the fields this profile adds, and a record that does not use them passes it untouched. Cross-field rules (§2.1, §2.3) are not expressible per record and are checked by the reference validator.
- **`tools/validate-vault.py`** applies this profile's checks wherever a record uses its fields. `--core-only` turns them off, which shows what a Core-only application would accept.
- **Fixtures** are in `fixtures/edibles/` (valid and invalid vaults, with the validator's expected verdicts). Every valid profile fixture is also a valid Core vault.

## 7. Open questions

This is a draft. Not specified in this revision; each would arrive as an additive revision:

- **Volume-dosed products** (beverages, tinctures, oils): a `unit` of `ml`, a `serving` in millilitres, and potency per millilitre or per container.
- **Profile declaration.** Whether the manifest should list the profiles a vault uses, so that a reader need not inspect records to find out.
- **Onset, peak and duration.** Edible effects arrive late and last long, and applications will want to record when. There is no common shape yet; experiment in `ext` (Core §9.1) first.
- **Low-supply threshold.** `lowThreshold` is defined in grams (Core §5.1). Its meaning on a `unit: each` supply, for example as a number of pieces, is not defined.
- **Home-made edibles.** The potency of a batch the user infused themselves (material used, yield, pieces per batch) is not modelled. Record the labelled or estimated `mgPerUnit` and explain it in `notes`.

## Revision history

- **r1 (2026-10-10).** Extracted from Core's October 8 revision (Core §4.1.3 and §5.1.1 as they then stood) when Core's scope was stated (Core §1.2). The wire format is unchanged: a vault written against that text is valid under this profile and means the same thing.
