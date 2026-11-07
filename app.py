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

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("OSINT-Core-v2")


# ==========================================
# GEOSPATIAL & UTILITY FUNCTIONS
# ==========================================
def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * r * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def match_sector(lat: float, lon: float) -> Optional[str]:
    for _, sec in config.SECTORS.items():
        if sec["min_lat"] <= lat <= sec["max_lat"] and sec["min_lon"] <= lon <= sec["max_lon"]:
            return sec["name_ar"]
    return None


def check_strategic_proximity(lat: float, lon: float) -> Optional[Tuple[str, float]]:
    for site in config.STRATEGIC_SITES:
        dist = haversine_km(lat, lon, site["lat"], site["lon"])
        if dist <= site["radius_km"]:
            return site["name"], round(dist, 1)
    return None


def is_known_oil_flare(lat: float, lon: float) -> bool:
    for flare in config.KNOWN_OIL_FLARE_ZONES:
        if haversine_km(lat, lon, flare["lat"], flare["lon"]) <= flare["radius_km"]:
            return True
    return False


# ==========================================
# TACTICAL STATIC MAP GENERATOR (RADAR + SATELLITE)
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
    label_code: str = "TARGET"
) -> bytes:
    """
    Fetches real Esri World Imagery / Dark Canvas map tiles around (lat, lon),
    applies a high-contrast tactical dark radar filter, and draws targeting reticles,
    heading vectors, proximity rings, and telemetry HUD overlay.
    """
    zoom = 9 if "AVIATION" in category else 11
    cx, cy = deg2num_float(lat, lon, zoom)
    center_tile_x, center_tile_y = int(cx), int(cy)

    # Stitch a 3x3 tile grid (768x768) then crop 640x400 centered on exact coordinates
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

    await asyncio.gather(*(fetch_tile(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)))

    # Calculate exact pixel position of target on the 768x768 canvas
    px_x = int((cx - center_tile_x + 1) * 256)
    px_y = int((cy - center_tile_y + 1) * 256)

    # Crop 640x400 centered on (px_x, px_y)
    w, h = 640, 400
    left = max(0, min(768 - w, px_x - w // 2))
    top = max(0, min(768 - h, px_y - h // 2))
    cropped = grid_img.crop((left, top, left + w, top + h)).convert("RGBA")

    # Target point inside cropped image
    tx_px = px_x - left
    ty_px = px_y - top

    # Apply Dark Tactical Radar Overlay Tint
    overlay = Image.new("RGBA", (w, h), (8, 14, 24, 115))
    draw = ImageDraw.Draw(overlay)

    # Draw subtle tactical coordinate grid lines
    for gx in range(0, w, 64):
        draw.line([(gx, 0), (gx, h)], fill=(48, 209, 88, 28), width=1)
    for gy in range(0, h, 64):
        draw.line([(0, gy), (w, gy)], fill=(48, 209, 88, 28), width=1)

    primary_color = (255, 69, 58, 255) if severity == "CRITICAL" else (255, 159, 10, 255)
    glow_color = (255, 69, 58, 65) if severity == "CRITICAL" else (255, 159, 10, 65)

    # Draw outer pulsing radar rings
    for r in (65, 38):
        draw.ellipse([tx_px - r, ty_px - r, tx_px + r, ty_px + r], outline=primary_color, width=2)
    draw.ellipse([tx_px - 22, ty_px - 22, tx_px + 22, ty_px + 22], fill=glow_color)

    # Draw Crosshair Reticle
    draw.line([(tx_px - 80, ty_px), (tx_px - 12, ty_px)], fill=primary_color, width=2)
    draw.line([(tx_px + 12, ty_px), (tx_px + 80, ty_px)], fill=primary_color, width=2)
    draw.line([(tx_px, ty_px - 80), (tx_px, ty_px - 12)], fill=primary_color, width=2)
    draw.line([(tx_px, ty_px + 12), (tx_px, ty_px + 80)], fill=primary_color, width=2)

    # If Aviation: Draw Heading Vector or Orbit Ring
    if heading is not None:
        rad = math.radians(heading - 90)
        end_x = int(tx_px + 75 * math.cos(rad))
        end_y = int(ty_px + 75 * math.sin(rad))
        draw.line([(tx_px, ty_px), (end_x, end_y)], fill=(10, 210, 255, 255), width=3)
        draw.ellipse([end_x - 4, end_y - 4, end_x + 4, end_y + 4], fill=(10, 210, 255, 255))

    if is_orbiting:
        draw.ellipse([tx_px - 90, ty_px - 50, tx_px + 90, ty_px + 50], outline=(10, 210, 255, 220), width=2)

    # Center target pin
    draw.ellipse([tx_px - 5, ty_px - 5, tx_px + 5, ty_px + 5], fill=(255, 255, 255, 255), outline=primary_color, width=2)

    # Top & Bottom HUD Telemetry Bars
    draw.rectangle([0, 0, w, 36], fill=(10, 12, 16, 220))
    draw.rectangle([0, h - 32, w, h], fill=(10, 12, 16, 220))

    font = ImageFont.load_default()
    hud_top = f"OSINT TACTICAL RECON // {category} // [{severity}]"
    hud_bottom = f"LAT: {lat:.4f} N   LON: {lon:.4f} E   ID: {label_code}   ZOOM: Z{zoom}"
    draw.text((14, 11), hud_top, fill=primary_color, font=font)
    draw.text((14, h - 22), hud_bottom, fill=(220, 220, 230, 255), font=font)

    combined = Image.alpha_composite(cropped, overlay).convert("RGB")
    buf = io.BytesIO()
    combined.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


# ==========================================
# STATE & DEDUPLICATION ENGINE
# ==========================================
class StateEngine:
    def __init__(self):
        self.seen_events: Dict[str, float] = {}
        self.aircraft_tracks: Dict[str, List[Tuple[float, float, float, float]]] = {}
        self.stats = {
            "started_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "alerts_sent": 0,
            "aviation_scans": 0,
            "seismic_scans": 0,
            "thermal_scans": 0,
            "nga_scans": 0,
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

    def record_aircraft_heading(self, hex_code: str, lat: float, lon: float, track: float) -> bool:
        now = time.time()
        history = self.aircraft_tracks.get(hex_code, [])
        history = [pt for pt in history if now - pt[0] <= 1500]
        history.append((now, lat, lon, track))
        self.aircraft_tracks[hex_code] = history

        if len(history) < 4:
            return False

        total_turn = 0.0
        for i in range(1, len(history)):
            diff = abs(history[i][3] - history[i - 1][3])
            if diff > 180:
                diff = 360 - diff
            total_turn += diff

        displacement = haversine_km(history[0][1], history[0][2], history[-1][1], history[-1][2])
        return total_turn >= 160.0 and displacement < 90.0


state = StateEngine()


# ==========================================
# TELEGRAM PRESENTATION & DISPATCHER (WITH PHOTO MAP)
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
    label_code: str = "OSINT"
) -> Tuple[bool, str]:
    if not config.TELEGRAM_BOT_TOKEN or not config.TELEGRAM_CHAT_ID:
        msg = "TELEGRAM_BOT_TOKEN أو TELEGRAM_CHAT_ID غير مضاف في إعدادات Render."
        logger.warning(msg)
        return False, msg

    badge = "🔴 CRITICAL" if severity == "CRITICAL" else "🟠 HIGH PRIORITY"
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    msg_parts = [
        f"<b>{badge} | {category}</b>",
        "━━━━━━━━━━━━━━━━━━━━",
        f"<b>الحدث:</b> {title}",
        f"<b>القطاع:</b> {sector_name}",
    ]

    if lat is not None and lon is not None:
        msg_parts.append(f"<b>الإحداثيات:</b> <code>{lat:.4f}, {lon:.4f}</code>")
        prox = check_strategic_proximity(lat, lon)
        if prox:
            site_name, dist_km = prox
            msg_parts.append(f"⚠️ <b>قرب موقع حساس:</b> {site_name} ({dist_km} كم)")

    msg_parts.append("")
    msg_parts.append("<b>البيانات الخام (Raw Telemetry):</b>")
    for line in telemetry_lines:
        msg_parts.append(f"• {line}")

    msg_parts.append("━━━━━━━━━━━━━━━━━━━━")
    msg_parts.append(f"⏱ <code>{now_str}</code>")

    text = "\n".join(msg_parts)

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
            {"text": "🔥 NASA FIRMS Thermal", "url": firms_url}
        ])

    if extra_links:
        row = [{"text": label, "url": url} for label, url in extra_links]
        inline_keyboard.append(row)

    reply_markup_json = json.dumps({"inline_keyboard": inline_keyboard}) if inline_keyboard else None

    # If coordinates exist, generate tactical map image and send via sendPhoto
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
                label_code=label_code
            )
            photo_url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendPhoto"
            data_form = {
                "chat_id": config.TELEGRAM_CHAT_ID,
                "caption": text,
                "parse_mode": "HTML"
            }
            if reply_markup_json:
                data_form["reply_markup"] = reply_markup_json

            files = {"photo": ("tactical_map.jpg", map_bytes, "image/jpeg")}
            resp = await client.post(photo_url, data=data_form, files=files, timeout=20.0)
            if resp.status_code == 200:
                state.stats["alerts_sent"] += 1
                state.stats["last_alert_time"] = now_str
                return True, "تم إرسال التنبيه مع الخريطة التكتيكية بنجاح."
            else:
                logger.warning(f"sendPhoto failed ({resp.status_code}), falling back to sendMessage: {resp.text}")
        except Exception as exc:
            logger.warning(f"Map generation/sendPhoto error, falling back to text: {exc}")

    # Fallback or coordinate-less alert via sendMessage
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
            return True, "تم إرسال التنبيه النصي بنجاح."
        return False, f"خطأ من تيليجرام ({resp.status_code}): {resp.text}"
    except Exception as exc:
        return False, f"فشل الاتصال بواجهة تيليجرام: {exc}"


# ==========================================
# COLLECTOR 1: MILITARY AVIATION & ISR (ADS-B RAW)
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

    for ac in aircraft_list:
        lat, lon = ac.get("lat"), ac.get("lon")
        if lat is None or lon is None:
            continue

        sector_name = match_sector(lat, lon)
        if not sector_name:
            continue

        hex_code = str(ac.get("hex", "")).upper()
        callsign = str(ac.get("flight", "")).strip().upper() or "UNKNOWN"
        ac_type = str(ac.get("t", "")).strip().upper()
        alt_baro = ac.get("alt_baro", "N/A")
        gs = ac.get("gs", "N/A")
        track = float(ac.get("track", 0.0) or 0.0)
        squawk = str(ac.get("squawk", ""))

        type_desc = config.HIGH_VALUE_AIRCRAFT_TYPES.get(ac_type)
        is_strategic_callsign = callsign.startswith(config.MILITARY_CALLSIGN_PREFIXES)
        is_emergency = squawk in ("7700", "7600", "7500")
        is_orbiting = state.record_aircraft_heading(hex_code, lat, lon, track)

        if not (type_desc or is_strategic_callsign or is_emergency or is_orbiting):
            continue

        severity = "CRITICAL" if (is_orbiting or is_emergency or ac_type in ("R135", "E3CF", "E3TF", "B52", "B1", "RQ4")) else "HIGH"
        dedup_suffix = "ORBIT" if is_orbiting else "DETECT"
        if state.is_duplicate(f"AIR_{hex_code}_{dedup_suffix}", ttl_seconds=7200):
            continue

        pattern_note = "🔄 مدار دائري نشط (Orbit/Racetrack - مؤشر عمليات قتالية أو تزود بالوقود)" if is_orbiting else "عبور / دورية استطلاع نشطة"
        title = type_desc if type_desc else f"طائرة عسكرية خاصة ({ac_type or 'غير مصنف'})"
        if is_orbiting:
            title = f"نشاط عملياتي (مدار مستمر): {title}"

        telemetry = [
            f"النداء اللاسلكي (Callsign): <code>{callsign}</code>",
            f"كود الإيكاو (ICAO Hex): <code>{hex_code}</code>",
            f"الطراز الخام (Type): <code>{ac_type or 'N/A'}</code>",
            f"الارتفاع (Altitude): <code>{alt_baro} ft</code> | السرعة: <code>{gs} kt</code>",
            f"الاتجاه (Heading): <code>{track}°</code> | Squawk: <code>{squawk or 'N/A'}</code>",
            f"نمط الطيران: {pattern_note}"
        ]

        adsb_url = f"https://globe.adsbexchange.com/?icao={hex_code.lower()}"
        airframes_url = f"https://app.airframes.io/aircraft/{hex_code.lower()}"

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="MILITARY AVIATION / SIGINT",
            title=title,
            sector_name=sector_name,
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            extra_links=[("✈️ ADS-B Exchange", adsb_url), ("📡 ACARS Feed", airframes_url)],
            heading=track,
            is_orbiting=is_orbiting,
            label_code=callsign
        )


