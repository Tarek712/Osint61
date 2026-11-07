import os
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# TELEGRAM, AI & SERVER CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
NASA_FIRMS_MAP_KEY = os.getenv("NASA_FIRMS_MAP_KEY", "")
PORT = int(os.getenv("PORT", 8000))

# Ultra-Light & Fast Model Fallback Cascade (Lowest Token Cost & Highest Speed)
GEMINI_MODEL_CASCADE = [
    GEMINI_MODEL,
    "gemini-3-flash-lite",
    "gemini-flash-lite-latest",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash"
]

# Polling intervals (in seconds)
POLL_INTERVAL_AVIATION = int(os.getenv("POLL_INTERVAL_AVIATION", 180))  # 3 minutes
POLL_INTERVAL_SEISMIC = int(os.getenv("POLL_INTERVAL_SEISMIC", 180))    # 3 minutes
POLL_INTERVAL_THERMAL = int(os.getenv("POLL_INTERVAL_THERMAL", 300))    # 5 minutes
POLL_INTERVAL_NGA = int(os.getenv("POLL_INTERVAL_NGA", 600))            # 10 minutes
POLL_INTERVAL_IODA = int(os.getenv("POLL_INTERVAL_IODA", 600))          # 10 minutes

STARTUP_LOOKBACK_MINUTES = int(os.getenv("STARTUP_LOOKBACK_MINUTES", 20))

# Thermal Filtering Thresholds (MW)
MIN_FRP_DAY_MW = float(os.getenv("MIN_FRP_DAY_MW", 25.0))
MIN_FRP_NIGHT_MW = float(os.getenv("MIN_FRP_NIGHT_MW", 12.0))

# ==========================================
# GEOSPATIAL BOUNDING BOXES (MIDDLE EAST & IRAN)
# ==========================================
SECTORS = {
    "IRAN_AND_GULF": {
        "name_ar": "العمق الإيراني والخليج العربي",
        "min_lat": 24.0, "max_lat": 39.8,
        "min_lon": 44.0, "max_lon": 63.3,
        "center_lat": 32.0, "center_lon": 53.0,
        "radius_nm": 250
    },
    "LEVANT_AND_EAST_MED": {
        "name_ar": "بلاد الشام وشرق المتوسط",
        "min_lat": 31.0, "max_lat": 37.5,
        "min_lon": 32.0, "max_lon": 42.5,
        "center_lat": 34.2, "center_lon": 36.5,
        "radius_nm": 250
    },
    "IRAQ_CORRIDOR": {
        "name_ar": "الممر الجوي العراقي والجزيرة",
        "min_lat": 29.0, "max_lat": 37.5,
        "min_lon": 38.5, "max_lon": 48.5,
        "center_lat": 33.3, "center_lon": 43.8,
        "radius_nm": 250
    },
    "RED_SEA_BAB_EL_MANDEB": {
        "name_ar": "البحر الأحمر وباب المندب",
        "min_lat": 11.5, "max_lat": 22.0,
        "min_lon": 37.0, "max_lon": 46.0,
        "center_lat": 15.5, "center_lon": 42.0,
        "radius_nm": 250
    }
}

