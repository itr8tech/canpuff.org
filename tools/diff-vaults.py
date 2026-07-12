#!/usr/bin/env python3
"""CanPUFF v1 vault equivalence checker — round-trip integrity verification.

Usage:  diff-vaults.py <vaultA> <vaultB> [--json] [--verify-hashes]

        Each vault is a plain-vault directory or a zipped vault
        (.canpuff.zip, Core §8). Conventionally A is the "before" side of
        a round trip (e.g. an iOS export) and B the "after" (e.g. a web
        app's re-export of the same data).

Compares the two vaults record-by-record for semantic equivalence — the
identity test Core §8 rule 1 applies at import (RFC 8785 canonical-JSON
equality), evaluated at the spec's stated equivalences:

  - numbers compare by decimal value (22.50 == 22.5, 4 == 4.0)
  - `notes` compares trimmed; empty equals absent (Core §6.2)
  - attachment references compare case-folded (Core §7)
  - everything else — key sets, array order, string content — must match

Reported: record counts by type; ids present on one side only; per-field
differences for shared ids; journal/catalog placement mismatches;
attachment stems on one side only; apps/ files missing or differing in
bytes. Manifest identity (vaultId, created, generator) is reported as
informational only — a re-export legitimately mints its own (Core §3.1).

Exit codes:
        0  vaults are equivalent (informational notes allowed)
        1  differences or load anomalies found
        2  usage or environment error

Needs:  pip install pyyaml
"""
import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import tempfile
import zipfile
from decimal import Decimal

try:
    import yaml
except ImportError:
    print("diff-vaults.py requires: pip install pyyaml", file=sys.stderr)
    sys.exit(2)

SHA_REF = re.compile(r"^sha256:([0-9A-Fa-f]{64})$")
KNOWN_TOP = {"manifest.json", "journal", "catalog", "attachments", "apps"}
ABSENT = "∅ absent"


@contextlib.contextmanager
def vault_root(path):
    """Yield the vault root: the directory itself, or a zip extracted to a tempdir."""
    if os.path.isdir(path):
        yield path
        return
    if not zipfile.is_zipfile(path):
        print(f"{path}: not a vault directory or zip archive", file=sys.stderr)
        sys.exit(2)
    with tempfile.TemporaryDirectory(prefix="canpuff-") as td, zipfile.ZipFile(path) as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.startswith("/") or any(part == ".." for part in name.split("/")):
                print(f"{path}: archive member {info.filename!r} escapes the vault root; refusing to extract",
                      file=sys.stderr)
                sys.exit(2)
        zf.extractall(td)
        root = td
        if not os.path.isfile(os.path.join(td, "manifest.json")):
            entries = [e for e in os.listdir(td) if e != "__MACOSX" and not e.startswith(".")]
            if len(entries) == 1 and os.path.isdir(os.path.join(td, entries[0])):
                root = os.path.join(td, entries[0])  # Core §8: sole top-level directory wrapper
        yield root


# ---------------------------------------------------------------- canonical form

def canon(v):
    """Normalize a parsed value to the comparison form: all numbers become
    Decimal (so 4 == 4.0 == "4.00-as-number" across JSON/YAML parsers),
    attachment references fold to lowercase, containers recurse."""
    if isinstance(v, bool):
        return v
    if isinstance(v, float):
        return Decimal(repr(v))
    if isinstance(v, int):
        return Decimal(v)
    if isinstance(v, str):
        m = SHA_REF.match(v)
        return "sha256:" + m.group(1).lower() if m else v
    if isinstance(v, dict):
        return {k: canon(x) for k, x in v.items()}
    if isinstance(v, list):
        return [canon(x) for x in v]
    return v


def canon_record(obj):
    rec = canon(obj)
    notes = rec.get("notes")
    if isinstance(notes, str):
        notes = notes.strip()
        if notes:
            rec["notes"] = notes
        else:
            del rec["notes"]  # Core §6.2: empty notes == absent
    return rec


