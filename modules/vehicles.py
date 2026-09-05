"""
GTA V vehicle models.

Why this exists: security-firm vehicle alarm broadcasts put the MODEL and the
LOCATION in the same sentence, e.g.

    "Security Firm: vehicle alarm was set off on a Tavros, closest street:
     Alta Street"

The old parser grabbed whatever followed "on" and read "location Tavros" over
the air. Tavros is a motorcycle, not a street. This list lets the flagger
reject a model outright before it can be mistaken for a location.
"""

from __future__ import annotations

import re
from functools import lru_cache

MODELS = (
    # --- Sports / super -----------------------------------------------------
    "Adder", "Autarch", "Banshee", "Bullet", "Cheetah", "Comet", "Coquette",
    "Cyclone", "Deveste", "Deveste Eight", "Diablous", "Elegy", "Emerus",
    "Entity XF", "Entity XXR", "ETR1", "Feltzer", "Furia", "FMJ", "GP1",
    "Infernus", "Ithaca", "Itali GTB", "Jester", "Krieger", "Nero", "Ninef",
    "Osiris", "Penetrator", "Pfister", "Reaper", "Sultan", "Tempesta",
    "Thrax", "Tigon", "Turismo", "Tyrant", "Tyrus", "Vacca", "Vagner",
    "Visione", "Voltic", "Zentorno", "Zorrusso", "T20", "X80 Proto",
    "Neon", "Raiden", "Sentinel", "Schafter", "Massacro", "Alpha",
    "Carbonizzare", "Rapid GT", "Surano", "Verlierer", "Omnis", "Tampa",
    "Drift Tampa", "Jugular", "Paragon", "Locust", "Neo", "Komoda",
    "Vectre", "Sultan RS", "Kanjo", "Zion", "Growler", "Itali RSX",
    # --- Muscle -------------------------------------------------------------
    "Blade", "Buccaneer", "Chino", "Clique", "Coquette BlackFin", "Deviant",
    "Dominator", "Dukes", "Ellie", "Faction", "Gauntlet", "Hermes",
    "Hotknife", "Impaler", "Imperator", "Lurcher", "Manana", "Moonbeam",
    "Nightshade", "Peyote", "Phoenix", "Picador", "Ratloader", "Ruiner",
    "Sabre Turbo", "Slamvan", "Stallion", "Tampa", "Tulip", "Vamos",
    "Vigero", "Virgo", "Voodoo", "Yosemite", "Weevil", "Broadway",
    # --- Sedans / compacts --------------------------------------------------
    "Asea", "Asterope", "Cognoscenti", "Emperor", "Fugitive", "Glendale",
    "Ingot", "Intruder", "Premier", "Primo", "Regina", "Romero", "Stanier",
    "Stratum", "Stretch", "Superd", "Surge", "Tailgater", "Warrener",
    "Washington", "Blista", "Brioso", "Dilettante", "Issi", "Panto",
    "Prairie", "Rhapsody", "Club", "Kanjo SJ", "Vivanite",
    # --- SUVs / vans --------------------------------------------------------
    "Baller", "BeeJay XL", "Cavalcade", "Contender", "Dubsta", "FQ2",
    "Granger", "Gresley", "Habanero", "Huntley S", "Landstalker", "Mesa",
    "Patriot", "Radius", "Rocoto", "Seminole", "Serrano", "Toros",
    "XLS", "Bison", "Bobcat XL", "Burrito", "Camper", "Journey", "Minivan",
    "Paradise", "Pony", "Rumpo", "Speedo", "Surfer", "Youga", "Boxville",
    "Gang Burrito", "Novak", "Astron", "Jubilee", "Iwagen", "Rebla",
    # --- Motorcycles (the class that caused the bug) ------------------------
    "Akuma", "Avarus", "Bagger", "Bati 801", "BF400", "Carbon RS",
    "Chimera", "Cliffhanger", "Daemon", "Defiler", "Deathbike", "Double T",
    "Enduro", "Esskey", "Faggio", "FCR 1000", "Gargoyle", "Hakuchou",
    "Hexer", "Innovation", "Lectro", "Manchez", "Nemesis", "Nightblade",
    "Oppressor", "PCJ 600", "Ratbike", "Rampant Rocket", "Ruffian",
    "Sanchez", "Sanctus", "Shotaro", "Sovereign", "Stryder", "Thrust",
    "Vader", "Vindicator", "Vortex", "Wolfsbane", "Zombie", "Tavros",
    "Reever", "Western", "Powersurge",
    # --- Off-road / utility / industrial ------------------------------------
    "Bifta", "Blazer", "Bodhi", "Brawler", "Dune Buggy", "Everon",
    "Freecrawler", "Injection", "Kalahari", "Kamacho", "Marshall",
    "Monster", "Outlaw", "Rancher XL", "Rebel", "Riata", "Sandking",
    "Trophy Truck", "Vagrant", "Verus", "Winky", "Zhaba", "Caracara",
    "Bulldozer", "Cutter", "Dump", "Flatbed", "Guardian", "Handler",
    "Mixer", "Rubble", "Tipper", "Dock Handler", "Forklift",
    "Airtug", "Caddy", "Docktug", "Lawn Mower", "Ripley", "Sadler",
    "Scrap Truck", "Towtruck", "Tractor", "Trashmaster", "Utility Truck",
    "Benson", "Biff", "Hauler", "Mule", "Packer", "Phantom", "Pounder",
    "Stockade", "Terrorbyte", "Titan", "Yankee",
    # --- Coupes / classics --------------------------------------------------
    "Cogncabrio", "Exemplar", "F620", "Felon", "Jackal", "Oracle",
    "Sentinel XS", "Windsor", "Zion Cabrio", "Casco", "Cheburek",
    "Coquette Classic", "Fagaloa", "JB 700", "Mamba", "Michelli GT",
    "Monroe", "Pigalle", "Retinue", "Roosevelt", "Savestra", "Stinger",
    "Swinger", "Torero", "Tornado", "Viseris", "Z190", "Zion Classic",
    "Peyote Gasser", "Deluxo", "Stirling GT",
    # --- Emergency / service ------------------------------------------------
    "Ambulance", "Fire Truck", "Police Cruiser", "Police Buffalo",
    "Police Interceptor", "Police Bike", "Riot", "Sheriff Cruiser",
    "Sheriff SUV", "Park Ranger", "Unmarked Cruiser", "Taxi", "Bus",
    "Coach", "Dashound", "Rental Shuttle", "Tour Bus", "Trailer",
)

