from __future__ import annotations

import itertools
import os
import random
import re

import requests

_INCIDENTS: list[tuple[str, str]] = [
    (r"capital murder", "a 201 capital murder"),
    (r"first[- ]?degree murder", "a 202 first degree murder"),
    (r"second[- ]?degree murder", "a 203 second degree murder"),
    (r"homicide|murder|dead body|deceased|\bdb\b|body found|found dead", "a 202 murder"),
    (r"voluntary manslaughter", "a 204 voluntary manslaughter"),
    (r"involuntary manslaughter|manslaughter", "a 205 manslaughter"),
    (r"armed robbery|robbery.*(gun|armed|weapon|knife)|(gun|armed).*robbery", "a 216 armed robbery"),
    (r"\brobbery\b|\brobbed\b|robbing|mugg", "a 215 robbery"),
    (r"carjack", "a 216 armed robbery, vehicle taken"),
    (r"human trafficking|traffick", "a 211 human trafficking"),
    (r"kidnap|abduct|hostage", "a 210 kidnapping"),
    (r"assault with a deadly weapon|\badw\b|stab|slash", "a 207 assault with a deadly weapon"),
    (r"aggravated battery", "a 209 aggravated battery"),
    (r"\bbattery\b", "a 208 battery"),
    (r"sexual battery|\brape\b|molest", "a 219 sexual battery"),
    (r"caustic chemical|acid attack", "a 222 assault with caustic chemicals"),
    (r"\bassault\b|attacked|attacking", "a 206 assault"),
    (r"criminal threats?|threaten|\bthreat\b", "a 214 criminal threats"),
    (r"domestic violence|domestic dispute|domestic", "a 221 domestic violence"),
    (r"arson", "a 301 arson"),
    (r"burglar|break[- ]?in|broke? in|broke into|breaking in|breaking and entering|\bb ?& ?e\b", "a 302 burglary"),
    (r"grand theft auto|\bgta\b|stolen (car|vehicle)|vehicle theft", "a 306 grand theft auto"),
    (r"grand theft of a firearm|stolen (gun|firearm)", "a 307 grand theft of a firearm"),
    (r"grand theft", "a 304 grand theft"),
    (r"petty theft|shoplift|pickpocket", "a 305 petty theft"),
    (r"theft|stolen|stole|stealing|larceny", "a 304 grand theft"),
    (r"vandal|graffiti|property damage", "a 311 vandalism"),
    (r"trespass|prowler", "a 310 trespassing"),
    (r"brandish", "a 706 brandishing a deadly weapon"),
    (r"drive[- ]?by|shooting from (a )?vehicle|shots from a (car|vehicle)", "a 708 shooting from a motor vehicle"),
    (r"shots? fired|shooting|gun ?shot|\bgsw\b|discharg", "a 707, shots fired"),
    (r"reckless handling", "a 709 reckless handling of a firearm"),
    (r"\bdui\b|impaired driv|drunk driv|intoxicated driv", "a 430 impaired driver"),
    (r"reckless driv", "a 419 reckless driving"),
    (r"street rac|motor vehicle contest|drag rac", "a 432 street race"),
    (r"traffic (collision|accident)|car (crash|accident)|\btc\b|collision|hit and run|vehicle (crash|accident)", "a traffic collision"),
    (r"stalk", "a 505 stalking"),
    (r"prostitut|solicit", "a 503 prostitution"),
    (r"drug traffick|drug smuggl|narcotics? sale", "a 606 drug trafficking"),
    (r"drug|narcotic", "a narcotics violation"),
    (r"\briot\b|rioting", "a 106 incitement to riot"),
    (r"disturb|fight|brawl|loud|noise|\b415\b", "a 125 disturbing the peace"),
    (r"structure fire|building fire|\bfire\b|smoke|burning|explos", "a structure fire"),
    (r"overdose|\bod\b|unconscious|not breathing|cardiac|heart attack|injured|bleeding|medical|ambulance|\bems\b|collapse|seizure|choking", "a medical emergency"),
    (r"firearm|\bgun\b|weapon|\barmed\b|rifle|pistol", "a 701 firearm violation"),
    (r"suspicious|casing", "a suspicious person"),
    (r"pursuit|chasing|fleeing|foot bail|foot pursuit", "a suspect fleeing"),
    (r"officer needs|backup|back[- ]?up|\bpd\b|shots at police", "an officer needs assistance"),
]

_EMS_PHRASES = {"a medical emergency", "a structure fire"}

_NON_EMERGENCY = re.compile(
    r"landline|non[- ]?emergency|not an emergency|this is not urgent|routine transport|"
    r"information only|general inquiry|wrong number|test call|test 911|butt ?dial|"
    r"pocket ?dial|accidental(?:ly)? (?:call|dial)|didn'?t mean to (?:call|dial)|"
    r"sorry,? wrong|meant to (?:call|dial) someone else|false alarm|no emergency|"
    r"everything(?:'s| is) (?:fine|ok|okay|alright)|disregard|nevermind|never mind|\bnvm\b",
    re.I,
)

_EMERGENCY_HINT = re.compile(
    r"help|emergency|urgent|gun|weapon|knife|shot|shoot|fire|smoke|blood|bleed|dying|"
    r"dead|stab|robb|assault|attack|hostage|kidnap|overdose|unconscious|not breathing|"
    r"crash|collision|accident|break[- ]?in|broke? in|broke into|breaking in|burglar|"
    r"armed|threat|scream|rape|abduct|carjack|explos|drown|suspicious|pursuit|fleeing|"
    r"domestic|arson|vandal|trespass|theft|stole|stolen|steal|\brob\b|mugg|"
    r"disturb|fight|brawl|jumped|beat|beaten|chok|strangl|hit and run|"
    r"hurt|injur|wound|unresponsive|passed out|collaps|seizure|"
    r"officer|backup|back[- ]?up",
    re.I,
)

_CLOSINGS = itertools.cycle(
    [
        "Units responding, identify.",
        "Any unit to handle, identify.",
        "Units to handle, identify.",
        "Handling unit, identify.",
    ]
)


def _next_closing() -> str:
    return next(_CLOSINGS)


_RP_LEADS = itertools.cycle(
    [
        "Reporting party states",
        "RP reports",
        "The RP advises",
        "Per the reporting party,",
    ]
)


def _next_rp_lead() -> str:
    return next(_RP_LEADS)


