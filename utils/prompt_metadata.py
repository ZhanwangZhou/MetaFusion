# utils/prompt_metadata.py
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Tuple
from utils.config import LOGGER
from utils.geocode import geocode_bbox
import re
import dateparser
import spacy


# Global lazy-loaded spaCy model to avoid reloading every time
_NLP = None


def extract_prompt_meta(prompt: str) -> dict:
    extractor = PromptMetadataExtractor()
    meta = extractor.extract(prompt)
    LOGGER.debug("Parsed metadata:", meta.to_dict())

    min_lat, max_lat, min_lon, max_lon = -90, 90, -180, 180

    # If a location was extracted (e.g., ["Yosemite"]), geocode the first place
    if meta.locations:
        bbox = geocode_bbox(meta.locations[0], radius_km=50.0)
        if bbox is not None:
            min_lat, max_lat, min_lon, max_lon = bbox
            LOGGER.info(
                f"Geocoded location '{meta.locations[0]}' "
                f"-> bbox: lat[{min_lat: .4f}, {max_lat: .4f}], "
                f"lon[{min_lon: .4f}, {max_lon: .4f}]"
            )
        else:
            LOGGER.warning(f"Warning: could not geocode location: {meta.locations[0]}")

    return {
        'start_ts': meta.start_ts or datetime.min,
        'end_ts': meta.end_ts or datetime.max,
        'min_lat': min_lat,
        'max_lat': max_lat,
        'min_lon': min_lon,
        'max_lon': max_lon,
        'any_tags': meta.tags or None
    }


def _get_nlp():
    global _NLP
    if _NLP is None:
        # You need to run beforehand: python -m spacy download en_core_web_sm
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


@dataclass
class PromptMetadata:
    """Structured information extracted from the user's query."""
    # Time range (if only a single point, start == end)
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None

    # Location phrases recognized in the original text (e.g., "Yosemite", "New York")
    locations: List[str] = None

    # Words used as tags/keywords (e.g., "dog", "wedding")
    tags: List[str] = None

    # Original query text
    raw_prompt: str = ""

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # convert datetimes to ISO strings for printing / JSON
        if self.start_ts:
            d["start_ts"] = self.start_ts.isoformat()
        if self.end_ts:
            d["end_ts"] = self.end_ts.isoformat()
        return d


class PromptMetadataExtractor:
    """
    Extract from a user's natural language prompt:
    - time range (start_ts, end_ts)
    - location phrases (locations)
    - keyword tags (can be used for the metadata table's tags field)
    """

    def __init__(self):
        self.nlp = _get_nlp()

    # -------- Public entry point --------
    def extract(self, prompt: str) -> PromptMetadata:
        doc = self.nlp(prompt)

        locations = self._extract_locations(doc)
        start_ts, end_ts = self._extract_time_range(doc, prompt)
        tags = self._extract_tags(doc, locations)

        return PromptMetadata(
            start_ts=start_ts,
            end_ts=end_ts,
            locations=locations,
            tags=tags,
            raw_prompt=prompt,
        )

    # -------- Internal: location extraction --------
    def _extract_locations(self, doc) -> List[str]:
        locs = []
        for ent in doc.ents:
            if ent.label_ in ("GPE", "LOC", "FAC"):
                text = ent.text.strip()
                if text and text not in locs:
                    locs.append(text)
        return locs

    # -------- Internal: time range extraction --------
    def _extract_time_range(self, doc, prompt: str) -> Tuple[Optional[datetime], Optional[datetime]]:
        """
        Strategy:
        - Find the first DATE entity and parse it with dateparser.
        - If it looks like:
            * year-only:      expand to whole year
            * year-month:     expand to whole month
            * full date:      expand to that day (00:00–23:59:59.999999)
        - If no DATE entity, fall back to parsing the whole prompt.
        """
        date_text = None
        for ent in doc.ents:
            if ent.label_ == "DATE":
                date_text = ent.text.strip()
                break

        if not date_text:
            # Fallback: try parsing the entire prompt
            date_text = prompt.strip()

        dt = dateparser.parse(date_text)
        if not dt:
            return None, None

        # Normalize parsed datetime (we'll set precise bounds below)
        dt = dt.replace(tzinfo=None)

        text = date_text.strip()
        lower = text.lower()

        # 1) Year-only: "2025"
        if re.fullmatch(r"\d{4}", text):
            year = dt.year
            start = datetime(year, 1, 1, 0, 0, 0, 0)
            end = datetime(year, 12, 31, 23, 59, 59, 999999)
            return start, end

        # 2) Month-name + year: "June 2025", "november 2024", etc.
        months = [
            "january", "february", "march", "april", "may", "june",
            "july", "august", "september", "october", "november", "december"
        ]
        looks_like_month_name_year = any(m in lower for m in months) and any(c.isdigit() for c in lower)

        # Also treat numeric "YYYY/MM" or "YYYY-MM" as year-month
        looks_like_numeric_year_month = bool(re.fullmatch(r"\d{4}[-/]\d{1,2}", text))

        if looks_like_month_name_year or looks_like_numeric_year_month:
            year = dt.year
            month = dt.month
            start = datetime(year, month, 1, 0, 0, 0, 0)
            # end = last microsecond of the month
            if month == 12:
                next_month_start = datetime(year + 1, 1, 1, 0, 0, 0, 0)
            else:
                next_month_start = datetime(year, month + 1, 1, 0, 0, 0, 0)
            end = next_month_start - timedelta(microseconds=1)
            return start, end

        # 3) Otherwise: treat as a specific day
        day_start = dt.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return day_start, day_end

    # -------- Internal: tag extraction --------
    def _extract_tags(self, doc, locations: List[str]) -> List[str]:
        """
        Very simple heuristic:
        - Use nouns (NOUN, PROPN) and adjectives (ADJ) as tags
        - Exclude words already recognized as locations
        """
        loc_set = set(l.lower() for l in locations)
        tags = []

        for token in doc:
            if token.is_stop or token.is_punct or not token.text.strip():
                continue
            if token.pos_ not in ("NOUN", "PROPN", "ADJ"):
                continue

            text = token.lemma_.lower()
            if text in loc_set:
                continue
            if text not in tags:
                tags.append(text)

        return tags
