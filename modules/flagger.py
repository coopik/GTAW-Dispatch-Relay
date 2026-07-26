from __future__ import annotations

import re
import time
from collections import OrderedDict, deque
from difflib import SequenceMatcher

_SELF_NOISE = [
    r"dispatch relay",
    r"recent flagged",
    r"flagged:",
    r"dispatch:",
    r"synth queue",
    r"playback queue",
    r"play queue",
    r"watching",
    r"loop error",
    r"tts/?fx error",
    r"llm error",
    r"init error",
    r"select the chat",
    r"select a window",
    r"calibration",
    r"saved region",
    r"stopping\b",
    r"^\s*started\.?\s*$",
    r"^\s*idle\s*$",
    r"^\s*running\s*$",
    r"all units",
    r"be advised",
    r"respond code",
    r"rescue ambulance",
    r"now occurring",
    r"reporting party",
    r"caller reports",
    r"officer in distress",
    r"refer to tac",
    r"computer[- ]aided dispatch",
    r"did not provide a location",
    r"units responding",
    r"units to assist",
    r"control copies",
    r"for emergencies",
    r"emergencies dial",
    r"non[- ]?emergenc",
    r"welcome to",
    r"discord\.gg",
]

_DIGIT_NOISE = {"ill", "iii", "lll", "il", "li", "l", "i"}

_URGENT_RE = re.compile(
    r"shots fired|officer (?:down|needs help|needs assistance|in distress|in trouble)|"
    r"man down|11[- ]?99|\b998\b|\b999\b|in pursuit|foot pursuit|vehicle pursuit",
    re.IGNORECASE,
)

_RADIO_KEYWORDS = re.compile(
    r"code\s*six|code\s*6|code\s*3|code\s*four|code\s*4|shots fired|"
    r"officer (?:down|needs help|needs assistance|in distress|in trouble|requesting)|"
    r"need(?:s|ing)?\s+(?:an?\s+)?(?:additional|backup|back[- ]?up|another unit|assistance|supervisor|air unit)|"
    r"requesting\s+(?:an?\s+)?(?:additional|backup|back[- ]?up|supervisor|unit|air ?ship)|"
    r"roll\s+(?:me|us|a|an|out)\b|send\s+(?:me|us|a|an)\b|"
    r"in pursuit|foot pursuit|vehicle pursuit|in custody|man down|"
    r"11[- ]?99|\b998\b|\b999\b",
    re.IGNORECASE,
)

_CALLSIGN_RE = re.compile(
    r"^\s*([0-9]{1,2}[- ]?[A-Za-z]{1,4}[- ]?[0-9]{1,3}|[A-Za-z]{1,3}[- ]?[0-9]{2,3})\b"
)

_CODE_SIX_RE = re.compile(r"code\s*six|code\s*6\b", re.I)
_CODE_SIX_HANDOFF_RE = re.compile(
    r"backup|back[- ]?up|need(?:s|ing)?\s+(?:help|assistance)|shots fired|"
    r"officer (?:down|needs|in distress|in trouble)|man down|in pursuit|"
    r"foot pursuit|vehicle pursuit|\b998\b|\b999\b|11[- ]?99|"
    r"additional unit|another unit|more units?|second unit|extra unit|"
    r"supervisor|air ?unit|air ?ship|ambulance|\bems\b|fire|rescue",
    re.I,
)
_CODE_SIX_LOC_RE = re.compile(
    r"\b(?:on|at|near|by)\s+([A-Za-z0-9 .'\-/&]+?)"
    r"(?=,|\bwith\b|\boccupied\b|\bocc\b|\bindex\b|\bplate\b|\bregistration\b|\breg\b|$)",
    re.I,
)
_STREET_SUFFIX_RE = re.compile(
    r"\b(?:drive|dr|avenue|ave|av|street|st|boulevard|blvd|road|rd|way|lane|ln|"
    r"court|ct|place|pl|plaza|park|parkway|pkwy|highway|hwy|freeway|fwy|terrace|"
    r"circle|cir|alley|trail|route|rte|bridge|pier|docks|station|mall|square)\b\.?$",
    re.I,
)
_KNOWN_AREAS = {
    "mission row", "pillbox hill", "davis", "strawberry", "vinewood",
    "east vinewood", "west vinewood", "vinewood hills", "del perro",
    "vespucci", "vespucci beach", "rockford hills", "burton", "morningwood",
    "chamberlain hills", "la mesa", "el burro heights", "sandy shores",
    "paleto bay", "grapeseed", "harmony", "banning", "elysian island",
    "terminal", "little seoul", "textile city", "hawick", "downtown",
    "downtown vinewood", "alta", "richman", "pacific bluffs", "tataviam",
    "cypress flats", "murrieta heights", "rancho", "mirror park",
    "pillbox south", "legion square", "maze bank", "forum drive",
    "grove street", "strawberry avenue", "innocence boulevard",
}
_NOT_A_PLACE = {
    "be advised", "advised", "standby", "stand by", "copy", "copy that",
    "thanks", "thank you", "no further", "nothing further", "code four",
    "code 4", "clear", "en route", "enroute", "on scene", "out", "out here",
    "i am out", "im out", "one moment", "go ahead", "received", "roger",
    "affirm", "affirmative", "negative", "show me", "mark me", "put me",
}
_CODE_SIX_DETAIL_RE = re.compile(
    r"\b((?:with|occupied|occ|index|plate|registration|reg)\b.*)$",
    re.I,
)

