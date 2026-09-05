"""
Dispatch brain: decides what deserves radio traffic and what does not.

The old pipeline flagged anything that matched a keyword, then let the LLM (or
the offline builder) turn it into a call-out. That produced a lot of noise:
out-of-character chatter, hang-ups, prank calls, information requests and
duplicate reports were all read over the air as if they were real incidents.

This module scores each candidate before it ever reaches TTS. It is fully
offline and deterministic, so it costs no tokens and adds no latency.

Usage:
    brain = Brain(cfg.get("brain", {}))
    verdict = brain.evaluate(flag)
    if not verdict.broadcast:
        skip(verdict.reason)
"""

from __future__ import annotations

import re
import time

# ---------------------------------------------------------------------------
# Signal tables
# ---------------------------------------------------------------------------

# Things that make a call MORE worth broadcasting.
_WEAPON = re.compile(
    r"\b(gun|guns|firearm|pistol|handgun|revolver|rifle|shotgun|ak|uzi|smg|"
    r"armed|arming|weapon|weapons|knife|knives|blade|machete|switchblade|"
    r"bat|crowbar|machine ?gun|brandish\w*|draw\w* (?:a|his|her|their) \w*gun)\b",
    re.I,
)
_VIOLENCE = re.compile(
    r"\b(shot|shots|shoot\w*|shooting|gunshot\w*|gunfire|drive[- ]?by|"
    r"stab\w*|slash\w*|beat\w* up|assault\w*|batter\w*|jump\w* (?:me|him|her)|"
    r"attack\w*|strangl\w*|choke\w*|rape|raping|molest\w*|"
    r"murder\w*|homicide|kill\w*|killed|dead|dying|body|corpse)\b",
    re.I,
)
_MEDICAL = re.compile(
    r"\b(bleed\w*|blood|unconscious|not breathing|cannot breathe|can'?t breathe|"
    r"overdose|od'?d|seizure|seizing|heart attack|cardiac|stroke|choking|"
    r"collapsed|passed out|unresponsive|injured|injury|wounded|broken \w+|"
    r"burn\w*|hurt bad\w*|dying|ambulance|paramedic|ems)\b",
    re.I,
)
_IN_PROGRESS = re.compile(
    r"\b(in progress|right now|happening|currently|as we speak|still here|"
    r"still (?:there|inside|outside)|just (?:happened|now)|breaking in|"
    r"kicking (?:in|down)|trying to get in|chasing|fleeing|running (?:away|off)|"
    r"on scene|active|ongoing|hurry|please hurry|come quick|help me)\b",
    re.I,
)
_PROPERTY = re.compile(
    r"\b(burglar\w*|burglary|break[- ]?in|broke into|robbery|rob\w*|steal\w*|"
    r"stole|stolen|theft|shoplift\w*|carjack\w*|grand theft|gta|vandal\w*|"
    r"graffiti|tagg\w*|arson|trespass\w*|prowler|suspicious|loiter\w*)\b",
    re.I,
)
_TRAFFIC = re.compile(
    r"\b(collision|crash\w*|accident|hit and run|hit[- ]and[- ]run|"
    r"reckless driv\w*|street rac\w*|dui|drunk driv\w*|impaired driv\w*|"
    r"rolled over|flipped|t[- ]?boned|rear[- ]?ended|pedestrian struck)\b",
    re.I,
)
_DISTURBANCE = re.compile(
    r"\b(fight\w*|fighting|brawl|riot|disturb\w*|domestic|argu\w*|"
    r"screaming|yelling|threat\w*|harass\w*|stalk\w*|drunk|intoxicat\w*|"
    r"disorderly|noise|loud music|party|protest)\b",
    re.I,
)
_FIRE = re.compile(
    r"\b(fire|fires|burning|smoke|smoking|flames|explosion|explod\w*|"
    r"gas leak|blaze)\b",
    re.I,
)

