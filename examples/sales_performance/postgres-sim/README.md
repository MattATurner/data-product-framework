# On-Premises PostgreSQL 16 OLTP Simulator & 15-Minute Watermark Showcase

This folder brings the `sales_performance` source (`pg_local`, **ADR-015**) to life as a real transactional database you can start, mutate across five realistic business events, extract on a 15-minute watermark schedule (or on demand), and stop cleanly.

## Three Ways to Run It (Same Codebase, Zero Licensing Friction)

| Mode | Best For | Command |
| :--- | :--- | :--- |
| **1. Docker (`postgres:16-alpine`)** | Google Cloud Shell, macOS (Apple Silicon / Intel), Linux | `./demo_ctl.sh start --target docker` |
| **2. Zero-Docker (`sqlite` WAL)** | Restricted corporate laptops without Docker | `./demo_ctl.sh start --target sqlite` |
| **3. GCE Showcase VM (`pg-onprem-sim`)** | Live customer demos in GCP (`e2-small` COS, no external IP, Cloud NAT, 4h auto-stop TTL → \$0 idle compute) | `./demo_ctl.sh start --target gce --project <your-project>` |

## Walking Through the 5 Transactional Story Beats

```bash
cd examples/sales_performance/postgres-sim

# 1. Start PostgreSQL 16 (auto-selects Docker if running, else SQLite WAL; pass --target gce for GCP VM)
./demo_ctl.sh start

# 2. Step 1 (1a -> 1b -> 1c): Baseline sales + 2 real in-place OLTP amendments to SO-1001 line 2
./demo_ctl.sh step 1a --extract
./demo_ctl.sh step 1b --extract
./demo_ctl.sh step 1c --extract

# 3. Step 2: Mid-quarter reclassification — UPDATEs C-001 (SMB -> ENTERPRISE) and P-200 (GADGETS -> WIDGETS)
#    in-place in PostgreSQL (overwriting old values!) + inserts June order SO-1004
./demo_ctl.sh step 2 --extract

# 4. Step 3: Late-committing OLTP order timestamped 6 minutes BEHIND the last high-watermark
#    (rescued by extract_postgres.py's 15-minute lookback window, deduplicated in staging)
./demo_ctl.sh step 3 --extract

# 5. Step 4: Poison-pill order SO-1005 with cust_id = NULL -> quarantined by QR-1, blocks gold refresh
./demo_ctl.sh step 4 --extract

# 6. Step 5: Source ERP updates SO-1005 (cust_id = 'C-002') -> clears _rejects, unblocks gold
./demo_ctl.sh step 5 --extract

# 7. Stop cleanly when finished (powers off GCE VM so compute billing = $0.00)
./demo_ctl.sh stop
```
