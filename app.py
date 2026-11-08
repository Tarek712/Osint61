import os
import asyncio
import csv
import io
import json
import logging
import math
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from PIL import Image, ImageDraw, ImageFont

# Pure Python Zero-Dependency Arabic Shaper Built-in

import config

# --- AUTO-HEALING CONFIG DEFAULTS (Protects against outdated config.py on GitHub) ---
if not hasattr(config, "GEMINI_API_KEY"):
    config.GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not hasattr(config, "GEMINI_MODEL"):
    config.GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
if not hasattr(config, "MAP_WATERMARK_AR"):
    config.MAP_WATERMARK_AR = os.getenv("MAP_WATERMARK_AR", "خاص بتسريبات الحرب")
if not hasattr(config, "GEMINI_MODEL_CASCADE"):
    config.GEMINI_MODEL_CASCADE = [
        config.GEMINI_MODEL,
        "gemini-3-flash-lite",
        "gemini-flash-lite-latest",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash"
    ]
if not hasattr(config, "NASA_FIRMS_MAP_KEY"):
    config.NASA_FIRMS_MAP_KEY = os.getenv("NASA_FIRMS_MAP_KEY", "")
if not hasattr(config, "POLL_INTERVAL_THERMAL"):
    config.POLL_INTERVAL_THERMAL = int(os.getenv("POLL_INTERVAL_THERMAL", 300))
if not hasattr(config, "MIN_FRP_DAY_MW"):
    config.MIN_FRP_DAY_MW = float(os.getenv("MIN_FRP_DAY_MW", 25.0))
if not hasattr(config, "MIN_FRP_NIGHT_MW"):
    config.MIN_FRP_NIGHT_MW = float(os.getenv("MIN_FRP_NIGHT_MW", 12.0))
if not hasattr(config, "ALLOWED_MILITARY_OPERATORS"):
    config.ALLOWED_MILITARY_OPERATORS = {
        "USA": {
            "name_ar": "القوات الجوية/البحرية الأمريكية 🇺🇸 (USAF/USN)",
            "hex_prefixes": ("AE", "ADF"),
            "callsign_prefixes": ("HOMER", "FORTE", "JAKE", "PYTHON", "NCHO", "LAGR", "GOLD", "ETHYL", "RCH", "OLIVE", "DOOM", "BONE", "RAIDR", "NAVY", "CNV")
        },
        "ISRAEL": {
            "name_ar": "سلاح الجو الإسرائيلي 🇮🇱 (IAF)",
            "hex_prefixes": ("738A", "738B"),
            "callsign_prefixes": ("IAF", "ISD")
        },
        "SAUDI_ARABIA": {
            "name_ar": "القوات الجوية الملكية السعودية 🇸🇦 (RSAF)",
            "hex_prefixes": ("7102", "7103", "710"),
            "callsign_prefixes": ("RSAF", "SRG", "TUWAIQ")
        }
    }
if not hasattr(config, "KNOWN_OIL_FLARE_ZONES"):
    config.KNOWN_OIL_FLARE_ZONES = [
        {"name": "حقول صافر النفطية الروتينية (شرق مأرب)", "lat": 15.5500, "lon": 45.7800, "radius_km": 12},
        {"name": "حقول الأهواز وخوزستان النفطية", "lat": 31.3200, "lon": 48.6800, "radius_km": 45},
        {"name": "مصفاة عبادان وحقول خرمشهر", "lat": 30.3400, "lon": 48.2900, "radius_km": 28},
        {"name": "حقول عسلويه وبارس الجنوبي للغاز", "lat": 27.4700, "lon": 52.6100, "radius_km": 35},
        {"name": "حقول الرميلة والقرنة (البصرة)", "lat": 30.5800, "lon": 47.3400, "radius_km": 48}
    ]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("OSINT-Core-v4")


# ==========================================
# ARABIC FONT LOADER & SHAPER FOR MAP WATERMARK
# ==========================================
ARABIC_FONT_PATH = "/tmp/arabic_tactical_font.ttf"