_CODE_SEVEN_RE = re.compile(r"code\s*(?:seven|7)\b", re.I)
# phrasings so ordinary uses of the word "clear" (e.g. "clear the area") do not
_CLEAR_RE = re.compile(
    r"(?:show\s*me\s*clear\b|showing\s*(?:me\s*)?clear\b|"
    r"(?:i'?m|im|we'?re|were)?\s*clear(?:ing|ed)?\b|"
    r"back\s*in\s*service\b|(?:mark|put|show)\s*(?:me|us)\s*"
    r"(?:clear|available|in\s*service)\b|"
    r"(?:i'?m|im|we'?re|were|now|back|again)\s+available\b|"
    r"\bavailable\s+for\s+(?:call|calls|service|assignment|detail|details)\b|"
    r"\bin\s*service\b)",
    re.I,
)
_CLEAR_FROM_RE = re.compile(r"\bclear(?:ing)?\s+from\b\s*(?P<where>.*)$", re.I)
_CLEAR_NEG_RE = re.compile(
    r"all\s*clear|clear(?:ing|ed)?\s*(?:the|this|that)\b|"
    r"clear\s*(?:copy|channel|air|frequency|traffic)\b|not\s*clear\b|"
    r"is\s*(?:it|this)\s*clear\b",
    re.I,
)
_CLEAR_SELF_RE = re.compile(
    r"(?:show\s*me\s*clear|showing\s*(?:me\s*)?clear|"
    r"(?:i'?m|im|we'?re|were)\s*clear(?:ing|ed)?|"
    r"(?:mark|put|show)\s*(?:me|us)\s*(?:clear|available|in\s*service)|"
    r"back\s*in\s*service|clear(?:ing)?\s+from)",
    re.I,
)
_CLEAR_ASK_RE = re.compile(
    r"\?|\b(?:any|anyone|anybody|any\s*units?|who(?:'s|s|\s+is)|which\s*unit|"
    r"do\s*(?:we|you)\s*have|is\s*(?:there|anyone|any)|are\s*(?:there|any|you)|"
    r"got\s*(?:a|an|any)|need(?:s|ing)?\s*(?:a|an|any|another)|request(?:s|ing)?|"
    r"looking\s*for|can\s*(?:i|we|you)|could\s*(?:i|we|you)|available\s*unit)\b",
    re.I,
)
_CODE_SEVEN_LOC_RE = re.compile(
    r"(?:at|on|near|by|from|@)\s+([A-Za-z0-9 .'\-/&]+?)(?=,|$)",
    re.I,
)

_CHAT_SPEAKER_RE = re.compile(
    r"[A-Za-z][\w'.\-]*(?:\s+[A-Za-z][\w'.\-]*){0,3}\s+"
    r"(?:says|shouts|whispers|exclaims|mutters|asks|yells|screams|states|"
    r"radios|responds|adds|continues|answers|replies)\s*"
    r"(?:\[[^\]]*\]|\([^)]*\))?\s*:",
    re.IGNORECASE,
)
_CHAT_TAG_RE = re.compile(
    r"\[(?:ems|pd|fd|police|fire|ambulance|911|!|s\d+|ch\s*[:|]|dispatch|"
    r"info|radio|cad|mdt|mdc|ooc|do|me)\b",
    re.IGNORECASE,
)

