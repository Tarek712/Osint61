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

# Watermark Text on Tactical Map
MAP_WATERMARK_AR = os.getenv("MAP_WATERMARK_AR", "خاص بتسريبات الحرب")

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

STARTUP_LOOKBACK_MINUTES = int(os.getenv("STARTUP_LOOKBACK_MINUTES", 20))

# Thermal Filtering Thresholds (MW)
MIN_FRP_DAY_MW = float(os.getenv("MIN_FRP_DAY_MW", 25.0))
MIN_FRP_NIGHT_MW = float(os.getenv("MIN_FRP_NIGHT_MW", 12.0))

# ==========================================
# GEOSPATIAL BOUNDING BOXES (MIDDLE EAST, IRAN & YEMEN/KSA)
# ==========================================
SECTORS = {
    "YEMEN_AND_SOUTHERN_KSA": {
        "name_ar": "مسرح عمليات اليمن والحدود الجنوبية السعودية والبحر الأحمر",
        "min_lat": 11.5, "max_lat": 24.5,
        "min_lon": 37.0, "max_lon": 53.5,
        "center_lat": 16.5, "center_lon": 44.5,
        "radius_nm": 300
    },
    "LEVANT_AND_EAST_MED": {
        "name_ar": "جبهة بلاد الشام وشرق المتوسط وفلسطين",
        "min_lat": 29.0, "max_lat": 37.5,
        "min_lon": 32.0, "max_lon": 42.5,
        "center_lat": 33.5, "center_lon": 36.0,
        "radius_nm": 250
    },
    "IRAN_AND_GULF": {
        "name_ar": "العمق الإيراني والخليج العربي ومضيق هرمز",
        "min_lat": 24.0, "max_lat": 39.8,
        "min_lon": 44.0, "max_lon": 63.3,
        "center_lat": 32.0, "center_lon": 53.0,
        "radius_nm": 280
    },
    "IRAQ_AND_NORTHERN_KSA": {
        "name_ar": "الممر الجوي العراقي وشمال الجزيرة العربية",
        "min_lat": 24.5, "max_lat": 37.5,
        "min_lon": 38.5, "max_lon": 48.5,
        "center_lat": 32.0, "center_lon": 43.5,
        "radius_nm": 260
    }
}

# ==========================================
# EXCLUSIVE 3-NATION MILITARY AIRCRAFT FILTER (USA, ISRAEL, SAUDI ARABIA)
# ==========================================
ALLOWED_MILITARY_OPERATORS = {
    "USA": {
        "name_ar": "القوات الجوية/البحرية الأمريكية 🇺🇸 (USAF/USN)",
        "hex_prefixes": ("AE", "ADF"),
        "callsign_prefixes": (
            "HOMER", "FORTE", "JAKE", "PYTHON", "NCHO", "LAGR", "GOLD",
            "ETHYL", "RCH", "OLIVE", "DOOM", "DEATH", "BONE", "RAIDR",
            "HOBO", "SNOOP", "COBRA", "TITAN", "GORDO", "SHuck", "NAVY", "CNV"
        )
    },
    "ISRAEL": {
        "name_ar": "سلاح الجو الإسرائيلي 🇮🇱 (IAF)",
        "hex_prefixes": ("738A", "738B"),
        "callsign_prefixes": ("IAF", "ISD", "ELALMIL")
    },
    "SAUDI_ARABIA": {
        "name_ar": "القوات الجوية الملكية السعودية 🇸🇦 (RSAF)",
        "hex_prefixes": ("7102", "7103", "710"),
        "callsign_prefixes": ("RSAF", "SRG", "TUWAIQ", "SAUDIA")
    }
}