async def ensure_arabic_font(client: httpx.AsyncClient) -> Optional[str]:
    """Ensures a valid Arabic TTF font is available for rendering the Arabic watermark on Linux."""
    system_candidates = [
        ARABIC_FONT_PATH,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for path in system_candidates:
        if os.path.exists(path) and os.path.getsize(path) > 10000:
            return path

    # Download Cairo-Bold or Amiri Arabic TTF from Google Fonts GitHub if no system font exists
    font_urls = [
        "https://github.com/google/fonts/raw/main/ofl/cairo/static/Cairo-Bold.ttf",
        "https://github.com/google/fonts/raw/main/ofl/tajawal/Tajawal-Bold.ttf"
    ]
    for url in font_urls:
        try:
            resp = await client.get(url, timeout=8.0)
            if resp.status_code == 200 and len(resp.content) > 15000:
                with open(ARABIC_FONT_PATH, "wb") as f:
                    f.write(resp.content)
                return ARABIC_FONT_PATH
        except Exception:
            continue
    return None


ARABIC_FORMS = {
    '\u0621': ('\uFE80', '\uFE80', '\uFE80', '\uFE80'),
    '\u0622': ('\uFE81', '\uFE82', '\uFE81', '\uFE82'),
    '\u0623': ('\uFE83', '\uFE84', '\uFE83', '\uFE84'),
    '\u0624': ('\uFE85', '\uFE86', '\uFE85', '\uFE86'),
    '\u0625': ('\uFE87', '\uFE88', '\uFE87', '\uFE88'),
    '\u0626': ('\uFE89', '\uFE8A', '\uFE8B', '\uFE8C'),
    '\u0627': ('\uFE8D', '\uFE8E', '\uFE8D', '\uFE8E'),
    '\u0628': ('\uFE8F', '\uFE90', '\uFE91', '\uFE92'),
    '\u0629': ('\uFE93', '\uFE94', '\uFE93', '\uFE94'),
    '\u062A': ('\uFE95', '\uFE96', '\uFE97', '\uFE98'),
    '\u062B': ('\uFE99', '\uFE9A', '\uFE9B', '\uFE9C'),
    '\u062C': ('\uFE9D', '\uFE9E', '\uFE9F', '\uFEA0'),
    '\u062D': ('\uFEA1', '\uFEA2', '\uFEA3', '\uFEA4'),
    '\u062E': ('\uFEA5', '\uFEA6', '\uFEA7', '\uFEA8'),
    '\u062F': ('\uFEA9', '\uFEAA', '\uFEA9', '\uFEAA'),
    '\u0630': ('\uFEAB', '\uFEAC', '\uFEAB', '\uFEAC'),
    '\u0631': ('\uFEAD', '\uFEAE', '\uFEAD', '\uFEAE'),
    '\u0632': ('\uFEAF', '\uFEB0', '\uFEAF', '\uFEB0'),
    '\u0633': ('\uFEB1', '\uFEB2', '\uFEB3', '\uFEB4'),
    '\u0634': ('\uFEB5', '\uFEB6', '\uFEB7', '\uFEB8'),
    '\u0635': ('\uFEB9', '\uFEBA', '\uFEBB', '\uFEBC'),
    '\u0636': ('\uFEBD', '\uFEBE', '\uFEBF', '\uFEC0'),
    '\u0637': ('\uFEC1', '\uFEC2', '\uFEC3', '\uFEC4'),
    '\u0638': ('\uFEC5', '\uFEC6', '\uFEC7', '\uFEC8'),
    '\u0639': ('\uFEC9', '\uFECA', '\uFECB', '\uFECC'),
    '\u063A': ('\uFECD', '\uFECE', '\uFECF', '\uFED0'),
    '\u0641': ('\uFED1', '\uFED2', '\uFED3', '\uFED4'),
    '\u0642': ('\uFED5', '\uFED6', '\uFED7', '\uFED8'),
    '\u0643': ('\uFED9', '\uFEDA', '\uFEDB', '\uFEDC'),
    '\u0644': ('\uFEDD', '\uFEDE', '\uFEDF', '\uFEE0'),
    '\u0645': ('\uFEE1', '\uFEE2', '\uFEE3', '\uFEE4'),
    '\u0646': ('\uFEE5', '\uFEE6', '\uFEE7', '\uFEE8'),
    '\u0647': ('\uFEE9', '\uFEEA', '\uFEEB', '\uFEEC'),
    '\u0648': ('\uFEED', '\uFEEE', '\uFEED', '\uFEEE'),
    '\u0649': ('\uFEEF', '\uFEF0', '\uFEEF', '\uFEF0'),
    '\u064A': ('\uFEF1', '\uFEF2', '\uFEF3', '\uFEF4'),
}
NON_CONNECTING_NEXT = {'\u0621', '\u0622', '\u0623', '\u0624', '\u0625', '\u0627', '\u0629', '\u062F', '\u0630', '\u0631', '\u0632', '\u0648', '\u0649'}


def shape_arabic_text(text: str) -> str:
    """Pure Python Arabic glyph shaper and RTL BiDi converter (Zero external dependencies)."""
    res = []
    n = len(text)
    for i, ch in enumerate(text):
        if ch not in ARABIC_FORMS:
            res.append(ch)
            continue
        prev_ch = text[i - 1] if i > 0 else None
        next_ch = text[i + 1] if i + 1 < n else None
        connects_prev = (prev_ch in ARABIC_FORMS) and (prev_ch not in NON_CONNECTING_NEXT)
        connects_next = (next_ch in ARABIC_FORMS) and (ch not in NON_CONNECTING_NEXT)
        forms = ARABIC_FORMS[ch]
        if connects_prev and connects_next:
            res.append(forms[3])
        elif connects_prev and not connects_next:
            res.append(forms[1])
        elif not connects_prev and connects_next:
            res.append(forms[2])
        else:
            res.append(forms[0])
    return "".join(reversed(res))


# ==========================================
# GEOSPATIAL, 3-NATION OPERATOR ID & REVERSE GEOCODER
# ==========================================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def calculate_bearing_ar(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    x = math.sin(dlon) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - (math.sin(phi1) * math.cos(phi2) * math.cos(dlon))
    initial_bearing = (math.degrees(math.atan2(x, y)) + 360) % 360
    dirs = ["شمال", "شمال شرق", "شرق", "جنوب شرق", "جنوب", "جنوب غرب", "غرب", "شمال غرب"]
    idx = round(initial_bearing / 45.0) % 8
    return dirs[idx]


def match_sector(lat: float, lon: float) -> Optional[str]:
    for _, sec in config.SECTORS.items():
        if sec["min_lat"] <= lat <= sec["max_lat"] and sec["min_lon"] <= lon <= sec["max_lon"]:
            return sec["name_ar"]
    return None


def identify_allowed_military_operator(hex_code: str, callsign: str) -> Optional[str]:
    """
    Strictly checks if an aircraft belongs to USA, Israel, or Saudi Arabia
    using ICAO Hex prefix or military callsign prefix. Returns operator Arabic name or None.
    """
    hx = hex_code.strip().upper()
    cs = callsign.strip().upper()
    for _, op in config.ALLOWED_MILITARY_OPERATORS.items():
        if hx.startswith(op["hex_prefixes"]) or (cs and cs != "UNKNOWN" and cs.startswith(op["callsign_prefixes"])):
            return op["name_ar"]
    return None


def check_strategic_proximity(lat: float, lon: float) -> Optional[Tuple[str, float, str]]:
    for site in config.STRATEGIC_SITES:
        dist = haversine_km(lat, lon, site["lat"], site["lon"])
        if dist <= site["radius_km"]:
            direction = calculate_bearing_ar(site["lat"], site["lon"], lat, lon)
            return site["name"], round(dist, 1), direction
    return None


def find_nearest_landmark(lat: float, lon: float) -> Tuple[str, float, str]:
    best_site = "نقطة رصد إقليمية"
    best_dist = 999999.0
    best_dir = ""
    for site in config.STRATEGIC_SITES:
        dist = haversine_km(lat, lon, site["lat"], site["lon"])
        if dist < best_dist:
            best_dist = dist
            best_site = site["name"]
            best_dir = calculate_bearing_ar(site["lat"], site["lon"], lat, lon)
    return best_site, round(best_dist, 1), best_dir


def is_known_oil_flare(lat: float, lon: float) -> bool:
    for flare in config.KNOWN_OIL_FLARE_ZONES:
        if haversine_km(lat, lon, flare["lat"], flare["lon"]) <= flare["radius_km"]:
            return True
    return False


GEOCODE_CACHE: Dict[str, str] = {}


async def resolve_exact_location_ar(client: httpx.AsyncClient, lat: float, lon: float) -> str:
    cache_key = f"{lat:.2f}_{lon:.2f}"
    nearest_name, dist_km, bearing_ar = find_nearest_landmark(lat, lon)
    tactical_ref = (
        f"بجوار {nearest_name} ({dist_km} كم)"
        if dist_km <= 12.0
        else f"على بُعد {dist_km} كم {bearing_ar} {nearest_name}"
    )

    if cache_key in GEOCODE_CACHE:
        base_loc = GEOCODE_CACHE[cache_key]
        return f"{base_loc} — ({tactical_ref})"

    url = f"https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat={lat}&lon={lon}&zoom=10&accept-language=ar"
    headers = {"User-Agent": "OSINT-Tactical-Locator/4.0 (Strategic Research)"}
    base_loc = ""
    try:
        resp = await client.get(url, headers=headers, timeout=4.5)
        if resp.status_code == 200:
            data = resp.json()
            addr = data.get("address", {})
            city = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("county")
                or addr.get("municipality")
                or ""
            )
            state_prov = addr.get("state") or addr.get("region") or addr.get("province") or ""
            country = addr.get("country") or ""
            parts = [p for p in (city, state_prov, country) if p]
            if parts:
                base_loc = "، ".join(parts)
            elif data.get("display_name"):
                base_loc = "، ".join(data["display_name"].split(",")[:3]).strip()
    except Exception:
        pass

    if not base_loc:
        if 24.0 <= lat <= 30.5 and 48.0 <= lon <= 57.5:
            base_loc = "مياه الخليج العربي / مضيق هرمز"
        elif 11.5 <= lat <= 22.0 and 37.0 <= lon <= 44.5:
            base_loc = "المجال البحري للبحر الأحمر / باب المندب"
        elif 11.5 <= lat <= 16.0 and 44.5 <= lon <= 53.5:
            base_loc = "خليج عدن وبحر العرب (قبالة السواحل اليمنية)"
        elif 31.5 <= lat <= 36.5 and 31.5 <= lon <= 36.0:
            base_loc = "المجال البحري لشرق البحر المتوسط"
        else:
            base_loc = "نطاق عمليات جوي/ميداني"

    GEOCODE_CACHE[cache_key] = base_loc
    return f"{base_loc} — ({tactical_ref})"


