#!/usr/bin/env python3
"""CanPUFF v1 plain-vault validator.

Usage:  validate-vault.py <vault-directory>
Needs:  pip install jsonschema pyyaml

Checks a vault against the CanPUFF Core v1 spec: manifest, journal files,
catalog Markdown round-trip rules, attachment content-addressing, and
referential integrity. Errors are conformance failures; warnings are
spec-tolerated conditions worth surfacing (dangling refs, unknown types).
"""
import hashlib
import json
import os
import re
import sys

try:
    import jsonschema
    import yaml
except ImportError:
    sys.exit("validate-vault.py requires: pip install jsonschema pyyaml")

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "schemas", "v1")

TYPE_TO_DIR = {
    "supply": "supplies", "shop": "shops", "chain": "chains", "brand": "brands",
    "producer": "producers", "method": "methods", "tax-rate": "tax-rates",
    "terpene": "terpenes",
}
HASHREF = re.compile(r"sha256:([0-9a-f]{64})")

errors: list[str] = []
warnings: list[str] = []


def err(msg: str) -> None:
    errors.append(msg)


def warn(msg: str) -> None:
    warnings.append(msg)


def load_schemas() -> dict:
    schemas = {}
    for name in os.listdir(SCHEMA_DIR):
        if name.endswith(".json"):
            with open(os.path.join(SCHEMA_DIR, name)) as f:
                schemas[name.removesuffix(".json")] = json.load(f)
    return schemas