# Things that make a call NOT worth broadcasting.
# Out of character / meta chatter that leaked into the radio feed.
_OOC = re.compile(
    r"(^|\s)(\(\(|\)\)|//|ooc\b|oocly|\bafk\b|\bbrb\b|\blol\b|\blmao\b|"
    r"\brofl\b|\bwtf\b|\bomg\b|\bidk\b|\bnvm\b|\bxd\b|\bgg\b|\bez\b|"
    r"\bnoob\b|\bscript\b|\brestart\w*\b|\bcrash\w*ed? (?:my )?game\b|"
    r"\bping\b|\bfps\b|\bdesync\b|\bmod(?:s|ded|erator)?\b|\badmin\b|"
    r"\breport(?:ed)? (?:a )?player\b|\bban(?:ned)?\b)",
    re.I,
)
# Explicit test / prank / cancelled traffic.
_TEST = re.compile(
    r"\b(this is (?:a|only a) test|just testing|test call|testing testing|"
    r"disregard|dis ?regard|cancel(?:led)? (?:that|the call)|never ?mind|"
    r"my (?:bad|mistake)|wrong number|misdial\w*|butt[- ]?dial\w*|"
    r"pocket[- ]?dial\w*|accident(?:al)?(?:ly)? (?:called|dialed)|"
    r"prank|joking|just kidding|jk\b|false alarm|code four|code 4)\b",
    re.I,
)
# Pure information requests - a dispatcher would not broadcast these.
_INFO_REQUEST = re.compile(
    r"\b(what (?:time|are your hours)|when (?:do|does) you|are you open|"
    r"how (?:do|can) i (?:get|file|obtain|apply)|where (?:do|can) i "
    r"(?:get|file|pay)|non[- ]?emergency (?:line|number)|"
    r"phone number for|transfer me|speak to (?:a|an) (?:officer|supervisor)|"
    r"file a report (?:online|later)|records department|impound (?:lot|fee)|"
    r"pay (?:a|my) (?:ticket|fine)|court date|bail|visiting hours)\b",
    re.I,
)
# Hang ups and silence.
_HANGUP = re.compile(
    r"\b(hung up|hangup|hang[- ]?up|caller disconnected|line went dead|"
    r"no (?:answer|response|voice)|silent(?: call)?|open line|dead air|"
    r"abandoned call|dropped (?:the )?call)\b",
    re.I,
)
# Animal / quality-of-life items: real, but routine.
_ROUTINE = re.compile(
    r"\b(cat|kitten|dog|puppy|raccoon|coyote|animal control|"
    r"parking|parked|blocking (?:my|the) driveway|abandoned vehicle|"
    r"pothole|street ?light|graffiti|trash|garbage|litter|"
    r"lost (?:my )?(?:wallet|phone|keys|dog|cat)|found (?:a )?(?:wallet|phone))\b",
    re.I,
)
# Chat noise with no dispatchable content at all.
_GREETING = re.compile(
    r"^\s*(hi|hey|hello|yo|sup|thanks|thank you|ok|okay|k|yes|no|yeah|yep|"
    r"nope|maybe|sure|cool|nice|good|bye|goodbye|cya|later|copy|roger|"
    r"10-4|ten four|affirm\w*|negative)\s*[.!?]*\s*$",
    re.I,
)

_LOC_HINT = re.compile(
    r"\b(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|lane|ln|way|"
    r"court|ct|place|pl|highway|hwy|freeway|fwy|alley|plaza|park|mall|"
    r"store|shop|club|bank|motel|hotel|station|hospital|apartment|block|"
    r"corner|intersection|between|across from|near)\b",
    re.I,
)

_REPEAT_CHAR = re.compile(r"(.)\1{5,}")
_LETTERS = re.compile(r"[a-z]", re.I)


# ---------------------------------------------------------------------------
# Verdict
# ---------------------------------------------------------------------------


class Verdict:
    """The brain decision for one candidate flag."""

    __slots__ = (
        "broadcast",
        "score",
        "priority",
        "category",
        "reason",
        "signals",
        "has_location",
    )

    def __init__(
        self,
        broadcast: bool,
        score: int,
        priority: bool,
        category: str,
        reason: str,
        signals=None,
        has_location: bool = False,
    ) -> None:
        self.broadcast = broadcast
        self.score = score
        self.priority = priority
        self.category = category
        self.reason = reason
        self.signals = list(signals or [])
        self.has_location = has_location

    def __repr__(self) -> str:
        return (
            "Verdict(broadcast=%r, score=%d, priority=%r, category=%r, reason=%r)"
            % (self.broadcast, self.score, self.priority, self.category, self.reason)
        )

    def as_dict(self) -> dict:
        return {
            "broadcast": self.broadcast,
            "score": self.score,
            "priority": self.priority,
            "category": self.category,
            "reason": self.reason,
            "signals": list(self.signals),
            "has_location": self.has_location,
        }


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------

_POSITIVE = (
    # (name, regex, points, category, is_priority_signal)
    ("weapon", _WEAPON, 34, "weapons", True),
    ("violence", _VIOLENCE, 36, "violent crime", True),
    ("medical", _MEDICAL, 32, "medical", True),
    ("fire", _FIRE, 26, "fire", True),
    ("in_progress", _IN_PROGRESS, 22, "in progress", True),
    ("property", _PROPERTY, 18, "property crime", False),
    ("traffic", _TRAFFIC, 16, "traffic", False),
    ("disturbance", _DISTURBANCE, 12, "disturbance", False),
)

