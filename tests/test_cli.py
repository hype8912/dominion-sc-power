"""Tests for cli.py -- argument parsing and CSV output.

No network calls, no credentials. The async run() function is tested
by mocking async_login, async_get_accounts, and async_get_usage_reads.
See docs/REFACTOR_PLAN.md Phase 5.
"""

import csv
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dominionsc.cli import build_parser, main, run
from dominionsc.exceptions import InvalidAuth, MfaChallenge
from dominionsc.models.register_reads import RegisterReads
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

    def test_start_date_defaults_none(self):
        """When omitted, start_date/end_date are None at parse time (bound in run())."""
        parser = build_parser()
        args = parser.parse_args([])
        assert args.start_date is None
        assert args.end_date is None

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
    """Return a mock DominionSC that returns controlled data.

    The CLI now uses async_get_register_reads(), so the mock wraps the
    reads in a single RegisterReads (one register, id "UP1") by default.
    """
    reads = usage_reads or _make_usage_reads()
    mock = MagicMock()
    mock.async_login = AsyncMock()
    # Legacy list format: [[types], addr]
    mock.async_get_accounts = AsyncMock(return_value=[["ELECTRIC"], "3005 ELLINGTON DR"])
    mock.async_get_register_reads = AsyncMock(return_value=[RegisterReads(usage_point_id="UP1", reads=reads)])
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
        assert rows[0] == ["service", "register", "start_time", "end_time", "consumption"]

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
        # register column (row[1]) carries the UsagePoint id from the mock
        assert all(row[1] == "UP1" for row in data_rows)

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

        # Two accounts: electric (2 reads, one register) + gas (1 read, one register)
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
        mock.async_get_register_reads = AsyncMock(
            side_effect=[
                [RegisterReads(usage_point_id="ELEC_UP", reads=reads_electric)],
                [RegisterReads(usage_point_id="GAS_UP", reads=reads_gas)],
            ]
        )
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
    async def test_csv_separates_grid_and_solar_registers(self, tmp_path):
        """A multi-register ELECTRIC account writes distinct register ids per row.

        This is the net-metered solar case: one ELECTRIC measurement type
        contains two UsagePoints (grid + solar export). The register column
        must distinguish them, and negative solar values must be preserved.
        """
        out = tmp_path / "out.csv"
        args = _args("--csv", str(out))

        grid_reads = [
            UsageRead(
                start_time=datetime(2026, 8, 13, 0, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 8, 13, 0, 14, 59, tzinfo=UTC),
                consumption=209,
            )
        ]
        solar_reads = [
            UsageRead(
                start_time=datetime(2026, 8, 13, 0, 0, 0, tzinfo=UTC),
                end_time=datetime(2026, 8, 13, 0, 14, 59, tzinfo=UTC),
                consumption=-128,
            )
        ]

        mock = MagicMock()
        mock.async_login = AsyncMock()
        mock.async_get_accounts = AsyncMock(return_value=[["ELECTRIC"], "3005 ELLINGTON DR"])
        mock.async_get_register_reads = AsyncMock(
            return_value=[
                RegisterReads(usage_point_id="GRID_UP", reads=grid_reads),
                RegisterReads(usage_point_id="SOLAR_UP", reads=solar_reads),
            ]
        )
        mock.async_get_forecast = AsyncMock()

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        rows = list(csv.reader(out.read_text().splitlines()))
        data_rows = rows[1:]
        # Both registers present, distinguishable by the register column
        by_register = {row[1]: row for row in data_rows}
        assert set(by_register) == {"GRID_UP", "SOLAR_UP"}
        assert by_register["GRID_UP"][4] == "209"
        assert by_register["SOLAR_UP"][4] == "-128"  # solar export sign preserved

    @pytest.mark.asyncio
    async def test_run_skips_default_when_dates_provided(self, tmp_path):
        """Cover false branches: when dates are provided, lines 129/131 skip binding."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username", "u",
                "--password", "p",
                "--csv", str(out),
                "--start_date", "2026-09-01",
                "--end_date", "2026-09-08",
            ]
        )
        assert args.start_date is not None
        assert args.end_date is not None

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 0

    @pytest.mark.asyncio
    async def test_run_binds_default_dates_when_none(self, tmp_path):
        """Cover lines 129-134: run() binds datetime defaults when args are None."""
        out = tmp_path / "out.csv"
        parser = build_parser()
        args = parser.parse_args(
            [
                "--username", "u",
                "--password", "p",
                "--csv", str(out),
            ]
        )
        assert args.start_date is None
        assert args.end_date is None

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 0
        # After run(), defaults are bound to real datetime objects
        assert args.start_date is not None
        assert args.end_date is not None

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


def _args(*extra: str) -> object:
    """Build parsed args with username/password preset plus any extras."""
    return build_parser().parse_args(["--username", "u", "--password", "p", *extra])


# ---------------------------------------------------------------------------
# run() -- console (non-CSV) output path
# ---------------------------------------------------------------------------


class TestRunConsole:
    """Tests for run() when --csv is NOT provided (console output + forecast)."""

    @pytest.mark.asyncio
    async def test_console_prints_forecast_and_reads(self, capsys):
        """Without --csv, run() fetches the forecast and prints readings to stdout."""
        args = _args()  # no --csv
        mock = _mock_dominionsc()
        mock.async_get_forecast = AsyncMock(return_value="FORECAST_SENTINEL")

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        out = capsys.readouterr().out
        assert result == 0
        # forecast branch executed
        mock.async_get_forecast.assert_awaited_once()
        assert "FORECAST_SENTINEL" in out
        # console read-printing branch executed, now with register in the header
        assert "[ELECTRIC / register UP1]" in out
        assert "209" in out and "328" in out


# ---------------------------------------------------------------------------
# run() -- credential prompting when args omitted
# ---------------------------------------------------------------------------


class TestRunPrompting:
    """Tests for run() prompting for username/password when not passed as args."""

    @pytest.mark.asyncio
    async def test_prompts_for_username_and_password(self, tmp_path):
        """When --username/--password are omitted, run() prompts via input()/getpass()."""
        out = tmp_path / "out.csv"
        args = build_parser().parse_args(["--csv", str(out)])  # no username/password

        captured = {}

        def fake_dominionsc(session, username, password, login_data):
            captured["username"] = username
            captured["password"] = password
            return _mock_dominionsc()

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", side_effect=fake_dominionsc),
            patch("dominionsc.cli.input", return_value="typed_user"),
            patch("dominionsc.cli.getpass", return_value="typed_pass"),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        assert captured["username"] == "typed_user"
        assert captured["password"] == "typed_pass"

    @pytest.mark.asyncio
    async def test_reads_existing_login_data_file(self, tmp_path):
        """An existing login_data_file is read and passed into DominionSC."""
        out = tmp_path / "out.csv"
        login_file = tmp_path / "login.json"
        login_file.write_text('{"tfa_token": "saved_token"}')
        args = _args("--csv", str(out), "--login_data_file", str(login_file))

        captured = {}

        def fake_dominionsc(session, username, password, login_data):
            captured["login_data"] = login_data
            return _mock_dominionsc()

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", side_effect=fake_dominionsc),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            await run(args)

        assert captured["login_data"] == {"tfa_token": "saved_token"}

    @pytest.mark.asyncio
    async def test_missing_login_data_file_is_tolerated(self, tmp_path):
        """A non-existent login_data_file does not crash (FileNotFoundError swallowed)."""
        out = tmp_path / "out.csv"
        args = _args("--csv", str(out), "--login_data_file", str(tmp_path / "missing.json"))

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=_mock_dominionsc()),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 0


# ---------------------------------------------------------------------------
# run() -- login failure paths
# ---------------------------------------------------------------------------


class TestRunLoginFailures:
    """Tests for run() returning non-zero on auth failures."""

    @pytest.mark.asyncio
    async def test_invalid_auth_returns_one(self, tmp_path):
        """A plain InvalidAuth during login makes run() return exit code 1."""
        out = tmp_path / "out.csv"
        args = _args("--csv", str(out))

        mock = _mock_dominionsc()
        mock.async_login = AsyncMock(side_effect=InvalidAuth("bad creds"))

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 1

    @pytest.mark.asyncio
    async def test_mfa_failure_returns_one(self, tmp_path):
        """When MFA handling fails, run() returns exit code 1."""
        out = tmp_path / "out.csv"
        args = _args("--csv", str(out))

        mock = _mock_dominionsc()
        challenge = MfaChallenge("need tfa", MagicMock())
        mock.async_login = AsyncMock(side_effect=challenge)

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
            patch("dominionsc.cli._handle_mfa", AsyncMock(return_value=False)),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 1

    @pytest.mark.asyncio
    async def test_mfa_success_continues(self, tmp_path):
        """When MFA handling succeeds, run() proceeds and returns 0."""
        out = tmp_path / "out.csv"
        args = _args("--csv", str(out))

        mock = _mock_dominionsc()
        challenge = MfaChallenge("need tfa", MagicMock())
        mock.async_login = AsyncMock(side_effect=challenge)

        with (
            patch("dominionsc.cli.aiohttp.ClientSession") as mock_session_cls,
            patch("dominionsc.cli.DominionSC", return_value=mock),
            patch("dominionsc.cli._handle_mfa", AsyncMock(return_value=True)),
        ):
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)
            result = await run(args)

        assert result == 0


# ---------------------------------------------------------------------------
# _handle_mfa() tests
# ---------------------------------------------------------------------------


def _mfa_handler(options: dict | None = None, submit_result=None, submit_raises=False):
    """Build a mock TFA handler for _handle_mfa tests."""
    handler = MagicMock()
    handler.async_get_tfa_options = AsyncMock(return_value=options or {})
    handler.async_select_tfa_option = AsyncMock()
    if submit_raises:
        handler.async_submit_tfa_code = AsyncMock(side_effect=InvalidAuth("bad code"))
    else:
        handler.async_submit_tfa_code = AsyncMock(return_value=submit_result or {"tfa_token": "tok"})
    return handler


class TestHandleMfa:
    """Tests for the interactive _handle_mfa flow."""

    @pytest.mark.asyncio
    async def test_success_with_options(self, capsys):
        """Full happy path: select an option, submit code, retry login, return True."""
        from dominionsc.cli import _handle_mfa

        handler = _mfa_handler(options={"sms_1": "Text to ****1234"})
        challenge = MfaChallenge("tfa needed", handler)
        dominionsc = MagicMock()
        dominionsc.async_login = AsyncMock()

        with (
            patch("dominionsc.cli.input", side_effect=["1", "123456"]),
        ):
            result = await _handle_mfa(dominionsc, challenge, None)

        assert result is True
        handler.async_select_tfa_option.assert_awaited_once_with("sms_1")
        handler.async_submit_tfa_code.assert_awaited_once_with("123456")
        dominionsc.async_login.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_success_without_options(self):
        """When no TFA options are offered, the code is entered directly."""
        from dominionsc.cli import _handle_mfa

        handler = _mfa_handler(options={})  # no options -> skip selection
        challenge = MfaChallenge("tfa needed", handler)
        dominionsc = MagicMock()
        dominionsc.async_login = AsyncMock()

        with patch("dominionsc.cli.input", return_value="999999"):
            result = await _handle_mfa(dominionsc, challenge, None)

        assert result is True
        handler.async_select_tfa_option.assert_not_awaited()
        handler.async_submit_tfa_code.assert_awaited_once_with("999999")

    @pytest.mark.asyncio
    async def test_invalid_code_returns_false(self):
        """A rejected TFA code makes _handle_mfa return False."""
        from dominionsc.cli import _handle_mfa

        handler = _mfa_handler(options={}, submit_raises=True)
        challenge = MfaChallenge("tfa needed", handler)
        dominionsc = MagicMock()
        dominionsc.async_login = AsyncMock()

        with patch("dominionsc.cli.input", return_value="000000"):
            result = await _handle_mfa(dominionsc, challenge, None)

        assert result is False
        dominionsc.async_login.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_invalid_tfa_choice_returns_false(self):
        """Cover cli.py 103-105: bad option index returns False."""
        from dominionsc.cli import _handle_mfa
        handler = _mfa_handler(options={"sms_1": "Text to ***1234"})
        challenge = MfaChallenge("tfa needed", handler)
        dominionsc = MagicMock()
        dominionsc.async_login = AsyncMock()

        with patch("dominionsc.cli.input", side_effect=["99", "000000"]):
            result = await _handle_mfa(dominionsc, challenge, None)
        assert result is False

    @pytest.mark.asyncio
    async def test_saves_login_data_file_on_success(self, tmp_path):
        """On success with a login_data_file set, the token is written to disk."""
        from dominionsc.cli import _handle_mfa

        login_file = tmp_path / "login.json"
        handler = _mfa_handler(options={}, submit_result={"tfa_token": "persist_me"})
        challenge = MfaChallenge("tfa needed", handler)
        dominionsc = MagicMock()
        dominionsc.async_login = AsyncMock()

        with patch("dominionsc.cli.input", return_value="111111"):
            result = await _handle_mfa(dominionsc, challenge, str(login_file))

        assert result is True
        assert json.loads(login_file.read_text()) == {"tfa_token": "persist_me"}


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


class TestMain:
    """Tests for the main() entry point."""

    def test_main_parses_and_runs(self):
        """main() parses argv and calls asyncio.run(run(...)), exiting with its code."""
        with (
            patch("dominionsc.cli.build_parser") as mock_parser_builder,
            patch("dominionsc.cli.asyncio.run", return_value=0) as mock_run,
            patch("dominionsc.cli.sys.exit") as mock_exit,
        ):
            mock_parser = MagicMock()
            mock_parser.parse_args.return_value = MagicMock()
            mock_parser_builder.return_value = mock_parser
            main()

        mock_run.assert_called_once()
        mock_exit.assert_called_once_with(0)