def kind(v):
    if v is ABSENT:
        return "absent"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, Decimal):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, dict):
        return "object"
    if isinstance(v, list):
        return "array"
    if v is None:
        return "null"
    return type(v).__name__


def show(v, limit=64):
    if v is ABSENT:
        return ABSENT
    if isinstance(v, Decimal):
        s = str(v)
    else:
        s = json.dumps(v, ensure_ascii=False, default=lambda d: float(d) if isinstance(d, Decimal) else str(d))
    return s if len(s) <= limit else s[: limit - 1] + "…"


def sortable(v):
    return json.dumps(v, sort_keys=True, default=str)


def diff_values(a, b, path, out):
    """Append (path, a, b, tag) tuples for every leaf-level difference."""
    if kind(a) != kind(b):
        out.append((path, a, b, "type"))
        return
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            diff_values(a.get(k, ABSENT), b.get(k, ABSENT), f"{path}.{k}" if path else k, out)
        return
    if isinstance(a, list):
        if a == b:
            return
        if sorted(map(sortable, a)) == sorted(map(sortable, b)):
            out.append((path, a, b, "order"))  # same members, different order (§8 identity is order-sensitive)
            return
        for i in range(max(len(a), len(b))):
            av = a[i] if i < len(a) else ABSENT
            bv = b[i] if i < len(b) else ABSENT
            diff_values(av, bv, f"{path}[{i}]", out)
        return
    if a != b:
        out.append((path, a, b, "value"))


# ---------------------------------------------------------------- vault loading

def parse_md(text, where, anomalies):
    if not text.startswith("---\n"):
        anomalies.append(f"{where}: does not begin with '---' — not parseable as a catalog record")
        return None
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        anomalies.append(f"{where}: unterminated frontmatter")
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        anomalies.append(f"{where}: frontmatter is not parseable YAML: {e}")
        return None
    if not isinstance(fm, dict):
        anomalies.append(f"{where}: frontmatter is not a mapping")
        return None
    body = m.group(2).strip()
    if body:
        fm["notes"] = body
    return fm


