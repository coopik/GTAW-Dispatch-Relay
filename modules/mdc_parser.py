from __future__ import annotations

import re


def _soup(html: str):
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return None
    try:
        return BeautifulSoup(html or "", "html.parser")
    except Exception:
        return None


def _clean(text: str | None) -> str | None:
    if text is None:
        return None
    t = re.sub(r"\s+", " ", str(text)).strip()
    return t or None


def visible_text(html: str) -> str:
    soup = _soup(html)
    if soup is None:
        return re.sub(r"<[^>]+>", " ", html or "")
    for tag in soup(("script", "style", "noscript")):
        tag.decompose()
    return re.sub(r"\s+", " ", soup.get_text(" ", strip=True))


def looks_like_login(html: str, markers: list[str] | None = None) -> bool:
    markers = markers or ["login", "sign in", "log in", "username", "password", "unauthorized"]
    text = visible_text(html).lower()
    if not text:
        return False
    hits = sum(1 for m in markers if m in text)
    if "password" in text and "logout" not in text:
        return True
    return hits >= 2 and "logout" not in text and "sign out" not in text


def _select_text(soup, selector: str | None) -> str | None:
    if not soup or not selector:
        return None
    try:
        el = soup.select_one(selector)
    except Exception:
        return None
    return _clean(el.get_text(" ", strip=True)) if el else None


def _select_list(soup, selector: str | None) -> list[str]:
    if not soup or not selector:
        return []
    try:
        els = soup.select(selector)
    except Exception:
        return []
    out = []
    for el in els:
        t = _clean(el.get_text(" ", strip=True))
        if t:
            out.append(t)
    return out


def _label_map(soup) -> dict:
    pairs: dict[str, str] = {}
    if not soup:
        return pairs
    try:
        for label in soup.find_all("label"):
            key = _clean(label.get_text(" ", strip=True))
            if not key:
                continue
            key = key.strip(" :").lower()
            val = None
            sib = label.find_next_sibling()
            hops = 0
            while sib is not None and hops < 3 and not val:
                val = _clean(sib.get_text(" ", strip=True))
                sib = sib.find_next_sibling()
                hops += 1
            if not val and label.parent is not None:
                whole = _clean(label.parent.get_text(" ", strip=True)) or ""
                whole = whole.replace(_clean(label.get_text(" ", strip=True)) or "", "").strip(" :")
                val = _clean(whole)
            if key and val and key not in pairs:
                pairs[key] = val
    except Exception:
        pass
    return pairs


