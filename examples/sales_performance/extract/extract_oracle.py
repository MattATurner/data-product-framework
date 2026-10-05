#!/usr/bin/env python3
# dpf: skill=extract-rdbms-watermark tier=5 adr=ADR-015 requirements=R-10
"""Watermark extract: local Oracle -> BigQuery raw, outbound only.

Implements skill `extract-rdbms-watermark` at tool tier 5 (bespoke code) for BRD
R-10. ADR-015 records why: the source has no inbound route from Google Cloud, so
managed pull tools cannot reach it. This outbound-only extractor runs beside the
database and pushes to BigQuery over HTTPS.

    pip install oracledb google-cloud-bigquery pyyaml   # jsonschema: optional
    export ORACLE_USER=... ORACLE_PASSWORD=...
    python3 extract_oracle.py                    # all entities
    python3 extract_oracle.py customers          # one entity
    python3 extract_oracle.py --dry-run          # read Oracle only, print manifests
    python3 extract_oracle.py --config my.yaml   # default: config.yaml beside this file
    python3 extract_oracle.py orders --accept-schema   # after resolving breaking drift

Guarantees (platform capability specs land-immutable-raw, extract-incremental-capture):
  * raw is append-only; every row carries the lineage columns
  * every batch persists a landing-manifest.v1 row in <control>.landing_manifest
  * raw rows, watermark and manifest commit in ONE BigQuery transaction, with row
    counts asserted before COMMIT: the watermark never advances without the data,
    and a failed run commits nothing, so re-running cannot duplicate a batch
  * the predicate `watermark_column > watermark - lookback_minutes` re-reads late
    commits: at-least-once landing in raw, exactly-once after staging dedupe on
    natural key + source change timestamp
  * watermarks keep microsecond precision (ISO 8601, UTC); zone-less TIMESTAMPs
    are taken as UTC and TIMESTAMP WITH TIME ZONE columns are read as UTC instants
  * schemas come from the Oracle cursor, never autodetect; drift is classified
    against <control>.schema_registry. Additive drift lands; breaking drift
    quarantines the batch, holds the watermark and raises `schema_drift_breaking`
  * logs are single-line JSON for Cloud Logging; failures carry `dpf_alert`
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

SKILL = "extract-rdbms-watermark"
REQUIREMENT_IDS = ("R-10",)
UTC = timezone.utc
EPOCH = datetime(1900, 1, 1, tzinfo=UTC)
DEFAULT_CONFIG = Path(__file__).resolve().with_name("config.yaml")
DEFAULT_LOOKBACK_MINUTES = 15
DEFAULT_LOAD_TABLE_TTL_HOURS = 24
MANIFEST_SCHEMA = "landing-manifest.v1.schema.json"

LINEAGE_SCHEMA = {
    "_ingest_ts": "TIMESTAMP",
    "_batch_id": "STRING",
    "_source_system": "STRING",
    "_op": "STRING",
    "_source_pk_hash": "STRING",
}
LINEAGE = tuple(LINEAGE_SCHEMA)

# Type changes that keep every landed value representable; BigQuery can ALTER these.
WIDENING = frozenset({
    ("INT64", "NUMERIC"),
    ("INT64", "BIGNUMERIC"),
    ("NUMERIC", "BIGNUMERIC"),
})
DRIFT_KINDS = ("none", "additive", "breaking")
STATUSES = ("landed", "quarantined")


# --------------------------------------------------------------------------- logging

def log(severity: str, message: str, **fields: Any) -> None:
    """One JSON object per line on stdout. Cloud Logging reads severity/message/time."""
    entry = {"severity": severity, "message": message,
             "time": iso_utc(utcnow()), "skill": SKILL}
    entry.update(fields)
    sys.stdout.write(json.dumps(entry, default=str, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def alert(name: str, message: str, **fields: Any) -> None:
    """ERROR line carrying `dpf_alert`; log-based metrics alert on these."""
    log("ERROR", message, dpf_alert=name, **fields)


_WARNED: set = set()


def _warn_once(message: str) -> None:
    if message not in _WARNED:
        _WARNED.add(message)
        log("WARNING", message)


# --------------------------------------------------------------------------- time

def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_ts(value: str | datetime) -> datetime:
    """ISO 8601 string or datetime -> aware UTC datetime. Naive values are UTC."""
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()
        if text[-1:] in ("Z", "z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def iso_utc(value: str | datetime) -> str:
    """ISO 8601 in UTC with microseconds, e.g. 2026-03-10T09:45:00.123456+00:00."""
    return parse_ts(value).isoformat(timespec="microseconds")


def extraction_since(watermark_iso: str | None, lookback_minutes: float) -> datetime:
    """Exclusive lower bound of the next extract: watermark minus the lookback.

    No watermark yet means a full extract from EPOCH.
    """
    if lookback_minutes < 0:
        raise ValueError("lookback_minutes must be >= 0")
    if not watermark_iso:
        return EPOCH
    return parse_ts(watermark_iso) - timedelta(minutes=lookback_minutes)


# --------------------------------------------------------------------------- types

_FLOAT_TYPES = {"BINARY_FLOAT", "BINARY_DOUBLE", "FLOAT", "REAL", "DOUBLE_PRECISION"}
_NUMBER_TYPES = {"NUMBER", "NUMERIC", "DECIMAL", "DEC", "INTEGER", "INT", "SMALLINT"}
_INT_TYPES = {"BINARY_INTEGER", "PLS_INTEGER"}
_BYTES_TYPES = {"RAW", "LONG_RAW", "BLOB"}
_BQ_LEGACY = {"INTEGER": "INT64", "FLOAT": "FLOAT64", "BOOLEAN": "BOOL", "RECORD": "STRUCT"}


def _oracle_type_key(name: str) -> str:
    key = re.sub(r"\([^)]*\)", "", str(name).upper()).strip()
    if key.startswith("DB_TYPE_"):
        key = key[len("DB_TYPE_"):]
    return re.sub(r"\s+", "_", key)


def bq_type_for(oracle_type_name: str, precision: int | None = None,
                scale: int | None = None) -> str:
    """Map an Oracle type (dictionary name or python-oracledb DB_TYPE_*) to BigQuery.

    NUMBER(p, s) is INT64 when s == 0 and p <= 18, NUMERIC inside NUMERIC's range
    (<= 29 integer digits, s <= 9) and for unconstrained NUMBER, and BIGNUMERIC
    beyond that, so no declared value is rounded or rejected.
    """
    t = _oracle_type_key(oracle_type_name)
    if t in _FLOAT_TYPES:
        return "FLOAT64"
    if t in _NUMBER_TYPES:
        return _bq_number(precision or 0, 0 if scale is None else scale)
    if t in _INT_TYPES:
        return "INT64"
    if t == "DATE":
        return "DATETIME"          # Oracle DATE has a time of day and no zone
    if t.startswith("TIMESTAMP"):
        return "TIMESTAMP"         # with or without (local) time zone
    if t in _BYTES_TYPES:
        return "BYTES"
    if t in ("BOOLEAN", "BOOL"):
        return "BOOL"
    if t == "JSON":
        return "JSON"
    return "STRING"                # VARCHAR2, CHAR, CLOB, NCHAR, ... and unknown types


def _bq_number(precision: int, scale: int) -> str:
    if precision <= 0:             # unconstrained NUMBER
        return "NUMERIC"
    if scale == -127:              # FLOAT(b): binary precision, floating point
        return "FLOAT64"
    if scale <= 0:                 # integers; a negative scale rounds left of the point
        digits = precision - scale
        if digits <= 18:
            return "INT64"
        return "NUMERIC" if digits <= 29 else "BIGNUMERIC"
    return "NUMERIC" if precision - scale <= 29 and scale <= 9 else "BIGNUMERIC"


def normalise_bq_type(name: str) -> str:
    """BigQuery API legacy names (INTEGER, FLOAT, BOOLEAN) -> GoogleSQL names."""
    t = str(name).upper()
    return _BQ_LEGACY.get(t, t)


# --------------------------------------------------------------------------- schema

def bq_column_name(name: str) -> str:
    """BigQuery-safe column name. Oracle identifiers may contain $ and #."""
    out = re.sub(r"[^A-Za-z0-9_]", "_", str(name))
    return "_" + out if not out or out[0].isdigit() else out


