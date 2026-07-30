import json
import shutil
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.bigquery import BigQueryService, BigQuerySettings, parse_table_reference


class _FakeIterator:
    def __init__(self, schema, rows):
        self.schema = schema
        self.rows = rows

    def __iter__(self):
        return iter(self.rows)


class _FakeQueryJob:
    def __init__(self, rows):
        self.rows = rows
        self.total_bytes_processed = 128
        self.total_bytes_billed = 1024

    def result(self, max_results):
        schema = [
            SimpleNamespace(name="order_date"),
            SimpleNamespace(name="revenue"),
        ]
        return _FakeIterator(schema, self.rows[:max_results])


class FakeClient:
    def __init__(self):
        self.queries = []
        self.referenced_tables = [
            SimpleNamespace(
                project="project-one",
                dataset_id="sales",
                table_id="orders",
            )
        ]
        self.rows = [
            {"order_date": "2026-01-01", "revenue": 10},
            {"order_date": "2026-01-02", "revenue": 20},
        ]
        self.table = SimpleNamespace(
            schema=[
                SimpleNamespace(
                    name="order_date",
                    field_type="DATE",
                    mode="REQUIRED",
                    description="Order date",
                    fields=[],
                ),
                SimpleNamespace(
                    name="revenue",
                    field_type="NUMERIC",
                    mode="NULLABLE",
                    description=None,
                    fields=[],
                ),
            ]
        )

    def get_table(self, value):
        self.last_table = value
        return self.table

    def query(self, sql, **kwargs):
        self.queries.append((sql, kwargs))
        if kwargs["job_config"].dry_run:
            return SimpleNamespace(referenced_tables=self.referenced_tables)
        return _FakeQueryJob(self.rows)


class BigQueryTests(unittest.TestCase):
    def service(self, allowed_datasets="project-one.sales", client=None):
        return BigQueryService(
            BigQuerySettings(
                BIGQUERY_PROJECT_ID="project-one",
                BIGQUERY_ALLOWED_DATASETS=allowed_datasets,
            ),
            client or FakeClient(),
        )

    def test_parses_short_and_fully_qualified_tables(self):
        self.assertEqual(
            parse_table_reference("sales.orders", "project-one").full_name,
            "project-one.sales.orders",
        )
        self.assertEqual(
            parse_table_reference(
                "project-one.sales.orders", "other-project"
            ).full_name,
            "project-one.sales.orders",
        )

    def test_allowlist_rejects_unapproved_dataset(self):
        with self.assertRaises(PermissionError):
            self.service().schema("finance.payroll")

    def test_allowlist_is_required_for_table_access(self):
        with self.assertRaises(PermissionError):
            self.service(allowed_datasets="").schema("sales.orders")

    def test_schema_becomes_dashboard_catalog(self):
        catalog = self.service().catalog("sales.orders")
        fields = {
            field.name: field.data_type
            for field in catalog.tables[0].columns
        }
        self.assertEqual(catalog.tables[0].name, "orders")
        self.assertEqual(fields, {"order_date": "date", "revenue": "decimal"})

    def test_rejects_write_sql_before_calling_bigquery(self):
        with self.assertRaises(ValueError):
            self.service().query("DELETE FROM `project-one.sales.orders`")
        with self.assertRaises(ValueError):
            self.service().query("SELECT 1; SELECT 2")

    def test_query_counts_rows_and_authorizes_dry_run_references(self):
        client = FakeClient()
        result = self.service(client=client).query(
            "SELECT * FROM `project-one.sales.orders`",
            max_rows=1,
        )
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertEqual(
            result["referenced_tables"], ["project-one.sales.orders"]
        )
        self.assertEqual(len(client.queries), 2)
        self.assertTrue(client.queries[0][1]["job_config"].dry_run)
        self.assertFalse(client.queries[1][1]["job_config"].dry_run)

    def test_query_rejects_disallowed_dry_run_reference_before_execution(self):
        client = FakeClient()
        client.referenced_tables = [
            SimpleNamespace(
                project="project-one",
                dataset_id="finance",
                table_id="payroll",
            )
        ]
        with self.assertRaises(PermissionError):
            self.service(client=client).query(
                "SELECT * FROM `project-one.finance.payroll`"
            )
        self.assertEqual(len(client.queries), 0)

    def test_powerbi_model_contains_bigquery_partition_without_credentials(self):
        root = Path.cwd() / ".test-bigquery-model"
        shutil.rmtree(root, ignore_errors=True)
        try:
            binding = self.service().create_powerbi_model(
                "sales.orders", root, storage_mode="directQuery"
            )
            model_path = Path(binding.semantic_model_path)
            definition = json.loads(
                (model_path / "definition.pbism").read_text(encoding="utf-8")
            )
            model = json.loads(
                (model_path / "model.bim").read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (model_path / "bigquery-binding.json").read_text(
                    encoding="utf-8"
                )
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)
        partition = model["model"]["tables"][0]["partitions"][0]
        expression = "\n".join(partition["source"]["expression"])
        self.assertEqual(definition["version"], "4.2")
        self.assertEqual(partition["mode"], "directQuery")
        self.assertEqual(partition["source"]["type"], "m")
        self.assertIn("GoogleBigQuery.Database", expression)
        self.assertIn('BillingProject="project-one"', expression)
        self.assertIn('Implementation="2.0"', expression)
        self.assertIn("UseStorageApi=false", expression)
        self.assertNotIn("private_key", expression)
        self.assertFalse(manifest["credential_material_embedded"])
        self.assertEqual(binding.catalog["tables"][0]["name"], "orders")

    def test_powerbi_model_rejects_invalid_storage_mode(self):
        with self.assertRaises(ValueError):
            self.service().create_powerbi_model(
                "sales.orders", ".", storage_mode="dual"
            )

    def test_external_query_is_rejected_before_calling_bigquery(self):
        client = FakeClient()
        with self.assertRaises(ValueError):
            self.service(client=client).query(
                "SELECT * FROM EXTERNAL_QUERY('connection', 'SELECT 1')"
            )
        self.assertEqual(client.queries, [])

    def test_disallowed_information_schema_is_rejected_before_dry_run(self):
        client = FakeClient()
        with self.assertRaises(PermissionError):
            self.service(client=client).query(
                "SELECT * FROM `project-one.finance.INFORMATION_SCHEMA.TABLES`"
            )
        self.assertEqual(client.queries, [])


if __name__ == "__main__":
    unittest.main()
