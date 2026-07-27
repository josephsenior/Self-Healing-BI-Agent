import unittest
from types import SimpleNamespace

from backend.bigquery import BigQueryService, BigQuerySettings, parse_table_reference


class FakeClient:
    def __init__(self):
        self.table = SimpleNamespace(schema=[
            SimpleNamespace(name="order_date", field_type="DATE", mode="REQUIRED", description="Order date", fields=[]),
            SimpleNamespace(name="revenue", field_type="NUMERIC", mode="NULLABLE", description=None, fields=[]),
        ])

    def get_table(self, value):
        self.last_table = value
        return self.table


class BigQueryTests(unittest.TestCase):
    def service(self, allowed_datasets="project-one.sales"):
        return BigQueryService(
            BigQuerySettings(
                BIGQUERY_PROJECT_ID="project-one",
                BIGQUERY_ALLOWED_DATASETS=allowed_datasets,
            ),
            FakeClient(),
        )

    def test_parses_short_and_fully_qualified_tables(self):
        self.assertEqual(
            parse_table_reference("sales.orders", "project-one").full_name,
            "project-one.sales.orders",
        )
        self.assertEqual(
            parse_table_reference("project-one.sales.orders", "other-project").full_name,
            "project-one.sales.orders",
        )

    def test_allowlist_rejects_unapproved_dataset(self):
        with self.assertRaises(PermissionError):
            self.service().schema("finance.payroll")

    def test_schema_becomes_dashboard_catalog(self):
        catalog = self.service().catalog("sales.orders")
        fields = {field.name: field.data_type for field in catalog.tables[0].columns}
        self.assertEqual(catalog.tables[0].name, "orders")
        self.assertEqual(fields, {"order_date": "date", "revenue": "decimal"})

    def test_rejects_write_sql_before_calling_bigquery(self):
        with self.assertRaises(ValueError):
            self.service().query("DELETE FROM `project-one.sales.orders`")
        with self.assertRaises(ValueError):
            self.service().query("SELECT 1; SELECT 2")

