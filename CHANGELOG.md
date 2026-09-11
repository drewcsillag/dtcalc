# Changelog

Notable changes to dtcalc. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

Dates are now distinct from date-times, and days no longer group into weeks.

### Added

- **A `Date` value type**: a calendar day, with no time and no zone. A bare
  date literal is a date, and so are `today`, `tomorrow`, `yesterday`,
  `upcoming friday` and `previous 15th`. A date stays a date under calendar
  arithmetic and becomes an instant as soon as something names a time — an
  exact duration, a clock reading, or a zone.
- `2027-01-03 - 2026-12-24` answers `10d`. Subtracting two dates counts
  calendar days; subtracting two instants still measures elapsed time.
- `trunc`, `round` and `ceil` accept **month and year granularities**, which
  previously errored. They only ever errored because the result had to be an
  instant and a month has no fixed length; the result is now a date, which
  needs none.
- `:fmt weeks` / `:fmt noweeks` to control week grouping.
- `--tz ZONE` to set the working zone for one invocation, overriding
  `DTCALC_TZ`.
- `:vars` names each value's kind, since a date and a midnight instant can
  otherwise look alike.
- `--dump-ast` distinguishes `date(2026-12-24)` from `dt(2026-12-24T12:15)`.

### Changed

- **Days no longer group into weeks.** `8d` prints `8d` rather than `1w1d`,
  and weeks you type are echoed back as days, so `3w2h5m` prints `21d2h5m`.
  `:fmt weeks` restores the old rendering. The toggle covers the day ladder
  only: `15mo` is still `1y3mo`.
- **A bare date no longer prints as a midnight instant.** `2026-05-23` was
  `2026-05-23T00:00:00-04:00  America/New_York`; it is now `2026-05-23`.
- **`trunc(x, 1d)` and friends return a date**, where they previously returned
  a midnight instant. The granularity decides the result type.
- `:tz` calls it the **working zone** rather than the display zone, because it
  governs the arithmetic and not just the rendering. The old wording hid a
  capability that was already there.
- Error wording widened with the concept: "cannot add two points in time"
  rather than "two instants".

### Fixed

- `diff` was not invertible in the backward direction. It computed the
  backward case by negating the forward one, but negating a months-plus-days
  duration is not its inverse when month steps clamp the day of month: Jan 2
  `+1mo +28d` is Mar 1, while Mar 1 `-1mo -28d` is Jan 4. Each direction is
  decomposed on its own now. Found by a property test.
- The coverage badge understated `repl.py` at 56%: the pty-driven subprocess
  was not being measured, though it is exercised end to end.

## [0.1.0]

First release.

### Added

- An interactive REPL, a one-shot mode and a pipe mode for date, time,
  duration and timezone arithmetic.
- Instants, durations, numbers and booleans. Variables.
- Durations across four ladders that never convert into each other: exact
  (`ms`/`s`/`m`/`h`), calendar days (`d`/`w`), calendar months (`mo`/`y`) and
  business days (`bd`). `24h` is never `1d`.
- Timezone conversion with `in` and reinterpretation with `@`, over a curated
  alias table plus the full IANA database.
- Colon literals resolved from context, with `12:15m` and `:12:15` to force a
  duration; 12-hour clock readings such as `4p` and `4:30pm`.
- Comparisons, `min`, `max`, `round`, `trunc`, `ceil`, `diff`, `epoch`,
  `epochms`, `unix`.
- `:fmt iso|human|unix|timeonly` and a 12/24-hour clock setting.
- Published to PyPI as `dtcalc-cli`; the command and the import package are
  both `dtcalc`.

[Unreleased]: https://github.com/drewcsillag/dtcalc/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/drewcsillag/dtcalc/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/drewcsillag/dtcalc/releases/tag/v0.1.0
