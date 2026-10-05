# dpf: element=source:ora_local satisfies=R-10 implements=land-immutable-raw
resource "google_bigquery_table" "extract_watermark" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.control.dataset_id
  table_id            = "extract_watermark"
  description         = "One row per committed batch; MAX(watermark_high) is the entity's watermark."
  deletion_protection = true
  schema = jsonencode([
    { name = "source_system", type = "STRING", mode = "NULLABLE" },
    { name = "entity", type = "STRING", mode = "NULLABLE" },
    { name = "watermark_high", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "batch_id", type = "STRING", mode = "NULLABLE" },
    { name = "row_count", type = "INT64", mode = "NULLABLE" },
    { name = "updated_at", type = "TIMESTAMP", mode = "NULLABLE" }
  ])
}

# dpf: element=source:ora_local satisfies=R-10 implements=land-immutable-raw
resource "google_bigquery_table" "landing_manifest" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.control.dataset_id
  table_id            = "landing_manifest"
  description         = "One landing-manifest.v1 per landed batch; a batch without a manifest is not consumable."
  deletion_protection = true
  clustering          = ["source_system", "entity"]
  schema = jsonencode([
    { name = "batch_id", type = "STRING", mode = "REQUIRED" },
    { name = "source_system", type = "STRING", mode = "REQUIRED" },
    { name = "entity", type = "STRING", mode = "REQUIRED" },
    { name = "ingest_ts", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "row_count", type = "INT64", mode = "REQUIRED" },
    { name = "watermark_low", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "watermark_high", type = "TIMESTAMP", mode = "NULLABLE" },
    { name = "schema_fingerprint", type = "STRING", mode = "NULLABLE" },
    { name = "drift", type = "STRING", mode = "NULLABLE" },
    { name = "status", type = "STRING", mode = "REQUIRED" },
    { name = "manifest", type = "JSON", mode = "NULLABLE" },
    { name = "recorded_at", type = "TIMESTAMP", mode = "REQUIRED" }
  ])
}

# dpf: element=source:ora_local satisfies=R-10 implements=land-immutable-raw
resource "google_bigquery_table" "schema_registry" {
  project             = var.project_id
  dataset_id          = google_bigquery_dataset.control.dataset_id
  table_id            = "schema_registry"
  description         = "Accepted schema per source entity; the latest recorded_at wins."
  deletion_protection = true
  clustering          = ["source_system", "entity"]
  schema = jsonencode([
    { name = "source_system", type = "STRING", mode = "REQUIRED" },
    { name = "entity", type = "STRING", mode = "REQUIRED" },
    { name = "fingerprint", type = "STRING", mode = "REQUIRED" },
    { name = "schema_json", type = "JSON", mode = "NULLABLE" },
    { name = "recorded_at", type = "TIMESTAMP", mode = "REQUIRED" },
    { name = "batch_id", type = "STRING", mode = "NULLABLE" }
  ])
}