_PANIC_RE = re.compile(r"panic\s*(?:button|alarm)", re.I)
_PANIC_CALLSIGN_RE = re.compile(r"\((\d{1,3}[A-Za-z]{1,3}\d{0,3})\)")
_PANIC_ACTIVE_RE = re.compile(r"activat|press|push|hit|trigger|enabl", re.I)
_PANIC_NAME_RE = re.compile(
    r"(?:officer|deputy|dep\.?|off\.?|sergeant|sgt\.?|detective|det\.?|"
    r"lieutenant|lt\.?|corporal|cpl\.?|sheriff|trooper|captain|cpt\.?|"
    r"chief|cadet|recruit|sr\.?|master|principal|lead|senior)\s+"
    r"([A-Za-z][A-Za-z'.\-]+(?:\s+[A-Za-z][A-Za-z'.\-]+){0,3})",
    re.I,
)
_RANK_TOKENS = {
    "officer", "deputy", "dep", "off", "sergeant", "sgt", "detective", "det",
    "lieutenant", "lt", "corporal", "cpl", "sheriff", "trooper", "captain",
    "cpt", "chief", "cadet", "recruit", "sr", "lead", "senior", "police",
    "master", "principal",
}
_CAD_UPDATE_RE = re.compile(
    r"\bcad\b[^.]*\b(?:location|status|position|update)\b|"
    r"\bupdate\b[^.]*\bcad\b|"
    r"\bupdate\s+my\s+(?:location|status|position)\b|"
    r"\b(?:location|status)\s+update\b",
    re.I,
)
_ANY_CALLSIGN_RE = re.compile(
    r"\b([0-9]{1,2}[- ]?[A-Za-z]{1,4}[- ]?[0-9]{1,3}|[A-Za-z]{1,3}[- ]?[0-9]{2,3})\b"
)


