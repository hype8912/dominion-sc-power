"""Tests for cli.py -- argument parsing and CSV output.

No network calls, no credentials. The async run() function is tested
by mocking async_login, async_get_accounts, and async_get_usage_reads.
See docs/REFACTOR_PLAN.md Phase 5.
"""

import csv
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dominionsc.cli import build_parser, run
from dominionsc.usage_read import UsageRead

# ---------------------------------------------------------------------------
# build_parser() tests
# ---------------------------------------------------------------------------


class TestBuildParser:
    """Tests for build_parser()."""

    def test_default_csv_is_none(self):
        """--csv defaults to None when not provided."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.csv is None

    def test_csv_path_accepted(self):
        """--csv accepts a path string."""
        parser = build_parser()
        args = parser.parse_args(["--csv", "output.csv"])
        assert args.csv == "output.csv"

    def test_username_and_password_accepted(self):
        """--username and --password are stored on the namespace."""
        parser = build_parser()
        args = parser.parse_args(["--username", "u@example.com", "--password", "s3cr3t"])
        assert args.username == "u@example.com"
        assert args.password == "s3cr3t"

    def test_start_date_parsed(self):
        """--start_date is parsed to a datetime object."""
        parser = build_parser()
        args = parser.parse_args(["--start_date", "2026-08-13"])
        assert args.start_date == datetime(2026, 8, 13)

    def test_end_date_parsed(self):
        """--end_date is parsed to a datetime object."""
        parser = build_parser()
        args = parser.parse_args(["--end_date", "2026-09-10"])
        assert args.end_date == datetime(2026, 9, 10)

    def test_verbose_default_is_zero(self):
        """Verbosity defaults to 0."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.verbose == 0

    def test_verbose_increments(self):
        """-v increments the verbose count."""
        parser = build_parser()
        args = parser.parse_args(["-v", "-v"])
        assert args.verbose == 2


# ---------------------------------------------------------------------------
# run() tests -- CSV output
# ---------------------------------------------------------------------------


def _make_usage_reads() -> list[UsageRead]:
    """Return two synthetic UsageRead objects for testing."""
    tz = UTC
    return [
        UsageRead(
            start_time=datetime(2026, 8, 13, 0, 0, 0, tzinfo=tz),
            end_time=datetime(2026, 8, 13, 0, 14, 59, tzinfo=tz),
            consumption=209,
        ),
        UsageRead(
            start_time=datetime(2026, 8, 13, 0, 15, 0, tzinfo=tz),
            end_time=datetime(2026, 8, 13, 0, 29, 59, tzinfo=tz),
            consumption=328,
        ),
    ]


def _mock_dominionsc(usage_reads: list[UsageRead] | None = None):
    """Return a mock DominionSC that returns controlled data."""
    mock = MagicMock()
    mock.async_login = AsyncMock()
    # Legacy list format: [[types], addr]
    mock.async_get_accounts = AsyncMock(return_value=[["ELECTRIC"], "3005 ELLINGTON DR"])
    mock.async_get_usage_reads = AsyncMock(return_value=usage_reads or _make_usage_reads())
    mock.async_get_forecast = AsyncMock()
    return mock


class TestRunCSV:
    """Tests for run() CSV writing behaviour."""

    @pytest.mark.asyncio
    async def test_csv_has_header_row(self, tmp_path):
        """CSV output includes a header row with service column."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username",
                "u",
                "--password",
                "p",
                "--csv",
                str(out),
            ]
        )

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        rows = list(csv.reader(out.read_text().splitlines()))
        assert rows[0] == ["service", "start_time", "end_time", "consumption"]

    @pytest.mark.asyncio
    async def test_csv_includes_service_column(self, tmp_path):
        """Every data row starts with the measurement type (account name)."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username",
                "u",
                "--password",
                "p",
                "--csv",
                str(out),
            ]
        )

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        rows = list(csv.reader(out.read_text().splitlines()))
        # Skip header
        data_rows = rows[1:]
        assert all(row[0] == "ELECTRIC" for row in data_rows)

    @pytest.mark.asyncio
    async def test_csv_not_overwritten_between_accounts(self, tmp_path):
        """Multi-account output is all in one file, not overwritten per account."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username",
                "u",
                "--password",
                "p",
                "--csv",
                str(out),
            ]
        )

        # Two accounts, two reads each
        reads_electric = _make_usage_reads()
        reads_gas = [
            UsageRead(
                start_time=datetime(2026, 8, 13, 0, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 8, 13, 0, 59, 59, tzinfo=UTC),
                consumption=15,
            )
        ]

        mock = MagicMock()
        mock.async_login = AsyncMock()
        mock.async_get_accounts = AsyncMock(return_value=[["ELECTRIC", "GAS"], "3005 ELLINGTON DR"])
        mock.async_get_usage_reads = AsyncMock(side_effect=[reads_electric, reads_gas])
        mock.async_get_forecast = AsyncMock()

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        rows = list(csv.reader(out.read_text().splitlines()))
        data_rows = rows[1:]  # strip header
        # 2 electric + 1 gas = 3 data rows in one file
        assert len(data_rows) == 3
        assert data_rows[0][0] == "ELECTRIC"
        assert data_rows[1][0] == "ELECTRIC"
        assert data_rows[2][0] == "GAS"

    @pytest.mark.asyncio
    async def test_run_returns_zero_on_success(self, tmp_path):
        """run() returns exit code 0 on success."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username",
                "u",
                "--password",
                "p",
                "--csv",
                str(out),
            ]
        )

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 0
