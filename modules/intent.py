"""
Radio intent recognition for unit traffic.

The flagger used to gate unit transmissions behind a narrow keyword whitelist,
so a line only counted as radio traffic if it carried a literal code word
("code six", "shots fired", "in pursuit"). Players do not talk like that. They
say "I need backup on Calais" or "active brawl at Hawick's Clothing, roll
backup", and every one of those was dropped on the floor.

This module reads a transmission the way a dispatcher would and answers three
questions:

  1. What is being asked for?  -> request: backup (Code 3) / additional (Code 2)
  2. What happened?            -> incident label, category, weight
  3. Where?                    -> location, corrected against the gazetteer

Nothing here is model driven. It is a deterministic lexicon, so the same
transmission always grades the same way and the operator can predict it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

try:  # San Andreas gazetteer, used to validate and correct spoken locations
    from modules.geo import correct_location as geo_correct_location
    from modules.geo import is_known_place as geo_is_known_place
    from modules.geo import match_place as geo_match_place
except Exception:  # pragma: no cover - script/frozen import styles
    try:
        from .geo import correct_location as geo_correct_location
        from .geo import is_known_place as geo_is_known_place
        from .geo import match_place as geo_match_place
    except Exception:
        def geo_correct_location(text):
            return text

        def geo_is_known_place(_text):
            return False

        def geo_match_place(_text, threshold=0.78):
            return None


BACKUP = "backup"
ADDITIONAL = "additional"

# A transmission needs at least this much weight to be worth air time on its
# own. An explicit request for help is always actionable regardless of score.
MIN_ACTIONABLE = 14

_I = re.IGNORECASE

# ---------------------------------------------------------------------------
# What is being asked for
# ---------------------------------------------------------------------------

# "backup" is an emergency response: lights and siren, Code 3.
_REQUEST_BACKUP = re.compile(
    r"\bback[-\s]?up\b|\bcover unit\b|\ba cover\b|\bcode\s*3\b|\bexpedite\b|"
    r"need(?:s|ing)?\s+(?:immediate\s+)?(?:help|assistance)|"
    r"requesting\s+(?:immediate\s+)?(?:help|assistance)|"
    r"\bstep it up\b|\bstep on it\b|"
    r"send\s+(?:me\s+|us\s+)?(?:units?|everyone|anyone|whoever)|"
    r"roll\s+(?:me\s+|us\s+)?(?:back[-\s]?up|units?|everything)",
    _I,
)

# A bare noun is not a request. "Requesting a supervisor" is a request;
# "anyone know where the supervisor is" is chatter. Additional-unit wording has
# to be introduced by a real request verb before it counts.
#
# Deliberately NOT required for backup: missing a backup request is far worse
# than announcing one, so "backup on Calais" stands on its own.
_REQUEST_VERB = re.compile(
    r"\b(?:request(?:ing|ed|s)?|need(?:s|ing|ed)?|send(?:ing)?|roll(?:ing)?|"
    r"start(?:ing)?|dispatch|get me|get us|can i get|can we get|could i get|"
    r"could we get|require|assign|show me|give me)\b",
    _I,
)

# "additional" is a routine extra unit: no lights, no siren, Code 2.
_REQUEST_ADDITIONAL = re.compile(
    r"\badditionals?\b|\badditional unit\b|\banother unit\b|\bone more unit\b|"
    r"\bmore units?\b|\bsecond unit\b|\bextra unit\b|\bunits? to assist\b|"
    r"\bsupervisor\b|\bair\s?unit\b|\bair\s?ship\b|\bwatch commander\b",
    _I,
)

# ---------------------------------------------------------------------------
# What happened
#
# (category, spoken label, weight, inherently a priority, pattern)
#
# Weights are tuned so that one clear violent incident clears MIN_ACTIONABLE on
# its own, while soft chatter ("suspicious vehicle") needs a second signal or an
# explicit request before it takes the air.
# ---------------------------------------------------------------------------

_INCIDENTS: list[tuple[str, str, int, bool, re.Pattern]] = [
    ("officer", "officer needs help", 60, True, re.compile(
        r"officer (?:down|needs? (?:help|assistance)|in (?:distress|trouble))|"
        r"\b11[-\s]?99\b|\b998\b|\b999\b|shots fired at (?:police|officers?)",
        _I)),
    ("shooting", "shots fired", 52, True, re.compile(
        r"shots? fired|shooting in progress|\bactive shooter\b|"
        r"(?:some\s?one|someone|suspect)(?:'s| is| was)? shooting|"
        r"\bgsw\b|gun ?shot(?: wound)?|\b187\b", _I)),
    ("stabbing", "a stabbing", 46, True, re.compile(
        r"\bstabb(?:ed|ing)\b|\bslashed\b|knife wound", _I)),
    ("weapon", "a suspect armed with a weapon", 40, True, re.compile(
        r"\barmed\b|\bbrandish(?:ing|ed)?\b|(?:gun|firearm|pistol|rifle|shotgun|"
        r"knife|blade|machete|bat|crowbar)\s+(?:drawn|pulled|out|on him|on her)|"
        r"(?:has|had|got|holding|waving)\s+(?:a\s+)?(?:gun|firearm|pistol|rifle|"
        r"shotgun|knife|blade|machete)|\bhas a weapon\b|\b417\b", _I)),
    ("pursuit", "a pursuit", 44, True, re.compile(
        r"\bin pursuit\b|foot pursuit|vehicle pursuit|\bpursuing\b|"
        r"suspect (?:is )?(?:fleeing|running|took off)|\brunner\b|"
        r"\bchasing\b|\bfoot bail\b|\bbailed out\b", _I)),
    ("medical", "a medical emergency", 38, True, re.compile(
        r"body (?:on the ground|in the)|man down|woman down|person down|"
        r"\bunconscious\b|\bunresponsive\b|not breathing|\bno pulse\b|\bdoa\b|"
        r"\bbleeding\b|bleeding out|\boverdos(?:e|ing)\b|\b\bod'?ing\b|"
        r"\bseizure\b|\bcpr\b|need(?:s|ing)? (?:an )?(?:ambulance|ems|medic|rescue)|"
        r"rescue ambulance|\bems\b", _I)),
    ("robbery", "a robbery", 40, True, re.compile(
        r"\brobbery\b|\brobbing\b|\bbeing robbed\b|\bheld up\b|\bhold ?up\b|"
        r"\bmugging\b|\bcarjack(?:ing|ed)\b|\b211\b", _I)),
    ("violence", "a fight in progress", 34, True, re.compile(
        r"\bbrawl(?:ing)?\b|\bfight(?:ing)?\b|\bmelee\b|\briot(?:ing)?\b|"
        r"\bjumped\b|\bassault(?:ing|ed)?\b|\bbatter(?:y|ing)\b|\bbeating\b|"
        r"\battack(?:ing|ed)\b|\baltercation\b|\bscuffle\b|\bdomestic\b|"
        r"\bstrangl(?:ing|ed)\b|\b415 ?f\b|\b242\b|\b243\b", _I)),
    ("fire", "a fire", 32, True, re.compile(
        r"\bfire\b|\bsmoke\b|\bburning\b|\bexplosion\b|\bblaze\b|"
        r"need(?:s|ing)? (?:the )?fire department", _I)),
    ("hostage", "a hostage situation", 55, True, re.compile(
        r"\bhostage\b|\bbarricaded\b|\bkidnapp?(?:ing|ed)\b|\b207\b", _I)),
    ("burglary", "a burglary", 26, False, re.compile(
        r"\bburglary\b|\bburglar\b|break[-\s]?in|breaking (?:in|and entering)|"
        r"\bb ?and ?e\b|\b459\b", _I)),
    ("collision", "a traffic collision", 24, False, re.compile(
        r"\bcollision\b|\bcrash(?:ed)?\b|\bwreck\b|\btc\b|\bt ?bone[d]?\b|"
        r"hit and run|\brollover\b|\bvehicle (?:on its|flipped)\b|\b390\b", _I)),
    ("vehicle", "a stolen vehicle", 22, False, re.compile(
        r"stolen (?:vehicle|car|auto)|\bgta\b|\b10851\b|vehicle theft", _I)),
    ("impaired", "an impaired driver", 20, False, re.compile(
        r"\bdui\b|\bdrunk driver\b|\bimpaired driver\b|reckless driv(?:er|ing)|"
        r"\bstreet rac(?:e|ing)\b|\b23152\b", _I)),
    ("disturbance", "a disturbance", 18, False, re.compile(
        r"\bdisturbance\b|\bdisorderly\b|\bloud (?:music|party)\b|"
        r"\bargument\b|\byelling\b|\bscreaming\b|\b415\b", _I)),
    ("theft", "a theft", 16, False, re.compile(
        r"\btheft\b|\bstealing\b|\bshoplift(?:ing|er)\b|\bpickpocket\b|"
        r"\bvandalism\b|\bgraffiti\b|\btagging\b|\b484\b|\b594\b", _I)),
    ("suspicious", "a suspicious person", 15, False, re.compile(
        r"\bsuspicious\b|\bprowler\b|\btrespass(?:ing|er)?\b|\bcasing\b|"
        r"\bloiter(?:ing)?\b|\b459a\b|\b647\b", _I)),
    ("traffic", "a traffic stop", 12, False, re.compile(
        r"traffic stop|\bpulling over\b|\bpulled over\b|\bvehicle stop\b|"
        r"\bcode 6 charles\b", _I)),
    ("custody", "a suspect in custody", 12, False, re.compile(
        r"\bin custody\b|\bdetained\b|\bcuffed\b|\bone in custody\b|"
        r"\bcode 4\b|\bsuspect secured\b", _I)),
]

# "active", "in progress", "right now" turn a cold report into a hot one.
_IN_PROGRESS = re.compile(
    r"\bactive(?:ly)?\b|\bin progress\b|\bright now\b|\bhappening now\b|"
    r"\bongoing\b|\bcurrently\b|\bas we speak\b|\bjust (?:now|occurred|happened)\b",
    _I,
)

# Multiple suspects or victims raises the stakes.
_ESCALATORS = re.compile(
    r"\bmultiple\b|\bseveral\b|\bnumerous\b|\bgroup of\b|\bcrowd\b|"
    r"\bgang\b|\ba dozen\b|\blarge\b",
    _I,
)

# Out of character or meta chatter that leaked into the feed. These never take
# the air no matter what else they contain.
_META = re.compile(
    r"^\s*(?:\(\(|//|\.\.|ooc\b|\(ooc)|\bmeta\b|\bafk\b|\bbrb\b|"
    r"\bteamspeak\b|\bdiscord\b|\bmic\b(?! ?check ?up)|\blagging\b|\bcrashed\b|"
    r"\bframerate\b|\bfps\b|\brestart\b",
    _I,
)

# A question is a request for information, not a report of an incident.
_QUESTION = re.compile(
    r"^\s*(?:can|could|would|does|do|did|is|are|was|were|who|what|when|where|"
    r"why|how|any(?:one|body))\b",
    _I,
)

# ---------------------------------------------------------------------------
# Where
# ---------------------------------------------------------------------------

# Stop the location capture before the next clause begins, so "backup on
# Calais, suspect is armed" yields "Calais" and not the whole tail.
_LOC_STOP = (
    r"(?=,|\.|;|$|\s+\b(?:roll|send|requesting|request|need|needs|needing|"
    r"code|with|and|but|suspect|susp|male|female|possible|advise|advised|"
    r"i\s|we\s|he\s|she\s|they\s|its|it's|there(?:'s| is))\b)"
)
_LOC_RE = re.compile(
    r"\b(?:on|at|near|by|outside|inside|in front of|corner of|vicinity of)\s+"
    r"([A-Za-z0-9 .'\-/&]+?)" + _LOC_STOP,
    _I,
)

# Words that look like a location capture but are not places.
_LOC_BLOCKLIST = {
    "scene", "foot", "me", "us", "him", "her", "them", "it", "my location",
    "location", "the way", "my way", "our way", "the air", "the radio",
    "the channel", "standby", "stand by", "hand", "sight", "scene now",
    "the ground", "top", "the phone", "duty", "patrol", "a call", "the call",
}

# Time and courtesy phrases that trail a place name grammatically but are not
# part of it: "outside Hawick's Clothing right now" -> "Hawick's Clothing".
_LOC_TAIL_RE = re.compile(
    r"\s+(?:right now|now|as we speak|at this time|currently|immediately|"
    r"asap|please|over|in progress|still|code\s*\d+)$",
    _I,
)


def extract_location(text: str) -> str | None:
    """Pull a place name out of a transmission and correct it against the
    gazetteer. Returns None when nothing place-like is present."""
    raw = str(text or "")
    best = None
    for m in _LOC_RE.finditer(raw):
        cand = (m.group(1) or "").strip(" \t.,;:-'")
        # Peel off trailing time phrases, repeatedly ("... right now please").
        prev = None
        while prev != cand:
            prev = cand
            cand = _LOC_TAIL_RE.sub("", cand).strip(" \t.,;:-'")
        if not cand or len(cand) < 3:
            continue
        if cand.lower() in _LOC_BLOCKLIST:
            continue
        # A known place always wins over a mere grammatical match.
        try:
            if geo_is_known_place(cand):
                return geo_correct_location(cand) or cand
        except Exception:
            pass
        try:
            hit = geo_match_place(cand)
            if hit:
                return geo_correct_location(cand) or cand
        except Exception:
            pass
        if best is None:
            best = cand
    return best


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class Intent:
    """What a single unit transmission actually means."""

    request: str | None = None       # BACKUP, ADDITIONAL or None
    incident: str | None = None      # spoken label, e.g. "a fight in progress"
    category: str | None = None      # lexicon category, e.g. "violence"
    location: str | None = None      # corrected place name
    priority: bool = False           # True means Code 3
    score: int = 0
    actionable: bool = False         # worth putting on the air at all
    meta: bool = False               # out of character / not real traffic
    signals: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "request": self.request,
            "incident": self.incident,
            "category": self.category,
            "location": self.location,
            "priority": self.priority,
            "score": self.score,
            "actionable": self.actionable,
            "meta": self.meta,
            "signals": list(self.signals),
        }


def analyze(text: str) -> Intent:
    """Grade one transmission. Never raises."""
    raw = str(text or "").strip()
    out = Intent()
    if not raw:
        return out
    low = raw.lower()

    if _META.search(low):
        out.meta = True
        return out

    # 1. What is being asked for. Backup outranks additional when both appear,
    #    because the emergency response is the safe reading.
    if _REQUEST_BACKUP.search(low):
        out.request = BACKUP
        out.signals.append("request:backup")
    elif _REQUEST_ADDITIONAL.search(low) and _REQUEST_VERB.search(low):
        out.request = ADDITIONAL
        out.signals.append("request:additional")

    # 2. What happened. Highest weight wins as the primary incident; every
    #    other distinct category adds a smaller corroborating bonus.
    primary = None
    score = 0
    for cat, label, weight, prio, pat in _INCIDENTS:
        if not pat.search(low):
            continue
        out.signals.append(cat)
        if primary is None or weight > primary[2]:
            if primary is not None:
                score += max(4, primary[2] // 4)
            primary = (cat, label, weight, prio)
        else:
            score += max(4, weight // 4)
    if primary is not None:
        score += primary[2]
        out.category = primary[0]
        out.incident = primary[1]

    hot = _IN_PROGRESS.search(low) is not None
    if hot:
        out.signals.append("in_progress")
        score += 10
    if _ESCALATORS.search(low):
        out.signals.append("escalator")
        score += 8

    # An explicit request for help is itself strong evidence.
    if out.request == BACKUP:
        score += 30
    elif out.request == ADDITIONAL:
        score += 16

    # A bare question with no incident behind it is not dispatchable traffic.
    if primary is None and out.request is None and _QUESTION.search(low):
        out.score = 0
        return out

    # 3. Where.
    out.location = extract_location(raw)
    if out.location:
        out.signals.append("location")
        score += 8

    # Priority: asking for backup, an inherently violent incident, or a soft
    # incident that is explicitly happening right now.
    out.priority = bool(
        out.request == BACKUP
        or (primary is not None and primary[3])
        or (primary is not None and hot and primary[2] >= 20)
    )

    out.score = max(0, score)
    out.actionable = bool(out.request) or out.score >= MIN_ACTIONABLE
    return out


def describe(intent: Intent, callsign: str | None = None) -> str:
    """A short plain-text summary, used for logs and the activity feed."""
    bits = []
    if callsign:
        bits.append(str(callsign))
    if intent.incident:
        bits.append(intent.incident)
    if intent.request == BACKUP:
        bits.append("requesting backup")
    elif intent.request == ADDITIONAL:
        bits.append("requesting an additional unit")
    if intent.location:
        bits.append(f"at {intent.location}")
    return ", ".join(bits) if bits else "unit traffic"
