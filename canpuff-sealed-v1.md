# CanPUFF Sealed Vault & Sync Profile

**Version 1.0 — DRAFT r2 (2026-07-10)** · Companion to [CanPUFF Core v1](canpuff-v1.md)

This profile defines the **sealed vault**: the end-to-end-encrypted form of a CanPUFF vault used for synchronization, backup, and any off-device storage. It also defines the minimal file-server protocol a sealed vault synchronizes against.

Implementing this profile is OPTIONAL. An application that transmits or stores vault data off-device MUST implement it (Core §11). The server never sees plaintext, never holds keys, and requires no cannabis-specific — or CanPUFF-specific — logic.

The key words MUST, MUST NOT, REQUIRED, SHALL, SHALL NOT, SHOULD, SHOULD NOT, RECOMMENDED, NOT RECOMMENDED, MAY, and OPTIONAL in this document are to be interpreted as described in BCP 14 (RFC 2119, RFC 8174) when, and only when, they appear in all capitals.

Unless stated otherwise, **all hexadecimal strings in this profile — identifiers, object names, HLC components, server paths — are lowercase.**

---

## 1. Cryptographic primitives

| Purpose | Primitive |
|---|---|
| File encryption envelope | **age v1** (C2SP spec), X25519 recipient stanzas only. Passphrase (scrypt) stanzas MUST NOT be used for vault objects. |
| Key derivation from the root secret | HKDF-SHA-256 (RFC 5869), invoked exactly as §2 specifies. |
| Root secret encoding | **BIP39 mnemonic**, 12 or 24 words (128/256-bit entropy), **English wordlist only** (§2 Layer 0). |
| Object naming MAC | HMAC-SHA-256. |
| Padding | Padmé bucket sizes with the explicit framing in §1.1. |

Rationale: age is a small written spec with independent implementations (Go reference, Rust `rage`, TypeScript `typage`); every encrypted object in a sealed vault is an ordinary age file that the `age` CLI can decrypt with the vault identity. No bespoke cryptography is introduced by this profile.

### 1.1 Padding framing (normative)

Padmé defines a target size, not a mechanism. A **padded plaintext** is:

```
uint64 big-endian original length L  ||  the L plaintext bytes  ||  0x00 bytes
```

extended with zero bytes to the smallest Padmé-permitted size ≥ (8 + L), with a **minimum padded size of 4096 bytes** for oplog segments, checkpoints, and the manifest (no minimum for blobs). After decryption, readers MUST recover the plaintext via the length prefix, MUST take exactly L bytes, and MUST reject a length field larger than the padded size. The Core §7 SHA-256 and the §4 object name are computed over the **unpadded** plaintext bytes.

## 2. Key hierarchy

```
Layer 0 — ROOT
  entropy     := 128- or 256-bit random value, generated at vault creation,
                 shown to the user exactly once as a BIP39 mnemonic.
                 The mnemonic IS the recovery key and the sync credential.
                 The entropy is encoded/decoded by the mnemonic DIRECTLY:
                 BIP39's passphrase feature and its PBKDF2 seed-stretching
                 step are NOT used.

Layer 1 — DERIVED (see invocation below)
  "canpuff/v1/repo-id"     → repoId    (16 bytes → 32 lowercase hex chars)
  "canpuff/v1/write-key/" || origin
                           → writeKey  (32 bytes → 64 lowercase hex chars; §7)
  "canpuff/v1/master-key"  → masterKey (32 bytes)
  "canpuff/v1/mac-key"     → macKey    (32 bytes — object naming, §4)

Layer 2 — PER-OBJECT
  age's native per-file random file key, wrapped to the vault recipient.

Layer 3 — LOCAL CONVENIENCE UNLOCK (custody-free; see §2.3)
```

**HKDF invocation (normative).** Each Layer-1 value is `OKM = HKDF-Expand(HKDF-Extract(salt = zero-length, IKM = the raw BIP39 entropy bytes), info = the exact ASCII label bytes shown (no terminator), L = the stated output length)` per RFC 5869. For `write-key`, the label is the ASCII prefix `canpuff/v1/write-key/` concatenated with the server **origin**: the lowercase `scheme "://" host [":" port]` of the server URL (port omitted when default). Deriving writeKey per-origin means no server ever holds a credential replayable at another server.