# ==========================================
# STRATEGIC SITES & YEMEN/ME FRONTLINE LANDMARKS
# ==========================================
STRATEGIC_SITES = [
    # --- YEMEN & SOUTHERN SAUDI FRONTLINES (الحرب بين الحوثي والشرعية والسعودية) ---
    {"name": "معقل وجبهة صعدة (شمال اليمن - الحدود السعودية)", "lat": 16.9402, "lon": 43.7639, "radius_km": 40},
    {"name": "جبهة ومحافظة مأرب وحقول صافر (خط التماس الرئيسي)", "lat": 15.4625, "lon": 45.3258, "radius_km": 45},
    {"name": "جبهة حرض وميدي الحدودية (محافظة حجة، اليمن)", "lat": 16.4094, "lon": 43.0619, "radius_km": 35},
    {"name": "محافظة الجوف وجبهة اليتمة (شمال شرق اليمن)", "lat": 16.6167, "lon": 45.0333, "radius_km": 45},
    {"name": "العاصمة صنعاء وقاعدة الديلمي الجوية (اليمن)", "lat": 15.3694, "lon": 44.1910, "radius_km": 40},
    {"name": "ميناء ومطار الحديدة (ساحل البحر الأحمر، اليمن)", "lat": 14.7978, "lon": 42.9545, "radius_km": 40},
    {"name": "ميناء الصليف ورأس عيسى النفطي (الحديدة، اليمن)", "lat": 15.2917, "lon": 42.6722, "radius_km": 35},
    {"name": "جبهة ومحافظة تعز وميناء المخا (اليمن)", "lat": 13.5795, "lon": 44.0209, "radius_km": 40},
    {"name": "جبهة الضالع وقاعدة العند الجوية (لحج، اليمن)", "lat": 13.3369, "lon": 44.7636, "radius_km": 40},
    {"name": "جبهة ومحافظة البيضاء وعتق شبوة (وسط اليمن)", "lat": 14.2833, "lon": 46.2333, "radius_km": 45},
    {"name": "العاصمة المؤقتة عدن ومطارها الدولي (قوات الشرعية والتحالف)", "lat": 12.8295, "lon": 45.0288, "radius_km": 40},
    {"name": "مضيق باب المندب وجزيرة ميون (بريم)", "lat": 12.6558, "lon": 43.4214, "radius_km": 40},
    {"name": "قاعدة الريان والمكلا (حضرموت، اليمن)", "lat": 14.6625, "lon": 49.3750, "radius_km": 45},
    {"name": "أرخبيل جزيرة سقطرى (بحر العرب، اليمن)", "lat": 12.6300, "lon": 53.9058, "radius_km": 45},
    {"name": "قاعدة الملك خالد الجوية بخميس مشيط / عسير (السعودية)", "lat": 18.2972, "lon": 42.8036, "radius_km": 45},
    {"name": "قطاع جازان الحدودي وميناء جازان (جنوب غرب السعودية)", "lat": 16.8892, "lon": 42.5511, "radius_km": 40},
    {"name": "قطاع نجران الحدودي (جنوب السعودية)", "lat": 17.4924, "lon": 44.1277, "radius_km": 40},
    {"name": "قطاع شرورة والوديعة الحدودي (جنوب السعودية)", "lat": 17.4850, "lon": 47.1150, "radius_km": 40},
    {"name": "قاعدة الملك فهد الجوية (الطائف، السعودية)", "lat": 21.4833, "lon": 40.5444, "radius_km": 40},
    {"name": "قاعدة الأمير سلطان الجوية (الخرج، السعودية)", "lat": 24.0625, "lon": 47.5806, "radius_km": 45},

    # --- IRAN, GULF, LEVANT & IRAQ STRATEGIC SITES ---
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
    {"name": "العاصمة طهران (إيران)", "lat": 35.6892, "lon": 51.3890, "radius_km": 35},
    {"name": "قاعدة أكروتيري الجوية (قبرص)", "lat": 34.5904, "lon": 32.9879, "radius_km": 35},
    {"name": "قاعدة العديد الجوية (قطر)", "lat": 25.1173, "lon": 51.3150, "radius_km": 35},
    {"name": "قاعدة الظفرة الجوية (الإمارات)", "lat": 24.2483, "lon": 54.5477, "radius_km": 35},
    {"name": "قاعدة عين الأسد الجوية (الأنبار، العراق)", "lat": 33.7856, "lon": 42.4411, "radius_km": 35},
    {"name": "مطار حرير / أربيل (كردستان العراق)", "lat": 36.5381, "lon": 44.3472, "radius_km": 30},
    {"name": "العاصمة بغداد (العراق)", "lat": 33.3152, "lon": 44.3661, "radius_km": 35},
    {"name": "قاعدة التنف (المثلث الحدودي السوري العراقي الأردني)", "lat": 33.4867, "lon": 38.6186, "radius_km": 35},
    {"name": "قاعدة حميميم الجوية (اللاذقية، سوريا)", "lat": 35.4008, "lon": 35.9486, "radius_km": 35},
    {"name": "العاصمة دمشق ومطارها الدولي (سوريا)", "lat": 33.5138, "lon": 36.2765, "radius_km": 35},
    {"name": "الجنوب اللبناني / بيروت (لبنان)", "lat": 33.8938, "lon": 35.5018, "radius_km": 40},
    {"name": "قاعدة رامات دافيد الجوية (شمال فلسطين/إسرائيل)", "lat": 32.6653, "lon": 35.1794, "radius_km": 30},
    {"name": "قاعدة نيفاتيم الجوية (النقب)", "lat": 31.2083, "lon": 35.0122, "radius_km": 35},
    {"name": "قاعدة بلماحيم وتل نوف الجوية (وسط فلسطين/إسرائيل)", "lat": 31.8978, "lon": 34.6906, "radius_km": 30}
]