def source_schema(description: Sequence[Sequence[Any]]) -> dict[str, str]:
    """Ordered {column: BigQuery type} from a DB-API cursor.description."""
    schema: dict[str, str] = {}
    seen = {c.lower() for c in LINEAGE}
    for col in description:
        name, type_code, precision, scale = col[0], col[1], col[4], col[5]
        type_name = getattr(type_code, "name", None) or str(type_code)
        column = bq_column_name(name)
        if column.lower() in seen:
            raise ValueError(f"source column {name!r} collides with another column "
                             "or a lineage column")
        seen.add(column.lower())
        schema[column] = bq_type_for(type_name, precision, scale)
    return schema


def batch_schema(source: Mapping[str, str]) -> dict[str, str]:
    """Landed shape: source columns, then lineage columns."""
    return {**source, **LINEAGE_SCHEMA}


def schema_fingerprint(schema: Mapping[str, str]) -> str:
    """sha256 of {column: type}, independent of column order."""
    canonical = json.dumps(sorted([str(k), str(v)] for k, v in schema.items()),
                           separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def schema_to_json(schema: Mapping[str, str]) -> str:
    return json.dumps([{"name": k, "type": v} for k, v in schema.items()],
                      separators=(",", ":"))


def schema_from_json(text: str) -> dict[str, str]:
    data = json.loads(text)
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items()}
    return {str(c["name"]): str(c["type"]) for c in data}


def classify_drift(previous: Mapping[str, str] | None,
                   current: Mapping[str, str]) -> tuple[str, list[str]]:
    """Classify source-schema drift. Pure.

    A new column is additive. A removed column or a changed type is breaking,
    except widening (INT64 -> NUMERIC/BIGNUMERIC, NUMERIC -> BIGNUMERIC), which is
    additive. With no previous schema the current one is the baseline: ('none', []).
    """
    if previous is None:
        return "none", []
    breaking: list[str] = []
    additive: list[str] = []
    for column in sorted(previous):
        old = previous[column]
        if column not in current:
            breaking.append(f"removed column {column} ({old})")
        elif current[column] != old:
            new = current[column]
            if (old, new) in WIDENING:
                additive.append(f"widened column {column}: {old} -> {new}")
            else:
                breaking.append(f"changed type of {column}: {old} -> {new}")
    for column in sorted(set(current) - set(previous)):
        additive.append(f"added column {column} ({current[column]})")
    kind = "breaking" if breaking else ("additive" if additive else "none")
    return kind, breaking + additive


class SchemaConflict(ValueError):
    """The landed raw table cannot accept the batch schema."""


def evolution_ddl(table_ref: str, existing: Mapping[str, str],
                  desired: Mapping[str, str]) -> list[str]:
    """ALTER statements that let `table_ref` accept `desired`; SchemaConflict if none can.

    Runs before the load transaction: BigQuery forbids DDL on permanent tables
    inside one. Both statements are idempotent, so a failed run can repeat them.
    """
    have = {name.lower(): (name, normalise_bq_type(t)) for name, t in existing.items()}
    stmts: list[str] = []
    for column, typ in desired.items():
        found = have.get(column.lower())
        if found is None:
            stmts.append(f"ALTER TABLE `{table_ref}` ADD COLUMN IF NOT EXISTS `{column}` {typ}")
            continue
        name, landed = found
        if landed == typ or (typ, landed) in WIDENING:
            continue                       # same type, or narrower values fit the column
        if (landed, typ) in WIDENING:
            stmts.append(f"ALTER TABLE `{table_ref}` ALTER COLUMN `{name}` SET DATA TYPE {typ}")
        else:
            raise SchemaConflict(f"{table_ref}.{name} is {landed} but the batch has {typ}")
    return stmts


# --------------------------------------------------------------------------- rows