_NEGATIVE = (
    # (name, regex, points, reason)
    ("ooc", _OOC, -60, "out-of-character chatter"),
    ("test", _TEST, -70, "test, prank or cancelled call"),
    ("info_request", _INFO_REQUEST, -55, "information request, not an incident"),
    ("hangup", _HANGUP, -45, "hang-up or open line"),
    ("routine", _ROUTINE, -20, "routine quality-of-life call"),
)


class Brain:
    """
    Scores candidate flags so only real, dispatchable incidents go over the
    air. Every threshold is configurable under the `brain:` config section.
    """

    # Flag types that are unit traffic / system events. These are already
    # scope-filtered upstream and must never be second-guessed here.
    ALWAYS_PASS = frozenset(
        {
            "panic",
            "code6",
            "code7",
            "cad",
            "clear",
            "opg",
            "eow",
            "out_status",
            "mdc",
            "alarm",
        }
    )

    # Unit traffic bypasses SCORING, but it still needs a PRIORITY. A code six
    # asking for backup is a Code 3; one asking for an additional unit is a
    # routine Code 2. These are the words that make a unit's own traffic hot.
    _PRIORITY_HINT = re.compile(
        r"\bback[- ]?up\b|need(?:s|ing)?\s+(?:immediate\s+)?(?:help|assistance)|"
        r"\bcode\s*3\b|\bexpedite\b|shots fired|officer (?:down|needs)|"
        r"body on the ground|man down|woman down|person down|unresponsive|"
        r"not breathing|no pulse|\bdoa\b|\bgsw\b|gunshot|bleeding|stabbed|"
        r"hostage|overdose|\b998\b|\b999\b|11[- ]?99|"
        r"(?:gun|weapon|knife|blade)\s+(?:drawn|pulled|out)|"
        r"ambulance|\bems\b|fight(?:ing)? in progress|\btaser\b",
        re.I,
    )

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        # Score needed to broadcast a 911 / chat call.
        self.threshold = int(cfg.get("threshold", 18))
        # Score at or above which the call is treated as a priority.
        self.priority_threshold = int(cfg.get("priority_threshold", 50))
        # Drop repeats of the same incident within this many seconds.
        self.repeat_window_sec = int(cfg.get("repeat_window_sec", 120))
        # Require a usable location before broadcasting a routine call.
        self.require_location = bool(cfg.get("require_location", False))
        self.min_letters = int(cfg.get("min_letters", 12))
        self.log_decisions = bool(cfg.get("log_decisions", False))

        self._recent: dict = {}
        self.stats = {
            "evaluated": 0,
            "broadcast": 0,
            "suppressed": 0,
            "priority": 0,
        }

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _text_of(flag) -> str:
        if isinstance(flag, str):
            return flag
        if not isinstance(flag, dict):
            return ""
        for key in ("situation", "body", "raw", "details", "what"):
            val = flag.get(key)
            if isinstance(val, str) and val.strip():
                return val
        return ""

    @staticmethod
    def _location_of(flag) -> str:
        if isinstance(flag, dict):
            loc = flag.get("location")
            if isinstance(loc, str):
                return loc.strip()
        return ""

    def _is_repeat(self, key: str) -> bool:
        """Same incident already broadcast very recently?"""
        if not key or self.repeat_window_sec <= 0:
            return False
        now = time.time()
        # Opportunistic prune so the dict cannot grow without bound.
        if len(self._recent) > 256:
            cutoff = now - self.repeat_window_sec
            for k in [k for k, t in self._recent.items() if t < cutoff]:
                self._recent.pop(k, None)
        last = self._recent.get(key)
        if last is not None and (now - last) < self.repeat_window_sec:
            return True
        self._recent[key] = now
        return False

    @staticmethod
    def _repeat_key(text: str, location: str) -> str:
        base = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
        words = [w for w in base.split() if len(w) > 3]
        return " ".join(sorted(set(words))[:8]) + "|" + (location or "").lower()

    # -- main entry point -------------------------------------------------

    def evaluate(self, flag) -> Verdict:
        """Decide whether this candidate should be broadcast."""
        self.stats["evaluated"] += 1

        ftype = flag.get("type") if isinstance(flag, dict) else None
        text = self._text_of(flag)
        location = self._location_of(flag)
        has_loc = bool(location) or bool(_LOC_HINT.search(text))

        # Unit traffic and system events bypass scoring entirely: the flagger
        # already applied the operator scope rules to them.
        if not self.enabled or (ftype in self.ALWAYS_PASS):
            # Always broadcast, but still work out whether it is priority.
            # The flagger sets "priority"/"needs" on a code six; anything else
            # is judged on its wording.
            prio = False
            if isinstance(flag, dict):
                prio = bool(flag.get("priority"))
                if str(flag.get("needs") or "").lower() == "backup":
                    prio = True
            if not prio and self._PRIORITY_HINT.search(text):
                prio = True
            v = Verdict(
                True, 100, prio, ftype or "unit traffic",
                "bypass: unit/system traffic" if self.enabled else "brain disabled",
                has_location=has_loc,
            )
            self.stats["broadcast"] += 1
            return v

        # Unit radio traffic phrased in plain language. The flagger already
        # graded it with the intent reader, so trust that grade instead of
        # re-reading the line with the 911-call lexicon, which knows nothing
        # about "roll backup" and scored these at 0.
        if ftype == "radio" and isinstance(flag, dict):
            sense = flag.get("intent")
            if isinstance(sense, dict) and sense.get("actionable"):
                prio = bool(sense.get("priority")) or bool(flag.get("priority"))
                if str(flag.get("needs") or "").lower() == "backup":
                    prio = True
                reason = sense.get("incident") or sense.get("request") or "request"
                v = Verdict(
                    True,
                    int(sense.get("score") or 0),
                    prio,
                    sense.get("category") or "unit traffic",
                    "unit traffic: %s" % reason,
                    list(sense.get("signals") or []),
                    has_loc,
                )
                self.stats["broadcast"] += 1
                if prio:
                    self.stats["priority"] += 1
                return v

        if not text.strip():
            return self._suppress("empty message", has_loc)

        # Obvious junk: greetings, keysmash, letterless spam.
        if _GREETING.match(text.strip()):
            return self._suppress("acknowledgement / greeting only", has_loc)
        if _REPEAT_CHAR.search(text):
            return self._suppress("keysmash / spam", has_loc)
        if len(_LETTERS.findall(text)) < self.min_letters:
            return self._suppress("too short to be an incident", has_loc)

        score = 0
        signals: list[str] = []
        category = "unclassified"
        priority_signal = False
        best_points = 0

        for name, rx, points, cat, is_prio in _POSITIVE:
            if rx.search(text):
                score += points
                signals.append(name)
                if points > best_points:
                    best_points = points
                    category = cat
                if is_prio:
                    priority_signal = True

        blockers: list[str] = []
        for name, rx, points, reason in _NEGATIVE:
            if rx.search(text):
                score += points
                signals.append(name)
                blockers.append(reason)

        # A stated location is corroborating evidence that this is a real call.
        if has_loc:
            score += 10
            signals.append("location")

        # Longer, detailed reports are more likely to be genuine.
        letters = len(_LETTERS.findall(text))
        if letters >= 60:
            score += 6
            signals.append("detailed")

        # Hard blocks: an explicit cancel/test/OOC marker beats any keyword.
        if blockers and score < self.threshold:
            return self._suppress(blockers[0], has_loc, score, category, signals)

        if score < self.threshold:
            return self._suppress(
                "no dispatchable content (score %d < %d)" % (score, self.threshold),
                has_loc, score, category, signals,
            )

        if self.require_location and not has_loc:
            return self._suppress(
                "no usable location", has_loc, score, category, signals
            )

        if self._is_repeat(self._repeat_key(text, location)):
            return self._suppress(
                "duplicate of a call already broadcast",
                has_loc, score, category, signals,
            )

        priority = priority_signal and score >= self.priority_threshold
        self.stats["broadcast"] += 1
        if priority:
            self.stats["priority"] += 1
        return Verdict(
            True, score, priority, category,
            "score %d" % score, signals, has_loc,
        )

    def _suppress(
        self,
        reason: str,
        has_loc: bool = False,
        score: int = 0,
        category: str = "noise",
        signals=None,
    ) -> Verdict:
        self.stats["suppressed"] += 1
        v = Verdict(False, score, False, category, reason, signals, has_loc)
        if self.log_decisions:
            print("[brain] suppressed: %s" % reason)
        return v

    def summary(self) -> str:
        s = self.stats
        return "brain: %d evaluated, %d broadcast, %d suppressed, %d priority" % (
            s["evaluated"], s["broadcast"], s["suppressed"], s["priority"]
        )
