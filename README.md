# dtcalc

[![CI](https://github.com/drewcsillag/dtcalc/actions/workflows/ci.yml/badge.svg)](https://github.com/drewcsillag/dtcalc/actions/workflows/ci.yml)

An interactive REPL for date, time, duration and timezone calculations.

```
$ dtcalc
dtcalc — :help for the language, :q to quit
dtcalc> now + 7h
2026-09-11T18:27:54-04:00  America/New_York
dtcalc> standup = upcoming monday 09:30
2026-09-14T09:30:00-04:00  America/New_York
dtcalc> standup in London
2026-09-14T14:30:00+01:00  Europe/London
dtcalc> standup - now
70h2m6s
dtcalc> 12:13 @ sf
2026-09-11T15:13:00-04:00  America/New_York
```

Pure Python, no runtime dependencies.

## Install

```sh
uv tool install dtcalc-cli          # or: pipx install dtcalc-cli
```

From a clone: `uv tool install .`  ·  From git:
`uv tool install git+https://github.com/drewcsillag/dtcalc`

The distribution is named **`dtcalc-cli`** because `dtcalc` was already taken
on PyPI by an unrelated 2021 package. The command you run, and the package you
import, are both still `dtcalc`.

## Running it

| Command | What it does |
| --- | --- |
| `dtcalc` | interactive REPL |
| `dtcalc 'now + 7h'` | evaluate one expression and exit |
| `… \| dtcalc` | evaluate each line of stdin |
| `… \| dtcalc --transcript` | the same, echoing each line with a prompt |

In piped mode an error on one line does not stop the rest, but the process
still exits non-zero — so a batch of expressions is scriptable without
mistakes passing silently.

## Values

Four types: **instants**, **durations**, **numbers** and **booleans**.

### Instants

| Written | Means |
| --- | --- |
| `now` | the current instant, read once per line |
| `today`, `tomorrow`, `yesterday` | midnight, in the display zone |
| `today 09:30`, `tomorrow 17:00` | a day plus a clock reading |
| `2026-05-23T12:15:13` | ISO; the `T` may be a space |
| `2026-05-23T12:15` | seconds default to zero |
| `2026-05-23` | midnight |
| `2026-05-23T12:15:13Z`, `…-07:00` | with an explicit UTC offset |
| `upcoming friday`, `previous mon` | strictly after / before today |
| `upcoming 15th`, `previous 1st` | day of the month, strictly after / before |
| `epoch(1789073107)` | Unix seconds |
| `epochms(1789073107000)` | Unix milliseconds |
| `16:00`, `4p`, `4a`, `4:30pm` | a clock reading, today |

`upcoming friday` on a Friday means seven days out, not today — `today`
already names today. `upcoming 31st` skips months that have no 31st.

A meridiem suffix gives a 12-hour reading: `4p`, `4pm`, `4:30p`, `4:30:15pm`,
and the same with `a`/`am`. `12a` is midnight and `12p` is noon.

### Durations

Written as unit-suffixed runs: `3w2h5m`, `250ms`, `1.5s`, `3bd`, `1y2mo`.

The units form **four ladders that never convert into each other**:

| Ladder | Units | Cascades |
| --- | --- | --- |
| exact | `ms` `s` `m` `h` | `90m` → `1h30m`, `3661s` → `1h1m1s` |
| calendar days | `d` `w` | `8d` → `1w1d` |
| calendar months | `mo` `y` | `15mo` → `1y3mo` |
| business days | `bd` | Mon–Fri, no holidays |

See [Why `24h` is never `1d`](#why-24h-is-never-1d) — this is the one design
decision worth understanding before using the tool.

## Clock readings with colons

A colon literal means whatever the surrounding operator requires:

```
dtcalc> 12:15                  # nothing else to go on, so a clock reading
2026-05-23T12:15:00-04:00  America/New_York
dtcalc> now - 12:15            # only a duration typechecks here
2026-05-23T00:00:13-04:00  America/New_York
```

Where **both** readings would typecheck, the clock reading wins — on the
grounds that a duration is more naturally written `12h15m` anyway:

```
dtcalc> 12:15 + 3h
2026-05-23T15:15:00-04:00  America/New_York
```

Two explicit forms force a duration. A trailing `h` or `m` names the unit of
the **leftmost** field; a leading colon shifts the units down one place:

| Written | Means |
| --- | --- |
| `12:15` | 12h15m, or 12:15:00 — context decides |
| `12:15h` | 12h15m |
| `12:15m` | **12m15s** |
| `:12:15` | 12m15s |
| `::15` | 15s |
| `1:02:03` | 1h2m3s |

## Timezones

Two separate operations, which `TZ(zone, time)`-style syntax tends to
conflate:

| Syntax | Meaning | Example (display zone New York) |
| --- | --- | --- |
| `expr @ zone` | **attach** — read this wall clock as being in `zone` | `12:13 @ sf` → `15:13` |
| `expr in zone` | **convert** — same instant, shown in `zone` | `now in Tokyo` |

They compose: `12:13 @ sf + 2h in Tokyo`.

Zone names resolve in this order: an exact IANA name containing a `/`; then a
curated alias; then any other exact IANA name; then a **unique**
case-insensitive substring match. Several matches is an error that lists the
candidates rather than a guess.

Aliases cover `sf`, `la`, `seattle`, `denver`, `chicago`, `nyc`, `newyork`,
`boston`, `london`, `paris`, `berlin`, `amsterdam`, `telaviv`, `bangalore`,
`india`, `singapore`, `tokyo`, `sydney`, `utc`, and the usual abbreviations
(`PST`, `EST`, `CET`, `GMT`, …). Abbreviations deliberately resolve to the
*city* zone, so `EST` means US Eastern with daylight saving rather than the
fixed-offset `EST` zone that the tz database still carries and nobody means.

`:zones <text>` searches the full list.

## Setting the time on a date

`@` also attaches a **time of day**, keeping the date it is given:

```
dtcalc> deploy = 2026-07-04T09:00
2026-07-04T09:00:00-04:00  America/New_York
dtcalc> deploy @ 4p
2026-07-04T16:00:00-04:00  America/New_York
dtcalc> upcoming friday @ 4:30pm
2026-05-29T16:30:00-04:00  America/New_York
dtcalc> (now @ 16:00) - (now @ 12:00)
4h
```

The two forms of `@` never collide, because a zone name cannot begin with a
digit: an identifier after `@` is a zone, a clock reading is a time.

## Operators

Tightest binding first:

| Level | Operators |
| --- | --- |
| 1 | `@` |
| 2 | `*` `/` `%` |
| 3 | `+` `-` |
| 4 | `<` `<=` `>` `>=` `==` `!=` (non-associative) |
| 5 | `in` |
| 6 | `=` |

| Expression | Result |
| --- | --- |
| `instant + duration` | instant |
| `instant - duration` | instant |
| `instant - instant` | duration (**exact** elapsed time) |
| `duration ± duration` | duration |
| `duration * number` | duration |
| `duration / number` | duration |
| `duration / duration` | number |
| `duration % duration` | duration (same ladder only) |
| `-duration` | duration |

`in` takes a bare zone *name* on the right, not an expression — zones are not
values. So `now + 1d in Tokyo` groups as `(now + 1d) in Tokyo`, and
`now in Tokyo + 2h` is a parse error; write `(now in Tokyo) + 2h`.

## Functions

| Function | Notes |
| --- | --- |
| `min(…)`, `max(…)` | one or more arguments, all the same kind |
| `round(x, g)`, `trunc(x, g)`, `ceil(x, g)` | `x` is an instant or a duration |
| `diff(a, b)` | the **calendar** duration from `a` to `b` |
| `epoch(n)`, `epochms(n)` | Unix seconds / milliseconds to an instant |
| `unix(x)` | an instant to Unix seconds |

`diff` is the counterpart to subtraction. Subtracting two instants measures
elapsed time, so a week apart reads as `168h`; `diff` decomposes against the
endpoints, so it reads as `1w`:

```
dtcalc> a = 2026-11-01T00:30
dtcalc> b = 2026-11-02T00:30
dtcalc> b - a
25h
dtcalc> diff(a, b)
1d
```

Both answers are right. That day really was 25 hours long, and it really was
one day.

Rounding an instant is anchored at **midnight in the display zone**. An exact
granularity (`15m`, `7h`) buckets elapsed time from there; a calendar
granularity (`1d`, `1w`) buckets whole local dates, so `trunc(x, 1d)` is
midnight even on a 23- or 25-hour day. Week buckets land on Monday. Months,
years and business days are refused as granularities for an instant, because
there is no anchor from which they are a fixed distance.

## Variables

```
dtcalc> foo = now
dtcalc> bar = foo + 5h
dtcalc> bar - foo
5h
```

Assignment is **eager**: `foo = now` captures a value rather than a live
reading of the clock. Assignment echoes what it stored. Variables last for
the session and are not saved. Keywords, unit names and function names cannot
be used as variable names.

## Commands

| Command | |
| --- | --- |
| `:help` | the language, in one screen |
| `:vars` | list the variables |
| `:zones <text>` | search timezone names |
| `:tz <zone>` | set the display zone |
| `:fmt <format>` and/or `<clock>` | `iso`, `human`, `unix`, `timeonly`; `24h`, `12h` |
| `:q` | quit (so does Ctrl-D) |

A leading `:` followed by a letter is a command; followed by a digit or
another colon it is a value, which is what lets `:help` and `:12:15` coexist.

`:fmt` takes a format, a clock convention, or both — `:fmt timeonly 12h`,
or `:fmt 12h` to change only the convention.

| Format | `now` renders as |
| --- | --- |
| `iso` | `2026-05-23T12:15:13-04:00  America/New_York` |
| `human` | `Sat 2026-05-23 12:15:13 EDT` |
| `timeonly` | `12:15:13 EDT` |
| `unix` | `1779552913` |

`iso`, `human` and `unix` always print the full date, so arithmetic that
rolled over into another day is visible. **`timeonly`** drops it, for
arithmetic where the date is not the point — but appends a relative day
marker when the result is not on today's date, so a rollover still cannot
hide:

```
dtcalc> :fmt timeonly
dtcalc> now
12:15:13 EDT
dtcalc> now + 20h
08:15:13 EDT (+1d)
```

The 12-hour clock applies to `human` and `timeonly`:

```
dtcalc> :fmt timeonly 12h
dtcalc> now
12:15:13 PM EDT
```

It deliberately does **not** apply to `iso`: a 12-hour ISO 8601 timestamp is
not ISO 8601, and would break anything parsing the output. `unix` has no
clock at all — and in that format a duration prints as a bare count of
seconds, so everything a pipeline sees is a number.

Colour is on when stdout is a terminal, and off for a pipe, for `NO_COLOR`,
or for `--no-color`. The prompt itself is coloured only under GNU readline:
libedit, which macOS ships, has no working way to mark escape sequences as
zero-width, and counting them puts the cursor in the wrong column after
Ctrl-A on a wrapped line.

## Two decisions worth explaining

### Why `24h` is never `1d`

`d` and `w` are **calendar** units: `+1d` means "the same wall-clock time
tomorrow", which is 23, 24 or 25 hours depending on where it lands. `h`, `m`,
`s` and `ms` are **exact** elapsed time. Since the two are not interchangeable,
normalization never promotes hours into days:

```
dtcalc> 8h * 3
24h
dtcalc> 2026-11-01T00:30 + 1d      # same wall clock, 25 real hours later
2026-11-02T00:30:00-05:00  America/New_York
dtcalc> 2026-11-01T00:30 + 24h     # 24 real hours later, one hour earlier on the clock
2026-11-01T23:30:00-05:00  America/New_York
```

The cost is that `8h * 3` does not print `1d`. The benefit is that no
expression silently assumes a day is 24 hours long, which would be wrong
twice a year with nothing to indicate it.

Comparison is the one place a nominal 24-hour day is allowed, because an
approximate answer there is still useful: `1d < 25h` is `true`. Months and
business days get no such fallback — `1mo < 720h` is an error rather than a
plausible-looking guess.

A duration can hold parts from several ladders at once, and prints them
honestly rather than pretending they reduce:

```
dtcalc> 1d - 90m
1d -1h30m
```

### Daylight saving

A **typed literal** naming a wall-clock time that does not exist, or one that
happens twice, is refused — that is a mistake worth hearing about:

```
dtcalc> 2026-03-08T02:30
error: 2026-03-08T02:30:00 does not exist in America/New_York: the clocks skip forward over it
  2026-03-08T02:30
  ^^^^^^^^^^^^^^^^
```

Reaching one **by arithmetic** is not the user's doing, so it resolves and
says what it did:

```
dtcalc> 2026-03-07T02:30 + 1d
2026-03-08T03:30:00-04:00  America/New_York
note: 2026-03-08T02:30:00 does not exist in America/New_York (clocks skip forward), so it was moved forward
```

Nonexistent times shift forward by the gap; ambiguous times take the earlier
of the two.

## Development

```sh
make check     # ruff + mypy --strict + pytest
make fmt       # format and autofix
make install   # uv tool install --force .
```

CI runs `make check` on Linux and macOS. Both are worth having: Linux uses
GNU readline and macOS ships libedit, and the REPL's prompt handling has to
differ between them.

Releases publish to PyPI from a GitHub release via Trusted Publishing, so
there is no API token anywhere. The version lives in `src/dtcalc/__init__.py`
and the packaging metadata reads it from there, so `dtcalc --version` and the
published version cannot drift; the release workflow additionally refuses to
publish if the tag and the version disagree.

The release workflow is split in two on purpose. The `build` job runs the
tests, the build and anything else that executes project code or code fetched
from PyPI, and it holds no permissions. Only the `publish` job holds
`id-token: write`, and it runs no project code at all — it takes the built
artifact and hands it to the publish action. Otherwise a compromised dev
dependency would be executing in a job able to mint a PyPI token.

Actions are pinned to commit SHAs rather than tags, since tags are mutable.

Two debugging aids print the intermediate stages. The parser leaves colon
literals undecided and a separate pass resolves them, so `--dump-ast` shows
the tree twice:

```sh
$ dtcalc --dump-tokens '2026-05-23T12:15:13 - 12:15'
$ dtcalc --dump-ast '12:15 + 3h'
parsed:   (+ colon(12:15) 3h)
resolved: (+ tod(12:15:00) 3h)
```

`DTCALC_NOW` freezes the clock and `DTCALC_TZ` sets the display zone. They
exist so output can be made reproducible — the golden transcripts in
`tests/golden/` could not otherwise mention `now`. To regenerate those after
an intentional change:

```sh
UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py
```

Then read the diff. A change you cannot explain is a bug, not a stale file.

## Licence

MIT.