def to_bq_value(value: Any, bq_type: str) -> Any:
    """JSON-safe value for a BigQuery load into a column of `bq_type`."""
    if value is None:
        return None
    if hasattr(value, "read"):                     # LOB locator
        value = value.read()
    if bq_type == "TIMESTAMP" and isinstance(value, datetime):
        return iso_utc(value)
    if bq_type == "DATETIME" and isinstance(value, datetime):
        return value.replace(tzinfo=None).isoformat(sep=" ", timespec="microseconds")
    if bq_type == "INT64":
        if isinstance(value, (Decimal, float)) and value != int(value):
            raise ValueError(f"non-integral value {value!r} for an INT64 column")
        return int(value)
    if bq_type in ("NUMERIC", "BIGNUMERIC"):       # text keeps every decimal digit
        return format(value if isinstance(value, Decimal) else Decimal(str(value)), "f")
    if bq_type == "FLOAT64":
        return float(value)
    if bq_type == "BOOL":
        return bool(value)
    if bq_type == "BYTES":
        raw = value if isinstance(value, bytes) else str(value).encode("utf-8")
        return base64.b64encode(raw).decode("ascii")
    if bq_type == "JSON":
        return json.loads(value) if isinstance(value, str) else value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else str(value)


def _column_index(columns: Sequence[str], name: str) -> int:
    wanted = bq_column_name(name).lower()
    for i, column in enumerate(columns):
        if column.lower() == wanted:
            return i
    raise ValueError(f"column {name!r} is not in the source result")


def decorate(rows: Iterable[Sequence[Any]], source: Mapping[str, str],
             natural_key: Sequence[str], *, batch_id: str, source_system: str,
             ingest_ts: datetime, op: str = "upsert") -> list[dict]:
    """Cursor rows -> load rows: typed values plus the lineage columns."""
    columns = list(source)
    types = [source[c] for c in columns]
    keys = [_column_index(columns, k) for k in natural_key]
    ingest = iso_utc(ingest_ts)
    out = []
    for row in rows:
        values = [to_bq_value(v, t) for v, t in zip(row, types)]
        pk = "|".join("" if values[i] is None else str(values[i]) for i in keys)
        record = dict(zip(columns, values))
        record.update({
            "_ingest_ts": ingest,
            "_batch_id": batch_id,
            "_source_system": source_system,
            "_op": op,
            "_source_pk_hash": hashlib.sha256(pk.encode("utf-8")).hexdigest(),
        })
        out.append(record)
    return out


def batch_watermark_high(rows: Sequence[Sequence[Any]], source: Mapping[str, str],
                         watermark_column: str) -> datetime:
    """Highest source change timestamp in the batch, full precision, UTC."""
    i = _column_index(list(source), watermark_column)
    values = [r[i] for r in rows if r[i] is not None]
    if not values:
        raise ValueError(f"{watermark_column} is NULL on every extracted row")
    if not all(isinstance(v, datetime) for v in values):
        raise TypeError(f"{watermark_column} must be a DATE or TIMESTAMP column")
    return max(parse_ts(v) for v in values)


def content_checksum(rows: Iterable[Mapping[str, Any]],
                     exclude: Iterable[str] = LINEAGE) -> str:
    """Order-independent sha256 over source values; replaying a window reproduces it."""
    skip = set(exclude)
    digests = sorted(
        hashlib.sha256(json.dumps({k: v for k, v in r.items() if k not in skip},
                                  sort_keys=True, separators=(",", ":"),
                                  default=str).encode("utf-8")).hexdigest()
        for r in rows)
    return "sha256:" + hashlib.sha256("\n".join(digests).encode("utf-8")).hexdigest()


def ndjson_bytes(rows: Sequence[Mapping[str, Any]]) -> int:
    """Size of the newline-delimited JSON payload sent to BigQuery."""
    body = sum(len(json.dumps(r, ensure_ascii=False).encode("utf-8")) for r in rows)
    return body + max(len(rows) - 1, 0)


# --------------------------------------------------------------------------- manifest

class ManifestInvalid(ValueError):
    """A manifest does not conform to landing-manifest.v1."""


def build_manifest(*, batch_id: str, source_system: str, entity: str,
                   ingest_ts: str | datetime, row_count: int,
                   watermark_low: str | datetime | None,
                   watermark_high: str | datetime | None,
                   fingerprint: str | None, drift: str | None = None,
                   status: str | None = None, byte_count: int | None = None,
                   checksum: str | None = None, uri_prefix: str | None = None,
                   requirement_ids: Sequence[str] = REQUIREMENT_IDS) -> dict:
    """A landing-manifest.v1 document. Timestamps are ISO 8601 UTC with microseconds."""
    if drift not in (None,) + DRIFT_KINDS:
        raise ValueError(f"drift must be one of {DRIFT_KINDS} or None, not {drift!r}")
    if status not in (None,) + STATUSES:
        raise ValueError(f"status must be one of {STATUSES} or None, not {status!r}")

    def ts(v: str | datetime | None) -> str | None:
        return None if v is None else iso_utc(v)

    return {
        "batch_id": batch_id,
        "source_system": source_system,
        "entity": entity,
        "ingest_ts": iso_utc(ingest_ts),
        "watermark_low": ts(watermark_low),
        "watermark_high": ts(watermark_high),
        "row_count": int(row_count),
        "byte_count": byte_count,
        "checksum": checksum,
        "schema_fingerprint": fingerprint,
        "uri_prefix": uri_prefix,
        "drift": drift,
        "status": status,
        "brd_requirement_id": list(requirement_ids),
    }


def find_contracts_dir() -> Path | None:
    """$DPF_CONTRACTS_DIR, else the nearest contracts/ directory above this file."""
    env = os.environ.get("DPF_CONTRACTS_DIR")
    if env:
        path = Path(env)
        return path if (path / MANIFEST_SCHEMA).is_file() else None
    here = Path(__file__).resolve().parent
    for directory in (here, *here.parents):
        if (directory / "contracts" / MANIFEST_SCHEMA).is_file():
            return directory / "contracts"
    return None


@lru_cache(maxsize=4)
def _manifest_validator(contracts_dir: str):
    import jsonschema

    root = Path(contracts_dir)
    schema = json.loads((root / MANIFEST_SCHEMA).read_text())
    docs = {}
    for path in sorted(root.glob("*.schema.json")):    # cross-file $refs by $id
        doc = json.loads(path.read_text())
        if isinstance(doc, dict) and isinstance(doc.get("$id"), str):
            docs[doc["$id"]] = doc
    cls = jsonschema.validators.validator_for(schema)
    format_checker = getattr(cls, "FORMAT_CHECKER", None)
    try:
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ImportError:                                # jsonschema < 4.18
        resolver = jsonschema.RefResolver.from_schema(schema, store=docs)
        return cls(schema, resolver=resolver, format_checker=format_checker)
    registry = Registry().with_resources(
        (uri, Resource.from_contents(doc, default_specification=DRAFT202012))
        for uri, doc in docs.items())
    return cls(schema, registry=registry, format_checker=format_checker)


