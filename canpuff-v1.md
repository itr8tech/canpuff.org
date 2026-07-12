# CanPUFF: Cannabis Personal Use File Format — Core Specification

**Version 1.0-rc (2026-07-11)** — the core format is frozen as a release candidate.
**Media type:** `application/canpuff+json` · **Format identifier:** `canpuff`
**License:** spec text and schemas CC0-1.0; OWFa 1.0 patent non-assert.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

---

## 1. Overview

CanPUFF defines:

1. A **data model** for personal cannabis consumption records, expressed canonically as JSON objects and normatively described by the JSON Schemas that accompany this document.
2. A **vault**: a directory layout that stores those records as plain files (the *plain vault*). A companion profile, [CanPUFF Sealed](canpuff-sealed-v1.md), defines the encrypted form of the same logical vault for synchronization and off-device storage.

A conforming **reader** consumes CanPUFF data; a conforming **writer** produces it. An application is typically both.

### 1.1 The journal / catalog split

Every record belongs to exactly one of two tiers, and the tier determines its privacy posture and file representation:

| Tier | Contains | Representation | Privacy posture |
|---|---|---|---|
| **Journal** | Events: what was consumed, when, how much, by/with whom, to what effect | JSON Lines (`.jsonl`), append-oriented | **Private.** MUST NOT leave a trusted device unencrypted (see Sealed profile). |
| **Catalog** | Documents: supplies (stash items), shops, chains, brands, producers, methods, tax rates, terpene notes | One Markdown file with YAML frontmatter per record (`.md`) | **Shareable.** Contains no information about the user's behavior. Plaintext by default. |

Sharing features (QR cards, exports to friends, any future federation) MUST only ever transmit catalog records and their referenced attachments — never journal records. An object of a type the reader does not recognize MUST be treated as journal-tier for all privacy rules unless it was read from a vault's `catalog/` directory; sharing features MUST NOT transmit objects of unrecognized type.

## 2. Common requirements for all objects

Every CanPUFF object, in any tier, MUST carry:

| Field | Type | Notes |
|---|---|---|
| `type` | string | One of the type identifiers in this spec (§4, §5), or an extension type (§9). |
| `version` | integer | The schema version of that object type. This spec defines version `1` of every type. |
| `id` | string | UUID, lowercase, hyphenated (RFC 4122 textual form). Assigned at creation, never reused, never changed. **ids MUST be unique across all objects in a vault, regardless of type or tier.** |

Additionally:

- **Timestamps** MUST be RFC 3339 strings with a UTC offset (e.g. `2026-07-09T16:20:00-07:00`). A numeric offset (`±HH:MM`) or `Z` is acceptable; `Z` and `-00:00` indicate that local offset was unknown or not recorded. Writers SHOULD prefer the numeric local offset — time-of-day is analytically meaningful for consumption data. Date-only values use `YYYY-MM-DD`.
- **Quantities of cannabis** are decimal numbers of **grams** with at most 4 decimal places. Potencies (`thc`, `cbd`, terpene percentages) are percentages by weight, `0`–`100`, at most 2 decimal places.
- **Money** is a decimal number with at most 2 decimal places; an object carrying `cost` MUST also carry `currency` (ISO 4217 code). The schemas enforce the pairing.
- Writers MUST emit numbers within the stated precision; readers SHOULD parse monetary and gram values into decimal (not binary-float) types where the platform allows. Precision limits are writer requirements; the schemas intentionally do not assert them (IEEE-754 `multipleOf` is unreliable).
- `created` and `updated` (RFC 3339) are OPTIONAL on every object; writers that edit records SHOULD maintain `updated`.
- **Unknown fields:** readers MUST ignore fields they do not recognize. Writers that modify a record they did not fully author MUST preserve `ext` content (§9.1) and SHOULD preserve other unrecognized fields on write-back.
- **References** between objects are by `id`. Readers MUST tolerate dangling references (the referenced record may not have synced yet or may have been deleted) and treat them as "unknown," not as errors.
- **Tombstones:** a deleted object MAY be represented by a tombstone — the object reduced to exactly `{ "type", "version", "id", "deleted": true, "updated" }` (with `updated` set to the deletion time). Readers MUST treat a record carrying `deleted: true` as a deletion marker for that id, regardless of type. Tombstones participate in import merging (§8) and validate against `schemas/v1/tombstone.json` rather than their type's schema. Writers SHOULD retain tombstones (they are what prevents deleted records from resurrecting on import of older exports).