# ==========================================
# STRATEGIC SENSITIVE SITES & TACTICAL REFERENCE LANDMARKS
# Used for Proximity Alerts AND Exact Bearing/Distance Geolocation
# ==========================================
STRATEGIC_SITES = [
    {"name": "منشأة نطنز النووية (محافظة أصفهان، إيران)", "lat": 33.7244, "lon": 51.7256, "radius_km": 35},
    {"name": "منشأة فوردو النووية (محافظة قم، إيران)", "lat": 34.8845, "lon": 50.9958, "radius_km": 35},
    {"name": "مجمع بارشين العسكري (جنوب شرق طهران، إيران)", "lat": 35.5200, "lon": 51.7700, "radius_km": 30},
    {"name": "قاعدة أصفهان الجوية والمركز النووي (إيران)", "lat": 32.7508, "lon": 51.8613, "radius_km": 40},
    {"name": "محطة بوشهر النووية (ساحل الخليج، إيران)", "lat": 28.8294, "lon": 50.8856, "radius_km": 40},
    {"name": "قاعدة بندر عباس ومضيق هرمز (إيران)", "lat": 27.2181, "lon": 56.3778, "radius_km": 45},
    {"name": "جزيرة قشم ومضيق هرمز", "lat": 26.8333, "lon": 55.9000, "radius_km": 40},
    {"name": "جزيرة خرج النفطية والعسكرية (إيران)", "lat": 29.2400, "lon": 50.3200, "radius_km": 30},
    {"name": "قاعدة تبريز الصاروخية والجوية (شمال غرب إيران)", "lat": 38.1339, "lon": 46.2350, "radius_km": 35},
    {"name": "قاعدة كرمانشاه الصاروخية (غرب إيران)", "lat": 34.3419, "lon": 47.1589, "radius_km": 35},
    {"name": "قاعدة شيراز الجوية (جنوب إيران)", "lat": 29.5392, "lon": 52.5897, "radius_km": 35},
    {"name": "قاعدة تشابهار البحرية والجوية (خليج عمان، إيران)", "lat": 25.4433, "lon": 60.3822, "radius_km": 40},
    {"name": "العاصمة طهران (إيران)", "lat": 35.6892, "lon": 51.3890, "radius_km": 35},
    {"name": "قاعدة أكروتيري الجوية البريطانية (قبرص)", "lat": 34.5904, "lon": 32.9879, "radius_km": 35},
    {"name": "قاعدة العديد الجوية (قطر)", "lat": 25.1173, "lon": 51.3150, "radius_km": 35},
    {"name": "قاعدة الظفرة الجوية (أبوظبي، الإمارات)", "lat": 24.2483, "lon": 54.5477, "radius_km": 35},
    {"name": "قاعدة الأمير سلطان الجوية (الخرج، السعودية)", "lat": 24.0625, "lon": 47.5806, "radius_km": 40},
    {"name": "قاعدة عين الأسد الجوية (الأنبار، العراق)", "lat": 33.7856, "lon": 42.4411, "radius_km": 35},
    {"name": "مطار حرير / أربيل (إقليم كردستان، العراق)", "lat": 36.5381, "lon": 44.3472, "radius_km": 30},
    {"name": "العاصمة بغداد (العراق)", "lat": 33.3152, "lon": 44.3661, "radius_km": 35},
    {"name": "قاعدة التنف (المثلث الحدودي السوري العراقي الأردني)", "lat": 33.4867, "lon": 38.6186, "radius_km": 35},
    {"name": "قاعدة حميميم الجوية (اللاذقية، سوريا)", "lat": 35.4008, "lon": 35.9486, "radius_km": 35},
    {"name": "ميناء طرطوس البحري (سوريا)", "lat": 34.9081, "lon": 35.8708, "radius_km": 30},
    {"name": "العاصمة دمشق ومطارها الدولي (سوريا)", "lat": 33.5138, "lon": 36.2765, "radius_km": 35},
    {"name": "الساحل اللبناني / بيروت (لبنان)", "lat": 33.8938, "lon": 35.5018, "radius_km": 35},
    {"name": "قاعدة رامات دافيد الجوية (شمال فلسطين/إسرائيل)", "lat": 32.6653, "lon": 35.1794, "radius_km": 30},
    {"name": "قاعدة نيفاتيم الجوية (النقب)", "lat": 31.2083, "lon": 35.0122, "radius_km": 35},
    {"name": "ميناء الحديدة (ساحل البحر الأحمر، اليمن)", "lat": 14.7978, "lon": 42.9545, "radius_km": 40},
    {"name": "العاصمة صنعاء (اليمن)", "lat": 15.3694, "lon": 44.1910, "radius_km": 35},
    {"name": "مضيق باب المندب وجزيرة بريم", "lat": 12.6558, "lon": 43.4214, "radius_km": 40}
]