def validate_manifest(manifest: Mapping[str, Any],
                      contracts_dir: str | Path | None = None) -> bool:
    """Validate against landing-manifest.v1 if jsonschema is importable.

    Returns True when validated, False when skipped; raises ManifestInvalid.
    """
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return False
    root = Path(contracts_dir) if contracts_dir else find_contracts_dir()
    if root is None:
        _warn_once(f"{MANIFEST_SCHEMA} not found; manifests not validated "
                   "(set DPF_CONTRACTS_DIR)")
        return False
    errors = sorted(_manifest_validator(str(root.resolve())).iter_errors(dict(manifest)),
                    key=lambda e: [str(p) for p in e.absolute_path])
    if errors:
        raise ManifestInvalid("; ".join(
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}"
            for e in errors))
    return True


# --------------------------------------------------------------------------- SQL

class Target:
    """BigQuery locations from config.target."""

    def __init__(self, project: str, location: str, raw_dataset: str,
                 control_dataset: str):
        self.project = project
        self.location = location
        self.raw_dataset = raw_dataset
        self.control_dataset = control_dataset

    @classmethod
    def from_config(cls, cfg: Mapping[str, Any]) -> Target:
        t = cfg["target"]
        return cls(t["project"], t["location"], t["raw_dataset"], t["control_dataset"])

    def raw(self, table: str) -> str:
        return f"{self.project}.{self.raw_dataset}.{table}"

    def ctl(self, table: str) -> str:
        return f"{self.project}.{self.control_dataset}.{table}"


def load_table_name(entity: str, batch_id: str) -> str:
    return f"raw_{entity}__load_{batch_id.rsplit('-', 1)[-1]}"


def quarantine_table_name(entity: str) -> str:
    return f"raw_{entity}__quarantine"


def control_tables_ddl(t: Target) -> str:
    return f"""
CREATE TABLE IF NOT EXISTS `{t.ctl('extract_watermark')}` (
  source_system STRING, entity STRING, watermark_high TIMESTAMP,
  batch_id STRING, row_count INT64, updated_at TIMESTAMP
)
OPTIONS (description = 'One row per committed batch. MAX(watermark_high) per entity is the watermark.');

CREATE TABLE IF NOT EXISTS `{t.ctl('landing_manifest')}` (
  batch_id STRING NOT NULL, source_system STRING NOT NULL, entity STRING NOT NULL,
  ingest_ts TIMESTAMP NOT NULL, row_count INT64 NOT NULL,
  watermark_low TIMESTAMP, watermark_high TIMESTAMP,
  schema_fingerprint STRING, drift STRING, status STRING NOT NULL,
  manifest JSON, recorded_at TIMESTAMP NOT NULL
)
CLUSTER BY source_system, entity
OPTIONS (description = 'One landing-manifest.v1 per batch. A batch without a row here is not consumable.');

CREATE TABLE IF NOT EXISTS `{t.ctl('schema_registry')}` (
  source_system STRING NOT NULL, entity STRING NOT NULL, fingerprint STRING NOT NULL,
  schema_json JSON, recorded_at TIMESTAMP NOT NULL, batch_id STRING
)
CLUSTER BY source_system, entity
OPTIONS (description = 'Accepted source schema per entity. The latest recorded_at wins.');
""".strip()


def raw_table_ddl(table_ref: str, schema: Mapping[str, str], description: str) -> str:
    columns = ",\n".join(f"  `{c}` {t}" for c, t in schema.items())
    return (f"CREATE TABLE IF NOT EXISTS `{table_ref}` (\n{columns}\n)\n"
            "PARTITION BY DATE(_ingest_ts)\n"
            "CLUSTER BY _source_pk_hash\n"
            f"OPTIONS (description = {json.dumps(description)})")


def quarantine_table_ddl(table_ref: str) -> str:
    lineage = ",\n".join(f"  `{c}` {t}" for c, t in LINEAGE_SCHEMA.items())
    return (f"CREATE TABLE IF NOT EXISTS `{table_ref}` (\n{lineage},\n"
            "  `_schema_fingerprint` STRING,\n  `_drift_changes` ARRAY<STRING>,\n"
            "  `payload` JSON\n)\n"
            "PARTITION BY DATE(_ingest_ts)\n"
            "CLUSTER BY _batch_id\n"
            "OPTIONS (description = 'Batches held back by breaking schema drift. "
            "Source rows as JSON. Not consumed downstream.')")


def _assert_staged(load_ref: str) -> str:
    return (f"ASSERT (SELECT COUNT(*) FROM `{load_ref}`) = @expected_rows\n"
            "  AS 'staged row count differs from extracted row count';")


_ASSERT_INSERTED = ("ASSERT @@row_count = @expected_rows\n"
                    "  AS 'inserted row count differs from extracted row count';")


def _manifest_insert(t: Target) -> str:
    return (f"INSERT INTO `{t.ctl('landing_manifest')}`\n"
            "  (batch_id, source_system, entity, ingest_ts, row_count, watermark_low,\n"
            "   watermark_high, schema_fingerprint, drift, status, manifest, recorded_at)\n"
            "VALUES (@batch_id, @source_system, @entity, @ingest_ts, @expected_rows,\n"
            "   @watermark_low, @watermark_high, @schema_fingerprint, @drift, @status,\n"
            "   PARSE_JSON(@manifest_json), CURRENT_TIMESTAMP());")


def _schema_insert(t: Target) -> str:
    return (f"INSERT INTO `{t.ctl('schema_registry')}`\n"
            "  (source_system, entity, fingerprint, schema_json, recorded_at, batch_id)\n"
            "VALUES (@source_system, @entity, @schema_fingerprint, PARSE_JSON(@schema_json),\n"
            "   CURRENT_TIMESTAMP(), @batch_id);")