# ==========================================
# COLLECTOR 2: SEISMIC & SURFACE EXPLOSIONS (USGS)
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
        place = str(props.get("place", "Unknown Location"))

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

        if is_explicit_blast or (depth_km <= 2.5 and prox is not None):
            severity = "CRITICAL"
            title = f"بصمة انفجار سطحي / ارتجاج عالي الخطورة ({mag}M)"
        elif is_shallow:
            severity = "CRITICAL"
            title = f"حدث زلزالي ضحل جداً (احتمال انفجار ضخم أو ضربة عميقة - {mag}M)"
        else:
            severity = "HIGH"
            title = f"نشاط زلزالي في قطاع استراتيجي ({mag}M)"

        event_dt = datetime.fromtimestamp(event_time_ms / 1000.0, tz=timezone.utc).strftime("%H:%M:%S UTC")
        telemetry = [
            f"القوة المسجلة (Magnitude): <code>{mag} M</code>",
            f"العمق الجيولوجي (Depth): <code>{depth_km:.1f} km</code> {'⚠️ (سطحي/ضحل جداً)' if is_shallow else ''}",
            f"التصنيف الخام للمرصد: <code>{event_type.upper()}</code>",
            f"النطاق المرجعي: <code>{place}</code>",
            f"وقت التسجيل الزلزالي: <code>{event_dt}</code>"
        ]

        usgs_url = props.get("url", "https://earthquake.usgs.gov")
        await send_telegram_alert(
            client=client,
            severity=severity,
            category="SEISMIC / BLAST SIGNATURE",
            title=title,
            sector_name=sector_name,
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            extra_links=[("📊 التقرير الموجي الخام (USGS)", usgs_url)],
            label_code=f"MAG-{mag}"
        )