def load_vault(root, label):
    v = {
        "label": label,
        "manifest": None,
        "records": {},      # id -> canonical record
        "where": {},        # id -> vault-relative file path
        "attachments": {},  # sha256 stem -> vault-relative path
        "apps": {},         # vault-relative path -> sha256 of bytes
        "extras": [],       # files outside the defined layout (informational)
        "anomalies": [],    # load problems that make comparison unreliable
    }

    def rel(p):
        return os.path.relpath(p, root).replace(os.sep, "/")

    manifest_path = os.path.join(root, "manifest.json")
    if os.path.isfile(manifest_path):
        try:
            with open(manifest_path, encoding="utf-8") as f:
                v["manifest"] = canon(json.load(f, parse_float=Decimal))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            v["anomalies"].append(f"manifest.json: invalid JSON: {e}")
    else:
        v["anomalies"].append("manifest.json missing — not a CanPUFF vault (Core §3.1)")

    def add(obj, where):
        oid = obj.get("id")
        if not isinstance(oid, str):
            v["anomalies"].append(f"{where}: record without a string id cannot be compared")
            return
        if oid in v["records"]:
            v["anomalies"].append(
                f"{where}: duplicate id {oid} (also in {v['where'][oid]}) — comparing the later copy")
        v["records"][oid] = canon_record(obj)
        v["where"][oid] = where

    journal_root = os.path.join(root, "journal")
    if os.path.isdir(journal_root):
        for dirpath, _, files in os.walk(journal_root):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                if not name.endswith(".jsonl"):
                    v["extras"].append(rel(full))
                    continue
                with open(full, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line, parse_float=Decimal)
                        except json.JSONDecodeError:
                            v["anomalies"].append(
                                f"{rel(full)}:{lineno}: unparseable JSONL line — a record may be missing from the comparison")
                            continue
                        if not isinstance(obj, dict):
                            v["anomalies"].append(f"{rel(full)}:{lineno}: line is not a JSON object")
                            continue
                        add(obj, rel(full))

    catalog_root = os.path.join(root, "catalog")
    if os.path.isdir(catalog_root):
        for dirpath, _, files in os.walk(catalog_root):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                if not name.endswith(".md"):
                    v["extras"].append(rel(full))
                    continue
                with open(full, encoding="utf-8") as f:
                    obj = parse_md(f.read(), rel(full), v["anomalies"])
                if obj is not None:
                    add(obj, rel(full))

    attachments_root = os.path.join(root, "attachments")
    if os.path.isdir(attachments_root):
        for dirpath, _, files in os.walk(attachments_root):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                stem = name.split(".")[0]
                if not re.fullmatch(r"[0-9a-f]{64}", stem):
                    v["anomalies"].append(f"{rel(full)}: attachment name is not a sha256 stem")
                    continue
                if stem in v["attachments"]:
                    v["anomalies"].append(
                        f"{rel(full)}: duplicate stem (also {v['attachments'][stem]}, Core §7)")
                    continue
                v["attachments"][stem] = rel(full)

    apps_root = os.path.join(root, "apps")
    if os.path.isdir(apps_root):
        for dirpath, _, files in os.walk(apps_root):
            for name in sorted(files):
                full = os.path.join(dirpath, name)
                with open(full, "rb") as f:
                    v["apps"][rel(full)] = hashlib.sha256(f.read()).hexdigest()

    for entry in sorted(os.listdir(root)):
        if entry in KNOWN_TOP or entry == "__MACOSX" or entry.startswith("."):
            continue
        full = os.path.join(root, entry)
        if os.path.isdir(full):
            for dirpath, _, files in os.walk(full):
                v["extras"].extend(rel(os.path.join(dirpath, n)) for n in sorted(files))
        else:
            v["extras"].append(rel(full))

    return v


def verify_hashes(v):
    """Re-hash every attachment; a stem/content mismatch is a damaged attachment (Core §7)."""
    for stem, relpath in sorted(v["attachments"].items()):
        with open(os.path.join(v["_root"], relpath), "rb") as f:
            digest = hashlib.sha256(f.read()).hexdigest()
        if digest != stem:
            v["anomalies"].append(f"{relpath}: content hashes to {digest[:12]}…, not the filename stem — damaged attachment")


# ---------------------------------------------------------------- comparison