def build_land_sql(t: Target, entity: str, load_ref: str, columns: Sequence[str],
                   record_schema: bool) -> str:
    """ONE transaction: raw rows + watermark + manifest (+ accepted schema).

    Without session mode, any error before COMMIT (including a failed ASSERT) makes
    BigQuery roll the whole transaction back, so nothing is half-written.
    """
    raw_ref = t.raw(f"raw_{entity}")
    cols = ", ".join(f"`{c}`" for c in columns)
    parts = [
        "BEGIN TRANSACTION;",
        _assert_staged(load_ref),
        f"INSERT INTO `{raw_ref}` ({cols})\nSELECT {cols} FROM `{load_ref}`;",
        _ASSERT_INSERTED,
        f"INSERT INTO `{t.ctl('extract_watermark')}`\n"
        "  (source_system, entity, watermark_high, batch_id, row_count, updated_at)\n"
        "VALUES (@source_system, @entity, @new_watermark, @batch_id, @expected_rows,\n"
        "   CURRENT_TIMESTAMP());",
        _manifest_insert(t),
    ]
    if record_schema:
        parts.append(_schema_insert(t))
    parts.append("COMMIT TRANSACTION;")
    return "\n".join(parts)


def build_quarantine_sql(t: Target, entity: str, load_ref: str) -> str:
    """ONE transaction: quarantined rows + manifest. The watermark is NOT touched."""
    quarantine_ref = t.raw(quarantine_table_name(entity))
    lineage = ", ".join(LINEAGE)
    return "\n".join([
        "BEGIN TRANSACTION;",
        _assert_staged(load_ref),
        f"INSERT INTO `{quarantine_ref}`\n"
        f"  ({lineage}, _schema_fingerprint, _drift_changes, payload)\n"
        f"SELECT {lineage}, @schema_fingerprint, @drift_changes,\n"
        "  TO_JSON(t, stringify_wide_numbers => TRUE)\n"
        f"FROM `{load_ref}` AS t;",
        _ASSERT_INSERTED,
        _manifest_insert(t),
        "COMMIT TRANSACTION;",
    ])


class Batch:
    """One extracted batch, ready to land or quarantine."""

    def __init__(self, *, entity: str, batch_id: str, source_system: str,
                 rows: list[dict], source: dict[str, str], fingerprint: str,
                 drift: str, changes: list[str], manifest: dict, ingest_ts: datetime,
                 watermark_low: datetime, watermark_high: datetime,
                 new_watermark: datetime, record_schema: bool,
                 ttl_hours: float = DEFAULT_LOAD_TABLE_TTL_HOURS):
        self.entity = entity
        self.batch_id = batch_id
        self.source_system = source_system
        self.rows = rows
        self.source = source
        self.fingerprint = fingerprint
        self.drift = drift
        self.changes = changes
        self.manifest = manifest
        self.ingest_ts = ingest_ts
        self.watermark_low = watermark_low
        self.watermark_high = watermark_high
        self.new_watermark = new_watermark
        self.record_schema = record_schema
        self.ttl_hours = ttl_hours

    @property
    def schema(self) -> dict[str, str]:
        return batch_schema(self.source)


def commit_params(batch: Batch, kind: str) -> list[tuple[str, str, Any]]:
    """(name, type, value) parameters for build_land_sql ('land') or
    build_quarantine_sql ('quarantine')."""
    params: list[tuple[str, str, Any]] = [
        ("source_system", "STRING", batch.source_system),
        ("entity", "STRING", batch.entity),
        ("batch_id", "STRING", batch.batch_id),
        ("expected_rows", "INT64", len(batch.rows)),
        ("ingest_ts", "TIMESTAMP", batch.ingest_ts),
        ("watermark_low", "TIMESTAMP", batch.watermark_low),
        ("watermark_high", "TIMESTAMP", batch.watermark_high),
        ("schema_fingerprint", "STRING", batch.fingerprint),
        ("drift", "STRING", batch.drift),
        ("status", "STRING", batch.manifest["status"]),
        ("manifest_json", "STRING", json.dumps(batch.manifest, separators=(",", ":"))),
    ]
    if kind == "land":
        params.append(("new_watermark", "TIMESTAMP", batch.new_watermark))
        if batch.record_schema:
            params.append(("schema_json", "STRING", schema_to_json(batch.source)))
    elif kind == "quarantine":
        params.append(("drift_changes", "ARRAY<STRING>", list(batch.changes)))
    else:
        raise ValueError(f"unknown commit kind {kind!r}")
    return params


# --------------------------------------------------------------------------- BigQuery I/O

def bq_client(t: Target):
    from google.cloud import bigquery
    return bigquery.Client(project=t.project, location=t.location)


def _query(bq, sql: str, params: Sequence[tuple[str, str, Any]] = (),
           job_id: str | None = None):
    from google.cloud import bigquery
    query_params = []
    for name, typ, value in params:
        if typ.startswith("ARRAY<"):
            query_params.append(bigquery.ArrayQueryParameter(name, typ[6:-1], value))
        else:
            query_params.append(bigquery.ScalarQueryParameter(name, typ, value))
    job = bq.query(sql, job_id=job_id,
                   job_config=bigquery.QueryJobConfig(query_parameters=query_params))
    return job.result()


def ensure_control_tables(bq, t: Target) -> None:
    _query(bq, control_tables_ddl(t))


def read_watermark(bq, t: Target, source_system: str, entity: str) -> datetime | None:
    rows = list(_query(bq, f"""
        SELECT MAX(watermark_high) AS wm FROM `{t.ctl('extract_watermark')}`
        WHERE source_system = @source_system AND entity = @entity""",
        [("source_system", "STRING", source_system), ("entity", "STRING", entity)]))
    wm = rows[0]["wm"] if rows else None
    return parse_ts(wm) if wm else None


def read_registered_schema(bq, t: Target, source_system: str,
                           entity: str) -> tuple[str, dict[str, str]] | None:
    rows = list(_query(bq, f"""
        SELECT fingerprint, TO_JSON_STRING(schema_json) AS schema_json
        FROM `{t.ctl('schema_registry')}`
        WHERE source_system = @source_system AND entity = @entity
        ORDER BY recorded_at DESC LIMIT 1""",
        [("source_system", "STRING", source_system), ("entity", "STRING", entity)]))
    if not rows:
        return None
    return rows[0]["fingerprint"], schema_from_json(rows[0]["schema_json"])