# ==========================================
# COLLECTOR 3: NASA FIRMS THERMAL ANOMALIES & STRIKE CLUSTERS
# ==========================================
async def poll_thermal_anomalies(client: httpx.AsyncClient):
    """
    Polls NASA FIRMS VIIRS Satellite Thermal Anomalies if NASA_FIRMS_MAP_KEY is provided,
    masks out routine Persian Gulf / Iraq / Iran oil & gas flaring fields,
    and alerts on high-FRP military strikes or clustered bombardment signatures.
    """
    state.stats["thermal_scans"] += 1
    if not config.NASA_FIRMS_MAP_KEY:
        return

    # Bounding box covering all Middle East & Iran sectors: 32E,11N to 63.5E,40N
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
        if not sector_name:
            continue

        # Filter 1: Exclude static known oil & gas flaring fields
        if is_known_oil_flare(lat, lon):
            continue

        # Filter 2: Ignore low-confidence or low radiative power agricultural burns
        if conf == "l":
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

    # Cluster analysis & Alerting
    for item in candidates:
        lat, lon = item["lat"], item["lon"]
        # Round coordinates to ~1km grid for deduplication
        dedup_key = f"THERMAL_{item['acq_date']}_{lat:.2f}_{lon:.2f}"
        if state.is_duplicate(dedup_key, ttl_seconds=43200):
            continue

        # Check how many other thermal points occurred within 6 km (Cluster Strike Detection)
        cluster_count = sum(
            1 for other in candidates
            if haversine_km(lat, lon, other["lat"], other["lon"]) <= 6.0
        )

        is_critical = cluster_count >= 3 or item["prox"] is not None or item["frp"] >= 60.0
        severity = "CRITICAL" if is_critical else "HIGH"

        if cluster_count >= 3:
            title = f"شذوذ حراري عنقودي ({cluster_count} بؤر متقاربة - احتمال قصف مكثف أو غارة)"
        elif item["prox"] is not None:
            title = f"بصمة حرارية / انفجار بجوار منطقة عسكرية حساسة ({item['frp']} MW)"
        else:
            title = f"شذوذ حراري عالي الطاقة مرصود بالأقمار الصناعية ({item['frp']} MW)"

        telemetry = [
            f"الطاقة الإشعاعية (FRP): <code>{item['frp']} MW</code>",
            f"عدد البؤر المشتعلة في النطاق (Cluster): <code>{cluster_count} نقاط</code>",
            f"التوقيت الفضائي (UTC): <code>{item['acq_date']} {item['acq_time']}</code> ({'ليلي 🌙' if item['daynight']=='N' else 'نهاري ☀️'})",
            f"المستشعر الفضائي: <code>VIIRS S-NPP / NOAA Infrared</code>"
        ]

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="NASA FIRMS / THERMAL STRIKE SIGNATURE",
            title=title,
            sector_name=item["sector_name"],
            lat=lat,
            lon=lon,
            telemetry_lines=telemetry,
            label_code=f"FRP-{int(item['frp'])}MW"
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
            "BAB EL MANDEB", "ISRAEL", "LEBANON", "SYRIA", "IRAN", "YEMEN", "CYPRUS"
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
            sector_name = "المجال البحري والجوي للشرق الأوسط (NAVAREA)"

        dedup_key = f"NGA_{nav_area}_{msg_year}_{msg_num}"
        if state.is_duplicate(dedup_key, ttl_seconds=86400 * 7):
            continue

        if state.stats["nga_scans"] == 1:
            continue

        severity = "CRITICAL" if ("MISSILE" in matched_kw or "ROCKET" in matched_kw) else "HIGH"
        title = f"إشعار عمليات عسكرية / إطلاق صواريخ (NGA {nav_area} {msg_num}/{msg_year})"

        clean_excerpt = " ".join(text.split())[:300] + "..."
        telemetry = [
            f"رقم التحذير العسكري: <code>{nav_area} {msg_num}/{msg_year}</code>",
            f"التصنيف المرصود: <code>{', '.join(matched_kw)}</code>",
            f"النص الخام للإشعار: <code>{clean_excerpt}</code>"
        ]

        await send_telegram_alert(
            client=client,
            severity=severity,
            category="NOTAM / NGA NAVIGATIONAL WARNING",
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
    logger.info("Starting Autonomous OSINT Ingestion Engine (Phase 2 Full)...")
    headers = {
        "User-Agent": "OSINT-Telemetry-Monitor/2.0 (Strategic Research; +https://github.com)"
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
# FASTAPI SERVER & INTERACTIVE TEST DASHBOARD
# ==========================================
app = FastAPI(title="OSINT Raw Telemetry Engine v2", lifespan=lifespan)


@app.get("/health")
async def health_check():
    return {
        "status": "operational",
        "phase": "Phase 2 - Tactical Maps, Aviation, Thermal, Seismic & NGA",
        "stats": state.stats,
        "cached_events": len(state.seen_events)
    }


@app.post("/api/test-alert")
async def trigger_test_alert(request: Request):
    """
    Triggers an immediate simulated OSINT alert with a real generated Tactical Map
    to verify Telegram bot configuration, permissions, and visual formatting.
    """
    try:
        body = await request.json()
        test_type = body.get("type", "aviation")
    except Exception:
        test_type = "aviation"

    headers = {"User-Agent": "OSINT-Telemetry-Monitor/2.0"}
    async with httpx.AsyncClient(headers=headers, follow_redirects=True) as client:
        if test_type == "thermal":
            ok, msg = await send_telegram_alert(
                client=client,
                severity="CRITICAL",
                category="TEST SIMULATION | THERMAL STRIKE",
                title="[اختبار النظام] رصد شذوذ حراري عنقودي عالي الطاقة (3 بؤر نشطة)",
                sector_name="العمق الإيراني والخليج العربي (محاكاة تجريبية)",
                lat=32.7508,
                lon=51.8613,
                telemetry_lines=[
                    "حالة الرسالة: <code>اختبار فحص الاتصال والخرائط التكتيكية</code>",
                    "الطاقة الإشعاعية (FRP): <code>78.4 MW (عالي جداً)</code>",
                    "المستشعر الفضائي: <code>VIIRS S-NPP Infrared</code>",
                    "فلتر حقول النفط: <code>تم التحقق (خارج نطاق آبار النفط)</code>"
                ],
                label_code="TEST-FRP"
            )
        else:
            ok, msg = await send_telegram_alert(
                client=client,
                severity="CRITICAL",
                category="TEST SIMULATION | MILITARY AVIATION",
                title="[اختبار النظام] طائرة استطلاع إلكتروني RC-135V Rivet Joint (مدار نشط)",
                sector_name="العمق الإيراني والخليج العربي (محاكاة تجريبية)",
                lat=26.6500,
                lon=55.9000,
                telemetry_lines=[
                    "حالة الرسالة: <code>اختبار فحص الاتصال والخرائط التكتيكية</code>",
                    "النداء اللاسلكي (Callsign): <code>HOMER71</code> | ICAO: <code>AE01CE</code>",
                    "الارتفاع (Altitude): <code>34,500 ft</code> | السرعة: <code>412 kt</code>",
                    "الاتجاه (Heading): <code>285°</code> | Squawk: <code>4412</code>",
                    "نمط الطيران: 🔄 مدار دائري نشط (Orbit/Racetrack)"
                ],
                extra_links=[("✈️ ADS-B Exchange Live", "https://globe.adsbexchange.com/")],
                heading=285.0,
                is_orbiting=True,
                label_code="HOMER71"
            )

    return JSONResponse({"ok": ok, "message": msg})


@app.get("/", response_class=HTMLResponse)
async def status_dashboard():
    firms_status = "مفعّل (Active)" if config.NASA_FIRMS_MAP_KEY else "اختياري (أضف NASA_FIRMS_MAP_KEY)"
    html = f"""<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT Telemetry Core v2</title>
    <style>
        :root {{
            --bg: #0a0a0c;
            --card: #121216;
            --border: #232329;
            --text: #f5f5f7;
            --muted: #86868b;
            --accent: #30d158;
            --primary: #0a84ff;
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
            max-width: 760px;
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
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 14px;
            margin-bottom: 24px;
        }}
        .metric {{
            background: rgba(255,255,255,0.02);
            border: 1px solid var(--border);
            border-radius: 14px;
            padding: 16px;
        }}
        .metric span {{
            display: block;
            color: var(--muted);
            font-size: 12px;
            margin-bottom: 8px;
        }}
        .metric strong {{
            font-size: 22px;
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
        }}
        .btn-group {{
            display: flex;
            gap: 12px;
            flex-wrap: wrap;
        }}
        .btn {{
            cursor: pointer;
            border: none;
            border-radius: 10px;
            padding: 11px 18px;
            font-size: 13px;
            font-weight: 600;
            color: #fff;
            background: var(--primary);
            transition: opacity 0.2s, transform 0.1s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }}
        .btn.secondary {{
            background: #ff453a;
        }}
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
                <h1>محرك الرصد العسكري الخام (OSINT Core v2)</h1>
                <p>الشرق الأوسط وإيران — الخرائط التكتيكية + الطيران + الزلازل + الرصد الحراري</p>
            </div>
            <div class="badge">
                <span class="dot"></span>
                ONLINE 24/7
            </div>
        </div>

        <div class="grid">
            <div class="metric">
                <span>التنبيهات المرسلة</span>
                <strong id="alerts-count">{state.stats["alerts_sent"]}</strong>
            </div>
            <div class="metric">
                <span>مسح الطيران (ADS-B)</span>
                <strong>{state.stats["aviation_scans"]}</strong>
            </div>
            <div class="metric">
                <span>فحص الانفجارات/الزلازل</span>
                <strong>{state.stats["seismic_scans"]}</strong>
            </div>
            <div class="metric">
                <span>فحص الصواريخ (NGA)</span>
                <strong>{state.stats["nga_scans"]}</strong>
            </div>
        </div>

        <div class="test-panel">
            <h3>⚡ لوحة التجربة الفورية (Live Telegram & Map Test)</h3>
            <p>اضغط على أحد الأزرار بالأسفل لتوليد خريطة تكتيكية حية وإرسال إشعار تجريبي فوري إلى قناتك/حسابك في تيليجرام للتأكد من عمل البوت:</p>
            <div class="btn-group">
                <button class="btn" id="btn-air" onclick="sendTest('aviation')">
                    ✈️ إرسال تجربة رصد طائرة استطلاع + خريطة
                </button>
                <button class="btn secondary" id="btn-thermal" onclick="sendTest('thermal')">
                    🔥 إرسال تجربة قصف حراري + خريطة
                </button>
            </div>
            <div id="test-status"></div>
        </div>

        <div class="footer">
            <span>بدء التشغيل: {state.stats["started_at"]}</span>
            <span>حالة الرصد الحراري (FIRMS): {firms_status}</span>
            <span>آخر تنبيه: {state.stats["last_alert_time"]}</span>
        </div>
    </div>

    <script>
        async function sendTest(type) {{
            const statusBox = document.getElementById('test-status');
            const btnAir = document.getElementById('btn-air');
            const btnThermal = document.getElementById('btn-thermal');
            btnAir.disabled = true;
            btnThermal.disabled = true;

            statusBox.style.display = 'block';
            statusBox.style.background = 'rgba(255,255,255,0.06)';
            statusBox.style.color = '#f5f5f7';
            statusBox.innerText = '⏳ جاري سحب صور الأقمار الصناعية ورسم الخريطة التكتيكية وإرسالها إلى تيليجرام...';

            try {{
                const res = await fetch('/api/test-alert', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ type }})
                }});
                const data = await res.json();
                if (data.ok) {{
                    statusBox.style.background = 'rgba(48, 209, 88, 0.15)';
                    statusBox.style.color = '#30d158';
                    statusBox.innerText = '✅ ' + data.message + ' تفقد تيليجرام الآن!';
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
                btnAir.disabled = false;
                btnThermal.disabled = false;
            }}
        }}
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=config.PORT, log_level="info")
