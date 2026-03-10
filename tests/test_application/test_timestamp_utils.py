import pytest
from augur.application.timestamp_utils import fix_invalid_timezone, POSTGRES_VALID_TIMEZONES


class TestFixInvalidTimezone:
    """Tests for fix_invalid_timezone()."""

    def test_valid_utc_offset_returns_none(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +0000")
        assert result is None

    def test_valid_positive_offset_returns_none(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +0530")
        assert result is None

    def test_valid_negative_offset_returns_none(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 -0500")
        assert result is None

    def test_invalid_offset_corrected_to_utc(self):
        # -13068837 is the corrupted timezone from issue #3472
        result = fix_invalid_timezone("2024-01-15 10:30:00 -13068837")
        assert result == "2024-01-15 10:30:00 +0000"

    def test_large_positive_invalid_offset(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +9999")
        assert result == "2024-01-15 10:30:00 +0000"

    def test_unparseable_timezone_string(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 UTC")
        assert result == "2024-01-15 10:30:00 +0000"

    def test_timezone_with_colon_valid(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +05:30")
        assert result is None

    def test_timezone_with_colon_invalid(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +99:99")
        assert result == "2024-01-15 10:30:00 +0000"

    def test_boundary_valid_max_offset(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +1400")
        assert result is None

    def test_boundary_valid_min_offset(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 -1200")
        assert result is None

    def test_boundary_invalid_beyond_max(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 +1500")
        assert result == "2024-01-15 10:30:00 +0000"

    def test_boundary_invalid_beyond_min(self):
        result = fix_invalid_timezone("2024-01-15 10:30:00 -1300")
        assert result == "2024-01-15 10:30:00 +0000"


class TestPostgresValidTimezones:
    """Tests for the POSTGRES_VALID_TIMEZONES constant."""

    def test_contains_utc(self):
        assert 0 in POSTGRES_VALID_TIMEZONES

    def test_contains_common_offsets(self):
        common = {-500, -400, 100, 200, 530, 900}
        assert common.issubset(POSTGRES_VALID_TIMEZONES)

    def test_max_offset_is_1400(self):
        assert max(POSTGRES_VALID_TIMEZONES) == 1400

    def test_min_offset_is_negative_1200(self):
        assert min(POSTGRES_VALID_TIMEZONES) == -1200