**Layer 0 rules.** Mnemonics MUST use the English BIP39 wordlist. On entry, implementations MUST validate the BIP39 checksum and reject invalid mnemonics rather than deriving keys from them. Word matching is case-insensitive after ASCII whitespace trimming; implementations MAY accept the standard unique 4-letter prefixes. Applications MUST require the user to confirm the mnemonic at creation (re-entry or equivalent), SHOULD offer a printable QR "paper key," and MUST state plainly that it cannot be reset or recovered by anyone. **Device pairing = entering (or QR-scanning) the mnemonic.** There is no other enrollment step.

### 2.1 The age identity (normative)

The age identity secret is **the raw 32-byte masterKey, used as-is**: implementations MUST pass the unmodified bytes to X25519 (which performs RFC 7748 clamping internally) and MUST NOT store or export a pre-clamped variant. For interoperability with the `age` CLI, the identity is the Bech32 encoding of the raw 32 bytes with HRP `AGE-SECRET-KEY-`; the vault recipient is the Bech32 `age1` encoding of `X25519(masterKey, basepoint)`. masterKey MUST NOT be used for any purpose other than serving as this identity. (128-bit-entropy vaults yield a 32-byte masterKey through HKDF like any other; the identity is always 32 bytes.)

### 2.2 Vault identity vs repository address

`repoId` names the vault **repository on a server** and is deliberately distinct from the plain vault's `manifest.json` `vaultId` (a UUID, per Core §3.1), which travels **inside** the encrypted state. On restore, the `vaultId` inside the decrypted checkpoint is authoritative for vault identity; `repoId` is only a server-side address.

### 2.3 Local convenience unlock (Layer 3)

Devices MAY cache masterKey wrapped for fast unlock. A **wrap record** is:

```json
{ "kdf": "argon2id" | "scrypt" | "pbkdf2-sha256" | "webauthn-prf",
  "params": { …including a fresh random 16-byte salt for password KDFs… },
  "credentialId": "…",          // webauthn-prf only
  "cipher": "chacha20-poly1305" | "aes-256-gcm",
  "nonce": "…12 bytes, base64…",
  "ciphertext": "…base64…" }
```

The 32-byte KDF/PRF output keys ChaCha20-Poly1305 (RFC 8439) — or AES-256-GCM where unavailable, as recorded — with a fresh random 12-byte nonce, over the 32-byte masterKey. Recommended password-KDF parameters: Argon2id m=64 MiB, t=3, p=1; PBKDF2-SHA-256 ≥ 600k iterations only where WASM is unavailable. For WebAuthn PRF, the evaluation input (`eval.first`) is `SHA-256("canpuff/v1/prf-unlock")` and the first 32 bytes of the PRF output are the wrap key; the credential id MUST be stored in the record. A PRF wrap MUST NOT be the only unlock path. Destroying Layer-3 state loses nothing: the mnemonic re-derives everything.

## 3. Sealed repository layout

What a server (or any untrusted storage) holds:

```
vaults/<repoId>/
  oplog/<deviceId>/<seq>.age      immutable  event segments (§5)
  blob/<name>.age                 immutable  attachments (§4)
  checkpoint/<hlc>.age            immutable  fold snapshots (§6)
  manifest.age                    mutable    the single coordination object (§6)
```

- `<deviceId>` is a UUID generated per device at pairing. `<seq>` is a decimal counter **starting at 1, zero-padded to exactly 9 digits** (`000000001`). Devices recovering from a lost counter MUST parse existing names under `oplog/<self>/` numerically and resume at max+1.
- Everything except `manifest.age` is **write-once**: created with `If-None-Match: *`, never modified, deleted only by compaction (§6).
- All plaintexts are padded per §1.1 before encryption. All objects are age files encrypted to the vault recipient.

## 4. Attachment naming (confirmation-attack resistance)

Attachments are addressed **inside** the vault by plaintext SHA-256 (Core §7). On a server, the object name MUST be:

```
name = lowercase-hex( HMAC-SHA-256( macKey, sha256_of_plaintext ) )
```

A bare plaintext hash as a server-visible name would let an adversary holding a candidate file *prove* the vault contains it (the classic convergent-encryption confirmation attack — directly relevant to this data class). The keyed name preserves what sync needs — deterministic per-vault identity, idempotent uploads, set-difference reconciliation — and leaks nothing.