## 3. The plain vault

A plain vault is a directory (or a ZIP archive of one — see §8):

```
<vault>/
  manifest.json                    REQUIRED  vault identity & format version
  journal/
    <YYYY>/<MM>.jsonl              journal events, one JSON object per line
  catalog/
    supplies/<id>.md
    shops/<id>.md
    chains/<id>.md
    brands/<id>.md
    producers/<id>.md
    methods/<id>.md
    tax-rates/<id>.md
    terpenes/<id>.md
  attachments/
    <hh>/<sha256>.<ext>            content-addressed binary files (§7)
  apps/
    <app-id>/...                   application-private data (§9.2)
```

- `manifest.json`, `journal/`, and `catalog/` are REQUIRED (they may be empty). `attachments/` and `apps/` are OPTIONAL.
- `<YYYY>` is four digits; `<MM>` is two digits, zero-padded (`01`–`12`).
- **Journal placement:** events are placed in the monthly file matching the calendar date of `at` **as expressed in the UTC offset recorded inside `at` itself** (i.e., the first ten characters of the RFC 3339 string). Placement does not depend on any device's timezone. Within a file, lines SHOULD be ordered by `at` ascending.
- **Journal id uniqueness:** an event id MUST appear in at most one journal file across the whole vault; within a file, at most once — the line present is the current state of that event (edits replace the line). A writer changing an event's `at` across a month boundary MUST write the line to the new monthly file and remove it from the old in the same operation. A reader that nevertheless encounters the same id in multiple files MUST keep the copy with the newest `updated` (falling back to the copy whose file matches its `at`'s date, then to the later file in path order), SHOULD warn, and SHOULD repair the vault on next write.
- **Catalog placement:** filenames MUST be the record's `id` plus `.md`, in the directory given by the normative table in §5. The record's `type` field is authoritative; the directory is a storage convention. Writers MUST place each record in its type's directory; a reader encountering a mismatch MUST honor the `type` field, SHOULD warn, and SHOULD move the file on next write. A reader encountering the same id in more than one catalog file MUST NOT silently discard either record; it SHOULD prefer the record whose directory matches its `type`, then the newest `updated`, and SHOULD report the vault as needing repair.
- Readers MUST NOT rely on any file or directory not defined here, but MUST tolerate the presence of unknown files and directories.

### 3.1 `manifest.json`

```json
{
  "format": "canpuff",
  "specVersion": 1,
  "vaultId": "1de2c1a7-4d3e-4a2b-9e6f-8b7a5c4d3e2f",
  "created": "2026-07-10T09:00:00-07:00",
  "generator": { "name": "PuffTab iOS", "version": "2.4.0" }
}
```

`format` MUST be `"canpuff"`. `specVersion` MUST be `1` for vaults conforming to this document. `vaultId` is a UUID identifying the vault (not the device, not the user). `generator` is informational.

A directory without a well-formed `manifest.json` whose `format` is `"canpuff"` is not a CanPUFF vault; readers MUST refuse it rather than guess. Readers encountering a `specVersion` greater than they support SHOULD attempt to read anyway (the unknown-field rule makes minor revisions forward-compatible) and MUST warn rather than silently drop data.

## 4. The journal

### 4.1 `consumption` — the core event

