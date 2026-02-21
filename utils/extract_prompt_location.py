# utils/extract_and_score_locations.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List
from utils.geocode import geocode_location
import spacy

# Global lazy-loaded spaCy model to avoid reloading every time
_NLP = None


def _get_nlp():
    global _NLP
    if _NLP is None:
        # Need to run beforehand: python -m spacy download en_core_web_sm
        _NLP = spacy.load("en_core_web_sm")
    return _NLP


@dataclass
class Location:
    name: str
    score: float
    lat: float
    lon: float
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


def extract_locations(prompt: str) -> List[Location]:
    """
    Extract and score all location mentions in the prompt.
    Return a list of Location object with lat, lon, score, and etc.
    """
    nlp = _get_nlp()
    doc = nlp(prompt)
    locs = []
    for ent in doc.ents:
        if ent.label_ in ("GPE", "LOC", "FAC"):
            loc_name = ent.text.strip()
            if not loc_name:
                continue
            lat, lon, bbox = geocode_location(loc_name)
            if not (lat and lon and bbox):
                continue
            score = _score_location_mention(ent, doc)
            locs.append(Location(loc_name, score, lat, lon, *bbox))
    return locs


def _score_location_mention(ent, doc) -> float:
    """
    Compute 0..1 intent-strength score for a location mention.
    Use: label priors + dependency role + coordination propagation + light lexical cues.
    """
    score = {"GPE": 0.70, "LOC": 0.60, "FAC": 0.50}.get(ent.label_, 0.50)

    root = ent.root
    head = root.head

    if root.dep_ == "pobj" and head.pos_ == "ADP":
        score += 0.22
    if root.dep_ in {"obl", "nmod"}:
        score += 0.10

    # Weaker: noun modifier of a retrieval noun ("London photos")
    retrieval_nouns = {"photo", "photos", "picture", "pictures", "image", "images", "video", "videos", "trip",
                       "travel"}
    if root.dep_ in {"compound", "amod", "nmod"} and head.lemma_.lower() in retrieval_nouns:
        score += 0.10

    # Penalize obvious non-location uses like person-name compounds ("Paris Hilton")
    if root.dep_ == "compound" and head.ent_type_ in {"PERSON"}:
        score -= 0.30

    # Coordination propagation: if ent is in a coordinated list with a strong sibling, boost
    coord_bonus = 0.0
    if root.dep_ == "conj":  # check the head of the conjunction (the first item)
        h = head
        if h.dep_ == "pobj" and h.head.pos_ == "ADP":
            coord_bonus = max(coord_bonus, 0.18)
        if h.dep_ in {"obl", "nmod"}:
            coord_bonus = max(coord_bonus, 0.08)
    else:  # if this is the head, look at its conj children
        for child in root.children:
            if child.dep_ == "conj" and child.ent_type_ in {"GPE", "LOC", "FAC"}:
                coord_bonus = max(coord_bonus, 0.06)
    score += coord_bonus

    # Light lexical cue: preceding preposition still helps, but smaller weight now ---
    preps_strong = {"in", "at", "near", "around", "within", "outside"}
    if ent.start > 0 and doc[ent.start - 1].lower_ in preps_strong:
        score += 0.06

    # Basic cleanliness
    if len(ent) >= 2:
        score += 0.03  # multi-token place names
    if ent.text[:1].isupper():
        score += 0.02

    # Penalize month/weekday if mis-tagged
    bad = {
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
        "november", "december",
    }
    if ent.text.strip().lower() in bad:
        score -= 0.40

    return max(0.0, min(1.0, score))