def _clean_ocr(text: str) -> str:
    t = (text or "").strip()
    if not t:
        return t
    m = re.search(r"911\s*[:\-]?", t, re.I)
    if m and m.start() <= 14:
        t = "911: " + t[m.end():].strip()
    t = re.sub(r"^[^\w\[]+", "", t)
    t = re.sub(r"[|\]\[]+$", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _strip_911_prefix(t: str) -> str:
    return re.sub(r"^\s*911\s*[:\-]?\s*", "", t, flags=re.I).strip() or t


def _strip_phone(t: str) -> str:
    t = re.sub(r"\b(phone|number|caller)\b.*?(\d[\d\s\-]{5,}\d)", " ", t, flags=re.I)
    t = re.sub(r"\b\d[\d\s\-]{5,}\d\b", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _clean_location(loc: str | None) -> str | None:
    if not loc:
        return None
    loc = re.sub(r"[|\]\[]+", " ", loc)
    loc = loc.strip(" .,-\t")
    loc = re.sub(r"\s+", " ", loc)
    return loc or None


def _extract_location(t: str) -> str | None:
    m = (
        re.search(r"\bat\s+(.+)", t, re.I)
        or re.search(r"\bon\s+(.+)", t, re.I)
        or re.search(
            r"\b((?:between|near|outside|inside|behind|across from|in front of|"
            r"corner of)\s+.+)",
            t, re.I,
        )
    )
    if not m:
        return None
    loc = re.split(
        r"[,.;]| units?\b| respond| suspect| please| asap",
        m.group(1),
        maxsplit=1,
        flags=re.I,
    )[0]
    return _clean_location(loc)


def match_incident(text: str) -> str | None:
    low = (text or "").lower()
    for pat, phrase in _INCIDENTS:
        if re.search(pat, low):
            return phrase
    return None


def is_emergency(text: str) -> bool:
    low = (text or "").lower().strip()
    if not low:
        return False
    if _NON_EMERGENCY.search(low):
        return False
    if match_incident(low):
        return True
    if _EMERGENCY_HINT.search(low):
        return True
    return len(re.sub(r"[^a-z]", "", low)) >= 12


_HIGH_RISK = re.compile(
    r"murder|manslaughter|homicide|dead|shot|shoot|gun|firearm|weapon|armed|"
    r"stab|knife|robbery|carjack|kidnap|hostage|assault|battery|adw|rape|"
    r"sexual|arson|fire|explos|domestic|overdose|unconscious|not breathing|"
    r"bleeding|drive[- ]?by|shots fired|in progress|active|fleeing|pursuit|"
    r"brandish|hit and run|traffic collision|crash|trafficking|threat",
    re.I,
)


def _incident_last4(incident) -> str:
    digits = re.sub(r"\D", "", str(incident or ""))
    return digits[-4:] if digits else ""


_CODE3_TERMS = re.compile(
    r"\b("
    r"murder|homicide|manslaughter|dead body|dying|bleeding|bleed|blood|"
    r"shot|shots? fired|shooting|gun ?fire|gun|firearm|rifle|pistol|weapon|armed|"
    r"stab|stabbing|knife|slash|"
    r"robbery|carjack|"
    r"kidnap|abduct|hostage|held (?:at|against)|"
    r"rape|sexual assault|molest|"
    r"assault|attack|attacking|beaten|beating|jumped|mugg|"
    r"strangl|chok(?:e|ing)|"
    r"scream|screaming|yell(?:ing)? for help|crying for help|help me|save me|"
    r"fight|fighting|brawl|"
    r"domestic|"
    r"arson|fire|smoke|burning|explos|"
    r"overdose|\bod\b|unconscious|not breathing|no pulse|cardiac|heart attack|"
    r"seizure|collaps|drown|"
    r"suicid|jump(?:ing|er)?|"
    r"pursuit|fleeing|chasing|foot bail|"
    r"hit and run|drive[- ]?by|"
    r"threaten(?:ing)?(?: with| to (?:kill|shoot|stab|hurt))|brandish|"
    r"trapped|traffick"
    r")\b",
    re.I,
)

_IN_PROGRESS = re.compile(
    r"in progress|right now|happening|currently|still (?:here|there|going|inside|"
    r"outside|on scene|at it)|as we speak|won'?t stop|won'?t leave|about to|"
    r"just (?:got|started|happened|now)|can'?t breathe|need help now|hurry|"
    r"breaking in|trying to (?:get in|break|kill|hurt|attack)|coming (?:at|after)",
    re.I,
)

_COLD_REPORT = re.compile(
    r"already (?:gone|left|fled)|long gone|got away|left the (?:scene|area)|"
    r"a while ago|earlier (?:today|tonight)|last night|yesterday|this morning|"
    r"hours? ago|no longer (?:here|there)|nobody(?:'s| is)? hurt|"
    r"no one(?:'s| is)? hurt|no injuries|not urgent|non[- ]?emergency",
    re.I,
)

_CODE2_TERMS = re.compile(
    r"\b(theft|stolen|shoplift|petty|larceny|burglar(?:y|ized)|break[- ]?in|"
    r"vandal|graffiti|property damage|trespass|prowler|suspicious|loiter|"
    r"noise|loud|disturb(?:ance)?|parking|abandoned|found property|lost|welfare|"
    r"panhandl|solicit|littering|drunk in public|public intox)\b",
    re.I,
)


_MEDICAL_TERMS = re.compile(
    r"\b("
    r"hurt|injur(?:ed|y|ies)?|wound(?:ed)?|bleeding|bleed|blood|"
    r"unconscious|unresponsive|passed out|won'?t wake|not breathing|no pulse|"
    r"cardiac|heart attack|overdose|\bod\b|seizure|collaps(?:e|ed|ing)|"
    r"chok(?:e|ing)|stabbed|shot|\bgsw\b|dying|hit by (?:a )?(?:car|vehicle)|"
    r"needs? (?:an )?(?:ambulance|medic|paramedic)|someone(?:'s| is) down|"
    r"person down|man down|people (?:are )?(?:hurt|injured|down)"
    r")\b",
    re.I,
)

_NO_INJURY = re.compile(
    r"no ?one(?:'s| is)?\s+(?:hurt|injured|hit|down)|"
    r"nobody(?:'s| is)?\s+(?:hurt|injured|hit|down)|"
    r"not (?:hurt|injured|bleeding)|no injur|uninjured|"
    r"everyone(?:'s| is)? (?:ok|okay|fine|alright|safe)|"
    r"everybody(?:'s| is)? (?:ok|okay|fine|alright|safe)",
    re.I,
)


def _decide_code(text: str, incident_phrase: str | None) -> str:
    hay = f"{text or ''} {incident_phrase or ''}".lower()
    injured = bool(_MEDICAL_TERMS.search(hay)) and not _NO_INJURY.search(hay)
    life_threat = bool(_CODE3_TERMS.search(hay))
    active = bool(_IN_PROGRESS.search(hay))
    cold = bool(_COLD_REPORT.search(hay))
    property_only = (
        bool(_CODE2_TERMS.search(hay)) and not life_threat and not injured
    )

    if injured:
        return "Code 3"
    if life_threat and not cold:
        return "Code 3"
    if life_threat and cold:
        return "Code 2"
    if property_only and active:
        return "Code 3"
    if property_only:
        return "Code 2"
    if active:
        return "Code 3"
    return "Code 2"


_JUNK_LOCATION = re.compile(
    r"^\s*(i\s*told\s*ya|i\s*told\s*you|told\s*you|dunno|idk|i\s*don'?t\s*know|"
    r"not\s*sure|no\s*idea|unknown|n/?a|none|somewhere|ask|you\s*tell\s*me|"
    r"find\s*out|classified|secret)\s*[.!?]*\s*$",
    re.I,
)

_LOC_HINT = re.compile(
    r"\b(street|st|avenue|ave|boulevard|blvd|road|rd|drive|dr|lane|ln|way|court|"
    r"ct|place|pl|highway|hwy|freeway|fwy|alley|plaza|park|mall|store|shop|club|"
    r"bank|motel|hotel|station|hospital|apartment|apartments|block|near|corner|"
    r"intersection|between|across|and|&)\b",
    re.I,
)

_CAD_FALLBACK = (
    "the caller did not provide a location; use the computer-aided dispatch to "
    "trace it"
)

_PRIORITY = re.compile(
    r"shots fired|shooting|drive[- ]?by|707|708|officer|pursuit|fleeing|armed|"
    r"\bgun\b|firearm|weapon|hostage|kidnap|murder|homicide|robbery|carjack",
    re.I,
)


def _usable_location(loc: str | None) -> str | None:
    loc = _clean_location(loc)
    if not loc:
        return None
    if _JUNK_LOCATION.match(loc):
        return None
    letters = re.sub(r"[^a-z]", "", loc.lower())
    if len(letters) < 3:
        return None
    if _LOC_HINT.search(loc) or re.search(r"[A-Z][a-z]{2,}", loc):
        return loc
    return None


def _normalize_apostrophes(text: str) -> str:
    if not text:
        return text
    for ch in ("\u2019", "\u2018", "\u02bc", "\u00b4", "\u2032", "`"):
        text = text.replace(ch, "'")
    return text


_RP_PRONOUN_SUBS = [
    (r"\bi'm\b", "they're"),
    (r"\bi am\b", "they are"),
    (r"\bi've\b", "they've"),
    (r"\bi have\b", "they have"),
    (r"\bi'll\b", "they'll"),
    (r"\bi'd\b", "they'd"),
    (r"\bi\b", "they"),
    (r"\bmy\b", "their"),
    (r"\bmine\b", "theirs"),
    (r"\bmyself\b", "themselves"),
    (r"\bme\b", "them"),
    (r"\bwe're\b", "they're"),
    (r"\bwe are\b", "they are"),
    (r"\bwe've\b", "they've"),
    (r"\bwe\b", "they"),
    (r"\bour\b", "their"),
    (r"\bours\b", "theirs"),
    (r"\bus\b", "them"),
]


def _to_reporting_party(text: str) -> str:
    out = _normalize_apostrophes(text)
    for pat, repl in _RP_PRONOUN_SUBS:
        out = re.sub(pat, repl, out, flags=re.I)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def _summarize_situation(text: str) -> str:
    t = _strip_phone(_strip_911_prefix(_clean_ocr(text)))
    t = re.sub(r"^\s*(help[!,. ]*)+", "", t, flags=re.I)
    t = re.sub(r"\bi\s*need\s*help\b[!,. ]*", "", t, flags=re.I)
    t = re.sub(r"\s*-{2,}\s*", ", ", t)
    t = re.sub(r"!+", "", t)
    t = re.sub(r"^\s*(?:so|uh|um|like|okay|ok|yeah|well|please|oh|hi|hello)[,. ]+", "", t, flags=re.I)
    t = re.sub(r"^\s*(?:we|i|they)\s*(?:'ve|\s+have|\s+just)?\s*(?:got|get)\b", "there is", t, flags=re.I)
    t = re.sub(r"^\s*(?:we|i)\s+have\b", "there is", t, flags=re.I)
    t = re.sub(r"^\s*there(?:'s|\s+is|\s+are)\s+", "", t, flags=re.I)
    t = re.sub(r"\b(?:right|over)\s+here\b|\bhere\b", "", t, flags=re.I)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    t = re.sub(r"([,;])\s*(?=[,;])", "", t)
    t = re.sub(r"\s+", " ", t).strip(" .,-")
    out = _to_reporting_party(t)
    words = out.split()
    if len(words) > 24:
        out = " ".join(words[:24]).rstrip(" .,-")
    return out


_DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def _spell_digits(num) -> str:
    return " ".join(_DIGIT_WORDS.get(c, c) for c in re.sub(r"\D", "", str(num or "")))


def _incident_number(incident_phrase: str | None) -> str | None:
    if not incident_phrase:
        return None
    m = re.search(r"\b(\d{2,3})\b", incident_phrase)
    return m.group(1) if m else None


def _incident_label(incident_phrase: str | None) -> str:
    if not incident_phrase:
        return ""
    return re.sub(r"^(?:a|an)\s+", "", incident_phrase).strip()


def build_callout(
    situation_text: str,
    location: str | None = None,
    incident: str | None = None,
    tac: bool = False,
) -> str:
    t = _strip_phone(_clean_ocr(situation_text))
    if not t:
        return situation_text
    low = t.lower()

    incident_phrase = match_incident(low)
    loc = _usable_location(location) if location else None
    if not loc:
        loc = _extract_location(t)

    code = _decide_code(low, incident_phrase)
    code_str = "Code 3 emergency" if code == "Code 3" else code
    closing = _next_closing()
    narrative = _summarize_situation(t)
    last4 = _incident_last4(incident)
    sec = _incident_number(incident_phrase)
    label = _incident_label(incident_phrase)
    where = f"at {loc}, {loc}" if loc else None

    if sec:
        head = f"All units, {label} {where}." if where else f"All units, {label}. Be advised, {_CAD_FALLBACK}."
    elif incident_phrase:
        head = f"All units, we have {incident_phrase} {where}." if where else f"All units, we have {incident_phrase}. Be advised, {_CAD_FALLBACK}."
    else:
        head = f"All units, respond to {loc}, {loc}." if where else f"All units, be advised. {_CAD_FALLBACK.capitalize()}."

    parts = [head]
    if narrative:
        parts.append(f"{_next_rp_lead()} {narrative}.")
    if incident_phrase in _EMS_PHRASES:
        parts.append("Requesting a rescue ambulance.")
    if last4:
        parts.append(f"Incident {_spell_digits(last4)}.")
    parts.append(f"{code_str}.")
    if tac and code == "Code 3" and _PRIORITY.search(f"{low} {incident_phrase or ''}"):
        parts.append("Refer to TAC-1.")
    parts.append(closing)
    return " ".join(p for p in parts if p).strip()


def lapd_callout(text: str) -> str:
    return build_callout(text, None, None)


_LAPD_PHONETIC_RULE = (
    "PHONETIC ALPHABET - CRITICAL: use the LAPD / APCO police alphabet ONLY, "
    "NEVER the NATO / military one. The letters are: A Adam, B Boy, C Charles, "
    "D David, E Edward, F Frank, G George, H Henry, I Ida, J John, K King, "
    "L Lincoln, M Mary, N Nora, O Ocean, P Paul, Q Queen, R Robert, S Sam, "
    "T Tom, U Union, V Victor, W William, X X-ray, Y Young, Z Zebra. NEVER say "
    "Alpha, Bravo, Charlie, Delta, Foxtrot, Tango, Uniform, Lima, Whiskey, or "
    "any other NATO word. Spell call signs and plates this way and read digits "
    "plainly: call sign 25T15 is 'twenty-five Tom fifteen'; plate ULX103 is "
    "'Union Lincoln X-ray, one zero three'."
)


_MDC_PROMPT = (
    "You are an LAPD radio dispatcher (RTO) on a GTA World roleplay server. A "
    "field unit has asked you to run a name (code ten / wants check) or a "
    "vehicle plate through the MDC, and you are given the STRUCTURED RESULT of "
    "that lookup. Read it back over the air as ONE short, natural, professional "
    "radio transmission - the way a real dispatcher relays a return to a unit.\n"
    "\n"
    "RULES:\n"
    "- Address the requesting unit by call sign if provided, e.g. 'Copy, "
    "twenty-five Tom fifteen, ...'. Spell call signs phonetically.\n"
    "- The unit already told you the name or plate, so DO NOT parrot it back as "
    "if it were news (never say 'that comes back to <the exact name they gave>'). "
    "Lead with the FINDINGS.\n"
    "- For a NAME return: lead with wants/warrants status ('no wants, no "
    "warrants' when clear, or 'WANTED, active warrants' on a hit), then read "
    "EVERY caution flag in the result (do not stop at one), then a one-line "
    "arrest history (e.g. 'two felonies, one misdemeanor' or 'no prior "
    "arrests'). Advise caution on any warrant or caution flag.\n"
    "- For a PLATE return, state the vehicle (year, color, make, model), the "
    "registered owner, any stolen flag, and its registration and INSURANCE "
    "status (e.g. 'insurance valid' / 'uninsured'). If the plate is flagged "
    "stolen, say so first and advise caution.\n"
    "- If the unit has ALREADY been acknowledged (told to stand by), do NOT "
    "begin with 'Copy' or another acknowledgment - lead directly with the call "
    "sign and the findings.\n"
    "- 'Clear' / 'comes back clear' means a record was FOUND with no wants or "
    "warrants. If NO record was found at all, say 'no record on file' - do NOT "
    "also say 'clear'.\n"
    "- Use ONLY the details in the provided result. NEVER invent names, "
    "warrants, vehicles, arrests, or flags that aren't in the data.\n"
    "- Do NOT read the person's age, fingerprints, DNA, phones, residences, or "
    "purchase history. AGE is NOT criminal points.\n"
    "\n" + _LAPD_PHONETIC_RULE +
    "\n- Keep it to one or two terse sentences. Do NOT assign a penal code and "
    "do NOT add a closing like 'units respond'."
)


_MDC_PAGE_PROMPT = (
    "You are an LAPD radio dispatcher (RTO) on a GTA World roleplay server. A "
    "field unit asked you to run a name (code ten / wants check) or a vehicle "
    "plate through the Web MDC. You are given the RAW VISIBLE TEXT of the "
    "logged-in MDC record page. Your job is to READ that page like a dispatcher "
    "looking at the screen, find the facts that matter, and read them back over "
    "the air as ONE short, natural, professional radio transmission.\n"
    "\n"
    "WHAT TO LOOK FOR:\n"
    "- NAME lookups: the person's full name, whether they are WANTED / have "
    "active warrants, EVERY caution code or flag listed (armed, dangerous, "
    "mental health, gang affiliate, sex offender, etc. - read them ALL, not "
    "just the first), and their arrest / criminal history (how many felonies "
    "vs misdemeanors, or whether they have never been arrested).\n"
    "- PLATE lookups: the vehicle year/color/make/model, the registered owner, "
    "whether it is flagged STOLEN, and the registration/insurance status.\n"
    "\n"
    "RULES:\n"
    "- Address the requesting unit by call sign if given, spelled phonetically "
    "(e.g. 'Copy, twenty-five Tom fifteen, ...').\n"
    "- Lead with the most safety-critical fact: if the subject is wanted or "
    "flagged, or the vehicle is stolen, say so first and advise caution.\n"
    "- If the page shows no matching record (or is an empty/search page), say "
    "the return comes back clear / no record on file.\n"
    "- Use ONLY facts visible on the page. NEVER invent warrants, names, "
    "vehicles, or flags. Ignore site navigation, menus, buttons, and unrelated "
    "chrome.\n"
    "\n"
    "KEEP IT FOCUSED - a real want/warrant return is terse. Give the officer: "
    "the wants/warrants status, ALL caution flags, and a one-line arrest history "
    "(felonies vs misdemeanors). Do NOT read fingerprint or DNA sample status, "
    "phone numbers, residences, businesses, firearms purchase history, related "
    "incidents, or the person's AGE.\n"
    "- The unit already gave you the name/plate: do NOT restate it as if it were "
    "a finding (never 'that comes back to <the same name>'). Lead with the "
    "results.\n"
    "- Players often SPELL the name out for immersion (e.g. 'Connor Myer, "
    "C-O-N-N-O-R M-Y-E-R'). IGNORE the letter-by-letter spelling; it is the same "
    "name.\n"
    "- 'Clear' means a record was FOUND with no wants/warrants. If there is NO "
    "matching record at all, say 'no record on file' and do NOT also say "
    "'clear'.\n"
    "DO NOT CONFUSE FIELDS: the subject's AGE is NOT criminal points. Only "
    "mention criminal points if the page has a field explicitly labeled "
    "'Criminal Points'. For a registered vehicle, read only the short LICENSE "
    "PLATE / tag (for example 'LZE150') - NEVER read the long VIN / vehicle "
    "identification number (a long 8-plus character code).\n"
    "\n" + _LAPD_PHONETIC_RULE +
    "\n- Keep it to one or two terse sentences. Do NOT assign a penal code and "
    "do NOT add a closing like 'units respond'."
)


def _phon_cs(callsign) -> str:
    try:
        return phonetic_callsign(callsign) if callsign else ""
    except Exception:
        return str(callsign or "")


def _build_name_phrase(lead: str, r: dict) -> str:
    name = r.get("name") or r.get("target") or "the subject"
    cc = [c for c in (r.get("caution_codes") or []) if c]
    wi = [w for w in (r.get("warrant_items") or []) if w]
    parts: list[str] = []
    if r.get("wanted") or r.get("has_warrants") is True:
        if wi:
            parts.append(f"{name} is WANTED, active warrants: " + ", ".join(wi))
        else:
            parts.append(f"{name} is showing active wants and warrants")
    elif r.get("has_warrants") is False:
        parts.append(f"{name}, no wants, no warrants")
    else:
        parts.append(f"{name}, record on file")
    if cc:
        parts.append("caution flags: " + ", ".join(cc))
    fel = int(r.get("felony_count") or 0)
    mis = int(r.get("misdemeanor_count") or 0)
    if fel or mis:
        bits = []
        if fel:
            bits.append(f"{fel} felon{'y' if fel == 1 else 'ies'}")
        if mis:
            bits.append(f"{mis} misdemeanor{'' if mis == 1 else 's'}")
        parts.append("prior arrests: " + ", ".join(bits))
    elif r.get("has_arrests") is False:
        parts.append("no prior arrests")
    cp = r.get("criminal_points")
    if cp and re.fullmatch(r"[0-9,]+", str(cp).strip()):
        parts.append(f"{cp} criminal points")
    caution = bool(cc) or bool(r.get("wanted")) or r.get("has_warrants") is True
    tail = ", use caution" if caution else ""
    return lead + "; ".join(parts) + tail + "."


def _build_plate_phrase(lead: str, r: dict) -> str:
    plate = r.get("plate") or r.get("target")
    veh_bits = " ".join(
        str(x) for x in [r.get("year"), r.get("color"), r.get("make"), r.get("model")] if x
    ).strip()
    if not veh_bits:
        veh_bits = r.get("vehicle") or "a vehicle"
    plate_spoken = _spell_plate_token(str(plate)) if plate else ""
    plate_str = f"plate {plate_spoken}, " if plate_spoken else ""
    parts = [f"{plate_str}that returns to {veh_bits}".strip()]
    if r.get("owner"):
        parts.append(f"registered to {r.get('owner')}")
    if r.get("stolen") is True:
        parts.insert(0, "be advised, that plate is flagged STOLEN, use caution")
    elif r.get("stolen") is False:
        parts.append("no flags")
    ins = r.get("insurance_status") or r.get("registration_status")
    if r.get("expired") is True:
        parts.append("insurance expired")
    elif r.get("expired") is False:
        parts.append("insurance valid")
    elif ins:
        parts.append(f"insurance {str(ins).lower()}")
    return lead + ", ".join(parts) + "."


def build_mdc_response(result: dict, callsign=None, acknowledged=False) -> str:
    result = result or {}
    cs = _phon_cs(callsign)
    if acknowledged:
        lead = f"{cs}, " if cs else ""
    else:
        lead = f"Copy, {cs}, " if cs else "Copy, "
    lookup = result.get("lookup")
    if not result.get("found"):
        if lookup == "plate":
            tgt = result.get("target")
            spoken = _spell_plate_token(str(tgt)) if tgt else "that plate"
            return f"{lead}no record on file for plate {spoken}, negative return."
        tgt = result.get("target") or "that name"
        return f"{lead}no record on file for {tgt}, negative return."
    if lookup == "plate":
        return _build_plate_phrase(lead, result)
    return _build_name_phrase(lead, result)


_DEFAULT_LAPD_PROMPT = (
    "You are a veteran LAPD radio dispatcher (RTO) for a GTA World roleplay "
    "server, working the San Andreas Penal Code. You receive either a 911 call "
    "(caller report or MDC call card) or a unit's radio transmission, and you "
    "produce ONE realistic dispatch broadcast to be read aloud over the air.\n"
    "\n"
    "CORE RULE - DO NOT PARROT: Never repeat the caller's words verbatim. "
    "Interpret what is actually happening and RE-STATE it the way a professional "
    "dispatcher relays it to officers: concise, third person, calm, informative. "
    "Turn a panicked account into a clear picture of the crime or emergency. "
    "Example: caller 'People are fighting in an alley and someone pulled a knife!' "
    "-> 'All units, a 207 assault with a deadly weapon in progress, subjects "
    "fighting in an alley, one armed with a knife.'\n"
    "\n"
    "FORMAT (911 calls): Open with 'All units'. State the crime by its San Andreas "
    "Penal Code section number and name, spoken as a BARE number - do NOT say the "
    "words 'penal code' out loud (say 'a 302 burglary', never 'penal code 302' or "
    "'penal code three zero two'; say 'a 459 in progress', never 'penal code 459'). "
    "Section numbers you may use (202 murder, 205 manslaughter, "
    "206 assault, 207 assault with a deadly weapon, 208 battery, 209 aggravated "
    "battery, 210 kidnapping, 214 criminal threats, 215 robbery, 216 armed "
    "robbery, 219 sexual battery, 221 domestic violence, 301 arson, 302 burglary, "
    "304 grand theft, 305 petty theft, 306 grand theft auto, 310 trespassing, 311 "
    "vandalism, 419 reckless driving, 430 impaired driver, 503 prostitution, 505 "
    "stalking, 606 drug trafficking, 706 brandishing, 707 shots fired, 708 "
    "shooting from a vehicle). For medical or fire, say 'a medical emergency' or "
    "'a structure fire' and request a rescue ambulance. Give the location; if none "
    "is usable, say 'refer to CAD for location'. State the incident by its last "
    "four digits only, calling it the 'incident' (never 'Call ID'). Add a one-line "
    "third-person summary of what the reporting party states. End with a closing "
    "such as 'Units responding, identify.' or 'Any unit to handle, identify.'\n"
    "\n"
    "RESPONSE CODE - CRITICAL, JUDGE THE SEVERITY:\n"
    "- Code 3 (lights and sirens, emergency) for ANY threat to life or violent "
    "crime in progress: shooting or shots fired, weapons, robbery, assault or "
    "battery in progress, domestic violence, someone screaming or crying for "
    "help, a person being attacked/beaten/chased/choked, kidnapping, hostage, "
    "rape or sexual assault, arson or fire, a person down, not breathing, "
    "unconscious, overdose, cardiac, drowning, a suicide in progress, or anything "
    "the caller says is happening right now / in progress.\n"
    "- Code 2 (routine, no lights or sirens) for cold or non-violent reports: a "
    "theft or burglary that already happened, vandalism, a suspect who already "
    "left, noise complaints, suspicious circumstances, trespassing, welfare "
    "checks, minor property crime.\n"
    "- A woman screaming for help in an alley is Code 3, NOT Code 2. When you are "
    "unsure and a life may be at risk, choose Code 3.\n"
    "\n"
    "FORMAT (unit radio traffic, NOT a 911 call): Do NOT assign a penal code. "
    "Acknowledge the unit by call sign and respond as Control. If a unit goes code "
    "six, reply 'Control copies, <unit>, code six at <location>' - or use 'refer "
    "to CAD for location' if none was given. BACKUP vs ADDITIONAL UNIT is a "
    "priority distinction: if a unit requests BACKUP (or says they need "
    "help/assistance), that officer needs help now - treat it as an urgent Code "
    "3 and put out an all-units call, e.g. 'All units, <unit> is requesting "
    "backup at <location>, Code 3, respond emergency and identify.' If a unit "
    "only requests an ADDITIONAL UNIT, it is a routine Code 2, e.g. 'Control "
    "copies, <unit> requesting an additional unit, Code 2, any available unit to "
    "handle and identify.' For an officer in distress or shots fired, put out an "
    "all-units emergency and refer responders to TAC-1.\n"
    "\n"
    "NUMBERS: write every number as separate spoken digits (911 -> 'nine one "
    "one', incident 0907 -> 'incident nine oh seven'); spell unit call signs "
    "phonetically (25T15 -> 'twenty-five Tom fifteen').\n"
    "\n"
    "NEVER read the caller's name or phone number. Use ONLY details present in the "
    "input; never invent suspect descriptions, names, vehicles, or specifics. Keep "
    "it to 1-3 short, terse, professional sentences."
)


_STYLE_ADDENDUM = (
    "REALISM AND CADENCE (always apply):\n"
    "- Speak like a real LAPD Radio Telephone Operator: calm, clipped, and "
    "economical. No filler, no drama, and never narrate your own actions.\n"
    "- Say the location the way LAPD does, repeating it once for clarity, for "
    "example: 'at Hawick and Spanish, Hawick and Spanish.' Repeat a unit's call "
    "sign the same way when you direct a specific unit.\n"
    "- Refer to the caller as 'the RP' or 'reporting party'. If more than one "
    "person is calling it in, say 'multiple RPs reporting'. Never read names or "
    "phone numbers.\n"
    "- Use natural dispatcher connectors: 'we have', 'reference', 'be advised', "
    "'RP states', 'suspect', 'possibly', and 'handle the call'.\n"
    "- Read vehicle plates and index numbers using the phonetic alphabet for the "
    "letters and plain digits for the numbers, for example 'index GJS 895' "
    "becomes 'index George John Sam, eight nine five'.\n"
    "- Give a full but tight picture in two to three sentences: crime and its code "
    "number said as a bare number (never the words 'penal code'), what is happening, "
    "location, key details, incident (last four digits "
    "only), the response code, then the closing.\n"
    "\n"
    "SEVERITY - THIS IS CRITICAL:\n"
    "- If ANYONE is hurt, injured, bleeding, unconscious, down, not breathing, "
    "or needs medical aid, it is CODE 3 - even if the suspect has already fled "
    "or left the scene. A person needing help is an active emergency.\n"
    "- Code 3 (Priority One, lights and sirens) also covers any weapon, a "
    "violent crime in progress, shots fired, robbery, assault or battery, "
    "domestic violence, kidnapping, or anything happening right now.\n"
    "- Code 2 (high priority, NO lights or sirens) is only for cold, non-violent "
    "reports where no one is hurt: a theft or burglary that already happened, "
    "vandalism, a suspect long gone, suspicious circumstances, welfare checks.\n"
    "- When a call has BOTH a fled suspect AND an injured person, it is CODE 3.\n"
    "- If you are ever unsure and a life may be at risk, choose Code 3.\n"
    "\n" + _LAPD_PHONETIC_RULE
)


_VERIFY_PROMPT = (
    "You screen text captured from a Grand Theft Auto roleplay game screen via OCR. "
    "Decide whether it is a genuine emergency a police dispatcher should broadcast: "
    "an actual 911/emergency call, or a police unit's radio transmission (code six, "
    "shots fired, pursuit, requesting backup, etc.). "
    "It is NOT genuine if it is on-screen interface text, advertisements, server "
    "banners, message-of-the-day, menus, property or business posters, or ordinary "
    "chatter that merely mentions such words. Reply with exactly one word: YES or NO."
)


class LLMProcessor:
    VERIFY_TYPES = {"call", "chat", "radio"}

    def __init__(self, cfg: dict):
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", True))
        self.provider = cfg.get("provider", "openai_compatible")
        self.base_url = str(cfg.get("base_url", "https://api.openai.com/v1")).rstrip("/")
        self.model = cfg.get("model", "gpt-4o")
        self.api_key = cfg.get("api_key") or os.getenv("OPENAI_API_KEY", "")
        base_prompt = cfg.get("system_prompt") or _DEFAULT_LAPD_PROMPT
        self.system_prompt = base_prompt.rstrip() + "\n\n" + _STYLE_ADDENDUM
        self.timeout = int(cfg.get("timeout", 20))
        self.max_tokens = int(cfg.get("max_tokens") or 400)
        self.reasoning_effort = str(cfg.get("reasoning_effort", "low") or "low").lower()
        self.emergency_only = bool(cfg.get("emergency_only", True))
        self.tac_referral = bool(cfg.get("tac_referral", True))
        self.verify_flags = bool(cfg.get("verify_flags", False))
        self._verify_cache: dict = {}

    @staticmethod
    def _format_call_input(incident: str | None, situation: str, location: str | None) -> str:
        lines = []
        if incident:
            lines.append(f"Incident (last four digits): {incident}")
        lines.append(f"Situation: {_strip_phone(situation)}")
        if location:
            lines.append(f"Location: {location}")
        return "\n".join(lines)

    def _skip_non_emergency(self, text: str) -> bool:
        return self.emergency_only and not is_emergency(text)

    def process(self, flag) -> str:
        if isinstance(flag, dict) and flag.get("type") == "panic":
            return build_panic_dispatch(
                flag.get("name"), flag.get("location"), flag.get("callsign")
            )
        if isinstance(flag, dict) and flag.get("type") == "cad":
            return build_cad_ack(flag.get("callsign"), flag.get("what"))
        if isinstance(flag, dict) and flag.get("type") == "code6":
            return build_code_six_ack(
                flag.get("callsign"), flag.get("location"), flag.get("details")
            )
        if isinstance(flag, dict) and flag.get("type") == "clear":
            if flag.get("start_of_watch"):
                return build_watch_start_ack(flag.get("callsign"))
            return build_clear_ack(flag.get("callsign"))
        if isinstance(flag, dict) and flag.get("type") == "code7":
            return build_code_seven_ack(flag.get("callsign"), flag.get("location"))
        if isinstance(flag, dict) and flag.get("type") == "radio":
            body = flag.get("body", "")
            offline = build_radio_dispatch(body, flag.get("callsign"))
            if self.enabled and self.api_key:
                out = self._api_rewrite(
                    "Unit radio transmission on the base channel. This is NOT a "
                    "911 call: acknowledge it as the dispatcher and do NOT assign "
                    "a penal code.\n" + body
                )
                if out:
                    return out
            return offline

        if isinstance(flag, dict) and flag.get("type") == "call":
            situation = flag.get("situation", "")
            location = flag.get("location")
            incident = flag.get("incident")
            if self._skip_non_emergency(situation):
                return ""
            offline = build_callout(situation, location, incident, tac=self.tac_referral)
            if self.enabled and self.api_key:
                user = self._format_call_input(incident, situation, location)
                out = self._api_rewrite(user)
                if out:
                    return out
            return offline if self.enabled else _strip_phone(situation)

        body = flag.get("body") if isinstance(flag, dict) else str(flag)
        cleaned = _clean_ocr(body)
        if not cleaned.strip():
            return ""
        if self._skip_non_emergency(cleaned):
            return ""
        offline = build_callout(cleaned, None, None, tac=self.tac_referral)
        if self.enabled and self.api_key:
            out = self._api_rewrite(cleaned)
            if out:
                return out
        return offline if self.enabled else body

    @staticmethod
    def _format_mdc_input(result: dict, callsign=None, acknowledged=False) -> str:
        result = result or {}
        lines = []
        if callsign:
            lines.append(f"Requesting unit call sign: {callsign}")
        lines.append(f"Lookup type: {result.get('lookup', 'name')}")
        lines.append(f"Query target: {result.get('target', '')}")
        lines.append(f"Record found: {'yes' if result.get('found') else 'no'}")
        for key in (
            "name", "has_warrants", "warrants_text", "warrant_items",
            "caution_codes", "criminal_points", "aliases",
            "vehicles", "license", "plate", "owner", "year", "color", "make",
            "model", "vehicle", "vehicle_class", "stolen",
            "registration_status", "insurance_status", "expired",
            "arrests", "felony_count", "misdemeanor_count", "has_arrests",
        ):
            val = result.get(key)
            if val in (None, "", [], {}):
                continue
            lines.append(f"{key}: {val}")
        if acknowledged:
            lines.append(
                "NOTE: The unit has ALREADY been acknowledged (told to stand by). "
                "Do NOT begin with 'Copy' or another acknowledgment; lead "
                "directly with the call sign and the findings."
            )
        return "\n".join(lines)

    def mdc_response(self, result: dict, callsign=None, acknowledged=False) -> str:
        offline = build_mdc_response(result, callsign, acknowledged=acknowledged)
        if self.enabled and self.api_key:
            out = self._api_rewrite_prompt(
                self._format_mdc_input(result, callsign, acknowledged=acknowledged), _MDC_PROMPT
            )
            if out:
                return out
        return offline

    def has_api(self) -> bool:
        return bool(self.enabled and self.api_key)

    def mdc_response_from_page(
        self, page_text: str, lookup: str, target: str, callsign=None, acknowledged=False
    ) -> str | None:
        if not self.has_api():
            return None
        page_text = (page_text or "").strip()
        if not page_text:
            return None
        if len(page_text) > 6000:
            page_text = page_text[:6000]
        header = []
        if callsign:
            header.append(f"Requesting unit call sign: {callsign}")
        header.append(f"Lookup type: {lookup or 'name'}")
        header.append(f"Query target: {target or ''}")
        header.append(
            "Below is the visible text of the GTA World Web MDC record page for "
            "this query. Read it, pull only the facts that matter for a radio "
            "return, and IGNORE navigation, menus, buttons, and unrelated text."
        )
        if acknowledged:
            header.append(
                "NOTE: The unit has ALREADY been acknowledged and told to stand "
                "by. Do NOT begin with 'Copy' or another acknowledgment; lead "
                "directly with the call sign and the findings."
            )
        user = "\n".join(header) + "\n\n--- MDC PAGE TEXT ---\n" + page_text
        return self._api_rewrite_prompt(user, _MDC_PAGE_PROMPT)

    # Substrings that identify a reasoning model whose completion budget must
    _REASONING_HINTS = (
        "gpt-oss", "o1", "o3", "o4", "deepseek-r", "-r1", "qwq", "reasoning", "magistral",
    )

    def _is_reasoning_model(self) -> bool:
        m = str(self.model or "").lower()
        return any(h in m for h in self._REASONING_HINTS)

    @staticmethod
    def _strip_think(text: str) -> str:
        if not text:
            return text
        text = re.sub(r"(?is)<think>.*?</think>", "", text)
        text = re.sub(r"(?is)^\s*<think>.*$", "", text)
        return text.strip()

    def _post_chat(self, messages: list, temperature: float, max_tokens: int) -> str | None:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self._is_reasoning_model():
            budget = max(int(max_tokens or 0), 1536)
            payload.pop("max_tokens", None)
            payload["max_completion_tokens"] = budget
            payload["reasoning_effort"] = self.reasoning_effort
        resp = requests.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        msg = resp.json()["choices"][0]["message"]
        out = (msg.get("content") or "").strip()
        return self._strip_think(out) or None

    def _api_rewrite_prompt(self, text: str, system_prompt: str) -> str | None:
        try:
            return self._post_chat(
                [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.4,
                max_tokens=self.max_tokens,
            )
        except Exception as e:
            print(f"[llm] MDC API failed, using offline generator ({e})")
            return None

    def _api_rewrite(self, text: str) -> str | None:
        try:
            return self._post_chat(
                [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.4,
                max_tokens=self.max_tokens,
            )
        except Exception as e:
            print(f"[llm] API failed, using offline LAPD generator ({e})")
            return None

    def verify_flag(self, flag) -> bool:
        if not isinstance(flag, dict):
            return True
        if not (self.enabled and self.api_key and self.verify_flags):
            return True
        if flag.get("type") not in self.VERIFY_TYPES:
            return True
        if flag.get("type") == "call":
            parts = [flag.get("situation") or "", flag.get("location") or ""]
            text = " -- ".join(p for p in parts if p)
        else:
            text = flag.get("body") or flag.get("raw") or ""
        text = text.strip()
        if not text:
            return True
        if text in self._verify_cache:
            return self._verify_cache[text]
        verdict = self._api_yes_no(text)
        result = True if verdict is None else verdict
        if len(self._verify_cache) > 256:
            self._verify_cache.clear()
        self._verify_cache[text] = result
        return result

    def _api_yes_no(self, text: str) -> bool | None:
        try:
            out = (self._post_chat(
                [
                    {"role": "system", "content": _VERIFY_PROMPT},
                    {"role": "user", "content": text},
                ],
                temperature=0,
                max_tokens=3,
            ) or "").strip().lower()
            if out.startswith("y"):
                return True
            if out.startswith("n"):
                return False
            return None
        except Exception as e:
            print(f"[llm] verify failed, allowing flag ({e})")
            return None


_PHONETIC = {
    "a": "Adam", "b": "Boy", "c": "Charles", "d": "David", "e": "Edward",
    "f": "Frank", "g": "George", "h": "Henry", "i": "Ida", "j": "John",
    "k": "King", "l": "Lincoln", "m": "Mary", "n": "Nora", "o": "Ocean",
    "p": "Paul", "q": "Queen", "r": "Robert", "s": "Sam", "t": "Tom",
    "u": "Union", "v": "Victor", "w": "William", "x": "X-ray", "y": "Young",
    "z": "Zebra",
}


_PLATE_KEYWORD_RE = re.compile(
    r"(?i)\b(index|plate|plates|registration|reg|tag|licen[cs]e(?:\s+plate)?)\b"
    r"(\s*(?:number|no\.?|#)?\s*[:\-]?\s+)"
    r"([A-Za-z]{1,4}\s?\d{1,4}|\d{1,4}\s?[A-Za-z]{1,4}|[A-Za-z0-9]{4,8})"
)


def _spell_plate_token(token: str) -> str:
    parts: list[str] = []
    digits = ""
    for ch in token:
        if ch.isalpha():
            if digits:
                parts.append(digits)
                digits = ""
            parts.append(_PHONETIC.get(ch.lower(), ch.upper()))
        elif ch.isdigit():
            digits += ch
        else:
            if digits:
                parts.append(digits)
                digits = ""
    if digits:
        parts.append(digits)
    return " ".join(parts)


def spell_plates(text: str) -> str:
    if not text:
        return text

    def _repl(m: "re.Match") -> str:
        token = m.group(3)
        if not any(c.isdigit() for c in token):
            return m.group(0)
        return f"{m.group(1)}{m.group(2)}{_spell_plate_token(token)}"

    try:
        return _PLATE_KEYWORD_RE.sub(_repl, text)
    except Exception:
        return text


_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = [
    "", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
    "eighty", "ninety",
]


def _number_to_words(num: int) -> str:
    n = int(num)
    if n < 20:
        return _ONES[n]
    if n < 100:
        tens, ones = divmod(n, 10)
        return _TENS[tens] + ("-" + _ONES[ones] if ones else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        if rest == 0:
            return _ONES[hundreds] + " hundred"
        return _ONES[hundreds] + " " + _number_to_words(rest)
    return " ".join(_ONES[int(d)] for d in str(n))


def phonetic_callsign(callsign: str) -> str:
    tokens = re.findall(r"\d+|[A-Za-z]", str(callsign).strip())
    out: list[str] = []
    for tok in tokens:
        if tok.isdigit():
            out.append(_number_to_words(int(tok)))
        else:
            out.append(_PHONETIC.get(tok.lower(), tok.upper()))
    return " ".join(out)


_AREA_STOP = {
    "the", "and", "of", "st", "street", "ave", "avenue", "blvd", "boulevard",
    "dr", "drive", "rd", "road", "ln", "lane", "way", "ct", "court", "pl",
    "place", "hwy", "highway", "los", "santos", "san", "county", "city",
    "north", "south", "east", "west", "near", "block", "intersection",
}


def _area_tokens(text: str) -> list[str]:
    text = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower())
    return [t for t in text.split() if len(t) >= 4 and t not in _AREA_STOP]


def area_match(call_location: str | None, current_area: str | None) -> bool:
    if not call_location or not current_area:
        return False
    cur = re.sub(r"[^a-z0-9 ]+", " ", current_area.lower())
    toks = _area_tokens(call_location)
    if not toks:
        return False
    return any(t in cur for t in toks)


_OFFICER_DISTRESS = re.compile(
    r"shots fired|officer (?:down|needs help|needs assistance|in distress|in trouble)|"
    r"man down|11[- ]?99|\b998\b|\b999\b",
    re.I,
)
_PURSUIT_RE = re.compile(r"in pursuit|foot pursuit|vehicle pursuit|chasing|fleeing", re.I)
_CODE6_RE = re.compile(r"code\s*six|code\s*6", re.I)
_BACKUP_RE = re.compile(
    r"backup|back[- ]?up|need(?:s|ing)?\s+(?:immediate\s+)?(?:help|assistance)|"
    r"requesting\s+(?:immediate\s+)?assistance|expedite|step it up|\burgent\b|"
    r"emergency assistance|roll\s+(?:me|us|a|an)|send\s+(?:me|us|a|an)|"
    r"code\s*3\s*(?:back|assist|respon)",
    re.I,
)
_ADDITIONAL_RE = re.compile(
    r"additional unit|additional units|an additional|another unit|one more unit|"
    r"extra unit|second unit|\badditional\b|air ?unit|air ?ship|supervisor",
    re.I,
)


def _bare_radio_location(raw: str) -> str | None:
    try:
        from modules.flagger import _KNOWN_AREAS, _NOT_A_PLACE, _STREET_SUFFIX_RE
    except Exception:
        return None
    for chunk in re.split(r"[,.;!?]", raw or ""):
        chunk = chunk.strip(" .;:-!?")
        low = chunk.lower()
        if not chunk or low in _NOT_A_PLACE:
            continue
        # only strong signals here: a street type or a known area. A loose
        # word-shape guess would read "shots fired" back as a location.
        if _STREET_SUFFIX_RE.search(low) or low in _KNOWN_AREAS:
            return chunk
    return None


def radio_location(raw: str) -> str | None:
    loc = _usable_location(_extract_location(raw)) or _bare_radio_location(raw)
    if not loc:
        return None
    loc = loc.strip(" \t!?.,;:-")
    return loc or None


def build_radio_dispatch(text: str, callsign: str | None = None) -> str:
    raw = _clean_ocr(text)
    low = raw.lower()
    unit = phonetic_callsign(callsign) if callsign else ""
    unit_str = f"{unit}, " if unit else ""
    loc = radio_location(raw)
    loc_str = f" at {loc}" if loc else ""
    loc_or_cad = f" at {loc}" if loc else ", refer to CAD for location"

    if _OFFICER_DISTRESS.search(low):
        who = unit or "a unit"
        where = f" at {loc}" if loc else ", refer to CAD for location"
        if re.search(r"shots fired", low):
            return (
                f"All units, all units. Shots fired, shots fired. {who}"
                f"{where}. All units in the vicinity, respond Code 3. "
                f"Additional units and an air unit refer to TAC-1. "
                f"Units responding, identify."
            )
        return (
            f"All units, all units. Officer in distress, {who}{where}. "
            f"All available units respond Code 3. Refer to TAC-1. "
            f"Units responding, identify."
        )
    if _PURSUIT_RE.search(low):
        return (
            f"All units, {unit_str}in pursuit{loc_str}. Clear the channel, this is "
            f"now a priority. Air unit and additional ground units refer to TAC-1. "
            f"Units to assist, identify."
        )
    if _CODE6_RE.search(low):
        base = f"Control copies, {unit_str}code six{loc_or_cad}."
        if _BACKUP_RE.search(low):
            who = unit or "the unit"
            return (
                f"{base} All units, {who} needs backup - Code 3, respond "
                f"emergency and identify."
            )
        if _ADDITIONAL_RE.search(low):
            who = unit or "the unit"
            return (
                f"{base} Additional unit requested for {who}, Code 2. Any "
                f"available unit to handle and identify."
            )
        return base
    if _BACKUP_RE.search(low):
        who = unit or "a unit"
        return (
            f"All units, {who} is requesting backup{loc_or_cad}. Code 3, "
            f"respond emergency and identify."
        )
    if _ADDITIONAL_RE.search(low):
        if unit:
            return (
                f"Control copies, {unit} requesting an additional unit{loc_or_cad}, "
                f"Code 2. Any available unit to handle and identify."
            )
        return (
            f"Dispatch, an additional unit is requested{loc_or_cad}, "
            f"Code 2. Any available unit to handle and identify."
        )
    summary = _summarize_situation(raw)
    return f"Control copies, {unit_str}{summary}{loc_str}. Units to assist, identify."


def build_panic_dispatch(
    name: str | None = None,
    location: str | None = None,
    callsign: str | None = None,
) -> str:
    who = (name or "").strip()
    unit = phonetic_callsign(callsign) if callsign else ""
    if who:
        ident = f"Officer {who}"
        if unit:
            ident = f"{ident}, {unit},"
    elif unit:
        ident = unit
    else:
        ident = "an officer"
    loc = _usable_location(location) if location else None
    loc_str = f" at {loc}" if loc else ""
    return (
        f"All units, all units. {ident} is in distress and requires immediate "
        f"response{loc_str}. Respond Code 3. Refer to TAC-1. Units en route, "
        f"identify."
    )


def build_cad_ack(callsign: str | None = None, what: str | None = "CAD") -> str:
    unit = phonetic_callsign(callsign) if callsign else "Unit"
    what = (what or "CAD").strip()
    if what.lower() == "cad":
        phrase = "updating your CAD"
    else:
        phrase = f"updating your CAD {what}"
    return f"{unit}, copy, {phrase}."


_CODE_SIX_OPENERS = [
    "showing you code six",
    "marking you code six",
    "you're code six",
    "got you out code six",
    "showing you out code six",
    "I have you code six",
    "you're out code six",
]
_CODE_SIX_CLOSERS = [
    "",
    "",
    " Use caution.",
    " Advise if you need anything.",
    " Ident when you're clear.",
]


def build_code_six_ack(
    callsign: str | None = None,
    location: str | None = None,
    details: str | None = None,
) -> str:
    unit = phonetic_callsign(callsign) if callsign else "Unit"
    opener = random.choice(_CODE_SIX_OPENERS)
    loc = _usable_location(location) or (location.strip() if location else None)
    loc_str = f" at {loc}" if loc else ""
    tail = ""
    if details:
        d = details.strip(" .,-")
        if d and not re.match(r"(?i)with\b", d):
            d = "with " + d
        if d:
            tail = f", {d}"
    closer = random.choice(_CODE_SIX_CLOSERS)
    return f"Copy {unit}, {opener}{loc_str}{tail}.{closer}".rstrip()


_CLEAR_ACKS = [
    "Copy {unit}, showing you clear.",
    "{unit}, roger, showing you clear and available.",
    "{unit}, copy, you're clear and available.",
    "Copy {unit}, showing you back in service.",
    "{unit}, roger, clear and available for calls.",
    "{unit}, copy, showing you in service.",
    "Copy {unit}, you're clear, available for the next one.",
    "{unit}, roger, showing you available.",
]


def build_clear_ack(callsign: str | None = None) -> str:
    unit = phonetic_callsign(callsign) if callsign else "Unit"
    return random.choice(_CLEAR_ACKS).format(unit=unit)


_WATCH_START_ACKS = [
    "{unit}, copy, have a safe shift.",
    "{unit}, roger, showing you in service, have a safe one out there.",
    "Copy {unit}, start of watch, stay safe.",
    "{unit}, roger, you're in service, have a good shift.",
    "{unit}, copy, showing you on the air, be safe out there.",
    "Copy {unit}, have a safe tour, showing you in service.",
    "{unit}, roger, logged on and in service, stay safe.",
    "{unit}, copy, you're in service, have a safe shift.",
]


def build_watch_start_ack(callsign: str | None = None) -> str:
    unit = phonetic_callsign(callsign) if callsign else "Unit"
    return random.choice(_WATCH_START_ACKS).format(unit=unit)


_CODE_SEVEN_ACKS = [
    "Copy {unit}, showing you code seven{loc}.",
    "{unit}, roger, code seven{loc}, be advised your time.",
    "{unit}, copy, showing you out code seven{loc}.",
    "Copy {unit}, code seven approved{loc}, monitor your radio.",
    "{unit}, roger, take your code seven{loc}.",
    "{unit}, copy, out for code seven{loc}, advise when you're back in service.",
]


def build_code_seven_ack(
    callsign: str | None = None,
    location: str | None = None,
) -> str:
    unit = phonetic_callsign(callsign) if callsign else "Unit"
    loc = _usable_location(location) or (location.strip() if location else None)
    loc_str = f" at {loc}" if loc else ""
    return random.choice(_CODE_SEVEN_ACKS).format(unit=unit, loc=loc_str)


def unit_area_line(units: str, high_risk: bool) -> str:
    if not units:
        return ""
    if high_risk:
        options = [
            f"{units}, this is in your area, respond Code 3 and use caution.",
            f"{units}, you are closest, roll Code 3, suspect may be armed.",
            f"{units}, priority call in your area, respond emergency and identify.",
        ]
    else:
        options = [
            f"{units}, the call is in your area, handle when available.",
            f"{units}, this is in your area, respond Code 2 and advise.",
            f"{units}, you are nearby, take a look when you get a chance.",
        ]
    return random.choice(options)