Two devices independently encrypting the same photo produce different ciphertexts under the same name; the first successful `If-None-Match: *` PUT wins and the outcome is identical after decryption.

## 5. Oplog: immutable encrypted segments

Devices never append to a remote file. Each **push** writes one new segment:

- A segment plaintext is a JSONL batch of **sync events**, each wrapping a CanPUFF object state:
  ```json
  {"op":"put","hlc":"2026-07-10T23:20:00.000Z-0001-b6b8f3a1","object":{ …full CanPUFF object… }}
  {"op":"del","hlc":"…","type":"supply","id":"9f3c…"}
  ```
- **HLC grammar (normative):** `hlc = <instant> "-" <counter> "-" <device>` where `<instant>` is RFC 3339 **in UTC with exactly millisecond precision and the `Z` designator** (`2026-07-10T23:20:00.000Z`); `<counter>` is exactly 4 lowercase hex digits (on overflow within one millisecond the device MUST wait for, or logically advance to, the next millisecond); `<device>` is exactly the first 8 lowercase hex characters of the deviceId with hyphens removed. Under these constraints, **HLC comparison is bytewise string comparison** and is the total order for folding; the `(deviceId, seq, line number)` tiebreak applies only when two hlc strings are byte-equal. Devices MUST maintain HLC monotonicity across restarts (persist the last issued HLC; never issue a smaller one, advancing the counter or waiting as needed when the wall clock regresses).
- `op:"del"` is a tombstone. Tombstones MUST be retained until compaction per §6 proves all manifest devices have folded past them.
- Segments are padded per §1.1; a device SHOULD batch events per push rather than writing one segment per event (bandwidth, metadata).

## 6. Synchronization algorithm

Each device keeps, locally: its plain vault (the materialized state), its own next `seq`, and per-device cursors of consumed remote segments.

A sync cycle:

1. **Push:** write local unpushed events as `oplog/<self>/<seq>.age` (`If-None-Match: *` — cannot conflict; on 412, re-read own directory to recover `seq`).
2. **Pull:** `LIST` the repo; fetch unseen segments from other devices (and any checkpoint newer than the local fold base).
3. **Fold (local, deterministic):** load the newest usable checkpoint's state (or empty). A checkpoint plaintext MUST embed its **coverage**: `{"<deviceId>": <lastSeqFoldedIntoIt>}`. Apply **only** events from segments with `seq > coverage[deviceId]` (all segments for devices absent from coverage), ordered by HLC. Events from segments at or below coverage MUST NOT be re-applied — re-applying them would resurrect objects whose tombstones were compacted away. A checkpoint is *usable* only if every segment it does not cover is still present. Per-object last-write-wins by HLC; `del` beats older `put`s. The result **is** the plain vault; write it to local storage. Folding is pure: every device folding the same checkpoint + event set MUST produce the same logical state, where object equality is defined over RFC 8785 (JSON Canonicalization Scheme) bytes of each object's canonical JSON form. (On-disk Markdown byte equality across implementations is NOT required; the JCS form is what is compared and hashed.)
4. **Checkpoint & compact (any device, occasionally):** write `checkpoint/<hlc>.age` containing the folded state **and its coverage map**; update `manifest.age` (CAS via `If-Match`) recording the checkpoint and per-device fold cursors; segments and checkpoints strictly older than a checkpoint acknowledged by **all devices listed in the manifest** MAY then be `DELETE`d. A 412 on the manifest means another device raced — re-pull, re-fold, retry.
5. **Attachments:** compute the set difference between locally referenced attachment names (§4) and server `blob/` names; PUT missing (one file each — naturally resumable), GET unknown-local ones lazily or eagerly per app policy.

### 6.1 Device lifecycle

- **Join:** a device adds itself to `manifest.devices` via the CAS loop on first push (creating `manifest.age` with `If-None-Match: *` if absent; on 412, merge and retry). Before compacting, a device MUST `LIST oplog/` and treat any device directory not yet in the manifest as an unacknowledged device (blocking compaction) and add it to the manifest.
- **Evict:** applications MUST provide user-initiated device eviction — removing the entry from `manifest.devices` via CAS — so one lost phone cannot block compaction and grow the repo forever. Devices SHOULD record a `lastSeen` HLC; applications MAY prompt to evict devices unseen for a configurable period.
- **Evicted device:** a device that discovers its deviceId absent from the manifest MUST NOT push under its old deviceId; it re-joins under a fresh deviceId (its local plain vault merges back naturally through new segments).