def compare(a, b):
    result = {
        "counts": {},          # type -> [nA, nB]
        "only_a": [],          # (id, type, where)
        "only_b": [],
        "field_diffs": [],     # (id, type, whereA, [(path, aval, bval, tag)])
        "placement": [],       # (id, type, whereA, whereB)
        "attachments": {"only_a": [], "only_b": [], "shared": 0, "ext_note": []},
        "apps": {"only_a": [], "only_b": [], "differ": [], "shared": 0},
        "manifest_diffs": [],  # real differences: format / specVersion
        "manifest_info": [],   # informational: vaultId / created / generator / anything else
        "extras": {"a": a["extras"], "b": b["extras"]},
        "anomalies": {"a": a["anomalies"], "b": b["anomalies"]},
    }

    def type_of(rec):
        t = rec.get("type")
        t = t if isinstance(t, str) and t else "(untyped)"
        return f"{t} [tombstone]" if rec.get("deleted") is True else t

    for side, vault in ((0, a), (1, b)):
        for rec in vault["records"].values():
            result["counts"].setdefault(type_of(rec), [0, 0])[side] += 1

    ids_a, ids_b = set(a["records"]), set(b["records"])
    for oid in sorted(ids_a - ids_b):
        rec = a["records"][oid]
        result["only_a"].append((oid, type_of(rec), a["where"][oid]))
    for oid in sorted(ids_b - ids_a):
        rec = b["records"][oid]
        result["only_b"].append((oid, type_of(rec), b["where"][oid]))

    for oid in sorted(ids_a & ids_b):
        ra, rb = a["records"][oid], b["records"][oid]
        diffs = []
        diff_values(ra, rb, "", diffs)
        if diffs:
            result["field_diffs"].append((oid, type_of(ra), a["where"][oid], diffs))
        if a["where"][oid] != b["where"][oid]:
            result["placement"].append((oid, type_of(ra), a["where"][oid], b["where"][oid]))

    stems_a, stems_b = set(a["attachments"]), set(b["attachments"])
    result["attachments"]["only_a"] = sorted(stems_a - stems_b)
    result["attachments"]["only_b"] = sorted(stems_b - stems_a)
    result["attachments"]["shared"] = len(stems_a & stems_b)
    for stem in sorted(stems_a & stems_b):
        ea, eb = a["attachments"][stem], b["attachments"][stem]
        if os.path.splitext(ea)[1] != os.path.splitext(eb)[1]:
            result["attachments"]["ext_note"].append(f"{stem[:12]}…: {ea} vs {eb} (extension is advisory, Core §7)")

    paths_a, paths_b = set(a["apps"]), set(b["apps"])
    result["apps"]["only_a"] = sorted(paths_a - paths_b)
    result["apps"]["only_b"] = sorted(paths_b - paths_a)
    result["apps"]["shared"] = len(paths_a & paths_b)
    result["apps"]["differ"] = sorted(p for p in paths_a & paths_b if a["apps"][p] != b["apps"][p])

    ma, mb = a["manifest"] or {}, b["manifest"] or {}
    for key in sorted(set(ma) | set(mb)):
        va, vb = ma.get(key, ABSENT), mb.get(key, ABSENT)
        if va == vb:
            continue
        line = f"manifest.{key}: {show(va)} ≠ {show(vb)}"
        if key in ("format", "specVersion"):
            result["manifest_diffs"].append(line)
        else:
            result["manifest_info"].append(line)

    result["difference_count"] = (
        len(result["only_a"]) + len(result["only_b"]) + len(result["field_diffs"])
        + len(result["placement"]) + len(result["attachments"]["only_a"])
        + len(result["attachments"]["only_b"]) + len(result["apps"]["only_a"])
        + len(result["apps"]["only_b"]) + len(result["apps"]["differ"])
        + len(result["manifest_diffs"])
    )
    result["anomaly_count"] = len(a["anomalies"]) + len(b["anomalies"])
    result["equivalent"] = result["difference_count"] == 0 and result["anomaly_count"] == 0
    return result


# ---------------------------------------------------------------- reporting