# ==========================================
# MILITARY INTELLIGENCE SYSTEM PROMPT (SITREP / INTSUM)
# ==========================================
async def generate_ai_military_post(
    client: httpx.AsyncClient,
    category: str,
    title: str,
    exact_location: str,
    telemetry_summary: str,
    operator_name: Optional[str] = None,
    correlation_note: Optional[str] = None
) -> Optional[str]:
    """
    Uses a specialized Military Intelligence Officer System Prompt (OSINT/SIGINT)
    with Flash-Lite (thinkingBudget=0) to produce a high-precision tactical SITREP
    linking the event to the ongoing Middle East war and the Yemen/Houthi-Legitimacy-Saudi conflict.
    """
    if not config.GEMINI_API_KEY:
        return None

    op_str = f" | القوة المشغلة: {operator_name}" if operator_name else ""
    corr_str = f" | تقاطع استخباراتي: {correlation_note}" if correlation_note else ""

    NL = chr(10)
    military_intel_prompt = NL.join([
        "أنت ضابط استخبارات عسكرية (OSINT/SIGINT) في غرفة عمليات متابعة الحرب الجارية في الشرق الأوسط والحرب الدائرة في اليمن بين الحوثيين وقوات الشرعية والمملكة العربية السعودية.",
        "صغ برقية استخباراتية ميدانية مركزة (3 إلى 4 أسطر كحد أقصى) بلغة عسكرية عربية رصينة وجاهزة للنشر الفوري بدون مقدمات أو عناوين إنشائية:",
        "1. ابدأ بذكر الحدث، القوة الجوية المشغلة (الأمريكية 🇺🇸 أو الإسرائيلية 🇮🇱 أو السعودية 🇸🇦 إن وجدت)، والموقع الجغرافي الدقيق والمسافة من أقرب قاعدة أو جبهة.",
        "2. حلل المهمة التكتيكية في سياق العمليات العسكرية الجارية:",
        "- إذا كان في مسرح اليمن وجنوب السعودية والبحر الأحمر (صعدة، مأرب، الحديدة، صنعاء، تعز، حرض، جازان، نجران، خميس مشيط، باب المندب): اربطه بمهام القوات الجوية السعودية والتحالف في اعتراض المسيّرات والصواريخ الباليستية الحوثية، الإسناد الجوي لقوات الشرعية على خطوط التماس، أو رصد واستهداف منصات الإطلاق الساحلية والجبلية.",
        "- إذا كان في مسرح إيران، الشام، العراق، فلسطين، أو الخليج: اربطه بالتصعيد العسكري الإقليمي، الاستطلاع الإلكتروني ELINT/SIGINT لكشف الرادارات والدفاعات الجوية، الإنذار المبكر AWACS، إسناد المقاتلات بالوقود لتنفيذ ضربات بعيدة المدى، أو نشاط الحرب الإلكترونية (إعاقة وتشويش GPS NIC<=2).",
        "3. اختم بسطر التقدير العملياتي لدلالة هذا الرصد على مسار المعركة.",
        f"البيانات المرصودة -> التصنيف: {category}{op_str} | الحدث: {title} | الموقع الدقيق: {exact_location} | التفاصيل التقنية: {telemetry_summary}{corr_str}"
    ])

    seen_m = set()
    models_to_try = []
    for m in config.GEMINI_MODEL_CASCADE:
        if m and m not in seen_m:
            seen_m.add(m)
            models_to_try.append(m)

    for model_name in models_to_try:
        api_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={config.GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": military_intel_prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 240,
                "temperature": 0.2,
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        try:
            resp = await client.post(api_url, json=payload, timeout=7.5)
            if resp.status_code != 200:
                payload["generationConfig"].pop("thinkingConfig", None)
                resp = await client.post(api_url, json=payload, timeout=7.5)

            if resp.status_code == 200:
                res_json = resp.json()
                candidates = res_json.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and parts[0].get("text"):
                        text_out = parts[0]["text"].strip()
                        text_out = text_out.replace("**", "").replace("*", "")
                        state.stats["ai_analyses"] += 1
                        state.stats["active_ai_model"] = model_name
                        return text_out
        except Exception as exc:
            logger.warning(f"AI Model {model_name} fallback trigger: {exc}")
            continue

    return None


# ==========================================
# TACTICAL STATIC MAP GENERATOR v4 (WITH "خاص بتسريبات الحرب" WATERMARK)
# ==========================================
def deg2num_float(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[float, float]:
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = (lon_deg + 180.0) / 360.0 * n
    ytile = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return xtile, ytile


async def generate_tactical_map_image(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    category: str,
    severity: str,
    heading: Optional[float] = None,
    is_orbiting: bool = False,
    label_code: str = "TARGET",
    trail_coords: Optional[List[Tuple[float, float]]] = None,
    is_ew_jamming: bool = False
) -> bytes:
    zoom = 8 if "AVIATION" in category else 10
    cx, cy = deg2num_float(lat, lon, zoom)
    center_tile_x, center_tile_y = int(cx), int(cy)

    grid_img = Image.new("RGB", (256 * 3, 256 * 3), (12, 16, 22))

    async def fetch_tile(dx: int, dy: int):
        tx = center_tile_x + dx
        ty = center_tile_y + dy
        url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{zoom}/{ty}/{tx}"
        try:
            resp = await client.get(url, timeout=6.0)
            if resp.status_code == 200:
                tile = Image.open(io.BytesIO(resp.content)).convert("RGB")
                grid_img.paste(tile, ((dx + 1) * 256, (dy + 1) * 256))
        except Exception:
            pass

    font_path_task = asyncio.create_task(ensure_arabic_font(client))
    await asyncio.gather(*(fetch_tile(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)))
    arabic_font_path = await font_path_task

    px_x = int((cx - center_tile_x + 1) * 256)
    px_y = int((cy - center_tile_y + 1) * 256)

    w, h = 640, 400
    left = max(0, min(768 - w, px_x - w // 2))
    top = max(0, min(768 - h, px_y - h // 2))
    cropped = grid_img.crop((left, top, left + w, top + h)).convert("RGBA")

    tx_px = px_x - left
    ty_px = px_y - top

    overlay = Image.new("RGBA", (w, h), (8, 14, 24, 120))
    draw = ImageDraw.Draw(overlay)

    # Radar Grid
    for gx in range(0, w, 64):
        draw.line([(gx, 0), (gx, h)], fill=(48, 209, 88, 28), width=1)
    for gy in range(0, h, 64):
        draw.line([(0, gy), (w, gy)], fill=(48, 209, 88, 28), width=1)

    # Draw Historical Flight Trail Polyline
    if trail_coords and len(trail_coords) >= 2:
        pts_px = []
        for t_lat, t_lon in trail_coords:
            tcx, tcy = deg2num_float(t_lat, t_lon, zoom)
            pt_x = int((tcx - center_tile_x + 1) * 256) - left
            pt_y = int((tcy - center_tile_y + 1) * 256) - top
            pts_px.append((pt_x, pt_y))
        if len(pts_px) >= 2:
            draw.line(pts_px, fill=(10, 210, 255, 210), width=3)
            for p_x, p_y in pts_px[:-1]:
                draw.ellipse([p_x - 3, p_y - 3, p_x + 3, p_y + 3], fill=(10, 210, 255, 180))

    # EW / GPS Jamming Zone
    if is_ew_jamming:
        draw.ellipse([tx_px - 95, ty_px - 95, tx_px + 95, ty_px + 95], fill=(191, 90, 242, 70), outline=(191, 90, 242, 255), width=2)

    primary_color = (255, 69, 58, 255) if severity == "CRITICAL" else (255, 159, 10, 255)
    glow_color = (255, 69, 58, 65) if severity == "CRITICAL" else (255, 159, 10, 65)

    for r in (65, 38):
        draw.ellipse([tx_px - r, ty_px - r, tx_px + r, ty_px + r], outline=primary_color, width=2)
    draw.ellipse([tx_px - 22, ty_px - 22, tx_px + 22, ty_px + 22], fill=glow_color)

    # Crosshair Reticle
    draw.line([(tx_px - 80, ty_px), (tx_px - 12, ty_px)], fill=primary_color, width=2)
    draw.line([(tx_px + 12, ty_px), (tx_px + 80, ty_px)], fill=primary_color, width=2)
    draw.line([(tx_px, ty_px - 80), (tx_px, ty_px - 12)], fill=primary_color, width=2)
    draw.line([(tx_px, ty_px + 12), (tx_px, ty_px + 80)], fill=primary_color, width=2)

    if heading is not None:
        rad = math.radians(heading - 90)
        end_x = int(tx_px + 75 * math.cos(rad))
        end_y = int(ty_px + 75 * math.sin(rad))
        draw.line([(tx_px, ty_px), (end_x, end_y)], fill=(10, 210, 255, 255), width=3)
        draw.ellipse([end_x - 4, end_y - 4, end_x + 4, end_y + 4], fill=(10, 210, 255, 255))

    if is_orbiting:
        draw.ellipse([tx_px - 90, ty_px - 50, tx_px + 90, ty_px + 50], outline=(10, 210, 255, 220), width=2)

    draw.ellipse([tx_px - 5, ty_px - 5, tx_px + 5, ty_px + 5], fill=(255, 255, 255, 255), outline=primary_color, width=2)

    # Top & Bottom HUD Bars
    draw.rectangle([0, 0, w, 36], fill=(10, 12, 16, 230))
    draw.rectangle([0, h - 38, w, h], fill=(10, 12, 16, 235))
    draw.line([(0, h - 38), (w, h - 38)], fill=primary_color, width=1)

    default_font = ImageFont.load_default()
    hud_top = f"OSINT FUSION CENTER v4 // {category} // [{severity}]"
    hud_bottom_left = f"LAT: {lat:.4f} N  LON: {lon:.4f} E  |  ID: {label_code}"
    draw.text((14, 11), hud_top, fill=primary_color, font=default_font)
    draw.text((14, h - 24), hud_bottom_left, fill=(215, 215, 225, 255), font=default_font)

    # Draw Arabic Watermark "خاص بتسريبات الحرب" on the bottom right badge
    watermark_raw = getattr(config, "MAP_WATERMARK_AR", "خاص بتسريبات الحرب")
    shaped_wm = shape_arabic_text(watermark_raw)

    # Tactical Red/Gold Badge on the Bottom Right
    badge_w = 195
    draw.rectangle([w - badge_w - 10, h - 33, w - 10, h - 5], fill=(255, 69, 58, 38), outline=primary_color, width=1)

    if arabic_font_path:
        try:
            ar_font = ImageFont.truetype(arabic_font_path, 15)
            draw.text((w - badge_w + 12, h - 30), shaped_wm, fill=(255, 214, 10, 255), font=ar_font)
        except Exception:
            draw.text((w - badge_w + 10, h - 24), "WAR LEAKS EXCLUSIVE", fill=(255, 214, 10, 255), font=default_font)
    else:
        draw.text((w - badge_w + 10, h - 24), "WAR LEAKS EXCLUSIVE", fill=(255, 214, 10, 255), font=default_font)

    combined = Image.alpha_composite(cropped, overlay).convert("RGB")
    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


# ==========================================
# STATE, MULTI-SENSOR CORRELATION & GHOST MODE ENGINE
# ==========================================
class StateEngine:
    def __init__(self):
        self.seen_events: Dict[str, float] = {}
        self.aircraft_tracks: Dict[str, List[Tuple[float, float, float, float]]] = {}
        self.active_high_value_flights: Dict[str, dict] = {}
        self.recent_air_presence: List[dict] = []
        self.stats = {
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "alerts_sent": 0,
            "ai_analyses": 0,
            "active_ai_model": config.GEMINI_MODEL if config.GEMINI_API_KEY else "غير مفعل (أضف GEMINI_API_KEY)",
            "aviation_scans": 0,
            "seismic_scans": 0,
            "thermal_scans": 0,
            "nga_scans": 0,
            "ew_jamming_events": 0,
            "correlated_strikes": 0,
            "last_alert_time": "لا يوجد حتى الآن"
        }

    def is_duplicate(self, event_key: str, ttl_seconds: int = 3600) -> bool:
        now = time.time()
        expired = [k for k, exp in self.seen_events.items() if exp < now]
        for k in expired:
            del self.seen_events[k]

        if event_key in self.seen_events:
            return True
        self.seen_events[event_key] = now + ttl_seconds
        return False

    def record_aircraft_heading(self, hex_code: str, lat: float, lon: float, track: float) -> Tuple[bool, List[Tuple[float, float]]]:
        now = time.time()
        history = self.aircraft_tracks.get(hex_code, [])
        history = [pt for pt in history if now - pt[0] <= 1800]
        history.append((now, lat, lon, track))
        self.aircraft_tracks[hex_code] = history

        trail = [(pt[1], pt[2]) for pt in history]
        if len(history) < 4:
            return False, trail

        total_turn = 0.0
        for i in range(1, len(history)):
            diff = abs(history[i][3] - history[i - 1][3])
            if diff > 180:
                diff = 360 - diff
            total_turn += diff

        displacement = haversine_km(history[0][1], history[0][2], history[-1][1], history[-1][2])
        return (total_turn >= 160.0 and displacement < 90.0), trail

    def log_air_activity_for_correlation(self, callsign: str, operator_name: str, ac_type_desc: str, lat: float, lon: float):
        now = time.time()
        self.recent_air_activity_cleanup(now)
        self.recent_air_presence.append({
            "time": now,
            "callsign": callsign,
            "operator": operator_name,
            "desc": ac_type_desc,
            "lat": lat,
            "lon": lon
        })

    def recent_air_activity_cleanup(self, now: float):
        self.recent_air_presence = [item for item in self.recent_air_presence if now - item["time"] <= 5400]

    def check_multi_sensor_correlation(self, lat: float, lon: float) -> Optional[str]:
        now = time.time()
        self.recent_air_activity_cleanup(now)
        for air in self.recent_air_presence:
            dist = haversine_km(lat, lon, air["lat"], air["lon"])
            if dist <= 130.0:
                mins_ago = int((now - air["time"]) // 60)
                self.stats["correlated_strikes"] += 1
                return f"تطابق رصد جوي/ميداني: رُصد تحليق عسكري لـ ({air['operator']} - {air['callsign']}) على بُعد {dist:.0f} كم قبل {mins_ago} دقيقة من الحدث."
        return None


state = StateEngine()


# ==========================================
# TELEGRAM PRESENTATION & AI DISPATCHER
# ==========================================
async def send_telegram_alert(
    client: httpx.AsyncClient,
    severity: str,
    category: str,
    title: str,
    sector_name: str,
    lat: Optional[float],
    lon: Optional[float],
    telemetry_lines: List[str],
    extra_links: Optional[List[Tuple[str, str]]] = None,
    heading: Optional[float] = None,
    is_orbiting: bool = False,
    label_code: str = "OSINT",
    trail_coords: Optional[List[Tuple[float, float]]] = None,
    is_ew_jamming: bool = False,
    operator_name: Optional[str] = None,
    correlation_note: Optional[str] = None
) -> Tuple[bool, str]:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        msg = "TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID غير مضاف في إعدادات Render."
        logger.warning(msg)
        return False, msg

    exact_location_str = sector_name
    if lat is not None and lon is not None:
        exact_location_str = await resolve_exact_location_ar(client, lat, lon)

    ai_post_text = await generate_ai_military_post(
        client=client,
        category=category,
        title=title,
        exact_location=exact_location_str,
        telemetry_summary=" | ".join(telemetry_lines),
        operator_name=operator_name,
        correlation_note=correlation_note
    )

    badge = "🔴 عاجل — رصد عسكري حرج" if severity == "CRITICAL" else "🟠 رصد عملياتي هام"
    if correlation_note:
        badge = "🚨 تقاطع استخباراتي مؤكد (MULTI-SENSOR)"

    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    msg_parts = [
        f"<b>{badge} | {category}</b>",
    ]
    if operator_name:
        msg_parts.append(f"🏳️ <b>القوة المشغلة:</b> {operator_name}")
    msg_parts.append(f"📍 <b>الموقع الدقيق:</b> {exact_location_str}")
    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")

    if ai_post_text:
        msg_parts.append("🧠 <b>التقدير العسكري والاستخباراتي:</b>" + chr(10) + ai_post_text)
        msg_parts.append("")
    else:
        msg_parts.append(f"<b>الحدث المرصود:</b> {title}")
        msg_parts.append(f"<b>المسرح العملياتي:</b> {sector_name}")

    if correlation_note:
        msg_parts.append(f"🔗 <b>ربط المصادر:</b> {correlation_note}")

    if lat is not None and lon is not None:
        msg_parts.append(f"🎯 <b>الإحداثيات:</b> <code>{lat:.4f}, {lon:.4f}</code>")

    msg_parts.append("<b>البيانات الخام (Telemetry):</b>")
    for line in telemetry_lines[:4]:
        msg_parts.append(f"• {line}")

    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")
    msg_parts.append(f"🛡 <b>خاص بتسريبات الحرب</b> | ⏱ <code>{now_str}</code>")

    text = chr(10).join(msg_parts)
    if len(text) > 1015:
        text = text[:1010] + "..."

    inline_keyboard = []
    if lat is not None and lon is not None:
        gmaps_url = f"https://www.google.com/maps?q={lat},{lon}&t=k"
        copernicus_url = f"https://browser.dataspace.copernicus.eu/?zoom=13&lat={lat}&lng={lon}"
        firms_url = f"https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@{lon:.2f},{lat:.2f},11z"
        inline_keyboard.append([
            {"text": "🛰 Google Satellite", "url": gmaps_url},
            {"text": "📡 Sentinel Radar", "url": copernicus_url}
        ])
        inline_keyboard.append([
            {"text": "🔥 NASA FIRMS", "url": firms_url},
            {"text": "⚡ خريطة تشويش GPS", "url": f"https://gpsjam.org/?lat={lat:.2f}&lon={lon:.2f}&z=7"}
        ])

    if extra_links:
        row = [{"text": label, "url": url} for label, url in extra_links]
        inline_keyboard.append(row)

    reply_markup_json = json.dumps({"inline_keyboard": inline_keyboard}) if inline_keyboard else None

    if lat is not None and lon is not None:
        try:
            map_bytes = await generate_tactical_map_image(
                client=client,
                lat=lat,
                lon=lon,
                category=category,
                severity=severity,
                heading=heading,
                is_orbiting=is_orbiting,
                label_code=label_code,
                trail_coords=trail_coords,
                is_ew_jamming=is_ew_jamming
            )
            photo_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
            data_form = {
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": text,
                "parse_mode": "HTML"
            }
            if reply_markup_json:
                data_form["reply_markup"] = reply_markup_json

            files = {"photo": ("warleaks_tactical_map.jpg", map_bytes, "image/jpeg")}
            resp = await client.post(photo_url, data=data_form, files=files, timeout=20.0)
            if resp.status_code == 200:
                state.stats["alerts_sent"] += 1
                state.stats["last_alert_time"] = now_str
                return True, "تم إرسال المنشور الاستخباراتي مع الخريطة الموقعة بـ (خاص بتسريبات الحرب) بنجاح."
            else:
                logger.warning(f"sendPhoto failed ({resp.status_code}), falling back to sendMessage: {resp.text}")
        except Exception as exc:
            logger.warning(f"Map generation error, falling back to text: {exc}")

    msg_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": config.TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    if inline_keyboard:
        payload["reply_markup"] = {"inline_keyboard": inline_keyboard}

    try:
        resp = await client.post(msg_url, json=payload, timeout=15.0)
        if resp.status_code == 200:
            state.stats["alerts_sent"] += 1
            state.stats["last_alert_time"] = now_str
            return True, "تم إرسال المنشور النصي بنجاح."
        return False, f"خطأ من تيليجرام ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return False, f"فشل الاتصال بواجهة تيليجرام: {exc}"


# ==========================================
# COLLECTOR 1: EXCLUSIVE US / ISRAELI / SAUDI MILITARY AVIATION
# ==========================================
async def poll_military_aviation(client: httpx.AsyncClient):
    state.stats["aviation_scans"] += 1
    endpoints = [
        "https://api.airplanes.live/v2/mil",
        "https://api.adsb.lol/v2/mil"
    ]

    aircraft_list = []
    for ep in endpoints:
        try:
            resp = await client.get(ep, timeout=15.0)
            if resp.status_code == 200:
                aircraft_list = resp.json().get("ac", [])
                break
        except Exception as exc:
            logger.warning(f"Aviation endpoint {ep} failed: {exc}")

    current_scan_hexes = set()
    now = time.time()

    for ac in aircraft_list:
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue

        sector_name = match_sector(lat, lon)
        if not sector_name:
            continue

        hex_code = str(ac.get("hex", "")).strip().upper()
        callsign = str(ac.get("flight", "")).strip().upper() or "UNKNOWN"
        ac_type = str(ac.get("t", "")).strip().upper()

        # STRICT 3-NATION FILTER: Only USA 🇺🇸, Israel 🇮🇱, or Saudi Arabia 🇸🇦 military aircraft
        operator_name = identify_allowed_military_operator(hex_code, callsign)
        if not operator_name:
            continue

        alt_baro = ac.get("alt_baro", 0)
        gs = ac.get("gs", "N/A")
        track = float(ac.get("track", 0.0) or 0.0)
        squawk = str(ac.get("squawk", ""))
        nic = ac.get("nic")
        nac_p = ac.get("nac_p")

        is_ew_jammed = (nic is not None and int(nic) <= 2) or (nac_p is not None and int(nac_p) <= 2)
        type_desc = config.HIGH_VALUE_AIRCRAFT_TYPES.get(ac_type)
        is_emergency = squawk in ("7700", "7600", "7500")
        is_orbiting, trail_coords = state.record_aircraft_heading(hex_code, lat, lon, track)

        current_scan_hexes.add(hex_code)
        alt_num = int(alt_baro) if isinstance(alt_baro, (int, float)) else 25000

        state.active_high_value_flights[hex_code] = {
            "last_seen": now,
            "callsign": callsign,
            "operator": operator_name,
            "desc": type_desc or f"طائرة عسكرية ({ac_type or 'غير مصنف'})",
            "lat": lat,
            "lon": lon,
            "alt": alt_num,
            "track": track,
            "sector_name": sector_name,
            "trail": trail_coords
        }

        state.log_air_activity_for_correlation(callsign, operator_name, type_desc or ac_type, lat, lon)

        if is_ew_jammed:
            state.stats["ew_jamming_events"] += 1

        severity = "CRITICAL" if (is_orbiting or is_emergency or is_ew_jammed or type_desc is not None) else "HIGH"
        dedup_suffix = "ORBIT" if is_orbiting else ("EW" if is_ew_jammed else "DETECT")
        if state.is_duplicate(f"AIR_{hex_code}_{dedup_suffix}", ttl_seconds=7200):
            continue

        pattern_note = "🔄 مدار عملياتي مستمر (Orbit/Loitering)" if is_orbiting else "تحليق / دورية عملياتية نشطة"
        if is_ew_jammed:
            pattern_note += " | ⚡ رصد تشويش حرب إلكترونية (GPS Jamming NIC<=2)"

        title = type_desc if type_desc else f"طائرة عسكرية ({ac_type or 'مهام خاصة'})"
        if is_orbiting:
            title = f"مدار عملياتي نشط: {title}"

        telemetry = [
            f"النداء اللاسلكي: <code>{callsign}</code> | كود ICAO: <code>{hex_code}</code>",
            f"الطراز: <code>{ac_type or 'N/A'}</code> | الارتفاع: <code>{alt_baro} ft</code>",
            f"السرعة: <code>{gs} kt</code> | الاتجاه: <code>{track}°</code>",
            f"النمط التكتيكي: {pattern_note}"
        ]

        adsb_url = f"https://globe.adsbexchange.com/?icao={hex_code.lower()}"
        airframes_url = f"https://app.airframes.io/aircraft/{hex_code.lower()}"

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="MILITARY AVIATION & SIGINT",
            title=title,
            sector_name=sector_name,
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            extra_links=[("✈️ ADS-B Exchange", adsb_url), ("📡 ACARS Feed", airframes_url)],
            heading=track,
            is_orbiting=is_orbiting,
            label_code=callsign if callsign != "UNKNOWN" else hex_code,
            trail_coords=trail_coords,
            is_ew_jamming=is_ew_jammed,
            operator_name=operator_name
        )

    # Check Ghost Mode for US/Israeli/Saudi aircraft turning off transponders at high altitude
    expired_hexes = []
    for hx, info in state.active_high_value_flights.items():
        if hx not in current_scan_hexes and (now - info["last_seen"]) >= 320:
            expired_hexes.append(hx)
            if info["alt"] >= 16000 and not state.is_duplicate(f"GHOST_{hx}", ttl_seconds=14400):
                await send_telegram_alert(
                    client=client,
                    severity="CRITICAL",
                    category="GHOST MODE / TRANSPONDER DARK",
                    title=f"إظلام راداري مفاجئ وإغلاق جهاز الإرسال في الجو: {info['desc']}",
                    sector_name=info["sector_name"],
                    lat=info["lat"],
                    lon=info["lon"],
                    telemetry_lines=[
                        f"النداء اللاسلكي: <code>{info['callsign']}</code> | ICAO: <code>{hx}</code>",
                        f"آخر ارتفاع مسجل قبل الإظلام: <code>{info['alt']} ft</code>",
                        f"آخر اتجاه: <code>{info['track']}°</code>",
                        "التفسير التكتيكي: إغلاق متعمد للبث الراداري لدخول منطقة عمليات"
                    ],
                    heading=info["track"],
                    label_code=f"DARK-{info['callsign']}",
                    trail_coords=info["trail"],
                    operator_name=info["operator"]
                )

    for hx in expired_hexes:
        del state.active_high_value_flights[hx]


# ==========================================
# COLLECTOR 2: SEISMIC & SURFACE EXPLOSIONS (WITH CORRELATION)
# ==========================================
async def poll_seismic_anomalies(client: httpx.AsyncClient):
    state.stats["seismic_scans"] += 1
    url = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_hour.geojson"

    try:
        resp = await client.get(url, timeout=15.0)
        if resp.status_code != 200:
            return
        data = resp.json()
    except Exception as exc:
        logger.warning(f"Seismic feed error: {exc}")
        return

    now_ms = time.time() * 1000.0
    max_age_ms = config.STARTUP_LOOKBACK_MINUTES * 60 * 1000.0

    for feat in data.get("features", []):
        feat_id = feat.get("id")
        props = feat.get("properties", {})
        coords = feat.get("geometry", {}).get("coordinates", [])
        if len(coords) < 3:
            continue

        lon, lat, depth_km = float(coords[0]), float(coords[1]), float(coords[2])
        mag = float(props.get("mag") or 0.0)
        event_time_ms = float(props.get("time") or 0.0)
        event_type = str(props.get("type", "earthquake")).lower()

        if (now_ms - event_time_ms) > max_age_ms:
            continue

        sector_name = match_sector(lat, lon)
        if not sector_name:
            continue

        prox = check_strategic_proximity(lat, lon)
        is_shallow = depth_km <= 5.0
        is_explicit_blast = "explosion" in event_type or "blast" in event_type

        if not (is_shallow or is_explicit_blast or prox is not None or mag >= 4.8):
            continue

        if state.is_duplicate(f"SEISMIC_{feat_id}", ttl_seconds=86400):
            continue

        correlation = state.check_multi_sensor_correlation(lat, lon)

        if is_explicit_blast or (depth_km <= 2.5 and prox is not None) or correlation:
            severity = "CRITICAL"
            title = f"بصمة انفجار سطحي / استهداف تكتيكي ({mag}M)"
        elif is_shallow:
            severity = "CRITICAL"
            title = f"حدث زلزالي سطحي ضحل جداً (احتمال انفجار مستودعات أو ضربة تحصينات - {mag}M)"
        else:
            severity = "HIGH"
            title = f"نشاط زلزالي قرب موقع عسكري/استراتيجي ({mag}M)"

        event_dt = datetime.fromtimestamp(event_time_ms / 1000.0, tz=timezone.utc).strftime("%H:%M:%S UTC")
        telemetry = [
            f"القوة المسجلة: <code>{mag} ريختر</code> | العمق: <code>{depth_km:.1f} كم</code> {'⚠️ (سطحي/ضحل)' if is_shallow else ''}",
            f"التصنيف الموجي الخام: <code>{event_type.upper()}</code>",
            f"وقت التسجيل (UTC): <code>{event_dt}</code>"
        ]

        usgs_url = props.get("url", "https://earthquake.usgs.gov")
        await send_telegram_alert(
            client=client,
            severity=severity,
            category="SEISMIC / KINETIC BLAST SIGNATURE",
            title=title,
            sector_name=sector_name,
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            extra_links=[("📊 التقرير الموجي الخام (USGS)", usgs_url)],
            label_code=f"MAG-{mag}",
            correlation_note=correlation
        )


# ==========================================
# COLLECTOR 3: NASA FIRMS THERMAL STRIKE CLUSTERS
# ==========================================
async def poll_thermal_anomalies(client: httpx.AsyncClient):
    state.stats["thermal_scans"] += 1
    if not config.NASA_FIRMS_MAP_KEY:
        return

    bbox = "32.0,11.5,63.5,40.0"
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{config.NASA_FIRMS_MAP_KEY}/VIIRS_SNPP_NRT/{bbox}/1"

    try:
        resp = await client.get(url, timeout=20.0)
        if resp.status_code != 200 or "Invalid" in resp.text:
            return
    except Exception as exc:
        logger.warning(f"NASA FIRMS poll error: {exc}")
        return

    reader = csv.DictReader(io.StringIO(resp.text))
    candidates = []
    for row in reader:
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            frp = float(row.get("frp") or 0.0)
            conf = str(row.get("confidence", "n")).lower()
            daynight = str(row.get("daynight", "D")).upper()
            acq_date = row.get("acq_date", "")
            acq_time = row.get("acq_time", "")
        except Exception:
            continue

        sector_name = match_sector(lat, lon)
        if not sector_name or is_known_oil_flare(lat, lon) or conf == "l":
            continue

        prox = check_strategic_proximity(lat, lon)
        min_frp = config.MIN_FRP_NIGHT_MW if daynight == "N" else config.MIN_FRP_DAY_MW
        if frp < min_frp and prox is None:
            continue

        candidates.append({
            "lat": lat, "lon": lon, "frp": frp, "conf": conf,
            "daynight": daynight, "acq_date": acq_date, "acq_time": acq_time,
            "sector_name": sector_name, "prox": prox
        })

    for item in candidates:
        lat, lon = item["lat"], item["lon"]
        dedup_key = f"THERMAL_{item['acq_date']}_{lat:.2f}_{lon:.2f}"
        if state.is_duplicate(dedup_key, ttl_seconds=43200):
            continue

        cluster_count = sum(
            1 for other in candidates
            if haversine_km(lat, lon, other["lat"], other["lon"]) <= 6.0
        )

        correlation = state.check_multi_sensor_correlation(lat, lon)
        is_critical = cluster_count >= 3 or item["prox"] is not None or item["frp"] >= 60.0 or correlation is not None
        severity = "CRITICAL" if is_critical else "HIGH"

        if cluster_count >= 3:
            title = f"شذوذ حراري عنقودي ({cluster_count} بؤر متقاربة - مؤشر قصف مكثف أو غارة جوية)"
        elif item["prox"] is not None:
            title = f"بصمة حرارية / استهداف ناري بجوار موقع عسكري أو جبهة ({item['frp']} MW)"
        else:
            title = f"شذوذ حراري عالي الطاقة مرصود بالأقمار الصناعية ({item['frp']} MW)"

        telemetry = [
            f"الطاقة الإشعاعية (FRP): <code>{item['frp']} MW</code> | البؤر المشتعلة: <code>{cluster_count}</code>",
            f"التوقيت الفضائي: <code>{item['acq_date']} {item['acq_time']} UTC</code> ({'ليلي 🌙' if item['daynight']=='N' else 'نهاري ☀️'})",
            f"المستشعر الفضائي: <code>VIIRS S-NPP Infrared</code>"
        ]

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="THERMAL STRIKE / FIRMS SIGNATURE",
            title=title,
            sector_name=item["sector_name"],
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            label_code=f"FRP-{int(item['frp'])}MW",
            correlation_note=correlation
        )


# ==========================================
# COLLECTOR 4: NGA NAVIGATIONAL & MISSILE WARNINGS
# ==========================================
def parse_nga_coordinates(text: str) -> Optional[Tuple[float, float]]:
    pattern = r"(\d{2})-(\d{2})(?:\.(\d+))?([NS])\s+(\d{3}|\d{2})-(\d{2})(?:\.(\d+))?([EW])"
    match = re.search(pattern, text)
    if not match:
        return None
    try:
        lat_deg = float(match.group(1))
        lat_min = float(match.group(2))
        lat_dec = float(f"0.{match.group(3)}") if match.group(3) else 0.0
        lat = lat_deg + (lat_min + lat_dec) / 60.0
        if match.group(4) == "S":
            lat = -lat

        lon_deg = float(match.group(5))
        lon_min = float(match.group(6))
        lon_dec = float(f"0.{match.group(7)}") if match.group(7) else 0.0
        lon = lon_deg + (lon_min + lon_dec) / 60.0
        if match.group(8) == "W":
            lon = -lon

        return round(lat, 4), round(lon, 4)
    except Exception:
        return None


async def poll_nga_warnings(client: httpx.AsyncClient):
    state.stats["nga_scans"] += 1
    url = "https://msi.nga.mil/api/publications/broadcast-warn?output=json&status=A"

    try:
        resp = await client.get(url, timeout=20.0)
        if resp.status_code != 200:
            return
        data = resp.json()
    except Exception as exc:
        logger.warning(f"NGA MSI feed error: {exc}")
        return

    warnings = data.get("broadcast-warn", [])
    for warn in warnings[:60]:
        msg_year = warn.get("msgYear")
        msg_num = warn.get("msgNumber")
        nav_area = str(warn.get("navArea", ""))
        subregion = str(warn.get("subregion", ""))
        text = str(warn.get("text", "")).upper()

        matched_kw = [kw for kw in config.NGA_CRITICAL_KEYWORDS if kw in text]
        if not matched_kw:
            continue

        me_regions = (
            "PERSIAN GULF", "RED SEA", "ARABIAN SEA", "GULF OF OMAN",
            "GULF OF ADEN", "EASTERN MEDITERRANEAN", "STRAIT OF HORMUZ",
            "BAB EL MANDEB", "ISRAEL", "LEBANON", "SYRIA", "IRAN", "YEMEN", "CYPRUS", "SAUDI"
        )
        in_me_text = any(r in text for r in me_regions) or subregion in ("62", "63", "26")

        coords = parse_nga_coordinates(text)
        sector_name = None
        lat, lon = None, None
        if coords:
            lat, lon = coords
            sector_name = match_sector(lat, lon)

        if not (sector_name or in_me_text):
            continue

        if not sector_name:
            sector_name = "المجال البحري والجوي للشرق الأوسط والبحر الأحمر (NAVAREA)"

        dedup_key = f"NGA_{nav_area}_{msg_year}_{msg_num}"
        if state.is_duplicate(dedup_key, ttl_seconds=86400 * 7):
            continue

        if state.stats["nga_scans"] == 1:
            continue

        severity = "CRITICAL" if ("MISSILE" in matched_kw or "ROCKET" in matched_kw) else "HIGH"
        title = f"إشعار عمليات عسكرية وإغلاق مجال (NGA {nav_area} {msg_num}/{msg_year})"

        clean_excerpt = " ".join(text.split())[:260] + "..."
        telemetry = [
            f"رقم الإشعار العسكري: <code>{nav_area} {msg_num}/{msg_year}</code>",
            f"طبيعة التحذير: <code>{', '.join(matched_kw)}</code>",
            f"النص الملاحي الخام: <code>{clean_excerpt}</code>"
        ]

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="NOTAM / NGA MISSILE & NAV WARNING",
            title=title,
            sector_name=sector_name,
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            extra_links=[("⚓ المصدر الخام (NGA MSI)", "https://msi.nga.mil/NavWarnings")],
            label_code=f"NGA-{msg_num}"
        )


# ==========================================
# BACKGROUND ORCHESTRATOR LOOP
# ==========================================
async def osint_scheduler_loop():
    logger.info("Starting Autonomous OSINT Fusion Center v4 (WarLeaks Edition)...")
    headers = {
        "User-Agent": "OSINT-Telemetry-Monitor/4.0 (Strategic Research; +https://github.com)"
    }
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        last_aviation = 0.0
        last_seismic = 0.0
        last_thermal = 0.0
        last_nga = 0.0

        while True:
            now = time.time()
            try:
                if now - last_aviation >= config.POLL_INTERVAL_AVIATION:
                    await poll_military_aviation(client)
                    last_aviation = time.time()

                if now - last_seismic >= config.POLL_INTERVAL_SEISMIC:
                    await poll_seismic_anomalies(client)
                    last_seismic = time.time()

                if now - last_thermal >= config.POLL_INTERVAL_THERMAL:
                    await poll_thermal_anomalies(client)
                    last_thermal = time.time()

                if now - last_nga >= config.POLL_INTERVAL_NGA:
                    await poll_nga_warnings(client)
                    last_nga = time.time()

            except Exception as exc:
                logger.error(f"Scheduler loop error: {exc}")

            await asyncio.sleep(10)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(osint_scheduler_loop())
    yield
    task.cancel()


# ==========================================
# FASTAPI SERVER & INTERACTIVE TEST DASHBOARD v4
# ==========================================
app = FastAPI(title="OSINT Strategic Fusion Center v4 - WarLeaks", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {
        "status": "operational",
        "version": "v4.0 - Exclusive US/IL/SA Aviation + Yemen/ME War Context + WarLeaks Watermark",
        "stats": state.stats,
        "cached_events": len(state.seen_events)
    }


@app.post("/api/test-alert")
async def trigger_test_alert(request: Request):
    """
    Triggers an immediate simulated OSINT alert with:
    - Arabic Watermark "خاص بتسريبات الحرب" on the Tactical Map
    - Military Intelligence SITREP Prompt (Yemen/Saudi/Houthi or Iran/ME War)
    """
    try:
        body = await request.json()
        test_type = body.get("type", "saudi_yemen")
    except Exception:
        test_type = "saudi_yemen"

    headers = {"User-Agent": "OSINT-Telemetry-Monitor/4.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        if test_type == "saudi_yemen":
            sample_trail = [
                (17.9500, 43.1000),
                (17.6500, 43.3500),
                (17.3500, 43.5500),
                (17.1200, 43.7200)
            ]
            ok, msg = await send_telegram_alert(
                client=client,
                severity="CRITICAL",
                category="MILITARY AVIATION & SIGINT",
                title="مدار عملياتي نشط: طائرة إنذار مبكر وقيادة جوية E-3 Sentry AWACS",
                sector_name="مسرح عمليات اليمن والحدود الجنوبية السعودية والبحر الأحمر",
                lat=17.1200,
                lon=43.7200,
                telemetry_lines=[
                    "النداء اللاسلكي: <code>RSAF18</code> | كود ICAO: <code>7102A4</code>",
                    "الطراز: <code>E3TF (AWACS)</code> | الارتفاع: <code>31,000 ft</code>",
                    "السرعة: <code>385 kt</code> | الاتجاه: <code>195°</code>",
                    "النمط التكتيكي: 🔄 مدار عملياتي مستمر لمراقبة الأجواء الحدودية وجبهتي صعدة ومأرب"
                ],
                extra_links=[("✈️ ADS-B Exchange Live", "https://globe.adsbexchange.com/?icao=7102a4")],
                heading=195.0,
                is_orbiting=True,
                label_code="RSAF18",
                trail_coords=sample_trail,
                operator_name="القوات الجوية الملكية السعودية 🇸🇦 (RSAF)"
            )
        elif test_type == "thermal":
            ok, msg = await send_telegram_alert(
                client=client,
                severity="CRITICAL",
                category="THERMAL STRIKE / FIRMS SIGNATURE",
                title="شذوذ حراري عنقودي (4 بؤر متقاربة - مؤشر قصف مكثف أو غارة جوية)",
                sector_name="مسرح عمليات اليمن والحدود الجنوبية السعودية والبحر الأحمر",
                lat=15.4850,
                lon=45.2800,
                telemetry_lines=[
                    "الطاقة الإشعاعية (FRP): <code>92.4 MW (انفجارات عالية الطاقة)</code>",
                    "المستشعر الفضائي: <code>VIIRS S-NPP Infrared</code>",
                    "فلتر الحقول النفطية: <code>خارج نطاق شعلات صافر الروتينية</code>"
                ],
                label_code="MARIB-FRP",
                correlation_note="تطابق رصد جوي/ميداني: رُصد تحليق عسكري لـ (القوات الجوية الملكية السعودية 🇸🇦 - RSAF) على بُعد 75 كم قبل 18 دقيقة من الحدث."
            )
        else:
            sample_trail = [
                (32.1000, 34.1500),
                (32.4500, 34.3000),
                (32.8500, 34.5000),
                (33.1500, 34.6500)
            ]
            ok, msg = await send_telegram_alert(
                client=client,
                severity="CRITICAL",
                category="MILITARY AVIATION & EW SIGINT",
                title="مدار عملياتي نشط: Gulfstream G550 Nachshon/Oron (استطلاع راداري وإنذار مبكر)",
                sector_name="جبهة بلاد الشام وشرق المتوسط وفلسطين",
                lat=33.1500,
                lon=34.6500,
                telemetry_lines=[
                    "النداء اللاسلكي: <code>IAF224</code> | كود ICAO: <code>738A54</code>",
                    "الطراز: <code>GLF5 (Nachshon)</code> | الارتفاع: <code>41,000 ft</code>",
                    "النمط التكتيكي: 🔄 مدار مسح راداري مستمر + ⚡ تشويش حرب إلكترونية (GPS Jamming NIC<=2)"
                ],
                extra_links=[("✈️ ADS-B Exchange Live", "https://globe.adsbexchange.com/?icao=738a54")],
                heading=35.0,
                is_orbiting=True,
                label_code="IAF224",
                trail_coords=sample_trail,
                is_ew_jamming=True,
                operator_name="سلاح الجو الإسرائيلي 🇮🇱 (IAF)"
            )

    return JSONResponse({"ok": ok, "message": msg})


@app.get("/", response_class=HTMLResponse)
async def status_dashboard():
    ai_badge = (
        f"مفعّل ({state.stats['active_ai_model']})"
        if config.GEMINI_API_KEY
        else "غير مفعّل (أضف GEMINI_API_KEY في Render)"
    )
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT Fusion v4 — خاص بتسريبات الحرب</title>
    <style>
        :root {{
            --bg: #0a0a0c;
            --card: #121216;
            --border: #232329;
            --text: #f5f5f7;
            --muted: #86868b;
            --accent: #30d158;
            --primary: #0a84ff;
            --gold: #ffd60a;
            --danger: #ff453a;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg);
            color: var(--text);
            font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Segoe UI", Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            padding: 20px;
        }}
        .container {{
            width: 100%;
            max-width: 820px;
            background: var(--card);
            border: 1px solid var(--border);
            border-radius: 22px;
            padding: 32px;
            box-shadow: 0 24px 48px rgba(0,0,0,0.65);
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .title-group h1 {{
            font-size: 20px;
            font-weight: 600;
            letter-spacing: -0.3px;
        }}
        .title-group p {{
            color: var(--muted);
            font-size: 13px;
            margin-top: 4px;
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: rgba(48, 209, 88, 0.12);
            color: var(--accent);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 12px;
            font-weight: 600;
        }}
        .dot {{
            width: 8px;
            height: 8px;
            background: var(--accent);
            border-radius: 50%;
            box-shadow: 0 0 8px var(--accent);
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(135px, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}
        .metric {{
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 15px;
        }}
        .metric span {{
            display: block;
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 6px;
        }}
        .metric strong {{
            font-size: 20px;
            font-weight: 600;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
        }}
        .test-panel {{
            background: rgba(10, 132, 255, 0.06);
            border: 1px solid rgba(10, 132, 255, 0.25);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 24px;
        }}
        .test-panel h3 {{
            font-size: 15px;
            margin-bottom: 6px;
            color: #fff;
        }}
        .test-panel p {{
            font-size: 13px;
            color: var(--muted);
            margin-bottom: 16px;
            line-height: 1.5;
        }}
        .btn-group {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .btn {{
            cursor: pointer;
            border: none;
            border-radius: 10px;
            padding: 11px 16px;
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            background: var(--primary);
            transition: opacity 0.2s, transform 0.1s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .btn.saudi {{ background: #1f8b4c; }}
        .btn.secondary {{ background: var(--danger); }}
        .btn:active {{ transform: scale(0.98); }}
        .btn:disabled {{ opacity: 0.5; cursor: not-allowed; }}
        #test-status {{
            margin-top: 12px;
            font-size: 13px;
            font-weight: 500;
            display: none;
            padding: 10px 14px;
            border-radius: 8px;
        }}
        .footer {{
            font-size: 12px;
            color: var(--muted);
            display: flex;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 8px;
            border-top: 1px solid var(--border);
            padding-top: 16px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="title-group">
                <h1>غرفة عمليات تسريبات الحرب (OSINT Fusion v4)</h1>
                <p>رصد حصري للطيران (الأمريكي 🇺🇸 / الإسرائيلي 🇮🇱 / السعودي 🇸🇦) + جبهات اليمن والشرق الأوسط</p>
            </div>
            <div class="badge">
                <span class="dot"></span>
                ONLINE 24/7
            </div>
        </div>

        <div class="grid">
            <div class="metric">
                <span>المنشورات المرسلة</span>
                <strong>{state.stats["alerts_sent"]}</strong>
            </div>
            <div class="metric">
                <span>التقارير الاستخباراتية (AI)</span>
                <strong>{state.stats["ai_analyses"]}</strong>
            </div>
            <div class="metric">
                <span>تقاطع المصادر المؤكد</span>
                <strong>{state.stats["correlated_strikes"]}</strong>
            </div>
            <div class="metric">
                <span>رصد تشويش GPS/EW</span>
                <strong>{state.stats["ew_jamming_events"]}</strong>
            </div>
            <div class="metric">
                <span>مسح الرادار الجوي</span>
                <strong>{state.stats["aviation_scans"]}</strong>
            </div>
        </div>

        <div class="test-panel">
            <h3>⚡ لوحة التجربة الفورية (مع توقيع "خاص بتسريبات الحرب" على الخريطة)</h3>
            <p>اختبر الآن البرومبت الاستخباراتي العسكري الجديد وتوقيع الخريطة في مسرح اليمن والحدود السعودية أو جبهة شرق المتوسط:</p>
            <div class="btn-group">
                <button class="btn saudi" id="btn-sa" onclick="sendTest('saudi_yemen')">
                    🇸🇦 تجربة طيران إنذار مبكر سعودي (جبهة صعدة/اليمن)
                </button>
                <button class="btn secondary" id="btn-th" onclick="sendTest('thermal')">
                    🔥 تجربة قصف حراري وتقاطع استخباراتي (جبهة مأرب)
                </button>
                <button class="btn" id="btn-il" onclick="sendTest(' aviation_il')">
                    🇮🇱 تجربة استطلاع وتشويش إلكتروني (شرق المتوسط)
                </button>
            </div>
            <div id="test-status"></div>
        </div>

        <div class="footer">
            <span>المحلل الاستخباراتي: {ai_badge}</span>
            <span>التوقيع المدمج: خاص بتسريبات الحرب</span>
            <span>آخر منشور: {state.stats["last_alert_time"]}</span>
        </div>
    </div>

    <script>
        async function sendTest(type) {{
            const statusBox = document.getElementById('test-status');
            const btns = document.querySelectorAll('.btn');
            btns.forEach(b => b.disabled = true);

            statusBox.style.display = 'block';
            statusBox.style.background = 'rgba(255,255,255,0.06)';
            statusBox.style.color = '#f5f5f7';
            statusBox.innerText = '⏳ جاري رسم الخريطة التكتيكية بتوقيع (خاص بتسريبات الحرب) وصياغة البرقية الاستخباراتية...';

            try {{
                const res = await fetch('/api/test-alert', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ type: type.trim() }})
                }});
                const data = await res.json();
                if (data.ok) {{
                    statusBox.style.background = 'rgba(48, 209, 88, 0.15)';
                    statusBox.style.color = '#30d158';
                    statusBox.innerText = '✅ ' + data.message + ' تفقد قناتك الآن!';
                }} else {{
                    statusBox.style.background = 'rgba(255, 69, 58, 0.15)';
                    statusBox.style.color = '#ff453a';
                    statusBox.innerText = '❌ فشل الإرسال: ' + data.message;
                }}
            }} catch (err) {{
                statusBox.style.background = 'rgba(255, 69, 58, 0.15)';
                statusBox.style.color = '#ff453a';
                statusBox.innerText = '❌ حدث خطأ في الشبكة: ' + err;
            }} finally {{
                btns.forEach(b => b.disabled = false);
            }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, log_level="info")