# ==========================================
# STATIC OIL & GAS FLARING MASK (EXCLUSION ZONES)
# Includes Yemen Safer/Shabwah fields to isolate actual military strikes
# ==========================================
KNOWN_OIL_FLARE_ZONES = [
    {"name": "حقول صافر النفطية الروتينية (شرق مأرب)", "lat": 15.5500, "lon": 45.7800, "radius_km": 12},
    {"name": "حقول المسيلة والعقلة النفطية (حضرموت/شبوة)", "lat": 15.5200, "lon": 49.1500, "radius_km": 18},
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
# HIGH-VALUE MILITARY AIRCRAFT DESCRIPTIONS
# ==========================================
HIGH_VALUE_AIRCRAFT_TYPES = {
    "R135": "RC-135 Rivet Joint (طائرة استطلاع وتجسس إلكتروني استراتيجي ELINT/SIGINT)",
    "E3CF": "E-3 Sentry AWACS (طائرة إنذار مبكر وقيادة وسيطرة جوية)",
    "E3TF": "E-3 Sentry AWACS (طائرة إنذار مبكر وقيادة وسيطرة جوية)",
    "SB20": "Saab 2000 Erieye AEW&C (طائرة إنذار مبكر ورقابة رادارية سعودية)",
    "E2": "E-2D Hawkeye (طائرة إنذار مبكر بحري وجوي)",
    "GLF5": "Gulfstream G550 Nachshon/Oron/Eitam (طائرة استطلاع راداري وإنذار مبكر إلكتروني)",
    "GLEX": "Bombardier E-11A BACN (طائرة عقدة اتصالات ساحة المعركة والربط التكتيكي)",
    "P8": "P-8A Poseidon (طائرة استطلاع بحري ومضادة للغواصات والأهداف الساحلية)",
    "EP3": "EP-3E Aries II (طائرة استخبارات إشارات إلكترونية SIGINT)",
    "RQ4": "RQ-4 Global Hawk / MQ-4C Triton (مسيرة استطلاع استراتيجي عالي الارتفاع)",
    "B350": "Beechcraft King Air / RC-12 Guardrail ISR (طائرة استطلاع تكتيكي وتحديد أهداف)",
    "K35R": "KC-135R Stratotanker (طائرة تزود بالوقود جواً لإسناد المقاتلات)",
    "KC46": "KC-46A Pegasus (طائرة تزود بالوقود جواً تكتيكية)",
    "A332": "Airbus A330 MRTT (طائرة تزود بالوقود جواً لإسناد المقاتلات)",
    "KC30": "KC-30A / A330 MRTT (طائرة تزود بالوقود جواً)",
    "B703": "Boeing 707 Re'em (طائرة تزود بالوقود جواً وقيادة استراتيجية - سلاح الجو الإسرائيلي)",
    "C130": "Lockheed C-130H/J Hercules / KC-130 (نقل تكتيكي وتزود بالوقود)",
    "C30J": "Lockheed C-130J Super Hercules / Shimshon (نقل وإسناد تكتيكي)",
    "B52": "B-52H Stratofortress (قاذفة قنابل وصواريخ كروز استراتيجية)",
    "B1": "B-1B Lancer (قاذفة استراتيجية ثقيلة أسرع من الصوت)",
    "F15": "F-15C/E/SA Strike Eagle (مقاتلة سيادة جوية وهجوم عميق)",
    "F16": "F-16 Fighting Falcon / Sufa (مقاتلة متعددة المهام)",
    "F35": "F-35I Adir / Lightning II (مقاتلة الجيل الخامس الشبحية)",
    "EUFI": "Eurofighter Typhoon (مقاتلة سيادة جوية وهجوم متعدد المهام)",
    "C17": "Boeing C-17A Globemaster III (طائرة نقل جوي عسكري استراتيجي)",
    "C5M": "Lockheed C-5M Super Galaxy (طائرة نقل جوي عسكري استراتيجي ثقيل)"
}

NGA_CRITICAL_KEYWORDS = [
    "MISSILE", "ROCKET", "HAZARDOUS OPERATIONS", "FIRING EXERCISE",
    "GUNNERY", "LIVE FIRE", "SPACE DEBRIS", "AIR DEFENSE",
    "MILITARY OPERATIONS", "PROHIBITED AREA", "DANGER AREA"
]