# ==========================================
# STATIC OIL & GAS FLARING MASK (EXCLUSION ZONES)
# ==========================================
KNOWN_OIL_FLARE_ZONES = [
    {"name": "حقول الأهواز وخوزستان النفطية", "lat": 31.3200, "lon": 48.6800, "radius_km": 45},
    {"name": "مصفاة عبادان وحقول خرمشهر", "lat": 30.3400, "lon": 48.2900, "radius_km": 28},
    {"name": "حقول عسلويه وبارس الجنوبي للغاز", "lat": 27.4700, "lon": 52.6100, "radius_km": 35},
    {"name": "جزيرة خرج النفطية", "lat": 29.2400, "lon": 50.3200, "radius_km": 15},
    {"name": "حقول الرميلة والقرنة (البصرة)", "lat": 30.5800, "lon": 47.3400, "radius_km": 48},
    {"name": "حقول كركوك النفطية", "lat": 35.5300, "lon": 44.3200, "radius_km": 30},
    {"name": "حقول برقان والأحمدي (الكويت)", "lat": 28.9800, "lon": 47.9500, "radius_km": 35},
    {"name": "حقول الظهران وبقيق والجبيل", "lat": 26.2500, "lon": 49.8000, "radius_km": 50},
    {"name": "حقول دير الزور والعمر النفطية", "lat": 35.0800, "lon": 40.5600, "radius_km": 22}
]

# ==========================================
# HIGH-VALUE MILITARY AIRCRAFT FILTERS
# ==========================================
HIGH_VALUE_AIRCRAFT_TYPES = {
    "R135": "RC-135 Rivet Joint (طائرة استطلاع وتجسس إلكتروني استراتيجي)",
    "E3CF": "E-3 Sentry AWACS (طائرة إنذار مبكر وقيادة وسيطرة جوية)",
    "E3TF": "E-3 Sentry AWACS (طائرة إنذار مبكر وقيادة وسيطرة جوية)",
    "E2": "E-2 Hawkeye (طائرة إنذار مبكر بحري وجوي)",
    "GLF5": "Gulfstream G550 Nachshon/Eitam (طائرة استطلاع راداري وإنذار مبكر)",
    "GLEX": "Bombardier E-11A BACN (طائرة عقدة اتصالات ساحة المعركة)",
    "P8": "P-8A Poseidon (طائرة استطلاع بحري ومضادة للغواصات والسفن)",
    "EP3": "EP-3E Aries II (طائرة استخبارات إشارات إلكترونية SIGINT)",
    "RQ4": "RQ-4 Global Hawk / MQ-4C Triton (مسيرة استطلاع استراتيجي عالي الارتفاع)",
    "B350": "Beechcraft RC-12 Guardrail / King Air ISR (طائرة استطلاع وتحديد أهداف)",
    "K35R": "KC-135R Stratotanker (طائرة تزود بالوقود جواً لدعم المقاتلات)",
    "KC46": "KC-46A Pegasus (طائرة تزود بالوقود جواً تكتيكية)",
    "A332": "Airbus A330 MRTT (طائرة تزود بالوقود جواً ونقل استراتيجي)",
    "KC30": "KC-30A MRTT (طائرة تزود بالوقود جواً)",
    "B52": "B-52H Stratofortress (قاذفة قنابل وصواريخ كروز استراتيجية)",
    "B1": "B-1B Lancer (قاذفة استراتيجية ثقيلة أسرع من الصوت)",
    "IL76": "Ilyushin Il-76 (طائرة شحن عسكري استراتيجي ثقيل)",
    "A124": "Antonov An-124 Ruslan (طائرة شحن عسكري عملاقة)",
    "C17": "Boeing C-17A Globemaster III (طائرة نقل جوي عسكري استراتيجي)",
    "C5M": "Lockheed C-5M Super Galaxy (طائرة نقل جوي عسكري استراتيجي ثقيل)",
    "B742": "Boeing 747-200F (طائرة شحن جوي عسكري خاص)"
}

MILITARY_CALLSIGN_PREFIXES = (
    "FORTE", "HOMER", "JAKE", "OLIVE", "NCHO", "LAGR", "GOLD", "PYTHON",
    "ETHYL", "NATO", "RRR", "RCH", "ASCOT", "IAM", "FAF", "GAF",
    "IRGC", "IRI", "POUYA", "FARS", "QESHM", "SYR", "RF", "RFF"
)

NGA_CRITICAL_KEYWORDS = [
    "MISSILE", "ROCKET", "HAZARDOUS OPERATIONS", "FIRING EXERCISE",
    "GUNNERY", "LIVE FIRE", "SPACE DEBRIS", "AIR DEFENSE",
    "MILITARY OPERATIONS", "PROHIBITED AREA", "DANGER AREA"
]
