# Python imports
from datetime import datetime, timezone

# Django imports
from django.test import SimpleTestCase

# Module imports
from plane.bgtasks.export_task import (
    COMPLEX_RESOLVERS,
    _introspect_field,
    dateTimeConverter,
)


class ExportDateTimeConverterTest(SimpleTestCase):
    # TICKET-1059306 (heineken-br1): created 19:33 UTC = 16:33 in Sao Paulo
    created_at = datetime(2026, 11, 18, 19, 33, 0, tzinfo=timezone.utc)

    def test_converts_to_project_timezone_on_24h_clock(self):
        self.assertEqual(
            dateTimeConverter(self.created_at, "America/Sao_Paulo"),
            "Wed, 18 Nov 2026 16:33:00 UTC-0300",
        )

    def test_utc_project_keeps_utc_suffix_with_24h_clock(self):
        # Was "Wed, 18 Nov 2026 07:33:00 UTC+0000" (12-hour clock, no AM/PM)
        expected = "Wed, 18 Nov 2026 19:33:00 UTC+0000"
        self.assertEqual(dateTimeConverter(self.created_at, "UTC"), expected)
        self.assertEqual(dateTimeConverter(self.created_at), expected)

    def test_conversion_can_move_the_calendar_day(self):
        # TICKET-1039482: 02:48 UTC on 12 Nov is 23:48 on 11 Nov in Sao Paulo
        late = datetime(2026, 11, 12, 2, 48, 37, tzinfo=timezone.utc)
        self.assertEqual(
            dateTimeConverter(late, "America/Sao_Paulo"),
            "Wed, 11 Nov 2026 23:48:37 UTC-0300",
        )

    def test_empty_value_stays_empty(self):
        self.assertIsNone(dateTimeConverter(None, "America/Sao_Paulo"))


class ExportDateTimeResolverTest(SimpleTestCase):
    row = {
        "created_at": datetime(2026, 11, 18, 19, 33, 0, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 11, 18, 19, 33, 3, tzinfo=timezone.utc),
        "start_date_time": datetime(2026, 11, 18, 19, 33, 0, tzinfo=timezone.utc),
        "project__timezone": "America/Sao_Paulo",
    }

    def test_created_and_updated_on_use_project_timezone(self):
        for key, expected in (
            ("created_on", "Wed, 18 Nov 2026 16:33:00 UTC-0300"),
            ("updated_on", "Wed, 18 Nov 2026 16:33:03 UTC-0300"),
        ):
            resolver = COMPLEX_RESOLVERS[key]
            self.assertIn("project__timezone", resolver.values_fields)
            self.assertEqual(resolver.extractor(self.row), expected)

    def test_introspected_datetime_column_uses_project_timezone(self):
        resolver = _introspect_field("start_date_time")
        self.assertIn("project__timezone", resolver.values_fields)
        self.assertEqual(
            resolver.extractor(self.row), "Wed, 18 Nov 2026 16:33:00 UTC-0300"
        )

    def test_introspected_date_column_does_not_fetch_timezone(self):
        resolver = _introspect_field("start_date")
        self.assertEqual(resolver.values_fields, ["start_date"])
