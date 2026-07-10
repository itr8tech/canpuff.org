# Mapping: PuffTab iOS ⟷ CanPUFF v1

**DRAFT (2026-07-10).** This document defines the lossless, bidirectional mapping between the PuffTab iOS app's persisted SwiftData model (13 entities) and CanPUFF v1. It is the conformance contract for the first reference implementation: *export from iOS, import anywhere, re-import to iOS — zero data loss.*

Conventions used below:

- **→ core** — maps to a standard CanPUFF field.
- **→ ext** — preserved under `ext.pufftab` on the same object (app-specific, not standardized).
- **→ apps/** — preserved under `apps/pufftab/` in the vault (whole-file app data).
- **derived** — not exported; recomputed from other fields (spec forbids storing it).
- UUIDs are lowercased on export; Swift `Decimal` serializes as JSON numbers within spec precision; Swift `Date` serializes as RFC 3339 **with the device's current or recorded local offset** (see Notes N1).

## 1. Puff → journal `consumption`

| iOS field | CanPUFF |
|---|---|
| `id` | `id` |
| `timestamp` | `at` |
| `grams` | `amount.grams` |
| `supply?.id` | `supply` |
| `method?.id` | `method` |
| `notes` | `notes` (empty string → omit) |
| `photo` | attachment (content-addressed; see §14) → `photo` |
| `purpose` | `context.purpose` |
| `effectiveness` (1–10, default 5) | `effects.rating` |
| `sideEffects` | `effects.sideEffects` |
| `location` (string) | `context.location.name` |
| `latitude` / `longitude` | `context.location.lat` / `.lon` — **previously not exported; MUST be exported now** |
| `isShared` | implied: `shared.people > 0` (see N2) |
| `sharedWithCount` | `shared.people` |
| `isGift` | `shared.gift` |
| `sortOrder` | `ext.pufftab.sortOrder` — **previously not exported** |
| `createdAt` / `updatedAt` | `created` / `updated` |

## 2. Supply → catalog `supply`

| iOS field | CanPUFF |
|---|---|
| `id` | `id` |
| `name` | `name` |
| `shortName` | `shortName` (empty → omit) |
| `varietyRaw` ("Hybrid"/"Indica"/"Sativa") | `variety` lowercased (`hybrid`/`indica`/`sativa`). If the stored string (lowercased) is not one of the three, omit `variety` and preserve the raw string as `ext.pufftab.varietyRaw`; importers restore it verbatim |
| `thc`, `cbd` | `thc`, `cbd` |
| `originalTHC`, `originalCBD` | `originalThc`, `originalCbd` |
| `totalTerpenes` | `totalTerpenes` |
| `terpenes` (SupplyTerpene rows) | `terpenes[]` — see §11 |
| `grams` | `grams` |
| `gramsstart` | `gramsStart` |
| `cost` | `cost` |
| `costpergram` | derived (`cost / gramsStart`) — not exported (N3) |
| `currencyCode` | `currency` — if the stored code is empty, `cost` and `currency` are both omitted and the amount is preserved as `ext.pufftab.costNoCurrency` (Core §2 pairing; never fabricate a currency) |
| `taxRates` (SupplyTaxRate rows) | `taxes[]` (array of tax-rate ids) — see §12 |
| `purchasedon` / `packagedon` | `purchased` / `packaged` — MUST be exported in full RFC 3339 timestamp form (the stored instant), never date-only: the app keys supply dedupe on the instant |
| `expiryDate` | `expiry` — full RFC 3339 timestamp form, as above |
| `shop?.id` / `brand?.id` | `shop` / `brand` |
| `rating` (0–5) | `rating` |
| `photo` | attachment → `photo` |
| `notes` | `notes` = Markdown body |
| `lowSupplyThreshold` | `lowThreshold` |
| `isFinished` / `finishedAt` | `finished` / `finishedAt` |
| `isFavorite` | `favorite` |
| `lastUsed` | `ext.pufftab.lastUsed` (RFC 3339, omit when nil) — **independently persisted state**, not derivable: the app sets it on finish actions, backdated puffs, and watch logging. Importers set it verbatim, falling back to max(`at`) of referencing consumption events only when the ext value is absent |
| `sortOrder` | `ext.pufftab.sortOrder` — **previously not exported** |
| `isSharedSupply` | `sharedSupply` — **previously not exported; MUST be (it changes consumption math)** |
| `createdAt` / `updatedAt` | `created` / `updated` |

## 3. Method → catalog `method`

| iOS field | CanPUFF |
|---|---|
| `id`, `name`, `notes` | `id`, `name`, `notes` (body) |
| `grams` (default dose) | `defaultGrams` |
| `shortName` | `shortName` |
| `aliases` (comma-separated string) | `aliases` (array — split on `,`, trim, drop empties; join on export back). Whitespace-around-comma and empty items are normalized away; this normalization is canonical and intentional |
| `icon` (SF Symbol name) | `ext.pufftab.icon` (Apple-specific vocabulary) |
| `isQuickAccess` | `ext.pufftab.quickAccess` |
| `sortOrder` | `ext.pufftab.sortOrder` |
| `createdAt`/`updatedAt` | `created`/`updated` |

## 4. Brand → catalog `brand`

`id`, `name`, `rating`, `photo`→attachment, `notes`→body, `producer?.id`→`producer`, `sortOrder`→ext, timestamps→`created`/`updated`.

## 5. Producer → catalog `producer`

| iOS | CanPUFF |
|---|---|
| `legalName` | `legalName` (falls back to `name` in iOS init; export verbatim) |
| `licenseNumber` | `licenseNumber` |
| `website`, `headquarters` | same |
| `yearFounded` (0 = unset) | `yearFounded` (omit when 0) |
| `isActive` | `active` |
| rest | as Brand pattern (`rating`, `photo`, `notes`→body, `sortOrder`→ext, timestamps) |

## 6. Shop → catalog `shop`

| iOS | CanPUFF |
|---|---|
| `name`, `rating`, `photo`, `notes`→body | same pattern |
| `city` / `address` | `city` / `address` |
| `location` (DEPRECATED) | if non-empty and `city` empty: migrate into `city`; else `ext.pufftab.legacyLocation` |
| `businessAddress` (DEPRECATED) | if non-empty and `address` empty: migrate into `address`; else `ext.pufftab.legacyBusinessAddress` |
| `latitude`/`longitude` | `lat`/`lon` |
| `phone`, `email`, `website` | same |
| `onlineOrderingUrl` | `orderingUrl` |
| `offersDelivery` | `delivery` |
| `chain?.id` | `chain` |
| `customerId` | `customerId` (note: iOS `effectiveCustomerId` fallback-to-chain is *derived*; CanPUFF specifies the same fallback in Core §5.2) |
| `sortOrder` | `ext.pufftab.sortOrder` |

**Delete-rule warning (implementation, not format):** iOS cascades Shop deletion to its Supplies. CanPUFF has no delete cascades — deletion semantics live in the app; the sealed profile records only per-object tombstones. The iOS importer MUST NOT re-apply its cascade when materializing a vault (a vault may legitimately contain supplies whose shop was deleted → dangling ref, which readers must tolerate).

**Importer requirement (events):** the iOS importer MUST materialize consumption events whose `supply` or `method` is absent or unresolvable — `Puff.supply`/`Puff.method` are optional stored properties; only the convenience init requires them. Silently skipping such events (current `DataTransferView` behavior, ≈ lines 2130–2138) is non-conforming.

## 7. ShopChain → catalog `chain`

`id`, `name`, `website`, `customerId`, `logo`→attachment (`logo` field), `notes`→body, `sortOrder`→ext, timestamps.

## 8. Terpene (dictionary) → catalog `terpene`

`id`, `name`, `commonEffects`→`commonEffects`, `aroma`, `boilingPoint`→`boilingPointC`, `displayOrder`→`ext.pufftab.displayOrder`. (No timestamps on the iOS entity.) These are seeded reference rows; exporters SHOULD export only rows the user edited or that are referenced, and importers merge by `name` case-insensitively when ids differ (N4). The reference exporter implements the referenced-rows half only (reliably detecting "edited" seeded rows is impractical).

## 9. TaxRate → catalog `tax-rate`

`id`, `name`, `rate`, `isDefault`→`default`, `sortOrder`→ext, `createdAt`/`updatedAt`→`created`/`updated`. The records themselves have always been in the legacy export (`TaxRateExport`); only the two timestamps were absent and are carried going forward.

## 10. UserPreferences → `apps/pufftab/settings.json`

The singleton (id `…0001`) is app configuration, not consumption data — it moves wholesale to `apps/pufftab/settings.json` (journal-tier under the Sealed profile). All fields export, including the previously-unexported `puffTrackingEnabled`, `accentColorName`, `trackPuffLocation`. Three transforms:

- `greenHoursScheduleData` (base64 blob of JSON-encoded `[Int: DaySchedule]`) MUST be **flattened to real JSON** — and emitted **only when the stored blob is non-nil** (flatten the stored blob, not the computed property: nil-ness is behavior-bearing — when nil the app derives the weekly schedule from the single start/end times). Importers MUST leave `greenHoursScheduleData` nil when the key is absent. Shape: `{"greenHoursSchedule": {"1": {"enabled": true, "start": "16:20", "end": "21:30"}, …}}` with weekday keys 1=Sunday…7=Saturday and `HH:MM` local times.
- `greenHoursStart`/`greenHoursEnd` (Dates where only time-of-day is meaningful) export as `"HH:MM"` strings.
- `taxRate` (legacy single rate) exports as `legacyTaxRate` for fidelity; the TaxRate records are authoritative.

## 11. SupplyTerpene (junction) → embedded `terpenes[]`

Each row becomes `{ "name": <terpene.name>, "percentage": <percentage> }` embedded in the supply. The junction row's own `id` and the `terpeneId` are dropped (recreatable; the dictionary merge key is `name` — N4). If strict junction-id round-trip is ever needed, `ext.pufftab.terpeneLinks` may carry `[{id, terpeneId}]`; the reference exporter does not.

Junction rows whose `terpene` reference is nil or unresolvable (CloudKit partial sync, deleted dictionary row) cannot produce the required `{name, percentage}` embed: preserve their percentages as `ext.pufftab.orphanedTerpenes: [1.25, …]` — an **array of scalars**, since the Core §6.2 ext profile forbids nested objects; exporters MUST NOT fail on them.

> **Known iOS bug (must fix before conformance):** the "Compressed" export path hard-codes `"supplyTerpenes": []` (`DataTransferView.swift` ≈ line 1203), silently dropping all terpene links.

## 12. SupplyTaxRate (junction) → `taxes[]`

Each row contributes its `taxRate.id` to the supply's `taxes` array. Junction `id` dropped (no payload, fully recreatable). Rows whose `taxRate` reference is nil or unresolvable are skipped with a warning (a tax link with no rate carries no information); exporters MUST NOT fail on them.

## 13. DailyLimitHistory → `apps/pufftab/daily-limit-history.jsonl`

Immutable per-day rows (`date` startOfDay, `limitGrams`, `consumedGrams`, `puffCount`, `isLimitEnabled`, timestamps) are PuffTab's materialized feature history — `consumedGrams`/`puffCount` are derivable from consumption events, but `limitGrams`-as-of-that-day is not (the app never recorded limit *changes*). Export verbatim as JSONL, one object per day: `{"date": "2026-07-09", "limitGrams": 1.0, "consumedGrams": 0.7, "puffCount": 3, "enabled": true, "created": …, "updated": …}`. `date` is date-only and identifies a **calendar day**: importers MUST dedupe by calendar day (not by instant) and reconstruct the stored `Date` as local-timezone startOfDay — the iOS row stores a local startOfDay instant that differs across timezones. Future iOS versions SHOULD additionally emit a `pufftab.limit-changed` extension journal event on change, making this file fully derivable.

## 14. Photos (all `Data` fields) → attachments

Every `photo`/`logo` blob: hash (SHA-256) → write `attachments/<hh>/<sha256>.<ext>` → reference `"sha256:<hex>"`, with `<ext>` sniffed from magic bytes (`jpg`/`png`/`webp`/`heic`, `bin` fallback) — never assumed. The reference exporter recompresses via the app's existing `ImageCompressor` (which strips EXIF, incl. GPS — Core §7) whenever `compressImages` is enabled (the default); `compressImages` **off** is the keep-originals opt-in and exports bytes verbatim. Hashes are computed over the exported (post-recompression) bytes. Base64-embedded photos in JSON exports are **prohibited** in CanPUFF interchange — this replaces the legacy 850 MB single-JSON problem structurally.

## 15. Out of scope

The seven `@Model` classes not registered in the SwiftData schema (`Session`, `QuickPuff`, `PuffTemplate`, `DailyPuffAverage`, `UsageAnalytics`, `AppIntentConfig`, `IntentData`) are unpersisted dead code and have no mapping. `@AppStorage`/UserDefaults state (`hasVerifiedAge`, `use24HourTime`, iCloud toggle, widget preferences) is device-local configuration and intentionally unmapped (a future `apps/pufftab/device-settings` note may carry `use24HourTime` if users ask).

## 16. Legacy import (the existing “1.x” JSON export)

PWA and future iOS versions MUST be able to ingest the current single-JSON export (streaming parse only — the file can exceed device memory): map per this document, lowercase UUIDs, convert base64 photos to attachments, flatten `greenHoursScheduleData`, migrate deprecated shop fields, and tolerate the known quirks (import requiring non-empty `shops`; `version` prefix `"1."`; the compressed-export terpene bug). Two legacy-only preference fields need dispositions: `userPreferences[].use24HourTime` (device-local) maps to `apps/pufftab/settings.json` as `use24HourTime`; `userPreferences[].currencyCode` (legacy global currency) maps to settings.json as `legacyCurrency` — per-supply `currency` remains authoritative. Legacy export is import-only; nothing writes it going forward.

## Notes

- **N1 — timestamps:** iOS currently exports ISO 8601 UTC (`Z`) via `.iso8601`, **which truncates fractional seconds** — and every `Date()` carries sub-second precision, so the legacy strategy changes every instant on round-trip, breaking merge-by-`updated` and timestamp-keyed dedupe. Exported RFC 3339 timestamps MUST include fractional seconds (at least millisecond precision, e.g. `ISO8601Format` with `fractionalSeconds`); the legacy second-truncating strategy is non-conforming for the CanPUFF exporter. Local offsets are SHOULD (Core §2) — emit the device's offset. Round-trip of instants is exact only under these requirements.
- **N2 — `isShared`:** iOS stores both `isShared` and `sharedWithCount` independently. Export `shared.people = isShared ? sharedWithCount : 0` — mirroring how the app's own math gates on `isShared` — so both contradictory legacy states round-trip to consistent behavior: (`isShared == true`, `count == 0`) exports as `people: 0`, and (`isShared == false`, `count > 0`) also exports as `people: 0` (the count was inert in-app). On import to iOS, set `isShared = (people > 0)` and `sharedWithCount = people`.
- **N3 — `costpergram`:** iOS stores it but computes `calculatedCostPerGram` identically; the stored value can drift from `cost/gramsstart` (user edits). If drift is detected at export (>0.005 difference), preserve the stored value as `ext.pufftab.costPerGramOverride`; otherwise drop. On import, absent an override, set `costpergram = NSDecimalRound(cost / gramsstart, 2, .plain)` (identical to `calculatedCostPerGram`); with an override, set it verbatim.
- **N4 — terpene identity:** terpene names (Myrcene, Limonene…) are the interchange key; per-app dictionary row UUIDs are not portable across apps that seed their own dictionaries.
- **N5 — empty strings (global):** every iOS non-optional `String` whose value is the empty string is **omitted** on export; importers materialize absent string fields as `""`. Explicit empty strings in incoming documents are equivalent to absent. (This subsumes the per-field notes above.)
- **N6 — precision & bounds (global):** values exceeding spec precision are rounded half-even to the permitted places (grams 4dp, money/percent 2dp) with the exact original preserved under **flat dotted ext keys** (`ext.pufftab["exact.thc"]`, `exact.grams`, … — the Core §6.2 ext profile forbids nested objects); values outside schema bounds (percent > 100, `effects.rating` outside 1–10 — `Puff.effectiveness` is an unconstrained Int — `yearFounded` 1–999) are omitted from the core field and carried verbatim in `ext.pufftab`.
