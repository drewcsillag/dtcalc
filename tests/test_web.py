"""The web bridge: a terminal-free facade over the session and completer.

These tests pin the contract the browser relies on — plain text out, an
outcome name, completions identical to the REPL's, and a state blob that
round-trips every value kind exactly.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from dtcalc.errors import DtcalcError
from dtcalc.web import WebSession

# 12:15:13 on 2026-05-23 in New York, as ms since the epoch.
NOW_MS = int(datetime(2026, 5, 23, 12, 15, 13, tzinfo=UTC).timestamp() * 1000) + 4 * 3600 * 1000


@pytest.fixture
def session() -> WebSession:
    return WebSession("America/New_York", now_ms=NOW_MS)


class TestRun:
    def test_ok_result_is_plain_text(self, session: WebSession) -> None:
        outcome, lines = session.run("now + 7h")
        assert outcome == "ok"
        assert lines == ["2026-05-23T19:15:13-04:00  America/New_York"]

    def test_no_ansi_escapes_anywhere(self, session: WebSession) -> None:
        for line in ("8h * 3", "now +", ":vars", ":help"):
            _, lines = session.run(line)
            assert all("\x1b" not in text for text in lines)

    def test_error_carries_the_caret_block(self, session: WebSession) -> None:
        outcome, lines = session.run("now +")
        assert outcome == "error"
        assert lines[0].startswith("error: ")
        assert any("^" in text for text in lines)

    def test_blank_line_is_nothing(self, session: WebSession) -> None:
        assert session.run("   ") == ("nothing", [])

    def test_quit_is_reported_not_acted_on(self, session: WebSession) -> None:
        assert session.run(":q") == ("quit", [])

    def test_variables_persist_between_lines(self, session: WebSession) -> None:
        session.run("foo = now")
        _, lines = session.run("foo + 1h - foo")
        assert lines == ["1h"]

    def test_meta_commands_work(self, session: WebSession) -> None:
        _, lines = session.run(":tz Tokyo")
        assert lines == ["working zone is now Asia/Tokyo"]
        _, lines = session.run("now")
        assert lines[0].endswith("Asia/Tokyo")

    def test_a_frozen_clock_is_honoured(self, session: WebSession) -> None:
        assert session.run("now")[1] == ["2026-05-23T12:15:13-04:00  America/New_York"]

    def test_set_now_none_returns_to_the_real_clock(self, session: WebSession) -> None:
        session.set_now(None)
        _, lines = session.run("unix(now)")
        assert int(lines[0]) > NOW_MS // 1000

    def test_set_now_replaces_the_frozen_time(self, session: WebSession) -> None:
        session.set_now(NOW_MS + 3_600_000)
        assert session.run("now")[1] == ["2026-05-23T13:15:13-04:00  America/New_York"]

    def test_unknown_zone_at_construction_is_a_clean_error(self) -> None:
        with pytest.raises(DtcalcError):
            WebSession("Not/AZone")


class TestComplete:
    def test_matches_the_repl_completer(self, session: WebSession) -> None:
        from dtcalc.repl import completions

        for line in ("to", ":t", "now in Toky", "12:13 @ s", ":fmt hu"):
            assert session.complete(line, len(line)) == completions(line, len(line), session._env)

    def test_sees_session_variables(self, session: WebSession) -> None:
        session.run("standup = upcoming monday")
        assert "standup" in session.complete("stan", 4)


class TestZoneNames:
    def test_lists_iana_names(self) -> None:
        names = WebSession.zone_names()
        assert "America/New_York" in names
        assert names == sorted(names)


VALUE_LINES = [
    "2026-12-24",  # date
    "now",  # instant
    "now in Tokyo",  # instant in another zone
    "12:15:13.5 @ london",  # sub-second instant
    "3w2h5m",  # exact + calendar days
    "1y2mo",  # months ladder
    "3bd",  # business days
    "250ms",  # exact only
    "8h / 3h",  # number
    "1 < 2",  # boolean
    "1.5s",  # fractional exact
    "-2d",  # negative
]


class TestState:
    def _populate(self, session: WebSession) -> None:
        for index, line in enumerate(VALUE_LINES):
            outcome, lines = session.run(f"v{index} = {line}")
            assert outcome == "ok", lines

    def test_round_trip_is_exact_for_every_value_kind(self, session: WebSession) -> None:
        self._populate(session)
        session.run(":fmt human 12h weeks")
        session.run(":tz Tokyo")
        blob = session.export_state()

        # A different frozen time and zone: the restore must not depend on either.
        restored = WebSession("UTC", now_ms=NOW_MS + 86_400_000)
        restored.import_state(blob)

        assert restored._env.variables == session._env.variables
        assert restored.run(":vars") == session.run(":vars")
        assert restored.run(":tz") == session.run(":tz")
        assert restored.run(":fmt") == session.run(":fmt")

    def test_instants_keep_their_own_zone(self, session: WebSession) -> None:
        session.run("t = now in Tokyo")
        restored = WebSession("UTC", now_ms=NOW_MS)
        restored.import_state(session.export_state())
        assert restored.run("t")[1][0].endswith("Asia/Tokyo")

    def test_a_restored_now_is_the_stored_value_not_a_fresh_reading(
        self, session: WebSession
    ) -> None:
        session.run("then = now")
        restored = WebSession("America/New_York", now_ms=NOW_MS + 3_600_000)
        restored.import_state(session.export_state())
        assert restored.run("now - then")[1] == ["1h"]

    def test_the_blob_is_json_with_a_version(self, session: WebSession) -> None:
        data = json.loads(session.export_state())
        assert data["v"] == 1

    def test_empty_session_round_trips(self, session: WebSession) -> None:
        restored = WebSession("UTC", now_ms=NOW_MS)
        restored.import_state(session.export_state())
        assert restored._env.variables == {}

    @pytest.mark.parametrize(
        "blob",
        [
            "not json",
            "[]",
            "{}",
            '{"v": 2}',
            '{"v": 1, "zone": "Not/AZone", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {}}',
            '{"v": 1, "zone": "UTC", "fmt": "bogus", "clock": "24h", "weeks": false, "vars": {}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "99h", "weeks": false, "vars": {}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": "yes", "vars": {}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false, "vars": []}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "mystery"}}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "date", "y": 2026, "m": 13, "d": 1}}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "instant", "utc": "garbage", "zone": "UTC"}}}',
            '{"v": 1, "zone": 5, "fmt": "iso", "clock": "24h", "weeks": false, "vars": {}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": 5}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "date", "y": true, "m": 1, "d": 1}}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "number", "n": "high"}}}',
            '{"v": 1, "zone": "UTC", "fmt": "iso", "clock": "24h", "weeks": false,'
            ' "vars": {"x": {"k": "boolean", "b": 1}}}',
        ],
    )
    def test_bad_state_is_a_clean_error_and_changes_nothing(
        self, session: WebSession, blob: str
    ) -> None:
        session.run("keep = 1h")
        with pytest.raises(DtcalcError, match="saved state"):
            session.import_state(blob)
        assert session.run("keep")[1] == ["1h"]
        assert session.run(":tz")[1] == ["working zone is America/New_York"]
