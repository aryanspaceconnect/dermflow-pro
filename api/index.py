"""DermFlow Pro - Vercel entry (serves clinic UI + API)."""
import os, sys, json, hashlib, random, sqlite3
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
app = Flask(__name__)
CORS(app)

IS_VERCEL = bool(os.environ.get("VERCEL"))
BASE_DIR = Path("/tmp") if IS_VERCEL else Path(__file__).parent.parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
DB_PATH = BASE_DIR / "dermflow.db"
UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)
ALLOWED = {"png", "jpg", "jpeg"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS api_config (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        skin_analysis_key TEXT, makeup_vto_key TEXT, clothes_vto_key TEXT,
        jewelry_vto_key TEXT, bg_removal_key TEXT, enhancement_key TEXT,
        file_upload_key TEXT, use_real_apis BOOLEAN DEFAULT 0,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT,
        phone TEXT, date_of_birth TEXT, skin_type TEXT, allergies TEXT,
        baseline_photo TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS analyses (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        original_image TEXT, processed_image TEXT, skin_tone_hex TEXT, undertone TEXT,
        texture_score INTEGER, pore_score INTEGER, wrinkle_score INTEGER,
        blemish_score INTEGER, hydration_score INTEGER, overall_score INTEGER,
        raw_data TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS face_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        analysis_id INTEGER NOT NULL, previous_analysis_id INTEGER,
        metric_name TEXT, old_value REAL, new_value REAL, change_percent REAL,
        change_direction TEXT, notes TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS treatment_plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        analysis_id INTEGER NOT NULL, am_routine TEXT, pm_routine TEXT,
        diet_suggestions TEXT, lifestyle_notes TEXT, follow_up_weeks INTEGER DEFAULT 4,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    c.execute("SELECT COUNT(*) FROM patients")
    if c.fetchone()[0] == 0:
        c.executemany(
            "INSERT INTO patients (name, email, phone, date_of_birth, skin_type, allergies) VALUES (?,?,?,?,?,?)",
            [
                ("Sarah Chen", "sarah.chen@email.com", "555-0101", "1992-03-15", "Combination", "None"),
                ("Marcus Johnson", "mjohnson@email.com", "555-0102", "1985-07-22", "Oily", "Fragrance"),
                ("Aisha Patel", "aisha.p@email.com", "555-0103", "1990-11-08", "Dry", "Retinol sensitivity"),
                ("David Kim", "dkim@email.com", "555-0104", "1978-01-30", "Sensitive", "Aloe vera"),
            ],
        )
        conn.commit()
    conn.close()

def _score_level(score):
    if score >= 80: return "excellent"
    if score >= 65: return "good"
    if score >= 50: return "fair"
    if score >= 35: return "poor"
    return "critical"

def mock_skin_analysis(image_url):
    seed = int(hashlib.md5(image_url.encode()).hexdigest(), 16)
    random.seed(seed)
    texture, pore, wrinkle, blemish, hydration = [random.randint(30, 85) for _ in range(5)]
    overall = int((texture + pore + wrinkle + blemish + hydration) / 5)
    undertone = ["warm", "cool", "neutral"][seed % 3]
    hex_tone = f"#{180 + seed % 50:02x}{140 + seed % 40:02x}{110 + seed % 35:02x}"
    random.seed()
    return {
        "status": "success",
        "results": {
            "skin_tone": {"hex": hex_tone, "undertone": undertone, "depth": random.choice(["light", "medium", "deep"])},
            "texture": {"score": texture, "level": _score_level(texture)},
            "pore_visibility": {"score": pore, "level": _score_level(pore)},
            "wrinkles": {"score": wrinkle, "level": _score_level(wrinkle)},
            "blemishes": {"score": blemish, "level": _score_level(blemish)},
            "hydration": {"score": hydration, "level": _score_level(hydration)},
            "overall_health": {"score": overall, "level": _score_level(overall)},
        },
    }

def generate_treatment_plan(analysis_data):
    scores = analysis_data.get("results", analysis_data)
    concerns = []
    if scores.get("hydration", {}).get("score", 100) < 50: concerns.append("dehydration")
    if scores.get("blemishes", {}).get("score", 100) < 50: concerns.append("acne")
    if scores.get("wrinkles", {}).get("score", 100) < 50: concerns.append("aging")
    if not concerns: concerns.append("maintenance")
    am = [{"step": 1, "action": "Gentle cleanser", "notes": "pH-balanced"},
          {"step": 2, "action": "Moisturizer", "notes": "Match skin type"},
          {"step": 3, "action": "SPF 30-50", "notes": "Broad spectrum"}]
    pm = [{"step": 1, "action": "Oil cleanser", "notes": "Remove makeup"},
          {"step": 2, "action": "Water cleanser", "notes": "Double cleanse"},
          {"step": 3, "action": "Moisturizer", "notes": "Richer PM"}]
    if "acne" in concerns:
        am.insert(1, {"step": 2, "action": "Niacinamide 5-10%", "notes": "Anti-inflammatory"})
        pm.insert(2, {"step": 3, "action": "Benzoyl peroxide 2.5%", "notes": "Spot treatment"})
    if "aging" in concerns:
        am.insert(1, {"step": 2, "action": "Vitamin C serum", "notes": "15-20%"})
        pm.insert(2, {"step": 3, "action": "Retinol 0.25-0.5%", "notes": "Start 2x/week"})
    diet = {"eat_more": ["Whole foods"], "avoid": ["Excess sugar"], "hydration_target": "2.5-3L"}
    if "acne" in concerns:
        diet = {"eat_more": ["Omega-3", "Zinc", "Probiotics"], "avoid": ["High-GI", "Dairy"], "hydration_target": "2.5-3L"}
    return {
        "primary_concerns": concerns, "am_routine": am, "pm_routine": pm,
        "diet_suggestions": diet, "lifestyle_notes": ["7-9h sleep", "Manage stress"],
        "recommended_products": {"foundation": "Match undertone", "blush": "Soft", "lipstick": "Neutral", "eyeshadow": "Neutral"},
        "follow_up_weeks": 4, "generated_at": datetime.now().isoformat(),
    }

def calculate_face_changes(current, previous):
    changes = []
    for name, key in [
        ("Overall Health", "overall_score"), ("Hydration", "hydration_score"),
        ("Texture", "texture_score"), ("Pore Visibility", "pore_score"),
        ("Wrinkles", "wrinkle_score"), ("Blemishes", "blemish_score"),
    ]:
        nv, ov = current.get(key, 0), previous.get(key, 0)
        ch = nv - ov
        pct = round((ch / max(ov, 1)) * 100, 1) if ov else 0
        direction = "improved" if ch > 0 else "declined" if ch < 0 else "stable"
        changes.append({"metric_name": name, "old_value": ov, "new_value": nv, "change": ch, "change_percent": pct, "direction": direction, "notes": ""})
    return changes

@app.route("/")
def index():
    for p in [
        Path(__file__).parent / "embedded_ui.html",
        Path("/var/task/api/embedded_ui.html"),
        Path("/var/task/embedded_ui.html"),
    ]:
        if p.exists():
            return p.read_text(encoding="utf-8"), 200, {"Content-Type": "text/html; charset=utf-8"}
    return (
        "<!DOCTYPE html><html><body style='font-family:system-ui;padding:40px'>"
        "<h1>DermFlow Pro</h1><p>UI file missing. API: <a href='/api/dashboard/stats'>/api/dashboard/stats</a></p>"
        "</body></html>",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )

@app.route("/api/config", methods=["GET"])
def get_config():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM api_config WHERE id = 1"); row = c.fetchone(); conn.close()
    if not row: return jsonify({"use_real_apis": False, "keys_configured": 0})
    config = dict(row); masked = {}; kc = 0
    for k, v in config.items():
        if k.endswith("_key") and v:
            masked[k] = (v[:8] + "..." + v[-4:]) if len(v) > 12 else "***"; kc += 1
        elif k.endswith("_key"): masked[k] = ""
        else: masked[k] = v
    masked["keys_configured"] = kc
    return jsonify(masked)

@app.route("/api/config", methods=["POST"])
def save_config():
    data = request.json or {}
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id FROM api_config WHERE id = 1"); exists = c.fetchone()
    fields = ["skin_analysis_key","makeup_vto_key","clothes_vto_key","jewelry_vto_key","bg_removal_key","enhancement_key","file_upload_key","use_real_apis"]
    values = [data.get(f, "") for f in fields]
    if exists:
        c.execute("UPDATE api_config SET " + ", ".join(f+"=?" for f in fields) + ", updated_at=CURRENT_TIMESTAMP WHERE id=1", values)
    else:
        c.execute("INSERT INTO api_config (id, " + ", ".join(fields) + ", updated_at) VALUES (1, " + ", ".join("?" for _ in fields) + ", CURRENT_TIMESTAMP)", values)
    conn.commit(); conn.close()
    return jsonify({"success": True, "message": "Configuration saved"})

@app.route("/api/config/test", methods=["POST"])
def test_config():
    data = request.json or {}
    if not data.get("use_real_apis"):
        return jsonify({"success": True, "message": "Mock mode is working", "mode": "mock"})
    key = data.get("skin_analysis_key") or data.get("file_upload_key") or ""
    if len(str(key)) < 8:
        return jsonify({"success": False, "error": "Provide a valid API key"}), 400
    return jsonify({"success": True, "message": "Keys accepted", "mode": "real"})

@app.route("/api/patients", methods=["GET"])
def get_patients():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM patients ORDER BY created_at DESC")
    rows = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify(rows)

@app.route("/api/patients", methods=["POST"])
def create_patient():
    data = request.json or {}
    conn = get_db(); c = conn.cursor()
    c.execute("INSERT INTO patients (name,email,phone,date_of_birth,skin_type,allergies) VALUES (?,?,?,?,?,?)",
              (data.get("name"), data.get("email"), data.get("phone"), data.get("date_of_birth"), data.get("skin_type"), data.get("allergies")))
    conn.commit(); pid = c.lastrowid; conn.close()
    return jsonify({"id": pid, "message": "Patient created"}), 201

@app.route("/api/patients/<int:patient_id>", methods=["GET"])
def get_patient(patient_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE id=?", (patient_id,)); row = c.fetchone()
    patient = dict(row) if row else None
    c.execute("SELECT * FROM analyses WHERE patient_id=? ORDER BY created_at DESC", (patient_id,))
    analyses = [dict(r) for r in c.fetchall()]
    c.execute("SELECT * FROM face_changes WHERE patient_id=? ORDER BY created_at DESC", (patient_id,))
    changes = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify({"patient": patient, "analyses": analyses, "face_changes": changes})

@app.route("/api/patients/<int:patient_id>/progress", methods=["GET"])
def get_progress(patient_id):
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT id,created_at,overall_score,hydration_score,texture_score,pore_score,wrinkle_score,blemish_score FROM analyses WHERE patient_id=? ORDER BY created_at ASC", (patient_id,))
    rows = c.fetchall(); conn.close()
    return jsonify([{"analysis_id": r[0], "date": r[1], "overall": r[2], "hydration": r[3], "texture": r[4], "pores": r[5], "wrinkles": r[6], "blemishes": r[7]} for r in rows])

@app.route("/api/analyze", methods=["POST"])
def analyze_skin():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400
    file = request.files["image"]
    patient_id = request.form.get("patient_id", type=int)
    if not (file and allowed_file(file.filename)):
        return jsonify({"error": "Invalid file type"}), 400
    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
    filepath = UPLOAD_FOLDER / filename
    file.save(filepath)
    image_url = f"https://mock-s3.dermflow.dev/uploads/{filename}"
    analysis_result = mock_skin_analysis(image_url)
    scores = analysis_result["results"]
    conn = get_db(); c = conn.cursor()
    c.execute("""INSERT INTO analyses (patient_id,original_image,processed_image,skin_tone_hex,undertone,
        texture_score,pore_score,wrinkle_score,blemish_score,hydration_score,overall_score,raw_data)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (patient_id, str(filepath), image_url, scores["skin_tone"]["hex"], scores["skin_tone"]["undertone"],
         scores["texture"]["score"], scores["pore_visibility"]["score"], scores["wrinkles"]["score"],
         scores["blemishes"]["score"], scores["hydration"]["score"], scores["overall_health"]["score"],
         json.dumps(analysis_result["results"])))
    analysis_id = c.lastrowid; conn.commit()
    c.execute("SELECT * FROM analyses WHERE patient_id=? AND id<? ORDER BY created_at DESC LIMIT 1", (patient_id, analysis_id))
    prev_row = c.fetchone(); face_changes = []
    if prev_row:
        previous = dict(prev_row)
        current = {
            "overall_score": scores["overall_health"]["score"], "hydration_score": scores["hydration"]["score"],
            "texture_score": scores["texture"]["score"], "pore_score": scores["pore_visibility"]["score"],
            "wrinkle_score": scores["wrinkles"]["score"], "blemish_score": scores["blemishes"]["score"],
        }
        face_changes = calculate_face_changes(current, previous)
        for ch in face_changes:
            c.execute("""INSERT INTO face_changes (patient_id,analysis_id,previous_analysis_id,metric_name,old_value,new_value,change_percent,change_direction,notes)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (patient_id, analysis_id, previous["id"], ch["metric_name"], ch["old_value"], ch["new_value"], ch["change_percent"], ch["direction"], ch["notes"]))
        conn.commit()
    treatment_plan = generate_treatment_plan(analysis_result)
    c.execute("""INSERT INTO treatment_plans (patient_id,analysis_id,am_routine,pm_routine,diet_suggestions,lifestyle_notes,follow_up_weeks)
        VALUES (?,?,?,?,?,?,?)""",
        (patient_id, analysis_id, json.dumps(treatment_plan["am_routine"]), json.dumps(treatment_plan["pm_routine"]),
         json.dumps(treatment_plan["diet_suggestions"]), json.dumps(treatment_plan["lifestyle_notes"]), treatment_plan["follow_up_weeks"]))
    plan_id = c.lastrowid; conn.commit(); conn.close()
    return jsonify({
        "success": True, "analysis_id": analysis_id, "plan_id": plan_id,
        "analysis": analysis_result, "treatment_plan": treatment_plan,
        "face_changes": face_changes, "image_path": f"/uploads/{filename}",
    })

@app.route("/api/dashboard/stats", methods=["GET"])
def get_dashboard_stats():
    conn = get_db(); c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM patients"); tp = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM analyses"); ta = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM treatment_plans"); tpl = c.fetchone()[0]
    c.execute("SELECT AVG(overall_score) FROM analyses"); avg = c.fetchone()[0] or 0
    c.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 5")
    recent = [dict(r) for r in c.fetchall()]; conn.close()
    return jsonify({"total_patients": tp, "total_analyses": ta, "total_plans": tpl,
                    "avg_skin_score": round(avg, 1), "recent_analyses": recent, "api_mode": "mock"})

@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

init_db()
