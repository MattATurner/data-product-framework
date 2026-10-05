"""Unit tests for the Oracle watermark extractor (skill extract-rdbms-watermark).

Pure logic plus the orchestration with Oracle and BigQuery replaced by fakes.
No oracledb, no google-cloud libraries, no network.

    .venv/bin/python -m pytest tests/unit/test_extract_oracle.py -q
"""
from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "examples" / "sales_performance" / "extract" / "extract_oracle.py"
CONTRACTS = ROOT / "contracts"
UTC = timezone.utc
MARKER = "# dpf: skill=extract-rdbms-watermark tier=5 adr=ADR-015 requirements=R-10"


def _load_module():
    spec = importlib.util.spec_from_file_location("dpf_extract_oracle", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


xo = _load_module()


@pytest.fixture(scope="module")
def manifest_validator():
    """landing-manifest.v1 validator; cross-file $refs resolved by $id."""
    import jsonschema
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for path in sorted(CONTRACTS.glob("*.schema.json")):
        doc = json.loads(path.read_text())
        if "$id" in doc:
            resources.append((doc["$id"], Resource.from_contents(
                doc, default_specification=DRAFT202012)))
    schema = json.loads((CONTRACTS / "landing-manifest.v1.schema.json").read_text())
    return jsonschema.Draft202012Validator(
        schema, registry=Registry().with_resources(resources),
        format_checker=jsonschema.Draft202012Validator.FORMAT_CHECKER)


def _errors(validator, doc):
    return [e.message for e in validator.iter_errors(doc)]


# --------------------------------------------------------------------------- module shape

def test_imports_without_oracle_or_google_cloud_libraries():
    assert "oracledb" not in sys.modules
    assert "google.cloud.bigquery" not in sys.modules
    assert not hasattr(xo, "CFG"), "config must not load at import time"


def test_tool_tier_marker_and_docstring():
    head = MODULE_PATH.read_text().splitlines()[:5]
    assert MARKER in head
    assert "Implements skill `extract-rdbms-watermark`" in xo.__doc__
    assert "ADR-015" in xo.__doc__
    assert "autodetect=True" not in MODULE_PATH.read_text()


def test_shipped_config_loads_with_lookback():
    pytest.importorskip("yaml")
    cfg = xo.load_config(xo.DEFAULT_CONFIG)
    assert cfg["lookback_minutes"] == 15
    assert [e["name"] for e in cfg["entities"]] == [
        "orders", "order_lines", "customers", "products"]


def test_config_defaults_and_rejects_unsafe_identifiers():
    cfg = xo.validate_config(_cfg_dict())
    assert cfg["lookback_minutes"] == 15
    bad = _cfg_dict()
    bad["entities"][0]["source_table"] = "SALES.ORDERS; DROP TABLE X"
    bad["lookback_minutes"] = -1
    with pytest.raises(ValueError) as err:
        xo.validate_config(bad)
    assert "lookback_minutes must be a number >= 0" in str(err.value)
    assert "entities[0].source_table must be a plain Oracle" in str(err.value)


# --------------------------------------------------------------------------- drift

BASE = {"ORDER_ID": "STRING", "QTY": "INT64", "LAST_MODIFIED_TS": "TIMESTAMP"}


def test_drift_none_for_identical_schema_in_any_order():
    assert xo.classify_drift(BASE, dict(BASE)) == ("none", [])
    assert xo.classify_drift(BASE, dict(reversed(list(BASE.items())))) == ("none", [])


def test_drift_baseline_when_nothing_registered():
    assert xo.classify_drift(None, BASE) == ("none", [])


def test_drift_additive_new_column():
    current = {**BASE, "DISCOUNT_AMT": "NUMERIC"}
    assert xo.classify_drift(BASE, current) == (
        "additive", ["added column DISCOUNT_AMT (NUMERIC)"])


def test_drift_breaking_removed_column():
    current = {k: v for k, v in BASE.items() if k != "QTY"}
    assert xo.classify_drift(BASE, current) == ("breaking", ["removed column QTY (INT64)"])


@pytest.mark.parametrize("old, new", [
    ("INT64", "STRING"),
    ("TIMESTAMP", "DATETIME"),
    ("NUMERIC", "INT64"),            # narrowing is a type change, not widening
    ("BIGNUMERIC", "NUMERIC"),
    ("INT64", "FLOAT64"),            # lossy for large integers
])
def test_drift_breaking_changed_type(old, new):
    kind, changes = xo.classify_drift({"C": old}, {"C": new})
    assert kind == "breaking"
    assert changes == [f"changed type of C: {old} -> {new}"]


@pytest.mark.parametrize("old, new", [
    ("INT64", "NUMERIC"), ("INT64", "BIGNUMERIC"), ("NUMERIC", "BIGNUMERIC")])
def test_drift_widening_is_additive(old, new):
    assert xo.classify_drift({"C": old}, {"C": new}) == (
        "additive", [f"widened column C: {old} -> {new}"])


def test_drift_breaking_wins_and_lists_every_change():
    previous = {"A": "STRING", "B": "INT64", "C": "INT64"}
    current = {"B": "NUMERIC", "C": "STRING", "D": "DATETIME"}
    kind, changes = xo.classify_drift(previous, current)
    assert kind == "breaking"
    assert changes == [
        "removed column A (STRING)",
        "changed type of C: INT64 -> STRING",
        "widened column B: INT64 -> NUMERIC",
        "added column D (DATETIME)",
    ]


def test_classify_drift_is_pure():
    previous, current = dict(BASE), {**BASE, "X": "STRING"}
    snapshot = (dict(previous), dict(current))
    xo.classify_drift(previous, current)
    assert (previous, current) == snapshot


# --------------------------------------------------------------------------- types

@pytest.mark.parametrize("oracle_type, precision, scale, expected", [
    ("NUMBER", 10, 0, "INT64"),
    ("NUMBER", 18, 0, "INT64"),
    ("NUMBER", 10, None, "INT64"),               # NUMBER(10) == NUMBER(10,0)
    ("DB_TYPE_NUMBER", 9, 0, "INT64"),           # python-oracledb type name
    ("NUMBER", 19, 0, "NUMERIC"),
    ("NUMBER", 12, 2, "NUMERIC"),
    ("NUMBER", 38, 9, "NUMERIC"),
    ("NUMBER", 0, -127, "NUMERIC"),              # unconstrained NUMBER (oracledb)
    ("NUMBER", None, None, "NUMERIC"),
    ("NUMBER", 38, 0, "BIGNUMERIC"),             # beyond NUMERIC's 29 integer digits
    ("NUMBER", 20, 12, "BIGNUMERIC"),            # beyond NUMERIC's scale of 9
    ("NUMBER", 126, -127, "FLOAT64"),            # FLOAT(126)
    ("BINARY_DOUBLE", None, None, "FLOAT64"),
    ("VARCHAR2", None, None, "STRING"),
    ("DB_TYPE_VARCHAR", None, None, "STRING"),
    ("CHAR", None, None, "STRING"),
    ("NVARCHAR2", None, None, "STRING"),
    ("CLOB", None, None, "STRING"),
    ("DB_TYPE_CLOB", None, None, "STRING"),
    ("DATE", None, None, "DATETIME"),
    ("DB_TYPE_DATE", None, None, "DATETIME"),
    ("TIMESTAMP", None, 6, "TIMESTAMP"),
    ("TIMESTAMP(6)", None, None, "TIMESTAMP"),
    ("DB_TYPE_TIMESTAMP", 0, 6, "TIMESTAMP"),
    ("TIMESTAMP(6) WITH TIME ZONE", None, None, "TIMESTAMP"),
    ("DB_TYPE_TIMESTAMP_TZ", None, None, "TIMESTAMP"),
    ("DB_TYPE_TIMESTAMP_LTZ", None, None, "TIMESTAMP"),
    ("RAW", None, None, "BYTES"),
    ("BLOB", None, None, "BYTES"),
    ("SOMETHING_NEW", None, None, "STRING"),
])
def test_bq_type_for(oracle_type, precision, scale, expected):
    assert xo.bq_type_for(oracle_type, precision, scale) == expected


class FakeDbType:
    def __init__(self, name):
        self.name = name


DESCRIPTION = [  # DB-API 7-tuples as python-oracledb reports them
    ("ORDER_ID", FakeDbType("DB_TYPE_VARCHAR"), 20, 20, None, None, False),
    ("LINE_NO", FakeDbType("DB_TYPE_NUMBER"), 11, None, 10, 0, False),
    ("GROSS_AMT", FakeDbType("DB_TYPE_NUMBER"), 15, None, 12, 2, True),
    ("ORDER_DT", FakeDbType("DB_TYPE_DATE"), 23, None, None, None, True),
    ("LAST_MODIFIED_TS", FakeDbType("DB_TYPE_TIMESTAMP"), 23, None, 0, 6, True),
]


def test_source_schema_from_cursor_description():
    schema = xo.source_schema(DESCRIPTION)
    assert schema == {"ORDER_ID": "STRING", "LINE_NO": "INT64", "GROSS_AMT": "NUMERIC",
                      "ORDER_DT": "DATETIME", "LAST_MODIFIED_TS": "TIMESTAMP"}
    assert list(schema) == [d[0] for d in DESCRIPTION]          # source order kept
    full = xo.batch_schema(schema)
    assert {k: full[k] for k in xo.LINEAGE} == {
        "_ingest_ts": "TIMESTAMP", "_batch_id": "STRING", "_source_system": "STRING",
        "_op": "STRING", "_source_pk_hash": "STRING"}


def test_source_column_colliding_with_lineage_is_rejected():
    with pytest.raises(ValueError, match="lineage"):
        xo.source_schema([("_BATCH_ID", "VARCHAR2", None, None, None, None, True)])


def test_evolution_ddl_adds_and_widens_but_refuses_conflicts():
    ref = "p.raw_ds.raw_orders"
    existing = {"order_id": "STRING", "QTY": "INTEGER", "AMT": "NUMERIC"}   # API names
    desired = {"ORDER_ID": "STRING", "QTY": "NUMERIC", "AMT": "INT64", "NOTE": "STRING"}
    assert xo.evolution_ddl(ref, existing, desired) == [
        "ALTER TABLE `p.raw_ds.raw_orders` ALTER COLUMN `QTY` SET DATA TYPE NUMERIC",
        "ALTER TABLE `p.raw_ds.raw_orders` ADD COLUMN IF NOT EXISTS `NOTE` STRING",
    ]
    with pytest.raises(xo.SchemaConflict):
        xo.evolution_ddl(ref, {"QTY": "STRING"}, {"QTY": "INT64"})


# --------------------------------------------------------------------------- watermark

def test_lookback_keeps_microseconds():
    since = xo.extraction_since("2026-03-10T10:00:00.123456+00:00", 15)
    assert since == datetime(2026, 3, 10, 9, 45, 0, 123456, tzinfo=UTC)
    assert xo.iso_utc(since) == "2026-03-10T09:45:00.123456+00:00"


@pytest.mark.parametrize("watermark", [
    "2026-03-10T20:00:00.000001+10:00",          # offset normalised to UTC
    "2026-03-10T10:00:00.000001Z",
    "2026-03-10T10:00:00.000001",                # naive is UTC by convention
])
def test_lookback_normalises_to_utc(watermark):
    since = xo.extraction_since(watermark, 15)
    assert xo.iso_utc(since) == "2026-03-10T09:45:00.000001+00:00"


def test_lookback_edges():
    assert xo.extraction_since(None, 15) == xo.EPOCH
    assert xo.extraction_since("2026-03-10T10:00:00.5+00:00", 0) == datetime(
        2026, 3, 10, 10, 0, 0, 500000, tzinfo=UTC)
    with pytest.raises(ValueError):
        xo.extraction_since("2026-03-10T10:00:00+00:00", -1)


def test_iso_utc_always_writes_microseconds():
    assert xo.iso_utc(datetime(2026, 3, 10, 10, 0, tzinfo=UTC)) == \
        "2026-03-10T10:00:00.000000+00:00"


def test_batch_watermark_high_keeps_precision_and_ignores_nulls():
    source = {"ID": "STRING", "TS": "TIMESTAMP"}
    rows = [("a", datetime(2026, 3, 12, 16, 45, 0, 123456)),
            ("b", None),
            ("c", datetime(2026, 3, 12, 16, 45, 0, 123457))]
    assert xo.batch_watermark_high(rows, source, "TS") == datetime(
        2026, 3, 12, 16, 45, 0, 123457, tzinfo=UTC)
    with pytest.raises(TypeError):
        xo.batch_watermark_high([("a", "2026-03-12")], source, "TS")


class FakeOracleCursor:
    def __init__(self, conn):
        self.conn, self.arraysize, self.description = conn, 100, None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def setinputsizes(self, **sizes):
        self.conn.input_sizes = sizes

    def execute(self, sql, **binds):
        self.conn.executed.append((sql, binds))
        self.description = self.conn.description

    def fetchall(self):
        return list(self.conn.rows)


class FakeOracleConnection:
    def __init__(self, description, rows=()):
        self.description, self.rows = description, rows
        self.executed, self.input_sizes = [], None

    def cursor(self):
        return FakeOracleCursor(self)


def test_select_list_reads_timestamp_with_time_zone_as_utc():
    assert xo.select_list(DESCRIPTION) == "*"
    assert xo.select_list([
        ("ID", FakeDbType("DB_TYPE_VARCHAR"), 20, 20, None, None, False),
        ("LTZ", FakeDbType("DB_TYPE_TIMESTAMP_LTZ"), 23, None, 0, 6, True),  # session UTC
        ("TS", FakeDbType("DB_TYPE_TIMESTAMP_TZ"), 23, None, 0, 6, True),
    ]) == '"ID", "LTZ", SYS_EXTRACT_UTC("TS") AS "TS"'


def test_fetch_binds_an_oracle_timestamp_with_microseconds(monkeypatch):
    monkeypatch.setitem(sys.modules, "oracledb",
                        SimpleNamespace(DB_TYPE_TIMESTAMP="DB_TYPE_TIMESTAMP"))
    description = [
        ("ORDER_ID", FakeDbType("DB_TYPE_VARCHAR"), 20, 20, None, None, False),
        ("LAST_MODIFIED_TS", FakeDbType("DB_TYPE_TIMESTAMP_TZ"), 23, None, 0, 6, True),
    ]
    conn = FakeOracleConnection(description, rows=[("SO-1", datetime(2026, 3, 10, 10, 0))])
    entity = {"name": "orders", "source_table": "SALES.ORDERS",
              "watermark_column": "LAST_MODIFIED_TS", "natural_key": ["ORDER_ID"]}
    since = datetime(2026, 3, 10, 20, 45, 0, 123456, tzinfo=timezone(timedelta(hours=10)))

    rows, desc = xo.fetch(conn, entity, since)

    (describe_sql, _), (sql, binds) = conn.executed
    assert describe_sql == "SELECT * FROM SALES.ORDERS WHERE 1 = 0"
    assert sql == ('SELECT "ORDER_ID", SYS_EXTRACT_UTC("LAST_MODIFIED_TS") AS '
                   '"LAST_MODIFIED_TS" FROM SALES.ORDERS '
                   "WHERE LAST_MODIFIED_TS > :since ORDER BY LAST_MODIFIED_TS")
    assert conn.input_sizes == {"since": "DB_TYPE_TIMESTAMP"}     # a DATE bind drops fractions
    assert binds == {"since": datetime(2026, 3, 10, 10, 45, 0, 123456)}   # naive UTC
    assert rows == [("SO-1", datetime(2026, 3, 10, 10, 0))] and desc == description


# --------------------------------------------------------------------------- rows

INGEST = datetime(2026, 10, 2, 1, 0, 0, 654321, tzinfo=UTC)
SOURCE = {"ORDER_ID": "STRING", "LINE_NO": "INT64", "GROSS_AMT": "NUMERIC",
          "ORDER_DT": "DATETIME", "LAST_MODIFIED_TS": "TIMESTAMP"}
ROWS = [
    ("SO-1001", Decimal("2"), Decimal("900.00"), datetime(2026, 3, 10),
     datetime(2026, 3, 12, 16, 45, 0, 123456)),
    ("SO-1001", Decimal("1"), Decimal("1000.00"), datetime(2026, 3, 10),
     datetime(2026, 3, 10, 10, 0, 0)),
]


def test_decorate_types_values_and_adds_lineage():
    out = xo.decorate(ROWS, SOURCE, ["ORDER_ID", "LINE_NO"], batch_id="order_lines-abc",
                      source_system="ora_local", ingest_ts=INGEST)
    first = out[0]
    assert first["LINE_NO"] == 2
    assert first["GROSS_AMT"] == "900.00"                  # decimal text, no float
    assert first["ORDER_DT"] == "2026-03-10 00:00:00.000000"
    assert first["LAST_MODIFIED_TS"] == "2026-03-12T16:45:00.123456+00:00"
    assert first["_ingest_ts"] == "2026-10-02T01:00:00.654321+00:00"
    assert (first["_batch_id"], first["_source_system"], first["_op"]) == (
        "order_lines-abc", "ora_local", "upsert")
    assert first["_source_pk_hash"] != out[1]["_source_pk_hash"]
    again = xo.decorate(ROWS[:1], SOURCE, ["ORDER_ID", "LINE_NO"], batch_id="x",
                        source_system="ora_local", ingest_ts=INGEST)
    assert again[0]["_source_pk_hash"] == first["_source_pk_hash"]
    with pytest.raises(ValueError, match="NOT_A_COLUMN"):
        xo.decorate(ROWS, SOURCE, ["NOT_A_COLUMN"], batch_id="x",
                    source_system="ora_local", ingest_ts=INGEST)


def test_content_checksum_is_order_independent_and_ignores_lineage():
    a = xo.decorate(ROWS, SOURCE, ["ORDER_ID"], batch_id="b1",
                    source_system="ora_local", ingest_ts=INGEST)
    b = xo.decorate(list(reversed(ROWS)), SOURCE, ["ORDER_ID"], batch_id="b2",
                    source_system="ora_local", ingest_ts=INGEST + timedelta(hours=1))
    assert xo.content_checksum(a) == xo.content_checksum(b)
    b[0]["GROSS_AMT"] = "1.00"
    assert xo.content_checksum(a) != xo.content_checksum(b)


# --------------------------------------------------------------------------- fingerprint

def test_schema_fingerprint_is_deterministic():
    fp = xo.schema_fingerprint(BASE)
    assert re.fullmatch(r"[0-9a-f]{64}", fp)
    assert xo.schema_fingerprint(dict(reversed(list(BASE.items())))) == fp
    assert xo.schema_fingerprint(dict(BASE)) == fp
    assert xo.schema_fingerprint({**BASE, "QTY": "NUMERIC"}) != fp
    assert xo.schema_fingerprint({**BASE, "NEW": "STRING"}) != fp


def test_schema_json_round_trip():
    assert xo.schema_from_json(xo.schema_to_json(SOURCE)) == SOURCE


# --------------------------------------------------------------------------- manifest

def _manifest(**overrides):
    kw = dict(batch_id="orders-0123456789ab", source_system="ora_local", entity="orders",
              ingest_ts=INGEST, row_count=2,
              watermark_low=datetime(2026, 3, 12, 16, 30, 0, 123456, tzinfo=UTC),
              watermark_high=datetime(2026, 3, 12, 16, 45, 0, 123457, tzinfo=UTC),
              fingerprint=xo.schema_fingerprint(BASE), drift="none", status="landed",
              byte_count=512, checksum="sha256:" + "0" * 64)
    kw.update(overrides)
    return xo.build_manifest(**kw)


@pytest.mark.parametrize("drift, status", [
    ("none", "landed"), ("additive", "landed"), ("breaking", "quarantined"),
    (None, None)])                                          # dry run
def test_manifest_validates_against_contract(manifest_validator, drift, status):
    m = _manifest(drift=drift, status=status)
    assert _errors(manifest_validator, m) == []
    assert m["brd_requirement_id"] == ["R-10"]
    assert m["watermark_high"] == "2026-03-12T16:45:00.123457+00:00"
    assert m["watermark_low"] == "2026-03-12T16:30:00.123456+00:00"
    assert m["ingest_ts"] == "2026-10-02T01:00:00.654321+00:00"


def test_module_validation_accepts_good_and_rejects_bad_manifests(manifest_validator):
    assert xo.validate_manifest(_manifest(), contracts_dir=CONTRACTS) is True
    assert xo.validate_manifest(_manifest()) is True          # finds contracts/ itself
    for bad in (dict(_manifest(), status="failed"),
                dict(_manifest(), brd_requirement_id=["10"]),
                dict(_manifest(), unexpected="field")):
        assert _errors(manifest_validator, bad)
        with pytest.raises(xo.ManifestInvalid):
            xo.validate_manifest(bad, contracts_dir=CONTRACTS)


def test_build_manifest_rejects_unknown_drift():
    with pytest.raises(ValueError):
        _manifest(drift="sideways")


# --------------------------------------------------------------------------- SQL

TARGET = xo.Target("p", "us-central1", "raw_ds", "ctl_ds")
LOAD_REF = "p.raw_ds.raw_orders__load_0123456789ab"


def _batch(record_schema=True, drift="none", status="landed", changes=()):
    source = {"ORDER_ID": "STRING", "QTY": "INT64", "LAST_MODIFIED_TS": "TIMESTAMP"}
    rows = xo.decorate([("SO-1", Decimal("6"), datetime(2026, 3, 12, 16, 45))], source,
                       ["ORDER_ID"], batch_id="orders-0123456789ab",
                       source_system="ora_local", ingest_ts=INGEST)
    wm = datetime(2026, 3, 12, 16, 45, tzinfo=UTC)
    return xo.Batch(entity="orders", batch_id="orders-0123456789ab",
                    source_system="ora_local", rows=rows, source=source,
                    fingerprint=xo.schema_fingerprint(source), drift=drift,
                    changes=list(changes), manifest=_manifest(drift=drift, status=status),
                    ingest_ts=INGEST, watermark_low=wm - timedelta(minutes=15),
                    watermark_high=wm, new_watermark=wm, record_schema=record_schema)


def _params_in(sql):
    return set(re.findall(r"(?<!@)@([A-Za-z_]\w*)", sql))


def _positions(sql, *needles):
    return [sql.index(n) for n in needles]


@pytest.mark.parametrize("record_schema", [True, False])
def test_land_sql_is_one_transaction_with_asserts(record_schema):
    sql = xo.build_land_sql(TARGET, "orders", LOAD_REF,
                            list(xo.batch_schema(_batch().source)), record_schema)
    assert sql.startswith("BEGIN TRANSACTION;")
    assert sql.endswith("COMMIT TRANSACTION;")
    assert sql.count("BEGIN TRANSACTION") == sql.count("COMMIT TRANSACTION") == 1
    order = _positions(sql, "ASSERT (SELECT COUNT(*) FROM `" + LOAD_REF,
                       "INSERT INTO `p.raw_ds.raw_orders` (",
                       "ASSERT @@row_count = @expected_rows",
                       "INSERT INTO `p.ctl_ds.extract_watermark`",
                       "INSERT INTO `p.ctl_ds.landing_manifest`",
                       "COMMIT TRANSACTION")
    assert order == sorted(order)
    assert ("schema_registry" in sql) is record_schema
    assert not re.search(r"\b(CREATE|ALTER|DROP)\b", sql)    # no DDL in a transaction
    batch = _batch(record_schema=record_schema)
    assert _params_in(sql) == {n for n, _, _ in xo.commit_params(batch, "land")}


def test_quarantine_sql_never_advances_the_watermark():
    sql = xo.build_quarantine_sql(TARGET, "orders", LOAD_REF)
    assert sql.startswith("BEGIN TRANSACTION;") and sql.endswith("COMMIT TRANSACTION;")
    assert "INSERT INTO `p.raw_ds.raw_orders__quarantine`" in sql
    assert "INSERT INTO `p.ctl_ds.landing_manifest`" in sql
    assert "extract_watermark" not in sql
    assert "schema_registry" not in sql
    assert "`p.raw_ds.raw_orders`" not in sql
    assert "ASSERT @@row_count = @expected_rows" in sql
    batch = _batch(drift="breaking", status="quarantined", changes=["removed column X"])
    assert _params_in(sql) == {n for n, _, _ in xo.commit_params(batch, "quarantine")}


def test_control_table_ddl_creates_all_three_tables():
    ddl = xo.control_tables_ddl(TARGET)
    for table in ("extract_watermark", "landing_manifest", "schema_registry"):
        assert f"CREATE TABLE IF NOT EXISTS `p.ctl_ds.{table}`" in ddl
    for column in ("batch_id", "source_system", "entity", "ingest_ts", "row_count",
                   "watermark_low", "watermark_high", "schema_fingerprint", "status",
                   "manifest JSON"):
        assert column in ddl


def test_load_table_name():
    assert xo.load_table_name("order_lines", "order_lines-0123456789ab") == \
        "raw_order_lines__load_0123456789ab"


# --------------------------------------------------------------------------- logging

def test_alert_is_one_structured_json_line(capsys):
    xo.alert("schema_drift_breaking", "orders: breaking drift", source_system="ora_local",
             entity="orders", batch_id="orders-abc", changes=["removed column QTY (INT64)"])
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["severity"] == "ERROR"
    assert entry["dpf_alert"] == "schema_drift_breaking"
    assert (entry["source_system"], entry["entity"], entry["batch_id"]) == (
        "ora_local", "orders", "orders-abc")
    assert entry["changes"] == ["removed column QTY (INT64)"]


# --------------------------------------------------------------------------- orchestration

def _cfg_dict():
    return {
        "source": {"system_id": "ora_local", "dsn": "localhost:1521/XEPDB1",
                   "user_env": "ORACLE_USER", "password_env": "ORACLE_PASSWORD"},
        "target": {"project": "data-product-framework", "location": "us-central1",
                   "raw_dataset": "raw_ora_local", "control_dataset": "dpf_control"},
        "entities": [{"name": "orders", "source_table": "SALES.ORDERS",
                      "watermark_column": "LAST_MODIFIED_TS",
                      "natural_key": ["ORDER_ID"]}],
    }


ORDERS_DESCRIPTION = [
    ("ORDER_ID", FakeDbType("DB_TYPE_VARCHAR"), 20, 20, None, None, False),
    ("QTY", FakeDbType("DB_TYPE_NUMBER"), 11, None, 10, 0, True),
    ("LAST_MODIFIED_TS", FakeDbType("DB_TYPE_TIMESTAMP"), 23, None, 0, 6, True),
]
ORDERS_SOURCE = {"ORDER_ID": "STRING", "QTY": "INT64", "LAST_MODIFIED_TS": "TIMESTAMP"}
ORDERS_ROWS = [
    ("SO-1001", Decimal("6"), datetime(2026, 3, 12, 16, 45, 0, 123456)),
    ("SO-1002", Decimal("1"), datetime(2026, 3, 18, 11, 0, 0, 654321)),
]
BATCH_HIGH = datetime(2026, 3, 18, 11, 0, 0, 654321, tzinfo=UTC)


class FakeConn:
    closed = False

    def close(self):
        self.closed = True


class Seams:
    """Records what the orchestration asked Oracle and BigQuery to do."""

    def __init__(self):
        self.conn = FakeConn()
        self.rows = list(ORDERS_ROWS)
        self.watermark = None
        self.registered = None
        self.raw_schema = None
        self.land_error = None
        self.since = []
        self.landed = []
        self.quarantined = []


@pytest.fixture
def seams(monkeypatch):
    s = Seams()

    def fetch(conn, entity, since):
        s.since.append(since)
        return s.rows, ORDERS_DESCRIPTION

    def land(bq, target, batch):
        if s.land_error:
            raise s.land_error
        s.landed.append(batch)

    monkeypatch.setattr(xo, "bq_client", lambda target: "bq")
    monkeypatch.setattr(xo, "ensure_control_tables", lambda bq, target: None)
    monkeypatch.setattr(xo, "oracle_connect", lambda cfg: s.conn)
    monkeypatch.setattr(xo, "fetch", fetch)
    monkeypatch.setattr(xo, "read_watermark", lambda bq, t, system, e: s.watermark)
    monkeypatch.setattr(xo, "read_registered_schema", lambda bq, t, system, e: s.registered)
    monkeypatch.setattr(xo, "get_table_schema", lambda bq, ref: s.raw_schema)
    monkeypatch.setattr(xo, "land_batch", land)
    monkeypatch.setattr(xo, "quarantine_batch",
                        lambda bq, t, batch: s.quarantined.append(batch))
    return s


def _lines(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


def _alerts(lines):
    return [line for line in lines if line.get("dpf_alert")]


def test_dry_run_prints_valid_manifests_and_never_touches_bigquery(
        monkeypatch, capsys, seams, manifest_validator):
    def forbidden(*args, **kwargs):
        raise AssertionError("dry run must not call BigQuery")

    for name in ("bq_client", "ensure_control_tables", "read_watermark",
                 "read_registered_schema", "get_table_schema", "land_batch",
                 "quarantine_batch"):
        monkeypatch.setattr(xo, name, forbidden)
    assert xo.run(xo.validate_config(_cfg_dict()), dry=True) == 0
    lines = _lines(capsys)
    manifests = [line for line in lines if "severity" not in line]
    assert len(manifests) == 1
    assert _errors(manifest_validator, manifests[0]) == []
    assert manifests[0]["row_count"] == 2
    assert manifests[0]["watermark_high"] == "2026-03-18T11:00:00.654321+00:00"
    assert seams.since == [xo.EPOCH]
    assert seams.conn.closed and not _alerts(lines)


def test_lookback_is_applied_to_the_stored_watermark(capsys, seams):
    seams.watermark = datetime(2026, 3, 12, 16, 45, 0, 123456, tzinfo=UTC)
    seams.registered = (xo.schema_fingerprint(ORDERS_SOURCE), dict(ORDERS_SOURCE))
    assert xo.run(xo.validate_config(_cfg_dict())) == 0
    assert seams.since == [datetime(2026, 3, 12, 16, 30, 0, 123456, tzinfo=UTC)]
    batch = seams.landed[0]
    assert batch.manifest["watermark_low"] == "2026-03-12T16:30:00.123456+00:00"
    assert batch.new_watermark == BATCH_HIGH
    assert (batch.drift, batch.record_schema) == ("none", False)


def test_breaking_drift_quarantines_holds_watermark_and_alerts_once(
        capsys, seams, manifest_validator):
    seams.watermark = datetime(2026, 3, 1, tzinfo=UTC)
    seams.registered = ("old-fp", {**ORDERS_SOURCE, "REGION_CD": "STRING"})
    assert xo.run(xo.validate_config(_cfg_dict())) == 1
    assert seams.landed == []                               # watermark not advanced
    assert len(seams.quarantined) == 1
    batch = seams.quarantined[0]
    assert (batch.manifest["status"], batch.manifest["drift"]) == ("quarantined", "breaking")
    assert _errors(manifest_validator, batch.manifest) == []
    alerts = _alerts(_lines(capsys))
    assert len(alerts) == 1
    assert alerts[0]["dpf_alert"] == "schema_drift_breaking"
    assert alerts[0]["severity"] == "ERROR"
    assert (alerts[0]["source_system"], alerts[0]["entity"], alerts[0]["batch_id"]) == (
        "ora_local", "orders", batch.batch_id)
    assert alerts[0]["changes"] == ["removed column REGION_CD (STRING)"]
    assert alerts[0]["quarantined"] is True


def test_additive_drift_lands_records_schema_and_logs_info(
        capsys, seams, manifest_validator):
    seams.watermark = datetime(2026, 3, 1, tzinfo=UTC)
    seams.registered = ("old-fp", {"ORDER_ID": "STRING", "LAST_MODIFIED_TS": "TIMESTAMP"})
    assert xo.run(xo.validate_config(_cfg_dict())) == 0
    assert len(seams.landed) == 1 and seams.quarantined == []
    batch = seams.landed[0]
    assert batch.record_schema is True
    assert (batch.manifest["status"], batch.manifest["drift"]) == ("landed", "additive")
    assert _errors(manifest_validator, batch.manifest) == []
    lines = _lines(capsys)
    info = [line for line in lines if line.get("dpf_event") == "schema_drift_additive"]
    assert len(info) == 1 and info[0]["severity"] == "INFO"
    assert info[0]["changes"] == ["added column QTY (INT64)"]
    assert not _alerts(lines)


def test_first_run_records_baseline_schema(capsys, seams):
    assert xo.run(xo.validate_config(_cfg_dict())) == 0
    batch = seams.landed[0]
    assert (batch.drift, batch.record_schema) == ("none", True)
    assert seams.since == [xo.EPOCH]


def test_registry_gap_falls_back_to_landed_raw_table(capsys, seams):
    seams.raw_schema = {**xo.batch_schema(ORDERS_SOURCE), "QTY": "STRING"}
    assert xo.run(xo.validate_config(_cfg_dict())) == 1
    assert seams.landed == [] and len(seams.quarantined) == 1
    alert = _alerts(_lines(capsys))[0]
    assert alert["compared_with"] == "raw_table"
    assert alert["changes"] == ["changed type of QTY: STRING -> INT64"]


def test_watermark_never_regresses_on_a_lookback_only_batch(capsys, seams):
    seams.watermark = datetime(2026, 3, 18, 11, 5, tzinfo=UTC)   # after every row
    seams.registered = (xo.schema_fingerprint(ORDERS_SOURCE), dict(ORDERS_SOURCE))
    assert xo.run(xo.validate_config(_cfg_dict())) == 0
    batch = seams.landed[0]
    assert batch.new_watermark == seams.watermark
    assert batch.manifest["watermark_high"] == "2026-03-18T11:00:00.654321+00:00"


def test_failure_emits_extract_failed_and_nonzero_exit(capsys, seams):
    seams.land_error = RuntimeError("Assertion failed: inserted row count differs")
    assert xo.run(xo.validate_config(_cfg_dict())) == 1
    alerts = _alerts(_lines(capsys))
    assert [a["dpf_alert"] for a in alerts] == ["extract_failed"]
    assert alerts[0]["severity"] == "ERROR"
    assert alerts[0]["stage"] == "land"
    assert "inserted row count" in alerts[0]["error"]


def test_no_new_rows_writes_nothing(capsys, seams):
    seams.rows = []
    assert xo.run(xo.validate_config(_cfg_dict())) == 0
    assert seams.landed == [] and seams.quarantined == []


def test_unknown_entity_is_a_usage_error(capsys, seams):
    assert xo.run(xo.validate_config(_cfg_dict()), only="nope") == 2
    assert [a["dpf_alert"] for a in _alerts(_lines(capsys))] == ["extract_failed"]