def validate_object(schemas, type_name, obj, where):
    schema = schemas.get(type_name)
    if schema is None:
        warn(f"{where}: unknown type {type_name!r} (tolerated; treated as journal-tier)")
        return
    try:
        jsonschema.validate(obj, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as e:
        err(f"{where}: {e.message} @ {'/'.join(map(str, e.path))}")


def parse_md(text, where):
    if not text.startswith("---\n"):
        err(f"{where}: file must begin with a '---' line")
        return None
    m = re.match(r"^---\n(.*?)\n---\n?(.*)$", text, re.S)
    if not m:
        err(f"{where}: unterminated frontmatter")
        return None
    try:
        fm = yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        err(f"{where}: frontmatter is not parseable YAML: {e}")
        return None
    if not isinstance(fm, dict):
        err(f"{where}: frontmatter must be a mapping")
        return None
    body = m.group(2).strip()
    if body:
        fm["notes"] = body
    if "notes" in fm and fm["notes"] == "":
        err(f"{where}: notes must be absent rather than empty (Core §6.2)")
    return fm


def main(root: str) -> int:
    schemas = load_schemas()
    ids_seen: dict[str, str] = {}
    all_ids: set[str] = set()
    refs: list[tuple[str, str, str]] = []      # (where, field, target-id)
    attachment_refs: set[str] = set()

    def register(obj, where):
        oid = obj.get("id")
        if isinstance(oid, str):
            if oid in ids_seen:
                err(f"{where}: id {oid} already used in {ids_seen[oid]} (Core §2: vault-wide uniqueness)")
            ids_seen[oid] = where
            all_ids.add(oid)
        for match in HASHREF.finditer(json.dumps(obj)):
            attachment_refs.add(match.group(1))

    # --- manifest ---
    manifest_path = os.path.join(root, "manifest.json")
    if not os.path.isfile(manifest_path):
        err("manifest.json missing — not a CanPUFF vault (Core §3.1)")
        return report()
    with open(manifest_path) as f:
        try:
            manifest = json.load(f)
        except json.JSONDecodeError as e:
            err(f"manifest.json: invalid JSON: {e}")
            return report()
    validate_object(schemas, "manifest", manifest, "manifest.json")
    if manifest.get("format") != "canpuff":
        err("manifest.json: format must be 'canpuff'")

    for required_dir in ("journal", "catalog"):
        if not os.path.isdir(os.path.join(root, required_dir)):
            err(f"{required_dir}/ directory is REQUIRED (Core §3)")

    # --- journal ---
    journal_root = os.path.join(root, "journal")
    if os.path.isdir(journal_root):
        for dirpath, _, files in os.walk(journal_root):
            for name in sorted(files):
                if not name.endswith(".jsonl"):
                    continue
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                if not re.search(r"journal/\d{4}/(0[1-9]|1[0-2])\.jsonl$", rel.replace(os.sep, "/")):
                    err(f"{rel}: journal files must be journal/<YYYY>/<MM>.jsonl with zero-padded month")
                with open(os.path.join(dirpath, name), encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        if not line.strip():
                            continue
                        where = f"{rel}:{lineno}"
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            err(f"{where}: unparseable JSONL line")
                            continue
                        if obj.get("deleted") is True:
                            validate_object(schemas, "tombstone", obj, where)
                            register(obj, where)
                            continue
                        otype = obj.get("type", "")
                        if otype == "consumption":
                            validate_object(schemas, "consumption", obj, where)
                            at = obj.get("at", "")
                            expected = f"journal/{at[:4]}/{at[5:7]}.jsonl"
                            if rel.replace(os.sep, "/") != expected:
                                err(f"{where}: event dated {at[:10]} belongs in {expected} (Core §3)")
                            for field in ("supply", "method"):
                                if field in obj:
                                    refs.append((where, field, obj[field]))
                        elif "." in otype:
                            if "at" not in obj:
                                err(f"{where}: extension journal events must carry at (Core §9.1)")
                        else:
                            warn(f"{where}: unrecognized journal type {otype!r} (tolerated)")
                        register(obj, where)

    # --- catalog ---
    catalog_root = os.path.join(root, "catalog")
    if os.path.isdir(catalog_root):
        for dirname in sorted(os.listdir(catalog_root)):
            dirfull = os.path.join(catalog_root, dirname)
            if not os.path.isdir(dirfull):
                continue
            expected_type = {v: k for k, v in TYPE_TO_DIR.items()}.get(dirname)
            if expected_type is None:
                warn(f"catalog/{dirname}/: unknown catalog directory (tolerated, not interpreted)")
                continue
            for name in sorted(os.listdir(dirfull)):
                if not name.endswith(".md"):
                    warn(f"catalog/{dirname}/{name}: non-.md file in catalog")
                    continue
                where = f"catalog/{dirname}/{name}"
                with open(os.path.join(dirfull, name), encoding="utf-8") as f:
                    obj = parse_md(f.read(), where)
                if obj is None:
                    continue
                if obj.get("deleted") is True:
                    validate_object(schemas, "tombstone", obj, where)
                    register(obj, where)
                    continue
                otype = obj.get("type")
                if otype != expected_type:
                    err(f"{where}: type {otype!r} in directory for {expected_type!r} "
                        "(type is authoritative; writers must place records correctly)")
                if obj.get("id") and name != f"{obj['id']}.md":
                    err(f"{where}: filename must be <id>.md")
                validate_object(schemas, otype or expected_type, obj, where)
                register(obj, where)
                for field in ("shop", "brand", "chain", "producer"):
                    if field in obj:
                        refs.append((where, field, obj[field]))
                for tax in obj.get("taxes", []):
                    refs.append((where, "taxes", tax))

    # --- attachments ---
    stems: dict[str, str] = {}
    attachments_root = os.path.join(root, "attachments")
    if os.path.isdir(attachments_root):
        for dirpath, _, files in os.walk(attachments_root):
            for name in sorted(files):
                rel = os.path.relpath(os.path.join(dirpath, name), root)
                stem = name.split(".")[0]
                if not re.fullmatch(r"[0-9a-f]{64}", stem):
                    err(f"{rel}: attachment name must be a lowercase sha256 stem")
                    continue
                if stem in stems:
                    err(f"{rel}: duplicate stem also at {stems[stem]} (Core §7)")
                stems[stem] = rel
                shard = os.path.basename(dirpath)
                if shard != stem[:2]:
                    err(f"{rel}: must live under attachments/{stem[:2]}/")
                with open(os.path.join(dirpath, name), "rb") as f:
                    digest = hashlib.sha256(f.read()).hexdigest()
                if digest != stem:
                    err(f"{rel}: content hash {digest[:12]}… does not match filename")

    # --- referential integrity (dangling = warning by spec) ---
    for where, field, target in refs:
        if target not in all_ids:
            warn(f"{where}: dangling {field} reference {target} (tolerated by Core §2)")
    for ref in sorted(attachment_refs):
        if ref not in stems:
            warn(f"attachment reference sha256:{ref[:12]}… has no file (dangling; tolerated)")
    for stem, rel in stems.items():
        if stem not in attachment_refs:
            warn(f"{rel}: unreferenced attachment (tolerated; GC candidate)")

    return report()


def report() -> int:
    for w in warnings:
        print(f"  warn  {w}")
    for e in errors:
        print(f"  ERROR {e}")
    print(f"\n{'FAIL' if errors else 'PASS'}: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    if len(sys.argv) != 2 or not os.path.isdir(sys.argv[1]):
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
