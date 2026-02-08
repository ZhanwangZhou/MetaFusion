# utils/extract_and_score_time.py
import re
import math
import calendar
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

import dateparser
from dateparser.search import search_dates


def extract_time_range(prompt: str, now: Optional[datetime] = None) -> Tuple[Optional[datetime], Optional[datetime]]:
    """
    Robust time extraction:
    - Uses dateparser.search.search_dates to find date-like chunks in the prompt
    - Handles explicit ranges ("from X to Y", "X - Y")
    - Expands year/month/week/quarter/season into bounds
    - Falls back to parsing entire prompt
    """

    # 1) Find all date-like chunks
    matches = search_dates(
        prompt,
        settings={
            "RETURN_AS_TIMEZONE_AWARE": False,
            "PREFER_DATES_FROM": "past",
            **({"RELATIVE_BASE": now} if now is not None else {}),
        },
    ) or []

    # If nothing found, fallback to parsing whole prompt as one date
    if not matches:
        dt = _parse_dt(prompt.strip(), now)
        return (None, None) if not dt else _day_bounds(dt.replace(tzinfo=None))

    # 2) If we found >=2, attempt explicit range detection using nearby connectors
    # We'll look at the first two *distinct* date texts and see if prompt contains a connector between them.
    texts: List[str] = []
    dts: List[datetime] = []
    for t, dt in matches:
        t = t.strip()
        if t and t not in texts:
            texts.append(t)
            dts.append(dt.replace(tzinfo=None))
        if len(texts) >= 2:
            break

    if len(texts) >= 2:
        # if connector appears between the first two occurrences in the prompt, treat as range
        p = prompt.lower()
        i1 = p.find(texts[0].lower())
        i2 = p.find(texts[1].lower(), i1 + 1)
        if i1 != -1 and i2 != -1:
            between = p[i1 + len(texts[0]): i2]
            if _RANGE_CONNECTOR.search(between):
                start = dts[0]
                end = dts[1]
                if end < start:
                    start, end = end, start
                # expand endpoints to day bounds to be consistent
                start = _day_bounds(start)[0]
                end = _day_bounds(end)[1]
                return start, end

    # 3) Infer granularity from the matched text
    text = texts[0]
    dt = dts[0]
    print(dt, texts)

    m = _YEAR_ONLY.match(text)
    if m:
        return _year_bounds(int(m.group(1)))

    m = _YEAR_MONTH_NUM.match(text)
    if m:
        return _month_bounds(int(m.group(1)), int(m.group(2)))

    m = _QUARTER.match(text)
    if m:
        return _quarter_bounds(int(m.group(1)), int(m.group(2)))

    if _WEEK_WORD.search(text):
        return _week_bounds(dt, week_starts_monday=True)

    if _SEASON.search(text) and re.search(r"\b\d{4}\b", text):
        year = int(re.search(r"\b(\d{4})\b", text).group(1))
        season = _SEASON.search(text).group(1)
        return _season_bounds(season, year)

    if _MONTH_WORD.search(text) and re.search(r'(\d{2})[,\s]+(\d{4})\b', text):
        return _day_bounds(dt)

    if _MONTH_WORD.search(text) and re.search(r"\b\d{4}\b", text):
        # likely "June 2025" style; dateparser already parsed dt correctly
        return _month_bounds(dt.year, dt.month)

    # default: treat as a specific day
    return _day_bounds(dt)


def w_timestamp(prompt: str,
                t_start: Optional[datetime],
                t_end: Optional[datetime],
                *,
                half_life_days: float = 30.0) -> float:
    """
    Returns timestamp score in [0,1].
    half_life_days=30 => month range gives ~0.5 specificity.
    """
    prompt_l = prompt.lower()

    if not (t_start and t_end):
        soft = 1.0 if SOFT_TIME.search(prompt_l) else 0.0
        return 0.25 * soft  # small but non-zero

    span_days = max(0.0001, (t_end - t_start).total_seconds() / 86400.0)

    s_span = math.exp(-math.log(2.0) * (span_days / half_life_days))

    hard_hits = 1.0 if HARD_TIME.search(prompt_l) else 0.0
    soft_hits = 1.0 if SOFT_TIME.search(prompt_l) else 0.0

    raw = 0.10 + 0.75 * s_span + 0.20 * hard_hits + 0.10 * soft_hits
    w = _sigmoid(3.0 * (raw - 0.5))
    return max(0.0, min(1.0, w))