class Flagger:
    def __init__(self, cfg: dict):
        cfg = cfg or {}
        flags = re.IGNORECASE
        self.patterns = [re.compile(p, flags) for p in cfg.get("patterns", [])]
        ignore = list(cfg.get("ignore_patterns", [])) + _SELF_NOISE
        self.ignore = [re.compile(p, flags) for p in ignore]
        self.min_body_length = int(cfg.get("min_body_length", 6))
        self.fuzzy_threshold = float(cfg.get("fuzzy_threshold", 0.82))
        maxlen = int(cfg.get("dedup_history", 400))
        self._dedup_maxlen = maxlen
        _cd = cfg.get("dedup_cooldown_sec")
        self.dedup_cooldown = float(180 if _cd is None else _cd)
        self._seen: "OrderedDict[str, float]" = OrderedDict()
        self._seen_calls: "OrderedDict[str, float]" = OrderedDict()
        cb = cfg.get("call_block", {}) or {}
        self.call_block_enabled = bool(cb.get("enabled", True))
        self.radio_enabled = bool(cfg.get("radio_traffic", True))
        self.require_structure = bool(cfg.get("require_chat_structure", True))
        self.panic_enabled = bool(cfg.get("panic_button", True))
        cad_cfg = cfg.get("cad_updates", {}) or {}
        self.cad_enabled = bool(cad_cfg.get("enabled", True))
        self.cad_scope = str(cad_cfg.get("scope", "own")).lower()
        c6_cfg = cfg.get("code_six", {}) or {}
        self.code6_enabled = bool(c6_cfg.get("enabled", True))
        self.code6_scope = str(c6_cfg.get("scope", "own")).lower()
        self.code6_detail = str(c6_cfg.get("detail", "detailed")).lower()
        clr_cfg = cfg.get("clear_ack", {}) or {}
        self.clear_enabled = bool(clr_cfg.get("enabled", True))
        self.clear_scope = str(clr_cfg.get("scope", "own")).lower()
        c7_cfg = cfg.get("code_seven", {}) or {}
        self.code7_enabled = bool(c7_cfg.get("enabled", True))
        self.code7_scope = str(c7_cfg.get("scope", "own")).lower()
        mdc_cfg = cfg.get("mdc_lookup", {}) or {}
        self.mdc_enabled = bool(mdc_cfg.get("enabled", False))
        self.mdc_scope = str(mdc_cfg.get("scope", "own")).lower()
        self.mdc_name_res = self._compile_list(mdc_cfg.get("name_patterns"), re.I)
        self.mdc_plate_res = self._compile_list(mdc_cfg.get("plate_patterns"), re.I)
        self.own_callsigns = [
            self._norm_callsign(c)
            for c in (cfg.get("own_callsigns") or cad_cfg.get("callsigns") or [])
            if str(c).strip()
        ]
        self.skip_names = [
            str(n).strip().lower()
            for n in (cfg.get("skip_own_names") or [])
            if str(n).strip()
        ]
        self.stability_frames = max(1, int(cfg.get("stability_frames") or 1))
        self._frame_counts: dict = {}

    @classmethod
    def _normalize(cls, line: str) -> str:
        key = re.sub(r"[^a-z0-9 ]+", " ", line.lower())
        tokens = key.split()
        while tokens and (
            not re.search(r"[a-z]", tokens[0])
            or tokens[0] in _DIGIT_NOISE
            or tokens[0] == "911"
        ):
            tokens.pop(0)
        return " ".join(tokens).strip()

    def _seen_lookup(
        self, store: "OrderedDict[str, float]", key: str, fuzzy: bool
    ) -> bool:
        now = time.monotonic()
        match = None
        if key in store:
            match = key
        elif fuzzy:
            for prev in store:
                if SequenceMatcher(None, key, prev).ratio() >= self.fuzzy_threshold:
                    match = prev
                    break
        if match is not None:
            last = store[match]
            if self.dedup_cooldown > 0 and (now - last) >= self.dedup_cooldown:
                del store[match]
                store[key] = now
                store.move_to_end(key)
                self._evict(store)
                return True
            store[match] = now
            store.move_to_end(match)
            return False
        store[key] = now
        self._evict(store)
        return True

    def _evict(self, store: "OrderedDict[str, float]") -> None:
        while len(store) > self._dedup_maxlen:
            store.popitem(last=False)

    def _is_new(self, line: str) -> bool:
        key = self._normalize(line)
        if not key:
            return False
        return self._seen_lookup(self._seen, key, fuzzy=True)

    def _is_new_call(self, key: str) -> bool:
        if not key:
            return False
        return self._seen_lookup(self._seen_calls, key, fuzzy=not key.isdigit())

    @staticmethod
    def _looks_like_garbage(text: str) -> bool:
        t = text.strip()
        if len(t) < 4:
            return True
        clean = sum(c.isalnum() or c.isspace() for c in t)
        if clean < 0.72 * len(t):
            return True
        tokens = re.findall(r"[A-Za-z0-9']+", t)
        if not tokens:
            return True

        def _real_word(w: str) -> bool:
            if not re.fullmatch(r"[A-Za-z]{3,}", w):
                return False
            wl = w.lower()
            if not re.search(r"[aeiou]", wl):
                return False
            if re.search(r"(.)\1\1", wl):
                return False
            if re.search(r"[bcdfghjklmnpqrstvwxyz]{5,}", wl):
                return False
            return True

        real = [w for w in tokens if _real_word(w)]
        if len(real) < 2 or len(real) < 0.5 * len(tokens):
            return True
        return False

    @staticmethod
    def _looks_like_sign(text: str) -> bool:
        t = text
        tl = t.lower()
        if re.search(
            r"\[(?:ems|pd|fd|911|!|dispatch)\b|\bdials\s+911|\bcalled\s+911|"
            r"[a-z][\w'.\-]*\s+says\s*(?:\[[^\]]*\]|\([^)]*\))?\s*:",
            tl,
        ):
            return False
        if re.search(r"[\u2122\u00ae\u00a9]", t):
            return True
        if re.search(r"\d+\s*[\"\u201d\u2019']\s*x\s*\d+", t):
            return True
        if re.search(
            r"in case of emergency|for fire,? police|police or par|safety supply|"
            r"signquick|fire safety|emergency servi|emergency dial|dial 9\s*-?1\s*-?1|"
            r"911 service|911 phone|our address|address text|building is closed|"
            r"custom message|smartsign|accuform|compliance sign|red rectangle|"
            r"\bsign\b",
            tl,
        ):
            return True
        if re.search(r"9\s*-?1\s*-?1|911|emergency", tl):
            words = re.findall(r"[A-Za-z]{3,}", t)
            caps = [w for w in words if w.isupper()]
            if len(words) >= 2 and len(caps) / len(words) >= 0.5:
                return True
        return False

    @classmethod
    def _has_chat_structure(cls, text: str) -> bool:
        if _CHAT_SPEAKER_RE.search(text):
            return True
        if _CHAT_TAG_RE.search(text):
            return True
        if "*" in text and re.search(r"\bdials?\b", text, re.IGNORECASE):
            return True
        return False

    @staticmethod
    def extract_body(line: str) -> str:
        cleaned = re.sub(r"^\s*\[?\d{1,2}:\d{2}(:\d{2})?\]?\s*", "", line)
        return cleaned.strip() or line.strip()

    @staticmethod
    def _field_label(line: str) -> str | None:
        l = re.sub(r"^[\s>*\u2022\u00b7|.\-,:]+", "", line.strip().lower())
        if re.match(r"(situation|nature|details|call type|reason)\b", l):
            return "situation"
        if re.match(r"(location|address|street)\b", l):
            return "location"
        if re.match(r"(call\s*id|log\s*(?:number|no|num|id|#)?|incident|case|event|ref)\b", l):
            return "incident"
        if re.match(r"(phone|number|caller|contact)\b", l):
            return "ignore"
        if re.match(r"#\s*\d{3,}", l):
            return "incident_inline"
        return None

    @staticmethod
    def _scan_incident(lines: list[str]) -> str | None:
        text = " ".join(lines)
        m = re.search(
            r"(?:incident|call\s*id|log\s*(?:number|no|num|id|#)?|case|cad|event|ref)"
            r"\D{0,6}(\d[\d\-\s]{2,}\d)",
            text, re.IGNORECASE,
        )
        if not m:
            m = re.search(r"#\s*(\d{3,})", text)
        if not m:
            return None
        digits = re.sub(r"\D", "", m.group(1))
        return digits[-4:] if len(digits) >= 3 else None

    def _parse_call_block(self, lines: list[str]) -> dict | None:
        if not self.call_block_enabled:
            return None
        fields: dict[str, str] = {}
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            label = self._field_label(line)
            if label == "incident_inline":
                m = re.search(r"#\s*(\d{3,})", line)
                if m:
                    fields.setdefault("incident", m.group(1))
                i += 1
                continue
            if label is None:
                i += 1
                continue
            if label == "incident":
                same = re.sub(r"\D", "", line)
                if same:
                    fields.setdefault("incident", same)
                    i += 1
                    continue
                if i + 1 < n and re.match(r"^#?\s*\d[\d\s]{2,}$", lines[i + 1].strip()):
                    fields.setdefault("incident", re.sub(r"\D", "", lines[i + 1]))
                    i += 2
                    continue
                i += 1
                continue
            parts = line.split(":", 1)
            value = parts[1].strip() if len(parts) > 1 else ""
            if not value:
                j = i + 1
                buff = []
                while j < n and self._field_label(lines[j]) is None and lines[j].strip():
                    buff.append(lines[j].strip())
                    j += 1
                value = " ".join(buff)
                i = j
            else:
                i += 1
            if label != "ignore" and value:
                fields.setdefault(label, value)
            continue

        situation = fields.get("situation", "").strip()
        location = (fields.get("location") or "").strip() or None

        incident = None
        if "incident" in fields:
            digits = re.sub(r"\D", "", fields["incident"])
            incident = digits[-4:] if digits else None
        if not incident:
            incident = self._scan_incident(lines)

        if not situation or not (location or incident):
            return None
        if self._looks_like_garbage(situation):
            return None
        return {
            "type": "call",
            "incident": incident,
            "situation": situation,
            "location": location,
            "raw": "; ".join(f"{k}={v}" for k, v in fields.items() if k != "ignore"),
        }

    def _is_own_message(self, line: str) -> bool:
        if not self.skip_names:
            return False
        body = self._strip_speaker_meta(line, keep_speaker=True)
        m = re.match(
            r"^\s*([A-Za-z][\w'.\-]*(?:\s+[A-Za-z][\w'.\-]*){0,3})"
            r"\s+says\s*(?:\[[^\]]*\]|\([^)]*\))?\s*:",
            body,
        )
        if not m:
            return False
        speaker = m.group(1).strip().lower()
        return any(
            speaker == n or speaker.startswith(n) or n in speaker
            for n in self.skip_names
        )

    @staticmethod
    def _norm_callsign(value: str) -> str:
        return re.sub(r"[^a-z0-9]", "", str(value).lower())

    def _match_own_callsign(self, callsign: str) -> bool:
        n = self._norm_callsign(callsign)
        if not n:
            return False
        for o in self.own_callsigns:
            if not o:
                continue
            if n == o or (len(o) >= 3 and (n.startswith(o) or o.startswith(n))):
                return True
        return False

    def _parse_panic(self, line: str) -> dict | None:
        if not self.panic_enabled:
            return None
        if not (_PANIC_RE.search(line) and _PANIC_ACTIVE_RE.search(line)):
            return None
        name = None
        m = _PANIC_NAME_RE.search(line)
        if m:
            tokens = m.group(1).split()
            while len(tokens) > 1 and tokens[0].strip(".").lower() in _RANK_TOKENS:
                tokens.pop(0)
            name = " ".join(tokens[:2]).strip(" .,-")
        callsign = None
        mp = _PANIC_CALLSIGN_RE.search(line)
        if mp:
            callsign = mp.group(1).strip()
        else:
            mc = _ANY_CALLSIGN_RE.search(line)
            if mc:
                callsign = mc.group(1).strip()
        location = None
        ml = re.search(
            r"\b(?:at|near|on|in|by the)\s+([A-Za-z0-9 ,.'/\-]{3,})", line, re.I
        )
        if ml:
            location = ml.group(1).strip(" .,]-")
        key = "panic:" + (
            self._norm_callsign(name or "") or self._normalize(line) or line.lower()
        )
        if not self._is_new_call(key):
            return None
        return {
            "type": "panic",
            "name": name or None,
            "callsign": callsign,
            "location": location or None,
            "raw": line.strip(),
        }

    def _parse_cad(self, line: str) -> dict | None:
        if not self.cad_enabled:
            return None
        body = self._strip_speaker_meta(line)
        if not body or not _CAD_UPDATE_RE.search(body):
            return None
        m = _CALLSIGN_RE.match(body)
        callsign = m.group(1).strip() if m else None
        if not callsign:
            m2 = _ANY_CALLSIGN_RE.search(body)
            callsign = m2.group(1).strip() if m2 else None
        if not callsign:
            return None
        if self.cad_scope == "own" and not (
            callsign and self._match_own_callsign(callsign)
        ):
            return None
        low = body.lower()
        has_loc = bool(re.search(r"location|position", low))
        has_stat = bool(re.search(r"status", low))
        if has_loc and has_stat:
            what = "status and location"
        elif has_stat:
            what = "status"
        elif has_loc:
            what = "location"
        else:
            what = "CAD"
        if not self._is_new(body):
            return None
        return {"type": "cad", "callsign": callsign, "what": what, "raw": body}

    def _parse_code6(self, line: str) -> dict | None:
        if not self.code6_enabled:
            return None
        body = self._strip_speaker_meta(line)
        if not body or not _CODE_SIX_RE.search(body):
            return None
        if _CODE_SIX_HANDOFF_RE.search(body):
            return None
        m = _CALLSIGN_RE.match(body)
        callsign = m.group(1).strip() if m else None
        if not callsign:
            m2 = _ANY_CALLSIGN_RE.search(body)
            callsign = m2.group(1).strip() if m2 else None
        if not callsign:
            return None
        if self.code6_scope == "own" and not (
            callsign and self._match_own_callsign(callsign)
        ):
            return None
        after = body[_CODE_SIX_RE.search(body).end():]
        location = None
        ml = _CODE_SIX_LOC_RE.search(after)
        if ml:
            location = ml.group(1).strip(" .,-") or None
        if not location:
            location = self._bare_location(after)
        details = None
        if self.code6_detail == "detailed":
            md = _CODE_SIX_DETAIL_RE.search(after)
            if md:
                details = md.group(1).strip(" .,-") or None
        if not self._is_new(body):
            return None
        return {
            "type": "code6",
            "callsign": callsign,
            "location": location,
            "details": details,
            "raw": body,
        }

    @staticmethod
    def _bare_location(after: str) -> str | None:
        for chunk in after.split(","):
            chunk = chunk.strip(" .;:-")
            if not chunk:
                continue
            low = chunk.lower()
            if low in _NOT_A_PLACE:
                continue
            if _CODE_SIX_DETAIL_RE.search(chunk):
                break
            if _STREET_SUFFIX_RE.search(low) or low in _KNOWN_AREAS:
                return chunk
            words = low.split()
            if (1 <= len(words) <= 4 and all(w.replace("'", "").replace("-", "").isalpha()
                                             for w in words)
                    and not any(w in _NOT_A_PLACE for w in words)):
                return chunk
        return None

    def _parse_clear(self, line: str) -> dict | None:
        if not self.clear_enabled:
            return None
        body = self._strip_speaker_meta(line)
        if not body:
            return None
        # Don't collide with code six / seven; those have their own handlers.
        if _CODE_SIX_RE.search(body) or _CODE_SEVEN_RE.search(body):
            return None
        if _CLEAR_NEG_RE.search(body):
            return None
        # Only an explicit self-report survives a question or a request for
        # another unit: "any available canine?" is asking, not clearing.
        if not _CLEAR_SELF_RE.search(body) and _CLEAR_ASK_RE.search(body):
            return None
        start_of_watch = False
        station = None
        mfrom = _CLEAR_FROM_RE.search(body)
        if mfrom:
            start_of_watch = True
            station = (mfrom.group("where") or "").strip(" .,-") or None
        elif not _CLEAR_RE.search(body):
            return None
        m = _CALLSIGN_RE.match(body)
        callsign = m.group(1).strip() if m else None
        if not callsign:
            m2 = _ANY_CALLSIGN_RE.search(body)
            callsign = m2.group(1).strip() if m2 else None
        if not callsign:
            return None
        if self.clear_scope == "own" and not self._match_own_callsign(callsign):
            return None
        if not self._is_new(body):
            return None
        flag = {"type": "clear", "callsign": callsign, "raw": body}
        if start_of_watch:
            flag["start_of_watch"] = True
            flag["location"] = station
        return flag

    def _parse_code7(self, line: str) -> dict | None:
        if not self.code7_enabled:
            return None
        body = self._strip_speaker_meta(line)
        if not body or not _CODE_SEVEN_RE.search(body):
            return None
        m = _CALLSIGN_RE.match(body)
        callsign = m.group(1).strip() if m else None
        if not callsign:
            m2 = _ANY_CALLSIGN_RE.search(body)
            callsign = m2.group(1).strip() if m2 else None
        if not callsign:
            return None
        if self.code7_scope == "own" and not self._match_own_callsign(callsign):
            return None
        after = body[_CODE_SEVEN_RE.search(body).end():]
        location = None
        ml = _CODE_SEVEN_LOC_RE.search(after)
        if ml:
            location = ml.group(1).strip(" .,-") or None
        if not self._is_new(body):
            return None
        return {"type": "code7", "callsign": callsign, "location": location, "raw": body}

    @staticmethod
    def _compile_list(patterns, flags) -> list:
        out = []
        for p in (patterns or []):
            try:
                out.append(re.compile(p, flags))
            except Exception:
                pass
        return out

    @staticmethod
    def _mdc_target(match) -> str:
        try:
            gd = match.groupdict()
            if gd.get("target"):
                return gd["target"]
        except Exception:
            pass
        try:
            if match.groups():
                return match.group(1) or ""
        except Exception:
            pass
        return ""

    @staticmethod
    def _looks_like_plate(token: str) -> bool:
        clean = re.sub(r"[^A-Za-z0-9]", "", token or "")
        if not (2 <= len(clean) <= 8):
            return False
        return any(c.isalpha() for c in clean) and any(c.isdigit() for c in clean)

    def _scan_plate(self, body: str, callsign: str | None) -> str:
        cs_key = re.sub(r"[^A-Za-z0-9]", "", (callsign or "")).upper()
        token_re = r"[A-Za-z]{1,4}[ -]?\d{1,4}|\d{1,4}[ -]?[A-Za-z]{1,4}|[A-Za-z0-9]{4,8}"

        def _find(space: str) -> str:
            best = ""
            for tok in re.findall(token_re, space or ""):
                key = re.sub(r"[^A-Za-z0-9]", "", tok).upper()
                if not self._looks_like_plate(tok):
                    continue
                if cs_key and key == cs_key:
                    continue
                best = tok
            return best

        kw = re.search(r"(?i)\b(?:plate|tag|registration|reg)\b", body or "")
        after = body[kw.end():] if kw else ""
        return _find(after) or _find(body or "")

    @staticmethod
    def _strip_rp_spelling(name: str) -> str:
        if not name:
            return name
        s = re.sub(r"(?i)\b(?:[a-z]-){2,}[a-z]\b", " ", name)
        s = re.sub(r"[.,;:]+", " ", s)
        tokens = [t for t in s.split() if len(re.sub(r"[^A-Za-z]", "", t)) > 1]
        return " ".join(tokens).strip()

    def _parse_mdc(self, line: str) -> dict | None:
        if not self.mdc_enabled:
            return None
        if not (self.mdc_name_res or self.mdc_plate_res):
            return None
        body = self._strip_speaker_meta(line)
        if not body:
            return None
        m = _CALLSIGN_RE.match(body)
        callsign = m.group(1).strip() if m else None
        if not callsign:
            m2 = _ANY_CALLSIGN_RE.search(body)
            callsign = m2.group(1).strip() if m2 else None
        if self.mdc_scope == "own" and not (callsign and self._match_own_callsign(callsign)):
            return None
        for rx in self.mdc_plate_res:
            mm = rx.search(body)
            if not mm:
                continue
            raw_target = self._mdc_target(mm).strip(" .,-")
            # Prefer the captured token when it's plate-shaped; otherwise scan
            candidate = raw_target if self._looks_like_plate(raw_target) else self._scan_plate(body, callsign)
            if not self._looks_like_plate(candidate):
                continue
            target = re.sub(r"[^A-Za-z0-9]", "", candidate).upper()
            if not self._is_new(body):
                return None
            return {"type": "mdc", "lookup": "plate", "target": target,
                    "callsign": callsign, "raw": body}
        for rx in self.mdc_name_res:
            mm = rx.search(body)
            if not mm:
                continue
            target = re.sub(r"\s+", " ", self._mdc_target(mm)).strip(" .,-")
            target = self._strip_rp_spelling(target)
            if len(re.sub(r"[^A-Za-z]", "", target)) < 3:
                continue
            target = " ".join(w.capitalize() for w in target.split())
            if not self._is_new(body):
                return None
            return {"type": "mdc", "lookup": "name", "target": target,
                    "callsign": callsign, "raw": body}
        return None

    def _stabilize(self, lines: list[str]) -> list[str]:
        if self.stability_frames <= 1:
            return lines
        counts: dict = {}
        out: list[str] = []
        for line in lines:
            key = self._normalize(line)
            if not key:
                out.append(line)
                continue
            seen = self._frame_counts.get(key, 0) + 1
            counts[key] = max(seen, counts.get(key, 0))
            if seen >= self.stability_frames:
                out.append(line)
        self._frame_counts = counts
        return out

    def process(self, lines: list[str]) -> list[dict]:
        flags: list[dict] = []
        call = self._parse_call_block(lines)
        if call is not None:
            key = call["incident"] or self._normalize(
                (call["situation"] or "") + " " + (call["location"] or "")
            )
            if self._is_new_call(key):
                flags.append(call)

        for line in self._stabilize(lines):
            if self._field_label(line) is not None:
                continue
            if any(p.search(line) for p in self.ignore):
                continue
            panic = self._parse_panic(line)
            if panic is not None:
                flags.append(panic)
                continue
            cad = self._parse_cad(line)
            if cad is not None:
                flags.append(cad)
                continue
            code6 = self._parse_code6(line)
            if code6 is not None:
                flags.append(code6)
                continue
            code7 = self._parse_code7(line)
            if code7 is not None:
                flags.append(code7)
                continue
            clear = self._parse_clear(line)
            if clear is not None:
                flags.append(clear)
                continue
            mdc = self._parse_mdc(line)
            if mdc is not None:
                flags.append(mdc)
                continue
            if self._is_own_message(line):
                continue
            is_911 = any(p.search(line) for p in self.patterns)
            if not is_911:
                radio = self._parse_radio(line)
                if radio is not None:
                    flags.append(radio)
                continue
            body = self.extract_body(line)
            if len(body) < self.min_body_length:
                continue
            if self._looks_like_garbage(body):
                continue
            if self._looks_like_sign(body):
                continue
            if self.require_structure and not self._has_chat_structure(line):
                continue
            if not self._is_new(line):
                continue
            flags.append({"type": "chat", "body": body, "raw": body})
        return flags

    @classmethod
    def _strip_speaker_meta(cls, line: str, keep_speaker: bool = False) -> str:
        body = cls.extract_body(line)
        body = re.sub(r"^[\s:;>*\-|.,]+", "", body)
        prev = None
        while prev != body:
            prev = body
            body = re.sub(r"^\s*\[[^\]]*\]\s*", "", body)
            body = re.sub(r"^[\s:;>*\-|.,]+", "", body)
        if not keep_speaker:
            m = re.search(
                r"[A-Za-z][\w'.\-]*(?:\s+[A-Za-z][\w'.\-]*){0,3}"
                r"\s+says\s*(?:\[[^\]]*\]|\([^)]*\))?\s*:\s*",
                body,
            )
            if m:
                body = body[m.end():].strip()
        return body.strip()

    def _parse_radio(self, line: str) -> dict | None:
        if not self.radio_enabled:
            return None
        body = self._strip_speaker_meta(line)
        if not body or not _RADIO_KEYWORDS.search(body):
            return None
        if len(body) < self.min_body_length:
            return None
        if not _URGENT_RE.search(body) and self._looks_like_garbage(body):
            return None
        m2 = _CALLSIGN_RE.match(body)
        callsign = m2.group(1).strip() if m2 else None
        if not callsign:
            return None
        if not self._is_new(body):
            return None
        return {"type": "radio", "body": body, "callsign": callsign, "raw": body}

    def process_lines(self, lines: list[str]) -> list[str]:
        return [f["body"] for f in self.process(lines) if f["type"] == "chat"]