# Words that only ever appear as a model qualifier, never as a street.
_MODEL_QUALIFIERS = {
    "gtb", "gts", "rs", "rsx", "xs", "xl", "sj", "gt", "turbo", "custom",
    "classic", "cabrio", "convertible", "coupe", "sedan", "wagon",
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


_MODEL_KEYS = frozenset(_norm(m) for m in MODELS if _norm(m))
_MODEL_TOKENS = frozenset(
    tok
    for m in MODELS
    for tok in re.split(r"[^A-Za-z0-9]+", m.lower())
    if len(tok) >= 4 and tok not in _MODEL_QUALIFIERS
)


@lru_cache(maxsize=2048)
def is_vehicle_model(text: str | None) -> bool:
    """True when the text is (or starts with) a known GTA V vehicle model."""
    if not text:
        return False
    key = _norm(text)
    if not key:
        return False
    if key in _MODEL_KEYS:
        return True
    # "a black Tavros" / "Tavros motorcycle" still counts as a model phrase.
    tokens = [t for t in re.split(r"[^A-Za-z0-9]+", str(text).lower()) if t]
    if not tokens:
        return False
    if any(t in _MODEL_TOKENS for t in tokens):
        # Only if there is no street-type word present.
        street_words = {
            "street", "avenue", "boulevard", "drive", "road", "lane", "way",
            "court", "place", "parkway", "highway", "freeway", "trail",
            "circus", "passage", "promenade", "vista", "incline", "pass",
        }
        if not (street_words & set(tokens)):
            return True
    return False


@lru_cache(maxsize=2048)
def find_model(text: str | None) -> str | None:
    """Return the first known model mentioned anywhere in the text."""
    if not text:
        return None
    low = str(text).lower()
    best = None
    for model in MODELS:
        if re.search(r"\b" + re.escape(model.lower()) + r"\b", low):
            if best is None or len(model) > len(best):
                best = model
    return best


__all__ = ["MODELS", "is_vehicle_model", "find_model"]