def get_table_schema(bq, ref: str) -> dict[str, str] | None:
    from google.api_core.exceptions import NotFound
    try:
        table = bq.get_table(ref)
    except NotFound:
        return None
    return {f.name: normalise_bq_type(f.field_type) for f in table.schema}


def stage_batch(bq, t: Target, batch: Batch) -> str:
    """Load the batch into its own expiring table and check the loaded row count."""
    from google.cloud import bigquery
    ref = t.raw(load_table_name(batch.entity, batch.batch_id))
    schema = [bigquery.SchemaField(c, typ, mode="NULLABLE")
              for c, typ in batch.schema.items()]
    table = bigquery.Table(ref, schema=schema)
    table.expires = utcnow() + timedelta(hours=batch.ttl_hours)
    table.description = f"Load table for batch {batch.batch_id}. Dropped after commit."
    bq.create_table(table)
    job = bq.load_table_from_json(
        batch.rows, ref, job_id=f"dpf_load_{batch.batch_id}",
        job_config=bigquery.LoadJobConfig(schema=schema, autodetect=False,
                                          write_disposition="WRITE_EMPTY"))
    job.result()
    if job.output_rows != len(batch.rows):
        raise RuntimeError(f"staged {job.output_rows} of {len(batch.rows)} rows into {ref}")
    return ref


def drop_table(bq, ref: str, **fields: Any) -> None:
    try:
        bq.delete_table(ref, not_found_ok=True)
    except Exception as exc:                       # it expires on its own
        log("WARNING", f"could not drop {ref}; it expires automatically",
            error=str(exc), **fields)


def land_batch(bq, t: Target, batch: Batch) -> None:
    """Evolve raw if needed, stage, then commit rows + watermark + manifest atomically."""
    raw_ref = t.raw(f"raw_{batch.entity}")
    existing = get_table_schema(bq, raw_ref)
    if existing is None:
        _query(bq, raw_table_ddl(raw_ref, batch.schema,
                                 f"Append-only raw landing of {batch.source_system} "
                                 f"entity {batch.entity} (skill {SKILL})."))
    else:
        ddl = evolution_ddl(raw_ref, existing, batch.schema)
        if ddl:
            _query(bq, ";\n".join(ddl) + ";")
    load_ref = stage_batch(bq, t, batch)
    _query(bq, build_land_sql(t, batch.entity, load_ref, list(batch.schema),
                              batch.record_schema),
           commit_params(batch, "land"), job_id=f"dpf_commit_{batch.batch_id}")
    drop_table(bq, load_ref, entity=batch.entity, batch_id=batch.batch_id)


def quarantine_batch(bq, t: Target, batch: Batch) -> None:
    """Stage, then commit quarantined rows + manifest atomically. No watermark."""
    _query(bq, quarantine_table_ddl(t.raw(quarantine_table_name(batch.entity))))
    load_ref = stage_batch(bq, t, batch)
    _query(bq, build_quarantine_sql(t, batch.entity, load_ref),
           commit_params(batch, "quarantine"), job_id=f"dpf_quarantine_{batch.batch_id}")
    drop_table(bq, load_ref, entity=batch.entity, batch_id=batch.batch_id)


# --------------------------------------------------------------------------- Oracle I/O

def _env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"environment variable {name} is not set")
    return value


def oracle_connect(cfg: Mapping[str, Any]):
    import oracledb
    src = cfg["source"]
    oracledb.defaults.fetch_decimals = True        # NUMBER -> Decimal, never float
    oracledb.defaults.fetch_lobs = False           # CLOB/BLOB -> str/bytes
    conn = oracledb.connect(user=_env(src["user_env"]),
                            password=_env(src["password_env"]), dsn=src["dsn"])
    with conn.cursor() as cur:                     # zone-less timestamps are UTC
        cur.execute("ALTER SESSION SET TIME_ZONE = 'UTC'")
    return conn


def select_list(description: Sequence[Sequence[Any]]) -> str:
    """`*`, or an explicit list when a column is TIMESTAMP WITH TIME ZONE.

    python-oracledb returns those values as naive wall-clock times in their own
    offset (thin mode rejects named zones); read as UTC they could move the
    watermark past rows not yet extracted. SYS_EXTRACT_UTC returns the UTC instant.
    The BigQuery type (TIMESTAMP) and the schema fingerprint stay the same.
    """
    items, convert = [], False
    for col in description:
        quoted = '"' + str(col[0]).replace('"', '""') + '"'
        type_name = getattr(col[1], "name", None) or str(col[1])
        if _oracle_type_key(type_name) in ("TIMESTAMP_TZ", "TIMESTAMP_WITH_TIME_ZONE"):
            items.append(f"SYS_EXTRACT_UTC({quoted}) AS {quoted}")
            convert = True
        else:
            items.append(quoted)
    return ", ".join(items) if convert else "*"


def fetch(conn, entity: Mapping[str, Any], since: datetime) -> tuple[list, list]:
    """Rows with watermark_column > since, and the cursor description."""
    import oracledb
    table, wm = entity["source_table"], entity["watermark_column"]
    columns = select_list(describe(conn, entity))
    sql = f"SELECT {columns} FROM {table} WHERE {wm} > :since ORDER BY {wm}"
    with conn.cursor() as cur:
        cur.arraysize = 5000
        cur.setinputsizes(since=oracledb.DB_TYPE_TIMESTAMP)   # keep fractional seconds
        cur.execute(sql, since=since.astimezone(UTC).replace(tzinfo=None))
        description = list(cur.description)
        rows = cur.fetchall()
    return rows, description


def describe(conn, entity: Mapping[str, Any]) -> list:
    with conn.cursor() as cur:
        cur.execute(f"SELECT * FROM {entity['source_table']} WHERE 1 = 0")
        return list(cur.description)


# --------------------------------------------------------------------------- config

