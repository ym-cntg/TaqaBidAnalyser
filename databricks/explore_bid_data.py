# Databricks notebook source
# MAGIC %md
# MAGIC # Maximo bid data exploration
# MAGIC
# MAGIC Unity Catalog: `ingestion_framework_test.bid_data_exploration`
# MAGIC
# MAGIC Goal: understand the real shape of TAQA's Maximo procurement data
# MAGIC (RFQ / vendor / quotation line tables) before extending the bid
# MAGIC analyzer to work against it, instead of assuming it looks like the
# MAGIC hand-curated sample data on `full-feature-buildout`.
# MAGIC
# MAGIC For each table below: schema (`DESCRIBE`), row count, and a sample of
# MAGIC rows. Fill in the "Observations" markdown cell under each table as you
# MAGIC go — that's the actual deliverable of this notebook, not the raw output.

# COMMAND ----------

CATALOG = "ingestion_framework_test"
SCHEMA = "bid_data_exploration"

TABLES = [
    "rfq",
    "rfqvendor",
    "quotationline",
    "altquotationline",
    "docinfo",
    "doclinks",
]
VIEWS = [
    "vw_rfqvendor_documents",
]

spark.sql(f"USE CATALOG {CATALOG}")
spark.sql(f"USE SCHEMA {SCHEMA}")
display(spark.sql(f"SHOW TABLES IN {CATALOG}.{SCHEMA}"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## `rfq` — tender / request for quotation header
# MAGIC
# MAGIC Expected: one row per tender (the thing D-111808 was, in the sample
# MAGIC data). Look for: a tender number / reference field, status, dates,
# MAGIC description, whether lots are modeled here or elsewhere.

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.rfq"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.rfq"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.rfq LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Observations:**
# MAGIC - _(fill in after running: which column is the tender/RFQ number, what
# MAGIC   a lot maps to, what "original vs. round1/2/3" looks like here if
# MAGIC   anything, status/lifecycle values seen)_

# COMMAND ----------

# MAGIC %md
# MAGIC ## `rfqvendor` — one row per bidder submission against an RFQ
# MAGIC
# MAGIC Expected: the bidder-level record (maps to AGPOWER / AL Geemi / etc.
# MAGIC in the sample data). Look for: bidder name/vendor id, round/revision
# MAGIC number, submission date, total price if rolled up here, status
# MAGIC (submitted / disqualified / awarded).

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.rfqvendor"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.rfqvendor"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.rfqvendor LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Observations:**
# MAGIC - _(fill in: how a vendor's negotiation round is represented, foreign
# MAGIC   key back to `rfq`, whether multiple rows per vendor exist per RFQ —
# MAGIC   i.e. is a round a new row or a new column)_

# COMMAND ----------

# MAGIC %md
# MAGIC ## `quotationline` — bidder's priced BOQ line items
# MAGIC
# MAGIC Expected: this is the real equivalent of the per-item CIF/Erection
# MAGIC rows the sample data's Excel/PDF parsers currently extract by hand.
# MAGIC Look for: item number, description, unit, qty, rate(s), total(s),
# MAGIC whether CIF/Erection are separate columns or need to be derived,
# MAGIC foreign key back to `rfqvendor`.

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.quotationline"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.quotationline"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.quotationline LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Observations:**
# MAGIC - _(fill in: column-to-BOQ-field mapping, whether item numbering
# MAGIC   matches an ADDC-standard template across vendors like the sample
# MAGIC   data does, how lots are distinguished if this table doesn't have a
# MAGIC   lot column directly)_

# COMMAND ----------

# MAGIC %md
# MAGIC ## `altquotationline` — alternate/optional quotation lines
# MAGIC
# MAGIC Expected: bidder-proposed alternates (a substitution/option, not part
# MAGIC of the base priced BOQ). No equivalent in the current sample-data
# MAGIC pipeline — worth understanding whether these should be excluded from
# MAGIC comparison entirely or surfaced separately.

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.altquotationline"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.altquotationline"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.altquotationline LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Observations:**
# MAGIC - _(fill in: how common are alternates, do they share item numbers
# MAGIC   with `quotationline`, should they factor into comparison at all)_

# COMMAND ----------

# MAGIC %md
# MAGIC ## `docinfo` / `doclinks` — attached document metadata and linkage
# MAGIC
# MAGIC Expected: `docinfo` describes each attached file (name, type, maybe a
# MAGIC storage pointer); `doclinks` connects a document to the RFQ/vendor
# MAGIC record it belongs to. This is the real-data equivalent of the
# MAGIC document-selection/curation step built for the sample data — worth
# MAGIC checking whether a stored file path or a blob is what's actually
# MAGIC retrievable from here.

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.docinfo"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.docinfo"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.docinfo LIMIT 20"))

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.doclinks"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.doclinks"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.doclinks LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC **Observations:**
# MAGIC - _(fill in: is the actual file content reachable from here or just
# MAGIC   metadata, how a document maps to "bidder's official submission" vs.
# MAGIC   cover letters/certificates the way water's sample data mixed them)_

# COMMAND ----------

# MAGIC %md
# MAGIC ## `vw_rfqvendor_documents` — vendor submissions joined to their documents
# MAGIC
# MAGIC A pre-built view — worth checking whether it already does the
# MAGIC document-curation join we'd otherwise have to write by hand.

# COMMAND ----------

display(spark.sql(f"DESCRIBE TABLE {CATALOG}.{SCHEMA}.vw_rfqvendor_documents"))

# COMMAND ----------

display(spark.sql(f"SELECT COUNT(*) AS row_count FROM {CATALOG}.{SCHEMA}.vw_rfqvendor_documents"))
display(spark.sql(f"SELECT * FROM {CATALOG}.{SCHEMA}.vw_rfqvendor_documents LIMIT 20"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cross-table sanity checks
# MAGIC
# MAGIC Quick profiling once the above shapes are understood — adjust column
# MAGIC names below to match what `DESCRIBE` actually showed.

# COMMAND ----------

# MAGIC %md
# MAGIC ### How many vendors per RFQ, and how many quotation lines per vendor?
# MAGIC Uncomment and fix column names once known:
# MAGIC ```python
# MAGIC display(spark.sql(f"""
# MAGIC     SELECT rfq_id, COUNT(DISTINCT vendor_id) AS vendor_count
# MAGIC     FROM {CATALOG}.{SCHEMA}.rfqvendor
# MAGIC     GROUP BY rfq_id
# MAGIC     ORDER BY vendor_count DESC
# MAGIC """))
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## Summary — fill in once the notebook has been run
# MAGIC
# MAGIC | Question | Answer |
# MAGIC |---|---|
# MAGIC | Which RFQ maps to a real tender like D-111808? | |
# MAGIC | Does one RFQ span multiple lots, or is a lot its own RFQ/line grouping? | |
# MAGIC | How are negotiation rounds represented? | |
# MAGIC | Does `quotationline` cleanly split CIF vs. Erection like the sample BOQs, or is pricing structured differently? | |
# MAGIC | Can bid documents (Excel/PDF) actually be retrieved via `docinfo`/`doclinks`, or is this metadata-only? | |
# MAGIC | Biggest blocker to reusing the existing extraction/comparison pipeline against this data? | |