def print_report(a, b, r, path_a, path_b):
    def mline(v, path):
        m = v["manifest"] or {}
        gen = m.get("generator") or {}
        gen_s = " ".join(str(x) for x in (gen.get("name"), gen.get("version")) if x) or "unknown generator"
        return (f"  {v['label']}: {path}\n     vaultId {m.get('vaultId', '?')} · {gen_s} · "
                f"{len(v['records'])} records · {len(v['attachments'])} attachments")

    print("CanPUFF vault diff")
    print(mline(a, path_a))
    print(mline(b, path_b))

    print("\nRecord counts by type            A      B")
    for t in sorted(r["counts"]):
        na, nb = r["counts"][t]
        marker = "" if na == nb else "   ← differs"
        print(f"  {t:<28}{na:>6}{nb:>7}{marker}")

    for label, items in (("Only in A", r["only_a"]), ("Only in B", r["only_b"])):
        if items:
            print(f"\n{label} ({len(items)}):")
            for oid, t, where in items:
                print(f"  {t}  {oid}  ({where})")

    if r["field_diffs"]:
        print(f"\nRecords with field differences ({len(r['field_diffs'])}):")
        for oid, t, where, diffs in r["field_diffs"]:
            print(f"  {t}  {oid}  ({where})")
            for path, va, vb, tag in diffs:
                note = {"type": "  [type change]", "order": "  [array order only]"}.get(tag, "")
                print(f"      {path or '(record)'}: {show(va)} → {show(vb)}{note}")

    if r["placement"]:
        print(f"\nPlacement differences ({len(r['placement'])}):")
        for oid, t, wa, wb in r["placement"]:
            print(f"  {t}  {oid}: {wa} → {wb}")

    att = r["attachments"]
    print(f"\nAttachments: {att['shared']} shared · {len(att['only_a'])} only in A · {len(att['only_b'])} only in B")
    for stem in att["only_a"]:
        print(f"  only in A: {stem}")
    for stem in att["only_b"]:
        print(f"  only in B: {stem}")

    ap = r["apps"]
    if ap["shared"] or ap["only_a"] or ap["only_b"]:
        state = "byte-identical" if not (ap["differ"] or ap["only_a"] or ap["only_b"]) else "DIFFERS"
        print(f"apps/: {ap['shared']} shared file(s), {state}")
        for p in ap["only_a"]:
            print(f"  only in A: {p}")
        for p in ap["only_b"]:
            print(f"  only in B: {p}")
        for p in ap["differ"]:
            print(f"  bytes differ: {p}")

    if r["manifest_diffs"]:
        print("\nManifest conformance differences:")
        for line in r["manifest_diffs"]:
            print(f"  {line}")

    info = r["manifest_info"] + att["ext_note"]
    for side, extras in (("A", r["extras"]["a"]), ("B", r["extras"]["b"])):
        info.extend(f"{side} carries a file outside the defined layout: {p} (tolerated, Core §3)" for p in extras)
    if info:
        print("\nInformational (does not affect equivalence):")
        for line in info:
            print(f"  {line}")

    for side, anomalies in (("A", r["anomalies"]["a"]), ("B", r["anomalies"]["b"])):
        if anomalies:
            print(f"\nLoad anomalies in {side} (comparison may be incomplete):")
            for m in anomalies:
                print(f"  {m}")

    verdict = "EQUIVALENT" if r["equivalent"] else "NOT EQUIVALENT"
    print(f"\n{verdict}: {r['difference_count']} difference(s), {r['anomaly_count']} load anomal(ies)")


def json_report(r):
    def jsonable(v):
        if isinstance(v, Decimal):
            return float(v) if v != v.to_integral_value() else int(v)
        if isinstance(v, dict):
            return {k: jsonable(x) for k, x in v.items()}
        if isinstance(v, (list, tuple)):
            return [jsonable(x) for x in v]
        return v

    print(json.dumps(jsonable(r), indent=2, ensure_ascii=False, default=str))


def main():
    ap = argparse.ArgumentParser(description="Compare two CanPUFF vaults for semantic equivalence.",
                                 add_help=True)
    ap.add_argument("vault_a")
    ap.add_argument("vault_b")
    ap.add_argument("--json", action="store_true", help="emit a machine-readable JSON report")
    ap.add_argument("--verify-hashes", action="store_true",
                    help="re-hash every attachment and flag stem/content mismatches")
    args = ap.parse_args()

    for p in (args.vault_a, args.vault_b):
        if not os.path.exists(p):
            print(f"{p}: no such file or directory", file=sys.stderr)
            return 2

    with vault_root(args.vault_a) as root_a, vault_root(args.vault_b) as root_b:
        a = load_vault(root_a, "A")
        b = load_vault(root_b, "B")
        a["_root"], b["_root"] = root_a, root_b
        if args.verify_hashes:
            verify_hashes(a)
            verify_hashes(b)
        r = compare(a, b)

    if args.json:
        json_report(r)
    else:
        print_report(a, b, r, args.vault_a, args.vault_b)
    return 0 if r["equivalent"] else 1


if __name__ == "__main__":
    sys.exit(main())