_ENTITY_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_ORACLE_TABLE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*(\.[A-Za-z][A-Za-z0-9_$#]*)?$")
_ORACLE_COLUMN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_$#]*$")
_DATASET_RE = re.compile(r"^[A-Za-z0-9_]+$")
_PROJECT_RE = re.compile(r"^[a-z0-9][a-z0-9.:-]*$")


def _non_negative(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0


def validate_config(cfg: dict) -> dict:
    """Apply defaults; reject configs that would build unsafe SQL or table names."""
    problems = []
    src, tgt = cfg.get("source") or {}, cfg.get("target") or {}
    for key in ("system_id", "dsn", "user_env", "password_env"):
        if not src.get(key):
            problems.append(f"source.{key} is required")
    for key in ("project", "location", "raw_dataset", "control_dataset"):
        if not tgt.get(key):
            problems.append(f"target.{key} is required")
    if tgt.get("project") and not _PROJECT_RE.match(str(tgt["project"])):
        problems.append("target.project is not a valid project id")
    for key in ("raw_dataset", "control_dataset"):
        if tgt.get(key) and not _DATASET_RE.match(str(tgt[key])):
            problems.append(f"target.{key} is not a valid dataset id")
    cfg.setdefault("lookback_minutes", DEFAULT_LOOKBACK_MINUTES)
    cfg.setdefault("load_table_ttl_hours", DEFAULT_LOAD_TABLE_TTL_HOURS)
    if not _non_negative(cfg["lookback_minutes"]):
        problems.append("lookback_minutes must be a number >= 0")
    if not _non_negative(cfg["load_table_ttl_hours"]) or not cfg["load_table_ttl_hours"]:
        problems.append("load_table_ttl_hours must be a number > 0")
    entities = cfg.get("entities") or []
    if not entities:
        problems.append("entities must list at least one entity")
    names: set = set()
    for i, e in enumerate(entities):
        where = f"entities[{i}]"
        name = str(e.get("name", ""))
        if not _ENTITY_RE.match(name):
            problems.append(f"{where}.name must match {_ENTITY_RE.pattern}")
        elif name in names:
            problems.append(f"{where}.name {name!r} is duplicated")
        names.add(name)
        if not _ORACLE_TABLE_RE.match(str(e.get("source_table", ""))):
            problems.append(f"{where}.source_table must be a plain Oracle [SCHEMA.]TABLE")
        if not _ORACLE_COLUMN_RE.match(str(e.get("watermark_column", ""))):
            problems.append(f"{where}.watermark_column must be a plain Oracle column")
        key = e.get("natural_key") or []
        if not key or not all(_ORACLE_COLUMN_RE.match(str(k)) for k in key):
            problems.append(f"{where}.natural_key must list plain Oracle columns")
        if "lookback_minutes" in e and not _non_negative(e["lookback_minutes"]):
            problems.append(f"{where}.lookback_minutes must be a number >= 0")
    if problems:
        raise ValueError("invalid config: " + "; ".join(problems))
    return cfg


def load_config(path: str | Path | None = None) -> dict:
    import yaml
    return validate_config(yaml.safe_load(Path(path or DEFAULT_CONFIG).read_text()) or {})


# --------------------------------------------------------------------------- run

class RunContext:
    def __init__(self, cfg: Mapping[str, Any], dry: bool):
        self.dry = dry
        self.target = Target.from_config(cfg)
        self.source_system = cfg["source"]["system_id"]
        self.lookback_minutes = cfg["lookback_minutes"]
        self.ttl_hours = cfg["load_table_ttl_hours"]
        self.bq = None
        self.conn = None


def new_batch_id(entity: str) -> str:
    return f"{entity}-{uuid.uuid4().hex[:12]}"


def process_entity(ctx: RunContext, entity: Mapping[str, Any]) -> bool:
    """Extract one entity and land or quarantine it. True on success or no new rows."""
    name = entity["name"]
    batch_id = new_batch_id(name)
    ids = {"source_system": ctx.source_system, "entity": name, "batch_id": batch_id}
    stage = "read_watermark"
    try:
        prev_wm = None if ctx.dry else read_watermark(ctx.bq, ctx.target,
                                                      ctx.source_system, name)
        lookback = entity.get("lookback_minutes", ctx.lookback_minutes)
        since = extraction_since(iso_utc(prev_wm) if prev_wm else None, lookback)

        stage = "extract"
        log("INFO", f"{name}: extracting", dpf_event="extract_started", **ids,
            watermark=iso_utc(prev_wm) if prev_wm else None, since=iso_utc(since),
            lookback_minutes=lookback)
        rows, description = fetch(ctx.conn, entity, since)
        if not rows:
            log("INFO", f"{name}: no new rows", dpf_event="no_new_rows", **ids,
                since=iso_utc(since))
            return True

        stage = "classify_drift"
        source = source_schema(description)
        fingerprint = schema_fingerprint(source)
        registered = None if ctx.dry else read_registered_schema(
            ctx.bq, ctx.target, ctx.source_system, name)
        compared_with = None
        previous = None
        if registered:
            previous, compared_with = registered[1], "schema_registry"
        elif not ctx.dry:                          # registry empty: use the landed table
            landed = get_table_schema(ctx.bq, ctx.target.raw(f"raw_{name}"))
            if landed:
                previous = {c: t for c, t in landed.items() if c not in LINEAGE_SCHEMA}
                compared_with = "raw_table"
        drift, changes = classify_drift(previous, source)

        stage = "prepare"
        ingest_ts = utcnow()
        payload = decorate(rows, source, entity["natural_key"], batch_id=batch_id,
                           source_system=ctx.source_system, ingest_ts=ingest_ts)
        wm_high = batch_watermark_high(rows, source, entity["watermark_column"])
        new_wm = max(prev_wm, wm_high) if prev_wm else wm_high    # never regress
        status = None if ctx.dry else ("quarantined" if drift == "breaking" else "landed")
        manifest = build_manifest(
            batch_id=batch_id, source_system=ctx.source_system, entity=name,
            ingest_ts=ingest_ts, row_count=len(payload), watermark_low=since,
            watermark_high=wm_high, fingerprint=fingerprint,
            drift=None if ctx.dry else drift, status=status,
            byte_count=ndjson_bytes(payload), checksum=content_checksum(payload))
        validate_manifest(manifest)

        if ctx.dry:
            print(json.dumps(manifest, separators=(",", ":")), flush=True)
            log("INFO", f"{name}: dry run, {len(payload)} rows not written",
                dpf_event="dry_run_batch", **ids)
            return True

        batch = Batch(entity=name, batch_id=batch_id, source_system=ctx.source_system,
                      rows=payload, source=source, fingerprint=fingerprint, drift=drift,
                      changes=changes, manifest=manifest, ingest_ts=ingest_ts,
                      watermark_low=since, watermark_high=wm_high, new_watermark=new_wm,
                      record_schema=registered is None or registered[0] != fingerprint,
                      ttl_hours=ctx.ttl_hours)

        if drift == "breaking":
            stage = "quarantine"
            error = None
            try:
                quarantine_batch(ctx.bq, ctx.target, batch)
            except Exception as exc:
                error = exc
            alert("schema_drift_breaking",
                  f"{name}: breaking schema drift; "
                  + ("batch quarantined" if error is None else "QUARANTINE FAILED")
                  + ", watermark not advanced",
                  **ids, changes=changes, quarantined=error is None,
                  quarantine_table=ctx.target.raw(quarantine_table_name(name)),
                  row_count=len(payload), schema_fingerprint=fingerprint,
                  compared_with=compared_with,
                  registered_fingerprint=registered[0] if registered else None)
            if error is not None:
                raise error
            return False

        stage = "land"
        land_batch(ctx.bq, ctx.target, batch)
        if drift == "additive":
            log("INFO", f"{name}: additive schema drift; batch landed, schema recorded",
                dpf_event="schema_drift_additive", **ids, changes=changes,
                schema_fingerprint=fingerprint)
        elif batch.record_schema:
            log("INFO", f"{name}: schema baseline recorded",
                dpf_event="schema_baseline_recorded", **ids,
                schema_fingerprint=fingerprint)
        log("INFO", f"{name}: landed {len(payload)} rows", dpf_event="batch_landed",
            **ids, row_count=len(payload), drift=drift,
            watermark_low=manifest["watermark_low"],
            watermark_high=manifest["watermark_high"], watermark=iso_utc(new_wm))
        return True

    except Exception as exc:                       # nothing committed for this batch
        alert("extract_failed", f"{name}: {stage} failed: {exc}", **ids, stage=stage,
              error=str(exc), error_type=type(exc).__name__)
        return False


def run(cfg: Mapping[str, Any], only: str | None = None, dry: bool = False) -> int:
    """Extract every configured entity (or just `only`). Exit code 0, 1 or 2."""
    source_system = cfg["source"]["system_id"]
    entities = [e for e in cfg["entities"] if not only or e["name"] == only]
    if not entities:
        alert("extract_failed", f"unknown entity {only!r}", source_system=source_system,
              entity=only, batch_id=None, stage="config",
              error=f"unknown entity {only!r}", error_type="ValueError")
        return 2

    ctx = RunContext(cfg, dry)
    stage = "connect_bigquery"
    try:
        if not dry:
            ctx.bq = bq_client(ctx.target)
            stage = "ensure_control_tables"
            ensure_control_tables(ctx.bq, ctx.target)
        stage = "connect_oracle"
        ctx.conn = oracle_connect(cfg)
    except Exception as exc:
        alert("extract_failed", f"{stage} failed: {exc}", source_system=source_system,
              entity=only, batch_id=None, stage=stage, error=str(exc),
              error_type=type(exc).__name__)
        return 1

    failures = 0
    try:
        for entity in entities:
            if not process_entity(ctx, entity):
                failures += 1
    finally:
        try:
            ctx.conn.close()
        except Exception:
            pass
    log("WARNING" if failures else "INFO", "run complete", dpf_event="run_complete",
        source_system=source_system, entities=len(entities), failures=failures,
        dry_run=dry)
    return 1 if failures else 0


def accept_schema(cfg: Mapping[str, Any], entity_name: str, dry: bool = False) -> int:
    """Record the entity's current source schema as accepted (resolves breaking drift).

    Migrate raw_<entity> first if a column changed type; the held window is
    re-read by the next run because the watermark never moved.
    """
    source_system = cfg["source"]["system_id"]
    ids = {"source_system": source_system, "entity": entity_name,
           "batch_id": f"accept-{uuid.uuid4().hex[:12]}"}
    entity = next((e for e in cfg["entities"] if e["name"] == entity_name), None)
    if entity is None:
        alert("extract_failed", f"unknown entity {entity_name!r}", **ids, stage="config",
              error=f"unknown entity {entity_name!r}", error_type="ValueError")
        return 2
    stage = "describe"
    try:
        conn = oracle_connect(cfg)
        try:
            source = source_schema(describe(conn, entity))
        finally:
            conn.close()
        fingerprint = schema_fingerprint(source)
        if dry:
            print(json.dumps({**ids, "fingerprint": fingerprint,
                              "schema": json.loads(schema_to_json(source))}))
            return 0
        stage = "record_schema"
        t = Target.from_config(cfg)
        bq = bq_client(t)
        ensure_control_tables(bq, t)
        _query(bq, _schema_insert(t), [
            ("source_system", "STRING", source_system),
            ("entity", "STRING", entity_name),
            ("schema_fingerprint", "STRING", fingerprint),
            ("schema_json", "STRING", schema_to_json(source)),
            ("batch_id", "STRING", ids["batch_id"]),
        ])
        log("NOTICE", f"{entity_name}: current source schema accepted",
            dpf_event="schema_accepted", **ids, schema_fingerprint=fingerprint)
        return 0
    except Exception as exc:
        alert("extract_failed", f"{entity_name}: {stage} failed: {exc}", **ids,
              stage=stage, error=str(exc), error_type=type(exc).__name__)
        return 1


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Oracle -> BigQuery raw watermark extract (skill extract-rdbms-watermark).")
    ap.add_argument("entity", nargs="?", help="extract only this entity (default: all)")
    ap.add_argument("--dry-run", action="store_true",
                    help="read Oracle only; write nothing to Google Cloud; "
                         "print manifests as JSON lines")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG),
                    help="config file (default: config.yaml beside this script)")
    ap.add_argument("--accept-schema", action="store_true",
                    help="record ENTITY's current source schema as accepted, then exit")
    args = ap.parse_args(argv)
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        alert("extract_failed", f"config: {exc}", source_system=None, entity=args.entity,
              batch_id=None, stage="config", error=str(exc), error_type=type(exc).__name__)
        return 2
    if args.accept_schema:
        if not args.entity:
            ap.error("--accept-schema needs an entity")
        return accept_schema(cfg, args.entity, dry=args.dry_run)
    return run(cfg, args.entity, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