`manifest.age` plaintext:

```json
{
  "type": "canpuff-sealed-manifest",
  "version": 1,
  "specVersion": 1,
  "devices": { "<deviceId>": { "lastSeq": 41, "foldedThrough": "<hlc>", "lastSeen": "<hlc>" } },
  "checkpoint": { "hlc": "<hlc>", "object": "checkpoint/<hlc>.age" }
}
```

(`version` is the schema version of this manifest object; `specVersion` echoes the Core specVersion of the vault state it coordinates.)

Conflict reality: consumption events are immutable in practice — the only true conflicts are concurrent edits to the *same field* of the same catalog record from two offline devices, which LWW resolves and the losing segment still preserves until compaction (an application MAY surface "an earlier edit was superseded" from the retained history).

## 7. Server protocol

Four operations against opaque paths — implementable in ~300 lines of PHP, with zero knowledge of CanPUFF:

| Operation | Wire form | Semantics |
|---|---|---|
| GET | `GET /v/<repoId>/<path>` | Returns object bytes + strong `ETag`. |
| PUT | `PUT /v/<repoId>/<path>` | Honors `If-None-Match: *` (create-only) and `If-Match: <etag>` (CAS). Writes MUST be atomic (temp file + rename). Returns new `ETag`. |
| DELETE | `DELETE /v/<repoId>/<path>` | Removes an object (compaction only). |
| LIST | `GET /v/<repoId>/?prefix=<p>` (trailing-slash collection form) | `application/json` array of `{path, etag, size}` sorted by `path`. Servers MAY paginate via a `cursor` query parameter and a `nextCursor` response field. |

- **Transport MUST be HTTPS.** Clients MUST NOT send the Authorization header over plaintext HTTP, and servers MUST reject non-TLS requests (a redirect is not sufficient — the credential has already been sent).
- **Auth:** `Authorization: Bearer <writeKey-hex>`. The server stores only `SHA-256(writeKey)` per vault; vault creation is first-PUT-wins registration of that hash (servers MAY require out-of-band provisioning instead). Unsalted, unstretched SHA-256 is sufficient here *only because* writeKey is a full-entropy derived key, not a password — this pattern MUST NOT be reused for user-chosen secrets. Servers MUST compare hashes in constant time and MUST NOT log Authorization header values. Because writeKey is derived per-origin (§2), a credential presented to one server is useless at any other.
- ETags are opaque ciphertext version tokens. The server never compares content, never inspects bytes, and can run on any storage (disk, S3) behind the same contract.
- Servers SHOULD enforce per-vault size quotas and MAY garbage-collect vaults per their own retention policy — clients are the durability authority (any device can fully restore from mnemonic + repo, and the plain vault always exists on-device).
- A generic WebDAV server MAY be used as the transport where it provides equivalent conditional-request semantics (`If-Match`/`If-None-Match` on PUT, strong ETags; `PROPFIND` depth-1 serves as LIST).

## 8. Threat model boundaries: what still leaks, and trust

Even with all payloads encrypted, an honest-but-curious server observes: object counts and padded sizes, push timing (activity cadence), device count, and IP addresses. Padmé padding and batching blunt size/count signals; scheduled/batched sync blunts timing; network-level privacy (VPN/Tor) is out of scope but compatible. Applications SHOULD document this residual surface in plain language. The design goal is that **seizure of the server yields nothing** — cadence metadata is the accepted residue of using a server at all.

**All paired devices are equally trusted.** Any device holding the vault key can write checkpoints and trigger compaction, so a malicious or buggy device can corrupt or destroy vault history — this is outside the threat model (which concerns the server), and the mnemonic is the security boundary. As a robustness measure, a device SHOULD verify that a new checkpoint matches its own independent fold (JCS canonical-bytes comparison per §6 step 3) before deleting any segment older than it, and compaction SHOULD retain the previous checkpoint as a fallback.

## 9. Web Push (informative)

A self-hosted sync server is a natural Web Push origin for reminder features that pure-local web clients cannot provide (scheduled notifications). Push payloads must not contain journal-tier plaintext (Core §11 makes this normative); clients precompute reminder schedules and register them as opaque timers — the server cannot compute anything about consumption because it can decrypt nothing.
