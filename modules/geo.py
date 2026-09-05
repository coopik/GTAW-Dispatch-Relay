"""
GTA V / GTA World geography for 911 Dispatch Relay.

What this module gives the app:
  * A full gazetteer of San Andreas street names, districts (neighbourhoods),
    landmarks and freeways.
  * Typo-tolerant resolution, so a caller who types "Little Soeul", "Vinwood"
    or "Grove St" still gets the correct, correctly-spelled place read out
    over TTS.
  * A deterministic, LAPD-style 4-digit Reporting District (RD) for any
    location, plus the spoken form ("thirteen thirteen", "forty fifty one").

Everything here is pure standard library so the app keeps working offline.
If `rapidfuzz` happens to be installed it is used automatically because it is
roughly 20x faster than difflib on the same comparisons.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

try:  # optional speed-up, never required
    from rapidfuzz import fuzz as _rf_fuzz  # type: ignore

    _HAVE_RAPIDFUZZ = True
except Exception:  # pragma: no cover - optional dependency
    _rf_fuzz = None
    _HAVE_RAPIDFUZZ = False


# ---------------------------------------------------------------------------
# Gazetteer
# ---------------------------------------------------------------------------

LOS_SANTOS_STREETS = (
    "Abattoir Avenue", "Abe Milton Parkway", "Ace Jones Drive",
    "Adam's Apple Boulevard", "Aguja Street", "Alta Place", "Alta Street",
    "Amarillo Vista", "Amarillo Way", "Americano Way", "Atlee Street",
    "Autopia Parkway", "Banham Canyon Drive", "Barbareno Road",
    "Bay City Avenue", "Bay City Incline", "Baytree Canyon Road",
    "Boulevard Del Perro", "Bridge Street", "Brouge Avenue", "Buccaneer Way",
    "Buen Vino Road", "Caesars Place", "Calais Avenue", "Capital Boulevard",
    "Carcer Way", "Carson Avenue", "Chum Street", "Chupacabra Street",
    "Clinton Avenue", "Cockingend Drive", "Conquistador Street",
    "Cortes Street", "Cougar Avenue", "Covenant Avenue", "Cox Way",
    "Crusade Road", "Davis Avenue", "Decker Street", "Didion Drive",
    "Dorset Drive", "Dorset Place", "Dry Dock Street", "Dunstable Drive",
    "Dunstable Lane", "Dutch London Street", "Eastbourne Way",
    "East Galileo Avenue", "East Mirror Drive", "Eclipse Boulevard",
    "Edwood Way", "Elgin Avenue", "El Burro Boulevard", "El Rancho Boulevard",
    "Equality Way", "Exceptionalists Way", "Fantastic Place", "Fenwell Place",
    "Forum Drive", "Fudge Lane", "Galileo Road", "Gentry Lane",
    "Ginger Street", "Glory Way", "Goma Street", "Greenwich Parkway",
    "Greenwich Place", "Greenwich Way", "Grove Street", "Hanger Way",
    "Hangman Avenue", "Hardy Way", "Hawick Avenue", "Heritage Way",
    "Hillcrest Avenue", "Hillcrest Ridge Access Road", "Imagination Court",
    "Industry Passage", "Ineseno Road", "Integrity Way", "Invention Court",
    "Innocence Boulevard", "Jamestown Street", "Kimble Hill Drive",
    "Kortz Drive", "Labor Place", "Laguna Place", "Lake Vinewood Drive",
    "Las Lagunas Boulevard", "Liberty Street", "Lindsay Circus",
    "Little Bighorn Avenue", "Low Power Street", "Macdonald Street",
    "Mad Wayne Thunder Drive", "Magellan Avenue", "Marathon Avenue",
    "Marlowe Drive", "Melanoma Street", "Meteor Street", "Milton Road",
    "Mirror Park Boulevard", "Mirror Place", "Morningwood Boulevard",
    "Mount Haan Drive", "Mount Haan Road", "Mount Vinewood Drive",
    "Movie Star Way", "Mutiny Road", "New Empire Way", "Nikola Avenue",
    "Nikola Place", "Normandy Drive", "North Archer Avenue",
    "North Conker Avenue", "North Sheldon Avenue", "North Rockford Drive",
    "Occupation Avenue", "Orchardville Avenue", "Palomino Avenue",
    "Peaceful Street", "Perth Street", "Picture Perfect Drive",
    "Plaice Place", "Playa Vista", "Popular Street", "Portola Drive",
    "Power Street", "Prosperity Street", "Prosperity Street Promenade",
    "Red Desert Avenue", "Richman Street", "Rockford Drive",
    "Roy Lowenstein Boulevard", "Rub Street", "Sam Austin Drive",
    "San Andreas Avenue", "Sandcastle Way", "San Vitus Boulevard",
    "Senora Road", "Shank Street", "Signal Street", "Sinner Street",
    "Sinners Passage", "South Arsenal Street", "South Boulevard Del Perro",
    "South Mo Milton Drive", "South Rockford Drive", "South Shambles Street",
    "Spanish Avenue", "Steele Way", "Strangeways Drive", "Strawberry Avenue",
    "Supply Street", "Sustancia Road", "Swiss Street", "Tackle Street",
    "Tangerine Street", "Tongva Drive", "Tower Way", "Tug Street",
    "Utopia Gardens", "Vespucci Boulevard", "Vinewood Boulevard",
    "Vinewood Park Drive", "Vitus Street", "Voodoo Place",
    "West Eclipse Boulevard", "West Galileo Avenue", "West Mirror Drive",
    "Whispymound Drive", "Wild Oats Drive", "York Street",
    "Zancudo Barranca",
)

BLAINE_STREETS = (
    "Algonquin Boulevard", "Alhambra Drive", "Armadillo Avenue",
    "Calafia Road", "Cascabel Avenue", "Cassidy Trail", "Cat-Claw Avenue",
    "Chianski Passage", "Cholla Road", "Cholla Springs Avenue",
    "Duluoz Avenue", "East Joshua Road", "Fort Zancudo Approach Road",
    "Grapeseed Avenue", "Grapeseed Main Street", "Joad Lane", "Joshua Road",
    "Lesbos Lane", "Lolita Avenue", "Marina Drive", "Meringue Lane",
    "Mountain View Drive", "Niland Avenue", "North Calafia Way",
    "Nowhere Road", "O'Neil Way", "Paleto Boulevard", "Panorama Drive",
    "Procopio Drive", "Procopio Promenade", "Pyrite Avenue", "Raton Pass",
    "Route 68 Approach", "Seaview Road", "Senora Way", "Smoke Tree Road",
    "Union Road", "Zancudo Avenue", "Zancudo Road", "Zancudo Trail",
)

HIGHWAYS = (
    "Interstate 1", "Interstate 2", "Interstate 4", "Interstate 5",
    "U.S. Route 1", "U.S. Route 11", "U.S. Route 13", "U.S. Route 15",
    "U.S. Route 20", "U.S. Route 23", "U.S. Route 68",
    "San Andreas State Route 14", "San Andreas State Route 16",
    "San Andreas State Route 17", "San Andreas State Route 18",
    "San Andreas State Route 19", "San Andreas State Route 20",
    "San Andreas State Route 22", "San Andreas State Route 51",
    "Great Ocean Highway", "Palomino Freeway", "Olympic Freeway",
    "La Puerta Freeway", "Del Perro Freeway", "Senora Freeway",
    "Elysian Fields Freeway", "Route 68", "Route 1",
)

# District -> LAPD-style division number used to build the RD.
# 2-digit division + 2-digit basic car area = the classic 4-digit RD.
DISTRICTS = {
    # ---- Central / Downtown ------------------------------------------------
    "Pillbox Hill": 1, "Legion Square": 1, "Textile City": 1,
    "Mission Row": 1, "Downtown Los Santos": 1, "Alta": 1,
    "Strawberry": 13, "Davis": 12, "Chamberlain Hills": 12,
    "Rancho": 12, "Carson": 12, "South Los Santos": 12,
    # ---- Rampart / Koreatown ----------------------------------------------
    "Little Seoul": 2, "La Puerta": 2, "Pacific Bluffs": 8,
    # ---- Hollenbeck / East -------------------------------------------------
    "La Mesa": 4, "El Burro Heights": 4, "Murrieta Heights": 4,
    "East Los Santos": 4, "Cypress Flats": 4, "Banning": 5,
    "Elysian Island": 5, "Terminal": 5, "Port of Los Santos": 5,
    # ---- Hollywood / Vinewood ---------------------------------------------
    "Vinewood": 6, "West Vinewood": 6, "East Vinewood": 6,
    "Downtown Vinewood": 6, "Vinewood Hills": 6, "Hawick": 6,
    "Mirror Park": 11, "Tataviam Mountains": 11,
    # ---- West LA -----------------------------------------------------------
    "Rockford Hills": 8, "Richman": 8, "Richman Glen": 8,
    "Morningwood": 8, "Burton": 8, "GWC and Golfing Society": 8,
    # ---- Pacific -----------------------------------------------------------
    "Vespucci": 14, "Vespucci Beach": 14, "Vespucci Canals": 14,
    "Del Perro": 14, "Del Perro Beach": 14, "Puerto Del Sol": 14,
    "Los Santos International Airport": 14, "LSIA": 14,
    # ---- County / Blaine ---------------------------------------------------
    "Sandy Shores": 20, "Grapeseed": 21, "Paleto Bay": 22,
    "Harmony": 20, "Stab City": 20, "Grand Senora Desert": 20,
    "Great Chaparral": 21, "Chumash": 23, "Tongva Hills": 23,
    "Tongva Valley": 23, "Banham Canyon": 23, "Chiliad Mountain": 22,
    "Mount Chiliad": 22, "Mount Gordo": 22, "Mount Josiah": 20,
    "Alamo Sea": 20, "Lago Zancudo": 21, "Fort Zancudo": 21,
    "Zancudo River": 21, "Braddock Pass": 22, "Raton Canyon": 22,
    "Paleto Forest": 22, "Paleto Cove": 22, "Procopio Beach": 22,
    "Catfish View": 22, "Galilee": 20, "North Chumash": 23,
    "Senora National Park": 20, "Redwood Lights Track": 20,
    "Davis Quartz": 20, "Palmer-Taylor Power Station": 20,
    "Humane Labs and Research": 21, "Bolingbroke Penitentiary": 20,
    "El Gordo Lighthouse": 22, "Cassidy Creek": 22,
    "San Chianski Mountain Range": 21, "Land Act Dam": 11,
    "Vinewood Racetrack": 6, "Maze Bank Arena": 5,
}

# High-traffic landmarks operators call in by name.
LANDMARKS = {
    "Maze Bank Tower": "Pillbox Hill",
    "Maze Bank Arena": "Maze Bank Arena",
    "Legion Square": "Legion Square",
    "Union Depository": "Pillbox Hill",
    "Pacific Standard Bank": "Pillbox Hill",
    "Mission Row Police Station": "Mission Row",
    "Pillbox Hill Medical Center": "Pillbox Hill",
    "Central Los Santos Medical Center": "Davis",
    "Mount Zonah Medical Center": "Rockford Hills",
    "St. Fiacre Hospital": "Rockford Hills",
    "Sandy Shores Medical Center": "Sandy Shores",
    "Vanilla Unicorn": "Strawberry",
    "Bahama Mamas": "Vinewood",
    "Tequi-la-la": "West Vinewood",
    "Vinewood Bowl": "Vinewood Hills",
    "Vinewood Sign": "Vinewood Hills",
    "Galileo Observatory": "Vinewood Hills",
    "Del Perro Pier": "Del Perro Beach",
    "Los Santos International Airport": "Los Santos International Airport",
    "Fort Zancudo": "Fort Zancudo",
    "Bolingbroke Penitentiary": "Bolingbroke Penitentiary",
    "Diamond Casino and Resort": "East Vinewood",
    "Los Santos Customs": "La Mesa",
    "Benny's Original Motor Works": "Strawberry",
    "Ammu-Nation": "Pillbox Hill",
    "Burger Shot": "Vinewood",
    "Cluckin Bell": "Little Seoul",
    "Up-n-Atom Burger": "Sandy Shores",
    "Bean Machine": "Rockford Hills",
    "Robs Liquor": "Vinewood",
    "LTD Gasoline": "Little Seoul",
    "Xero Gas Station": "Grapeseed",
    "RON Gas Station": "Sandy Shores",
    "24/7 Supermarket": "Strawberry",
    "Pink Cage Motel": "East Vinewood",
    "Vinewood Racetrack": "Vinewood Racetrack",
    "Palmer-Taylor Power Station": "Palmer-Taylor Power Station",
    "Humane Labs and Research": "Humane Labs and Research",
    "Sandy Shores Airfield": "Sandy Shores",
    "Paleto Bay Sheriff Station": "Paleto Bay",
    "Davis Sheriff Station": "Davis",
    "Vespucci Police Station": "Vespucci",
    "Rockford Hills Police Station": "Rockford Hills",
    "La Mesa Police Station": "La Mesa",
    "Vinewood Police Station": "West Vinewood",
    "Del Perro Police Station": "Del Perro",
}

STREETS = tuple(dict.fromkeys(LOS_SANTOS_STREETS + BLAINE_STREETS + HIGHWAYS))

# Which district each street mainly runs through, for RD purposes. Streets not
# listed fall back to a stable hash so they still get a consistent RD.
STREET_DISTRICT_HINTS = {
    "Grove Street": "Davis", "Carson Avenue": "Davis",
    "Davis Avenue": "Davis", "Roy Lowenstein Boulevard": "Davis",
    "Innocence Boulevard": "Strawberry", "Jamestown Street": "Chamberlain Hills",
    "Strawberry Avenue": "Strawberry", "Dutch London Street": "Elysian Island",
    "Vespucci Boulevard": "Vespucci", "Boulevard Del Perro": "Del Perro",
    "South Boulevard Del Perro": "Del Perro", "Bay City Avenue": "Vespucci",
    "Magellan Avenue": "Del Perro", "Cortes Street": "Del Perro",
    "Vinewood Boulevard": "Vinewood", "Mirror Park Boulevard": "Mirror Park",
    "Hawick Avenue": "Hawick", "Alta Street": "Alta", "Alta Place": "Alta",
    "Spanish Avenue": "Alta", "Las Lagunas Boulevard": "Vinewood",
    "Elgin Avenue": "Vinewood", "Power Street": "Pillbox Hill",
    "Low Power Street": "Pillbox Hill", "Integrity Way": "Pillbox Hill",
    "Palomino Avenue": "La Mesa", "Popular Street": "La Mesa",
    "Little Bighorn Avenue": "Rancho", "El Rancho Boulevard": "Rancho",
    "Macdonald Street": "El Burro Heights", "El Burro Boulevard": "El Burro Heights",
    "Capital Boulevard": "Textile City", "San Andreas Avenue": "Pillbox Hill",
    "Occupation Avenue": "Textile City", "Sinner Street": "Textile City",
    "Swiss Street": "Rockford Hills", "Rockford Drive": "Rockford Hills",
    "North Rockford Drive": "Rockford Hills",
    "South Rockford Drive": "Rockford Hills", "Portola Drive": "Rockford Hills",
    "Cougar Avenue": "Morningwood", "Morningwood Boulevard": "Morningwood",
    "Marathon Avenue": "Little Seoul", "Decker Street": "Little Seoul",
    "Ginger Street": "Little Seoul", "Carcer Way": "Little Seoul",
    "Sandcastle Way": "Vespucci Beach", "Prosperity Street": "Little Seoul",
    "Joshua Road": "Sandy Shores", "Algonquin Boulevard": "Sandy Shores",
    "Armadillo Avenue": "Sandy Shores", "Alhambra Drive": "Sandy Shores",
    "Niland Avenue": "Sandy Shores", "Cholla Springs Avenue": "Sandy Shores",
    "Paleto Boulevard": "Paleto Bay", "Procopio Drive": "Paleto Bay",
    "Duluoz Avenue": "Paleto Bay", "Grapeseed Avenue": "Grapeseed",
    "Grapeseed Main Street": "Grapeseed", "Joad Lane": "Grapeseed",
    "Union Road": "Grapeseed", "Zancudo Avenue": "Fort Zancudo",
    "Great Ocean Highway": "Chumash", "Barbareno Road": "Chumash",
    "Banham Canyon Drive": "Banham Canyon", "Kortz Drive": "Pacific Bluffs",
    "Tongva Drive": "Tongva Hills", "Baytree Canyon Road": "Tongva Valley",
    "Senora Road": "Grand Senora Desert", "Route 68": "Grand Senora Desert",
    "Marlowe Drive": "Vinewood Hills", "Mount Haan Drive": "Vinewood Hills",
    "Mount Vinewood Drive": "Vinewood Hills", "Didion Drive": "Vinewood Hills",
    "Whispymound Drive": "Vinewood Hills", "Wild Oats Drive": "Vinewood Hills",
    "Milton Road": "Richman", "Mad Wayne Thunder Drive": "Richman",
    "Dunstable Lane": "Richman", "Normandy Drive": "Richman",
    "Buen Vino Road": "Richman Glen", "Lake Vinewood Drive": "Vinewood Hills",
}


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

_SUFFIX_EXPAND = {
    "st": "street", "str": "street", "ave": "avenue", "av": "avenue",
    "blvd": "boulevard", "blv": "boulevard", "bvd": "boulevard",
    "dr": "drive", "drv": "drive", "rd": "road", "ln": "lane",
    "ct": "court", "crt": "court", "pl": "place", "plz": "plaza",
    "pkwy": "parkway", "pky": "parkway", "pwy": "parkway",
    "hwy": "highway", "fwy": "freeway", "expy": "expressway",
    "trl": "trail", "ter": "terrace", "cir": "circus", "sq": "square",
    "n": "north", "s": "south", "e": "east", "w": "west",
    "mt": "mount", "ft": "fort", "pt": "point",
    "intl": "international", "stn": "station",
}

_NOISE_WORDS = {
    "the", "a", "an", "at", "on", "in", "near", "by", "to", "of",
    "around", "outside", "inside", "somewhere", "here", "there",
    "corner", "block", "blocks", "area", "side", "off",
}

_INTERSECTION_SPLIT = re.compile(
    r"\s*(?:\band\b|&|/|\bx\b|\bcross\b|\bcorner of\b)\s*", re.I
)


def _strip_accents(text):
    return "".join(
        c for c in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(c)
    )


@lru_cache(maxsize=4096)
def normalize(text):
    """Aggressive normalisation used for fuzzy comparison only."""
    if not text:
        return ""
    t = _strip_accents(str(text)).lower()
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    tokens = []
    for tok in t.split():
        tok = _SUFFIX_EXPAND.get(tok, tok)
        if tok in _NOISE_WORDS:
            continue
        tokens.append(tok)
    return " ".join(tokens)


@lru_cache(maxsize=4096)
def _skeleton(text):
    """Letters only, collapsed doubles - forgives 'Seoul'/'Soeul' style slips."""
    t = normalize(text).replace(" ", "")
    return re.sub(r"(.)\1+", r"\1", t)


def _ratio(a, b):
    if not a or not b:
        return 0.0
    if _HAVE_RAPIDFUZZ:
        return float(_rf_fuzz.ratio(a, b)) / 100.0
    return SequenceMatcher(None, a, b).ratio()


# ---------------------------------------------------------------------------
# Index (built once at import)
# ---------------------------------------------------------------------------

class _Entry:
    __slots__ = ("canonical", "kind", "district", "norm", "skel", "tokens")

    def __init__(self, canonical, kind, district):
        self.canonical = canonical
        self.kind = kind
        self.district = district
        self.norm = normalize(canonical)
        self.skel = _skeleton(canonical)
        self.tokens = frozenset(self.norm.split())


def _build_index():
    entries = []
    for name in STREETS:
        kind = "highway" if name in HIGHWAYS else "street"
        entries.append(_Entry(name, kind, STREET_DISTRICT_HINTS.get(name)))
    for name in DISTRICTS:
        entries.append(_Entry(name, "district", name))
    for name, district in LANDMARKS.items():
        entries.append(_Entry(name, "landmark", district))

    exact = {}
    token_ix = {}
    for e in entries:
        exact.setdefault(e.norm, e)
        exact.setdefault(e.skel, e)
        for tok in e.tokens:
            token_ix.setdefault(tok, []).append(e)
            # 4-char prefix bucket catches misspelled tokens cheaply
            if len(tok) >= 4:
                token_ix.setdefault(tok[:4], []).append(e)
    return entries, exact, token_ix


_ENTRIES, _EXACT, _TOKEN_IX = _build_index()


class LocationMatch:
    """Result of resolving a caller-supplied location string."""

    __slots__ = (
        "canonical", "kind", "district", "confidence", "original", "corrected"
    )

    def __init__(self, canonical, kind, district, confidence, original):
        self.canonical = canonical
        self.kind = kind
        self.district = district
        self.confidence = confidence
        self.original = original
        self.corrected = bool(
            canonical and normalize(canonical) != normalize(original or "")
        )

    def __repr__(self):  # pragma: no cover - debugging aid
        return (
            "LocationMatch(%r, kind=%r, district=%r, conf=%.2f)"
            % (self.canonical, self.kind, self.district, self.confidence)
        )


@lru_cache(maxsize=2048)
def match_place(text, threshold=0.78):
    """Resolve one place name. Returns None when nothing is close enough."""
    if not text or not str(text).strip():
        return None
    original = str(text).strip()
    norm = normalize(original)
    if not norm or len(norm.replace(" ", "")) < 3:
        return None

    hit = _EXACT.get(norm) or _EXACT.get(_skeleton(original))
    if hit:
        return LocationMatch(hit.canonical, hit.kind, hit.district, 1.0, original)

    # Gather a small candidate pool instead of scanning the whole gazetteer.
    tokens = norm.split()
    pool = {}
    for tok in tokens:
        for key in (tok, tok[:4]):
            for e in _TOKEN_IX.get(key, ()):
                pool[id(e)] = e
    candidates = list(pool.values()) if pool else _ENTRIES

    skel = _skeleton(original)
    token_set = set(tokens)
    best = None
    best_score = 0.0
    for e in candidates:
        score = _ratio(norm, e.norm)
        if score < 0.95:
            score = max(score, _ratio(skel, e.skel) * 0.99)
        # Reward shared whole tokens: "little soeul" shares "little".
        if token_set and e.tokens:
            overlap = len(e.tokens & token_set) / max(len(e.tokens), len(token_set))
            score = max(score, (score * 0.7) + (overlap * 0.3))
        if score > best_score:
            best_score, best = score, e

    if best is None or best_score < threshold:
        return None
    return LocationMatch(
        best.canonical, best.kind, best.district, round(best_score, 3), original
    )


def district_for(name):
    """Best-guess district for a street, landmark or district name."""
    m = match_place(name) if name else None
    if not m:
        return None
    if m.kind == "district":
        return m.canonical
    return m.district


def resolve_location(raw, threshold=0.78):
    """
    Resolve a full location string, including intersections.

    Returns a dict with:
        spoken     - corrected text to read over TTS (falls back to the input)
        parts      - list of LocationMatch for each resolved component
        district   - best district guess
        corrected  - True when at least one spelling was fixed
        confidence - lowest confidence across resolved parts
    """
    raw = (raw or "").strip()
    if not raw:
        return {
            "spoken": "", "parts": [], "district": None,
            "corrected": False, "confidence": 0.0,
        }

    chunks = [c.strip(" .,;:-") for c in _INTERSECTION_SPLIT.split(raw)]
    chunks = [c for c in chunks if c]
    if not chunks:
        chunks = [raw]

    parts = []
    spoken_bits = []
    corrected = False
    confidences = []

    for chunk in chunks:
        m = match_place(chunk, threshold)
        if m:
            parts.append(m)
            spoken_bits.append(m.canonical)
            confidences.append(m.confidence)
            corrected = corrected or m.corrected
        else:
            spoken_bits.append(chunk)

    if len(spoken_bits) >= 2:
        spoken = " and ".join(spoken_bits[:2])
        if len(spoken_bits) > 2:
            spoken += ", " + ", ".join(spoken_bits[2:])
    else:
        spoken = spoken_bits[0] if spoken_bits else raw

    district = None
    for m in parts:
        district = m.canonical if m.kind == "district" else m.district
        if district:
            break

    return {
        "spoken": spoken,
        "parts": parts,
        "district": district,
        "corrected": corrected,
        "confidence": min(confidences) if confidences else 0.0,
    }


def correct_location(raw):
    """Convenience wrapper: return the corrected, speakable location text."""
    return resolve_location(raw)["spoken"] or (raw or "")


def is_known_place(text):
    """True when the text resolves to a real San Andreas place."""
    return match_place(text) is not None


# ---------------------------------------------------------------------------
# Reporting Districts (RD)
# ---------------------------------------------------------------------------

def _stable_hash(text):
    """FNV-1a. Deterministic across runs (unlike hash())."""
    h = 0x811C9DC5
    for ch in text.encode("utf-8", "ignore"):
        h ^= ch
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


@lru_cache(maxsize=2048)
def rd_for(location):
    """
    A stable, believable 4-digit LAPD-style Reporting District.

    Format mirrors the real thing: 2-digit division + 2-digit basic car area.
    The same location always produces the same RD, so a street keeps its RD
    for the whole shift instead of changing on every call.
    """
    text = (location or "").strip()
    if not text:
        division = 1
        seed = "unknown"
    else:
        district = district_for(text)
        division = DISTRICTS.get(district or "", 0)
        if not division:
            division = (_stable_hash(district or text) % 21) + 1
        m = match_place(text)
        seed = (m.canonical if m else text).lower()

    division = max(1, min(division, 26))
    beat = (_stable_hash(seed) % 98) + 1  # 01 - 98
    return "%02d%02d" % (division, beat)


_ONES = (
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
)
_TENS = (
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
)


def _two_digit_words(pair, leading):
    """Speak a 2-digit group the way a dispatcher reads an RD."""
    n = int(pair)
    if n == 0:
        return "oh oh" if leading else "hundred"
    if pair[0] == "0":
        return "oh " + _ONES[n]
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] if ones == 0 else _TENS[tens] + " " + _ONES[ones]


def speak_rd(rd):
    """'1313' -> 'thirteen thirteen'; '4051' -> 'forty fifty one'."""
    digits = re.sub(r"\D", "", str(rd or ""))
    if len(digits) != 4:
        return " ".join(_ONES[int(d)] for d in digits if d.isdigit())
    first = _two_digit_words(digits[:2], True)
    second = _two_digit_words(digits[2:], False)
    return first + " " + second


def rd_phrase(location):
    """Ready-to-speak RD fragment, e.g. 'R D, thirteen thirteen'.

    'R D' is spelled with spaces so every TTS engine reads the letters
    instead of trying to pronounce 'RD' as a word.
    """
    return "R D, " + speak_rd(rd_for(location))


__all__ = [
    "STREETS", "DISTRICTS", "LANDMARKS", "HIGHWAYS", "LocationMatch",
    "match_place", "resolve_location", "correct_location", "is_known_place",
    "district_for", "rd_for", "speak_rd", "rd_phrase", "normalize",
]