One consumption event. All fields except the common trio and `at` are OPTIONAL; when `amount` is present, `grams` is REQUIRED within it.

```json
{
  "type": "consumption",
  "version": 1,
  "id": "7c9e6679-7425-40de-944b-e07fc1f90ae7",
  "at": "2026-07-09T16:20:00-07:00",
  "supply": "9f3c1a2e-7b41-4c8e-9d2a-51f08c77b3aa",
  "method": "b6b8f3a1-2c4d-4e5f-8a9b-0c1d2e3f4a5b",
  "amount": { "grams": 0.35 },
  "shared": { "people": 2, "gift": false },
  "effects": { "rating": 7, "sideEffects": "dry mouth" },
  "context": {
    "purpose": "wind down",
    "location": { "name": "back porch", "lat": 49.2827, "lon": -123.1207 }
  },
  "photo": "sha256:ab3f5c9e…",
  "notes": "Paired with a movie."
}
```

| Field | Type | Meaning |
|---|---|---|
| `at` | timestamp | REQUIRED. When consumption occurred. |
| `supply` | uuid | The supply consumed. |
| `method` | uuid | The consumption method. |
| `amount.grams` | grams | Total product consumed in this event, by everyone who partook. |
| `shared.people` | integer ≥ 0 | Number of people who partook **besides** the user. Default 0. |
| `shared.gift` | boolean | The user did not partake: for the user's own supply, the amount was given entirely away; for a shared supply (§5.1 `sharedSupply`), the amount was received/consumed entirely by the user. Default false. |
| `effects.rating` | integer 1–10 | Subjective effectiveness. |
| `effects.sideEffects` | string | Free text. |
| `context.purpose` | string | Free text (e.g. "sleep", "pain", "social"). |
| `context.location` | object | `name` (string), `lat`/`lon` (WGS-84 decimal degrees), all optional. |
| `photo` | hash-ref | Attachment reference (§7). |
| `notes` | string | Free text. |