def _table_pairs(soup) -> dict:
    pairs: dict[str, str] = {}
    if not soup:
        return pairs
    try:
        for tr in soup.select("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) >= 2:
                key = (_clean(cells[0].get_text(" ", strip=True)) or "").strip(" :").lower()
                val = _clean(cells[1].get_text(" ", strip=True))
                if key and val and key not in pairs:
                    pairs[key] = val
    except Exception:
        pass
    try:
        for dl in soup.select("dl"):
            for dt, dd in zip(dl.find_all("dt"), dl.find_all("dd")):
                key = (_clean(dt.get_text(" ", strip=True)) or "").strip(" :").lower()
                val = _clean(dd.get_text(" ", strip=True))
                if key and val and key not in pairs:
                    pairs[key] = val
    except Exception:
        pass
    return pairs


def _first_pair(pairs: dict, *needles: str) -> str | None:
    for key, val in pairs.items():
        for n in needles:
            if n in key:
                return val
    return None


def _card_by_header(soup, *needles: str):
    if not soup:
        return None
    try:
        cards = soup.select("div.card")
    except Exception:
        cards = []
    for card in cards:
        try:
            for h in card.find_all(["h3", "h4", "h5", "h6"]):
                t = (h.get_text(" ", strip=True) or "").lower()
                if any(n in t for n in needles):
                    return card
        except Exception:
            continue
    return None


_NEGATIVE = re.compile(r"\b(no|none|nil|clear|not? found|n/?a|negative|0)\b", re.I)


def _truthy_flag(text: str | None) -> bool | None:
    if text is None:
        return None
    t = text.strip().lower()
    if not t:
        return None
    if re.fullmatch(r"(yes|true|active|flagged|stolen|expired|wanted|1)", t):
        return True
    if _NEGATIVE.search(t):
        return False
    return None


_CAUTION_KNOWN = [
    "armed and dangerous", "armed", "dangerous", "apb", "mental health",
    "sex offender", "fld applicant", "indef-pc", "indef pc", "hraw",
    "arsonist", "confirmed gang affiliate", "gang affiliate",
    "crimes against children", "escape risk", "suicidal",
]

_NOT_A_CAUTION = {
    "caution codes", "caution code", "caution", "add", "add code", "remove",
    "select", "select one", "choose", "none", "n/a", "code", "codes", "search",
    "edit", "save", "close", "cancel", "available codes", "all codes", "legend",
}
_PICKER_HINT = re.compile(r"picker|legend|available|template|modal|dropdown|menu|select", re.I)


def _in_picker(node) -> bool:
    # The MDC page ships every possible caution code inside its picker markup,
    # so anything living in that subtree is a menu entry, not a record flag.
    try:
        if node.find_parent(["select", "option", "template", "datalist"]) is not None:
            return True
        for parent in node.parents:
            ident = " ".join(
                [str(parent.get("id") or "")] + list(parent.get("class") or [])
            )
            if ident and _PICKER_HINT.search(ident):
                return True
    except Exception:
        return False
    return False


def _looks_like_caution(text: str | None) -> bool:
    t = (text or "").strip()
    if not t or t.lower() in _NOT_A_CAUTION:
        return False
    if len(t) > 40 or ":" in t:
        return False
    words = t.split()
    if len(words) > 5:
        return False
    if t.lower() in _CAUTION_KNOWN:
        return True
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z '\-/&.]*", t))


def _points_from_pairs(pairs: dict) -> str | None:
    for key, val in (pairs or {}).items():
        k = str(key).strip().lower().rstrip(":")
        if "criminal point" in k or k in ("points", "criminal points"):
            cand = _clean(str(val))
            if cand and re.fullmatch(r"[0-9,]+", cand):
                return cand
    return None


def parse_name_result(html: str, selectors: dict | None = None) -> dict:
    selectors = selectors or {}
    soup = _soup(html)
    text = visible_text(html)
    pairs = {}
    if soup is not None:
        pairs = {**_table_pairs(soup), **_label_map(soup)}

    name = (
        _select_text(soup, selectors.get("full_name") or selectors.get("name"))
        or _select_text(soup, "h3.characterDetailsName")
        or _first_pair(pairs, "full name", "name")
    )

    wanted = None
    warrant_items: list[str] = []
    if soup is not None:
        try:
            titles = [
                (t.get_text(" ", strip=True) or "").strip()
                for t in soup.select("h4.characterDetailsTitle, .characterDetailsTitle")
            ]
            if any("wanted" == t.lower() or "wanted" in t.lower() for t in titles if t):
                wanted = True
        except Exception:
            pass

    caution_codes: list[str] = []
    warrants_sel = selectors.get("warrants")
    warrant_item_sel = selectors.get("warrant_item")
    if soup is not None:
        try:
            holder = soup.select_one("#cautionCodes")
            if holder is not None:
                for b in holder.select("span.badge, .badge"):
                    if _in_picker(b):
                        continue
                    a = b.find("a")
                    t = _clean(a.get_text(" ", strip=True) if a else b.get_text(" ", strip=True))
                    if t and len(re.sub(r"[^A-Za-z]", "", t)) >= 2 and t.lower() not in ("caution codes",):
                        caution_codes.append(t)
        except Exception:
            pass
    if not caution_codes and warrant_item_sel:
        caution_codes = _select_list(soup, warrant_item_sel)
    if not caution_codes and soup is not None:
        card = _card_by_header(soup, "caution")
        if card is not None:
            try:
                for b in card.select("span.badge, .badge, li"):
                    if _in_picker(b):
                        continue
                    t = _clean(b.get_text(" ", strip=True))
                    if t and len(re.sub(r"[^A-Za-z]", "", t)) >= 3 and t.lower() not in ("caution codes",):
                        caution_codes.append(t)
            except Exception:
                pass
    # There is deliberately no page-text fallback here: the MDC renders the
    # whole caution-code list on every profile, so scanning the text marked
    # clean subjects with every flag that exists.
    seen = set()
    caution_codes = [c for c in caution_codes if not (c.lower() in seen or seen.add(c.lower()))]
    caution_codes = [c for c in caution_codes if _looks_like_caution(c)][:6]

    # separately so we don't mislabel a flagged-but-not-wanted subject.
    has_warrants = True if wanted else (False if (name or pairs or caution_codes) else None)
    warrants_txt = _select_text(soup, warrants_sel) if warrants_sel else None

    criminal_points = None
    if soup is not None:
        try:
            for title in soup.select(".characterDetailsTitle"):
                if "criminal point" in (title.get_text(" ", strip=True) or "").lower():
                    val = title.find_next(class_="characterDetailsValue")
                    if val is not None:
                        criminal_points = _clean(val.get_text(" ", strip=True))
                    break
            if criminal_points is None:
                criminal_points = _points_from_pairs(pairs)
        except Exception:
            pass

    arrests: list[str] = []
    felony_count = 0
    misdemeanor_count = 0
    if soup is not None:
        try:
            crim = soup.select_one("#tableCriminalRecord tbody") or soup.select_one("#profile-table-criminal table tbody")
            rows = crim.select("tr") if crim is not None else []
            for tr in rows:
                cells = [_clean(td.get_text(" ", strip=True)) for td in tr.select("td")]
                if not any(cells):
                    continue
                type_txt = (cells[3] if len(cells) > 3 else " ".join(cells)).lower()
                remark = cells[4] if len(cells) > 4 else ""
                if "felony" in type_txt:
                    kind = "Felony"; felony_count += 1
                elif "misdemeanor" in type_txt:
                    kind = "Misdemeanor"; misdemeanor_count += 1
                elif "arrest" in type_txt:
                    kind = "Arrest"
                else:
                    kind = None
                if kind:
                    arrests.append(f"{kind} - {remark}" if remark else kind)
        except Exception:
            pass
    has_arrests = True if arrests else (False if (name or pairs) else None)

    license_txt = _select_text(soup, selectors.get("license"))
    if not license_txt and soup is not None:
        lic_bits: list[str] = []
        try:
            for lic in soup.select(".card-license"):
                name_el = lic.find(["h5", "h6", "span", "div"])
                lname = _clean(name_el.get_text(" ", strip=True)) if name_el else None
                status_el = lic.select_one('span[name="licenseStatus"]')
                lstatus = _clean(status_el.get_text(" ", strip=True)) if status_el else None
                if lname and lstatus:
                    lic_bits.append(f"{lname} {lstatus}")
                elif lname:
                    lic_bits.append(lname)
        except Exception:
            pass
        if lic_bits:
            license_txt = "; ".join(lic_bits[:4])

    vehicles = _select_list(soup, selectors.get("vehicles"))
    if not vehicles and soup is not None:
        card = _card_by_header(soup, "registered vehicle", "vehicles")
        if card is not None:
            try:
                for row in card.select("tr, li, .card-body div"):
                    t = _clean(row.get_text(" ", strip=True))
                    if t and len(t) >= 3 and "registered vehicle" not in t.lower():
                        vehicles.append(t)
            except Exception:
                pass
            seenv = set()
            vehicles = [v for v in vehicles if not (v.lower() in seenv or seenv.add(v.lower()))][:3]

    aliases = _select_text(soup, selectors.get("aliases")) or _first_pair(pairs, "alias", "aka")

    found = bool(name) or bool(pairs) or bool(caution_codes)
    return {
        "lookup": "name",
        "found": found,
        "name": name,
        "wanted": bool(wanted),
        "has_warrants": has_warrants,
        "warrants_text": warrants_txt,
        "warrant_items": warrant_items,
        "caution_codes": caution_codes,
        "criminal_points": criminal_points,
        "arrests": arrests,
        "felony_count": felony_count,
        "misdemeanor_count": misdemeanor_count,
        "has_arrests": has_arrests,
        "aliases": aliases,
        "vehicles": [v for v in vehicles if v],
        "license": license_txt,
        "raw_text": (text or "")[:800],
    }


def parse_plate_result(html: str, selectors: dict | None = None) -> dict:
    selectors = selectors or {}
    soup = _soup(html)
    text = visible_text(html)
    pairs = {}
    if soup is not None:
        pairs = {**_table_pairs(soup), **_label_map(soup)}

    make = _select_text(soup, selectors.get("make"))
    model = _select_text(soup, selectors.get("model"))
    plate = _select_text(soup, selectors.get("plate"))
    vehicle = None
    if soup is not None:
        try:
            h2s = [_clean(h.get_text(" ", strip=True)) for h in soup.select("h2")]
            h2s = [h for h in h2s if h]
            for h in h2s:
                has_digit = any(c.isdigit() for c in h)
                words = h.split()
                if not vehicle and len(words) >= 2 and not has_digit:
                    vehicle = h
                elif not plate and (has_digit or "san andreas" in h.lower()):
                    tokens = re.findall(r"[A-Za-z0-9]{2,}", h)
                    if tokens:
                        plate = tokens[-1]
        except Exception:
            pass
    if vehicle and not (make and model):
        vw = vehicle.split()
        make = make or vw[0]
        model = model or (" ".join(vw[1:]) or None)

    owner = (
        _select_text(soup, selectors.get("owner"))
        or _first_pair(pairs, "registered owner", "owner", "registrant")
    )

    veh_class = _first_pair(pairs, "vehicle class", "class")
    color = (
        _select_text(soup, selectors.get("color"))
        or _first_pair(pairs, "vehicle paint", "paint", "colour", "color")
    )
    if color:
        color = color.split(",")[0].strip()
    year = _select_text(soup, selectors.get("year")) or _first_pair(pairs, "year")

    status_sel = selectors.get("status")
    insurance = (
        _select_text(soup, status_sel) if status_sel else None
    ) or _first_pair(pairs, "insurance status", "insurance", "registration status", "registration")
    expired = None
    reg_txt = insurance
    if insurance:
        low = insurance.lower()
        if "uninsured" in low or "expired" in low or "invalid" in low or "none" in low:
            expired = True
        elif "insured" in low or "valid" in low or "current" in low or "active" in low:
            expired = False

    stolen_sel = selectors.get("stolen")
    stolen_txt = _select_text(soup, stolen_sel) if stolen_sel else _first_pair(pairs, "stolen", "flag")
    stolen = _truthy_flag(stolen_txt)
    if stolen is None:
        low = (text or "").lower()
        if re.search(r"\b(reported )?stolen\b", low) and "not stolen" not in low:
            stolen = True
        elif owner or vehicle or make:
            stolen = False

    found = bool(owner) or bool(vehicle) or bool(make) or bool(plate) or bool(pairs)
    return {
        "lookup": "plate",
        "found": found,
        "plate": plate,
        "owner": owner,
        "make": make,
        "model": model,
        "color": color,
        "year": year,
        "vehicle": vehicle,
        "vehicle_class": veh_class,
        "stolen": stolen,
        "registration_status": reg_txt,
        "insurance_status": insurance,
        "expired": expired,
        "raw_text": (text or "")[:800],
    }