_RANGE_CONNECTOR = re.compile(r"\b(from|between)\b|\b(to|and|through|thru|until|till)\b|[-–—~]", re.I)

_YEAR_ONLY = re.compile(r"^\s*(\d{4})\s*$")
_YEAR_MONTH_NUM = re.compile(r"^\s*(\d{4})[-/](\d{1,2})\s*$")
_QUARTER = re.compile(r"^\s*Q([1-4])\s*(\d{4})\s*$", re.I)

_REGEX_MONTH = r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|"\
               r"sep(tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b"
_WEEK_WORD = re.compile(r"\b(this|last|next)\s+week\b", re.I)
_MONTH_WORD = re.compile(
    r"\b(jan(uary)?|feb(ruary)?|mar(ch)?|apr(il)?|may|jun(e)?|jul(y)?|aug(ust)?|"
    r"sep(tember)?|oct(ober)?|nov(ember)?|dec(ember)?)\b",
    re.I,
)

_SEASON = re.compile(r"\b(spring|summer|fall|autumn|winter)\b", re.I)


def _month_bounds(year: int, month: int) -> Tuple[datetime, datetime]:
    last_day = calendar.monthrange(year, month)[1]
    start = datetime(year, month, 1, 0, 0, 0, 0)
    end = datetime(year, month, last_day, 23, 59, 59, 999999)
    return start, end


def _year_bounds(year: int) -> Tuple[datetime, datetime]:
    return datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59, 999999)


def _day_bounds(dt: datetime) -> Tuple[datetime, datetime]:
    d0 = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    d1 = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return d0, d1


def _week_bounds(dt: datetime, week_starts_monday: bool = True) -> Tuple[datetime, datetime]:
    # dt is any day inside the week
    weekday = dt.weekday()  # Mon=0
    if not week_starts_monday:
        weekday = (weekday + 1) % 7  # Sun=0 equivalent
    start = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=weekday)
    end = start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999)
    return start, end


def _quarter_bounds(q: int, year: int) -> Tuple[datetime, datetime]:
    month0 = 1 + (q - 1) * 3
    start = datetime(year, month0, 1, 0, 0, 0, 0)
    end = _month_bounds(year, month0 + 2)[1]
    return start, end


def _season_bounds(season: str, year: int) -> Tuple[datetime, datetime]:
    # Northern hemisphere default; tweak if you care.
    s = season.lower()
    if s == "spring":
        return datetime(year, 3, 1), _month_bounds(year, 5)[1]
    if s == "summer":
        return datetime(year, 6, 1), _month_bounds(year, 8)[1]
    if s in ("fall", "autumn"):
        return datetime(year, 9, 1), _month_bounds(year, 11)[1]
    if s == "winter":
        # Winter spans years; choose Dec->Feb around the given year.
        start = datetime(year, 12, 1)
        end = _month_bounds(year + 1, 2)[1]
        return start, end
    raise ValueError(season)


def _parse_dt(text: str, now: Optional[datetime]) -> Optional[datetime]:
    settings = {
        "RETURN_AS_TIMEZONE_AWARE": False,
        "PREFER_DATES_FROM": "past",
    }
    if now is not None:
        settings["RELATIVE_BASE"] = now
    return dateparser.parse(text, settings=settings)


HARD_TIME = re.compile(r"\b(on|in|during|between|from|to|before|after|since|until|till|by)\b", re.I)
SOFT_TIME = re.compile(r"\b(recent|recently|latest|newest|new|old|earlier|back then|now|today|yesterday|tomorrow)\b", re.I)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