**Writer behavior — stash depletion:** a writer that creates a consumption event referencing a supply it manages SHOULD decrement that supply's `grams` by `amount.grams` (floored at 0) in the same logical operation, update the supply's `updated`, and SHOULD reverse/adjust the decrement when the event is edited or deleted. Supplies with `sharedSupply: true` are application-managed (the stash is not the user's) and SHOULD NOT be decremented by default. `supply.grams` remains authoritative thereafter (§5.1); applications MUST NOT recompute it from the journal except as an explicitly user-invoked repair.

#### 4.1.1 Consumption math (normative)

"How much did *the user* consume" MUST compute identically in every implementation:

```
persons = 1 + (shared.people ?? 0)

if shared.gift:
    userGrams = supply.sharedSupply ? amount.grams : 0
else:
    userGrams = amount.grams / persons
```

If the event has no `supply` field, or the referenced supply cannot be resolved, `sharedSupply` is treated as `false` for this computation. If `amount` is absent, the event records that consumption occurred but contributes 0 grams to both user-consumption and stash-depletion math.

Implementations MAY compute in IEEE-754 binary floating point or in decimal arithmetic; "identically" is defined at spec precision — two implementations' results MUST agree when rounded half-even to 4 decimal places of grams.

Rationale: for the user's own supply, a gifted amount left their stash but not through their lungs; for a friend's supply marked `sharedSupply`, a "gift" flows the other way. Stash depletion, by contrast, is always `amount.grams` against the referenced supply.

#### 4.1.2 Standard THC units (derived)

Implementations SHOULD be able to display dose in NIH standard THC units (1 unit = 5 mg Δ9-THC):

```
thcUnits = userGrams × (supply.thc / 100) × 1000 / 5
```

This value is derived and MUST NOT be stored as an authoritative field.

### 4.2 Other journal event types

This version defines only `consumption`. Applications needing additional event kinds (e.g. stash adjustments, tolerance-break markers) MUST use extension types (§9.1) until they are standardized.

## 5. The catalog

Catalog records are documents. In the vault they are stored as **Markdown files with YAML frontmatter** (§6); their canonical JSON form is what the schemas validate and what interchange uses. The mapping between the two is normative and lossless (§6.2).

**Type ⟷ directory (normative, closed set for v1):**

| `type` | Vault directory |
|---|---|
| `supply` | `catalog/supplies/` |
| `shop` | `catalog/shops/` |
| `chain` | `catalog/chains/` |
| `brand` | `catalog/brands/` |
| `producer` | `catalog/producers/` |
| `method` | `catalog/methods/` |
| `tax-rate` | `catalog/tax-rates/` |
| `terpene` | `catalog/terpenes/` |

This set is closed for spec v1: extension catalog record types are not permitted under `catalog/` — applications needing new document kinds MUST use `apps/<app-id>/` (§9.2) until the type is standardized. Readers MUST tolerate (and preserve) unknown directories under `catalog/` without interpreting them.

### 5.1 `supply` — a stash item

A purchased (or received) package of product.

| Field | Type | Meaning |
|---|---|---|
| `name` | string | REQUIRED. Product/strain name. |
| `shortName` | string | Nickname for quick entry / voice. |
| `variety` | string | One of `indica`, `sativa`, `hybrid`. |
| `thc`, `cbd` | percent | Current potency (user-editable). |
| `originalThc`, `originalCbd` | percent | As stated on the package at purchase. |
| `terpenes` | array | `[{ "name": "Myrcene", "percentage": 0.8 }, …]`. Names SHOULD use conventional terpene names; `totalTerpenes` (percent) MAY state the package total. |
| `grams` | grams | Current remaining amount. **Authoritative** (users adjust for spillage/drift). Writers apply consumption per §4.1; applications MUST NOT recompute this field from the event history except as an explicitly user-invoked repair. |
| `gramsStart` | grams | Package size at acquisition. |
| `cost` | money | Pre-tax cost. `currency`: ISO 4217 (REQUIRED when `cost` present). |
| `taxes` | array of uuid | References to `tax-rate` records applied to this purchase. |
| `purchased`, `packaged` | date/timestamp | Acquisition and packaging dates. |
| `expiry` | date/timestamp | Optional. |
| `shop`, `brand` | uuid | References. |
| `rating` | integer 0–5 | 0 = unrated. |
| `photo` | hash-ref | |
| `lowThreshold` | grams | Low-supply warning level. |
| `finished` | boolean | No longer in the stash. `finishedAt`: timestamp. |
| `favorite` | boolean | |
| `sharedSupply` | boolean | This is someone else's stash the user partakes from. Inverts gift math (§4.1.1). Default false. |
| `notes` | string | In the Markdown form, this is the document body. |

Derived values (`costPerGram = cost / gramsStart`, cost with taxes, freshness) MUST NOT be stored; the formulas above and the referenced `tax-rate` records make them reproducible.

### 5.2 `shop`, `chain`

`shop`: `name` (REQUIRED), `city`, `address`, `lat`/`lon`, `phone`, `email`, `website`, `orderingUrl`, `delivery` (boolean), `chain` (uuid ref), `customerId` (loyalty identifier; if absent, applications SHOULD fall back to the chain's), `rating` 0–5, `photo`, `notes` (body).

`chain`: `name` (REQUIRED), `website`, `customerId`, `logo` (hash-ref), `notes` (body).

### 5.3 `brand`, `producer`

`brand`: `name` (REQUIRED), `producer` (uuid ref), `rating` 0–5, `photo`, `notes` (body).

`producer`: `name` (REQUIRED), `legalName`, `licenseNumber`, `website`, `headquarters`, `yearFounded` (integer), `active` (boolean, default true), `rating` 0–5, `photo`, `notes` (body).

### 5.4 `method`

A way of consuming. `name` (REQUIRED), `shortName`, `aliases` (array of strings — e.g. `["j", "jay", "doobie"]`), `defaultGrams` (grams — the typical dose this method implies), `notes` (body).

### 5.5 `tax-rate`

A named tax applicable to purchases. `name` (REQUIRED, e.g. "GST"), `rate` (percent — `5` means 5%; REQUIRED), `default` (boolean — applied to new purchases by default), `notes` (body).

Tax math (normative): a supply's combined tax rate is the sum of the `rate` values of its resolvable referenced tax-rate records (dangling references contribute 0); `taxAmount = cost × combinedRate / 100`; `costWithTax = cost + taxAmount`.

### 5.6 `terpene`

An OPTIONAL dictionary entry describing a terpene: `name` (REQUIRED), `aroma`, `commonEffects`, `boilingPointC` (number), `notes` (body). Supplies embed terpene names and percentages directly (§5.1) and do not reference these records; `terpene` records exist so applications can ship or share reference notes.

## 6. File representations

### 6.1 Journal files: JSON Lines

Each line of a `journal/<YYYY>/<MM>.jsonl` file is one complete JSON object (UTF-8, no BOM, `\n` line endings, no trailing commas — standard JSONL). Blank lines MUST be ignored.

A line that is not a syntactically valid JSON object, or that carries a recognized `type` but fails validation, MUST NOT cause the reader to reject the rest of the file. Readers MUST skip such lines for processing and SHOULD surface a warning; writers rewriting a journal file MUST preserve byte-for-byte, in place, any lines they could not parse or validate.

### 6.2 Catalog files: Markdown + YAML frontmatter

A catalog file is:

```
---
<YAML frontmatter>
---

<body>
```

**File rules:** catalog files are UTF-8 without BOM, `\n` line endings (readers SHOULD tolerate `\r\n`). The file MUST begin with a line consisting of exactly `---`; frontmatter ends at the next such line; everything after it is the body. Writers SHOULD emit one blank line between the closing delimiter and the body.

The mapping to the canonical JSON object is normative and bidirectional:

- **Frontmatter ⟷ every JSON field except `notes`.**
- **Body ⟷ `notes`.** The canonical value of `notes` never has leading or trailing whitespace: writers MUST trim before storing it in either form, and two values differing only in leading/trailing whitespace are the same value. An empty body maps to `notes` **absent**; writers MUST NOT emit `notes` as an empty string. Under these equivalences, round-tripping in either direction MUST preserve all data.

**Frontmatter profile** (a deliberate subset of YAML to avoid parser divergence):

- Parsed per YAML 1.2 **core schema**.
- Writers MUST quote any string scalar that a YAML parser could read as something else (`no`, `on`, `1.0`, dates — the "Norway problem" set), and MUST write timestamps and dates as **quoted strings** in the RFC 3339 / `YYYY-MM-DD` forms.
- Allowed value shapes: scalars, arrays of scalars, arrays of flat objects (needed for `terpenes`), **and the `ext` object, whose per-app values are flat objects of scalars and arrays of scalars**. No other nesting, no anchors/aliases, no multi-line block scalars, no custom tags. (An application whose `ext` data cannot fit these shapes stores it under `apps/<app-id>/` instead.)
- Keys are the JSON field names verbatim (camelCase).

Example — `catalog/supplies/9f3c1a2e-7b41-4c8e-9d2a-51f08c77b3aa.md`:

```markdown
---
type: supply
version: 1
id: 9f3c1a2e-7b41-4c8e-9d2a-51f08c77b3aa
name: Pink Kush
variety: indica
brand: 4d6f8a2b-1c3e-4f5a-9b8c-7d6e5f4a3b2c
thc: 22.5
cbd: 0.1
terpenes:
  - { name: Myrcene, percentage: 0.8 }
  - { name: Caryophyllene, percentage: 0.4 }
grams: 2.1
gramsStart: 3.5
cost: 29.99
currency: CAD
purchased: "2026-07-02T18:05:00-07:00"
rating: 4
photo: "sha256:ab3f5c9e2d1f4e6a8b0c2d4e6f8a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a"
---

Dense buds, gassy. Better in the bong than rolled.
Second time buying — first batch was drier.
```

### 6.3 The JSON form

Any CanPUFF object serialized standalone as JSON (interchange, QR payloads, APIs) uses media type `application/canpuff+json`. A file containing one JSON object per catalog record is an acceptable alternative *interchange* form; **inside a vault**, catalog records MUST be `.md`.

## 7. Attachments

Binary files (photos, and in future perhaps lab-result PDFs) are stored **content-addressed**:

- Path: `attachments/<hh>/<sha256>.<ext>` where `<sha256>` is the lowercase hex SHA-256 of the file's bytes, `<hh>` its first two hex characters, and `<ext>` a conventional extension (`jpg`, `png`, `webp`, `pdf`).
- Objects reference attachments as `"sha256:<hex>"` strings. The hex in references MUST be lowercase; readers MAY accept uppercase on input by folding case. Comparison is case-insensitive after folding.
- **Resolution:** a reference resolves to the file under `attachments/<hh>/` whose basename (before the extension) equals the hash — the hash alone identifies the content; the extension is advisory. A vault MUST NOT contain two files with the same `<sha256>` stem. Readers SHOULD verify the SHA-256 of attachment bytes on first read and treat a mismatch as a damaged attachment (i.e., a dangling reference).
- Attachments are **immutable**: a modified image is a new attachment with a new hash. On import, if a hash already exists locally under any extension, the local file is kept and the incoming copy is ignored (identical hash = identical content).
- **Garbage collection:** for GC purposes, a reference is any string matching `sha256:[0-9a-f]{64}` appearing anywhere in any object in the vault — including `ext` content, unrecognized fields, and journal lines of unrecognized type. Writers MUST use this definition when deciding an attachment is unreferenced; readers MUST tolerate both dangling references and unreferenced files.
- Writers SHOULD strip EXIF metadata (recompression does this incidentally) unless the user opts to keep originals — photo EXIF frequently embeds GPS coordinates, which is journal-grade information inside a potentially catalog-referenced file.
- Photos referenced by **journal** events are journal-tier data (§1.1) regardless of storage location; photos referenced only by catalog records are catalog-tier.

## 8. Vault interchange (export/import)

A vault exported as a single file is a **ZIP archive** of the plain-vault directory (STORE or DEFLATE; Zip64 permitted; the manifest MUST be present). Conventional filename: `<name>.canpuff.zip`. Archive entries MUST be rooted at the vault directory itself (`manifest.json` a top-level entry); importers SHOULD additionally accept an archive whose sole top-level entry is a directory containing the vault.

**Share exports:** a partial export (e.g. sharing one supply card) MUST NOT reuse the source vault's `vaultId` — writers MUST mint a fresh random `vaultId` per share export, so shares cannot be correlated to each other or to the source vault.

Import semantics are **merge by `id`**:

1. If incoming and local records are identical under RFC 8785 canonical JSON, the import of that record is a no-op (no user interaction).
2. Both have `updated`: strictly newer wins. On exact equality with differing content, the local record wins and applications SHOULD surface a conflict.
3. Local has `updated`, incoming lacks it: local wins.
4. Incoming has `updated`, local lacks it: incoming wins.
5. Neither has `updated`: local wins unless the user explicitly chooses the incoming record.
6. An incoming record whose `id` is unknown locally is created. A tombstone (§2) is a record like any other under rules 1–5: a tombstone that wins deletes the local record; a losing tombstone is discarded.
7. Attachments merge by hash (§7). Import MUST NOT require the presence of any particular record type (an empty vault plus one supply card is a valid import).
8. Exception: `terpene` dictionary records MAY additionally be deduplicated by case-insensitive `name` when ids differ, since applications seed their own dictionaries (§5.6).

**Resurrection caveat:** absent tombstones, import cannot distinguish a record that is new to the local vault from one the user previously deleted — importing an older export may resurrect deleted records. Applications SHOULD retain tombstones (§2) and SHOULD warn or offer per-record review when importing an export older than local state.

## 9. Extensions

### 9.1 The `ext` field

Any object MAY carry an `ext` object whose keys are **application identifiers** (lowercase, `[a-z0-9-]+`, e.g. `pufftab`) and whose values are objects owned entirely by that application:

```json
"ext": { "pufftab": { "sortOrder": 3, "icon": "flame.fill" } }
```

Rules: applications MUST NOT write keys they do not own; writers MUST preserve `ext` content on round-trip (§2); no reader is required to understand any `ext` content. In catalog frontmatter, `ext` values are limited to the shapes in §6.2. Fields that prove broadly useful in `ext` are candidates for standardization in later versions.

Extension **journal event types** use the same identifiers, dotted: `"type": "<app-id>.<name>"` with `<name>` matching `[a-z0-9-]+` (e.g. `"pufftab.limit-changed"`). Extension journal events MUST carry a conforming `at` (it determines monthly-file placement). Readers MUST ignore — but writers rewriting the file MUST preserve — journal lines whose type they do not recognize.

### 9.2 The `apps/` area

Whole-file application data (settings, caches, app-specific histories) lives under `apps/<app-id>/` in whatever format the application chooses. Other applications MUST NOT interpret it but MUST carry it through export/import intact. On import, for each `apps/<app-id>/` path present on both sides: the importing application, if it owns `<app-id>`, applies its own merge; otherwise the local file is kept and the incoming file is discarded (or preserved under a conflict name). Paths present only in the import are copied. Data in `apps/` is journal-tier for the purposes of the Sealed profile (encrypted off-device) unless the owning app documents otherwise.

## 10. Versioning of this specification

- **Minor revisions** (1.1, 1.2 …) may add fields and object types. They MUST NOT change the meaning of existing fields. The `specVersion` in the manifest stays `1`; object `version` values stay `1` unless an object type itself is revised.
- An object type revision (`"version": 2` on that object) is a breaking change to that type alone and will be accompanied by mapping notes.
- Anything not expressible without breaking these rules waits for CanPUFF 2 — which the authors intend never to need.

## 11. Security & privacy considerations

- Journal records are health data (GDPR Art. 9 special category and equivalents) and, in some jurisdictions, records of unlawful conduct. Conforming applications MUST NOT transmit journal-tier data off-device without either (a) the Sealed profile's encryption, or (b) explicit, informed, per-action user consent (e.g. the user personally attaching an export to an email).
- The Sealed profile is OPTIONAL to implement but normative when implemented: an application that syncs or backs up vaults to any remote MUST use it.
- Catalog records are designed to be personally inert, but their *existence and cadence* still say something. Applications SHOULD surface this in sharing UI ("this card shows what the product is, never what you did with it").
- QR supply-card payloads (catalog `supply` JSON) SHOULD omit `taxes`, `grams`, `gramsStart`, `cost`, and `shop`-linked loyalty data unless the user opts in — a friend needs the product, not your purchasing profile. (A dedicated QR profile may formalize this in a minor revision.)

## 12. Media types & identifiers (registration intent)

- `application/canpuff+json` — a single CanPUFF object or an array of them.
- `.canpuff.zip` — a zipped plain vault (§8).
- Schema URLs: `https://canpuff.org/schemas/v1/<type>.json` (canpuff.org is the spec's canonical home).
- JSON-LD: a future informative `@context` document will map CanPUFF field names to IRIs to permit ActivityStreams-style projections; nothing in this spec requires JSON-LD processing.
