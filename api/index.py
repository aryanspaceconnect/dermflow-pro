"""
DermFlow Pro - Vercel Serverless Entry (self-contained for reliable deploy)
"""
import os
import sys
import json
import hashlib
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from io import BytesIO

from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS
from werkzeug.utils import secure_filename

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_root = Path(__file__).resolve().parent.parent
_static = _root / 'static'
if not _static.exists():
    _static = Path('static')
app = Flask(__name__, static_folder=str(_static), static_url_path='/static')
CORS(app)

IS_VERCEL = bool(os.environ.get('VERCEL'))
BASE_DIR = Path('/tmp') if IS_VERCEL else Path(__file__).parent.parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
REPORTS_FOLDER = BASE_DIR / "reports"
DB_PATH = BASE_DIR / "dermflow.db"
for folder in [UPLOAD_FOLDER, REPORTS_FOLDER]:
    folder.mkdir(parents=True, exist_ok=True)

ALLOWED = {'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED

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
        original_image TEXT, processed_image TEXT, preprocessed_image TEXT,
        skin_tone_hex TEXT, undertone TEXT, texture_score INTEGER, pore_score INTEGER,
        wrinkle_score INTEGER, blemish_score INTEGER, hydration_score INTEGER,
        overall_score INTEGER, preprocessing_applied TEXT, raw_data TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    c.execute("""CREATE TABLE IF NOT EXISTS face_changes (
        id INTEGER PRIMARY KEY AUTOINCREMENT, patient_id INTEGER NOT NULL,
        analysis_id INTEGER NOT NULL, previous_analysis_id INTEGER, change_type TEXT,
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
        patients = [
            ("Sarah Chen", "sarah.chen@email.com", "555-0101", "1992-03-15", "Combination", "None"),
            ("Marcus Johnson", "mjohnson@email.com", "555-0102", "1985-07-22", "Oily", "Fragrance"),
            ("Aisha Patel", "aisha.p@email.com", "555-0103", "1990-11-08", "Dry", "Retinol sensitivity"),
            ("David Kim", "dkim@email.com", "555-0104", "1978-01-30", "Sensitive", "Aloe vera"),
        ]
        c.executemany("INSERT INTO patients (name, email, phone, date_of_birth, skin_type, allergies) VALUES (?,?,?,?,?,?)", patients)
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
    texture = random.randint(45, 85)
    pore = random.randint(40, 80)
    wrinkle = random.randint(30, 75)
    blemish = random.randint(25, 70)
    hydration = random.randint(35, 80)
    overall = int((texture + pore + wrinkle + blemish + hydration) / 5)
    undertones = ["warm", "cool", "neutral"]
    undertone = undertones[seed % 3]
    base_r = 180 + (seed % 50)
    base_g = 140 + (seed % 40)
    base_b = 110 + (seed % 35)
    hex_tone = f"#{base_r:02x}{base_g:02x}{base_b:02x}"
    random.seed()
    return {
        "status": "success",
        "task_id": f"task_{seed % 100000}",
        "results": {
            "skin_tone": {"hex": hex_tone, "undertone": undertone, "depth": random.choice(["light", "medium", "deep"])},
            "texture": {"score": texture, "level": _score_level(texture)},
            "pore_visibility": {"score": pore, "level": _score_level(pore)},
            "wrinkles": {"score": wrinkle, "level": _score_level(wrinkle)},
            "blemishes": {"score": blemish, "level": _score_level(blemish)},
            "hydration": {"score": hydration, "level": _score_level(hydration)},
            "overall_health": {"score": overall, "level": _score_level(overall)}
        },
        "metadata": {"image_quality": "good", "face_detected": True, "analysis_timestamp": datetime.now().isoformat()}
    }

def generate_treatment_plan(analysis_data):
    scores = analysis_data.get("results", analysis_data)
    undertone = scores.get("skin_tone", {}).get("undertone", "neutral")
    concerns = []
    if scores.get("hydration", {}).get("score", 100) < 50: concerns.append("dehydration")
    if scores.get("blemishes", {}).get("score", 100) < 50: concerns.append("acne")
    if scores.get("wrinkles", {}).get("score", 100) < 50: concerns.append("aging")
    if scores.get("pore_visibility", {}).get("score", 100) < 50: concerns.append("enlarged_pores")
    if scores.get("texture", {}).get("score", 100) < 50: concerns.append("uneven_texture")
    if not concerns: concerns.append("maintenance")
    am_steps = [
        {"step": 1, "action": "Gentle cleanser", "product_type": "cleanser", "notes": "pH-balanced"},
        {"step": 2, "action": "Moisturizer", "product_type": "moisturizer", "notes": "Match to skin type"},
        {"step": 3, "action": "SPF 30-50", "product_type": "sunscreen", "notes": "Broad spectrum"}
    ]
    pm_steps = [
        {"step": 1, "action": "Oil cleanser", "product_type": "cleanser", "notes": "Remove makeup"},
        {"step": 2, "action": "Water-based cleanser", "product_type": "cleanser", "notes": "Double cleanse"},
        {"step": 3, "action": "Moisturizer", "product_type": "moisturizer", "notes": "Richer than AM"}
    ]
    if "dehydration" in concerns:
        am_steps.insert(1, {"step": 2, "action": "Hyaluronic acid serum", "product_type": "serum", "notes": "Apply to damp skin"})
    if "acne" in concerns:
        am_steps.insert(1, {"step": 2, "action": "Niacinamide 5-10%", "product_type": "serum", "notes": "Anti-inflammatory"})
        pm_steps.insert(2, {"step": 3, "action": "Benzoyl peroxide 2.5%", "product_type": "treatment", "notes": "Spot treatment"})
    if "aging" in concerns:
        am_steps.insert(1, {"step": 2, "action": "Vitamin C serum", "product_type": "serum", "notes": "L-Ascorbic acid 15-20%"})
        pm_steps.insert(2, {"step": 3, "action": "Retinol 0.25-0.5%", "product_type": "treatment", "notes": "Start 2x/week"})
    diet = {"eat_more": ["Balanced whole foods"], "avoid": ["Excess sugar"], "hydration_target": "2.5-3 liters daily"}
    if "acne" in concerns:
        diet["eat_more"] = ["Omega-3 fish", "Zinc seeds", "Probiotics", "Green tea"]
        diet["avoid"] = ["High-glycemic foods", "Dairy", "Whey protein"]
    lifestyle = ["Aim for 7-9 hours sleep", "Manage stress - cortisol triggers breakouts"]
    if "acne" in concerns:
        lifestyle.extend(["Change pillowcase every 2-3 days", "Clean phone screen daily"])
    products = {
        "warm": {"foundation": "Golden/olive shades", "blush": "Peach, coral", "lipstick": "Terracotta, brick red", "eyeshadow": "Bronze, gold"},
        "cool": {"foundation": "Pink-based shades", "blush": "Rose, mauve", "lipstick": "Berry, blue-red", "eyeshadow": "Silver, taupe"},
        "neutral": {"foundation": "Balanced shades", "blush": "Soft pink", "lipstick": "True red, mauve", "eyeshadow": "Champagne, soft brown"}
    }.get(undertone, {"foundation": "Balanced shades", "blush": "Soft pink", "lipstick": "True red, mauve", "eyeshadow": "Champagne, soft brown"})
    return {
        "primary_concerns": concerns, "am_routine": am_steps, "pm_routine": pm_steps,
        "diet_suggestions": diet, "lifestyle_notes": lifestyle, "recommended_products": products,
        "follow_up_weeks": 4 if len(concerns) <= 2 else 2, "generated_at": datetime.now().isoformat()
    }

def calculate_face_changes(current, previous):
    changes = []
    metrics = [
        ("Overall Health", current.get('overall_score', 0), previous.get('overall_score', 0)),
        ("Hydration", current.get('hydration_score', 0), previous.get('hydration_score', 0)),
        ("Texture", current.get('texture_score', 0), previous.get('texture_score', 0)),
        ("Pore Visibility", current.get('pore_score', 0), previous.get('pore_score', 0)),
        ("Wrinkles", current.get('wrinkle_score', 0), previous.get('wrinkle_score', 0)),
        ("Blemishes", current.get('blemish_score', 0), previous.get('blemish_score', 0)),
    ]
    for name, new_val, old_val in metrics:
        change = new_val - old_val
        change_pct = round((change / max(old_val, 1)) * 100, 1) if old_val else 0
        direction = "improved" if change > 0 else "declined" if change < 0 else "stable"
        notes = ""
        if name == "Hydration" and change < -10: notes = "Significant dehydration detected."
        elif name == "Blemishes" and change < -10: notes = "Breakout increase. Check for triggers."
        elif change > 15: notes = "Excellent improvement. Continue regimen."
        changes.append({"metric_name": name, "old_value": old_val, "new_value": new_val, "change": change, "change_percent": change_pct, "direction": direction, "notes": notes})
    return changes

@app.route('/')
def index():
    for base in [Path(__file__).resolve().parent.parent / 'static', Path('static'), Path('/var/task/static')]:
        idx = base / 'index.html'
        if idx.exists():
            return send_from_directory(str(base), 'index.html')
    emb = Path(__file__).parent / 'embedded_ui.html'
    if emb.exists():
        return emb.read_text(encoding='utf-8'), 200, {'Content-Type': 'text/html; charset=utf-8'}
    return jsonify({"message": "DermFlow Pro API is running", "docs": "/api/dashboard/stats"}), 200

@app.route('/css/<path:filename>')
def serve_css(filename):
    static = Path(app.static_folder)
    return send_from_directory(str(static / 'css'), filename)

@app.route('/js/<path:filename>')
def serve_js(filename):
    static = Path(app.static_folder)
    return send_from_directory(str(static / 'js'), filename)

@app.route('/manifest.json')
def serve_manifest():
    return send_from_directory(app.static_folder, 'manifest.json')

@app.route('/sw.js')
def serve_sw():
    return send_from_directory(app.static_folder, 'sw.js')

@app.route('/api/config', methods=['GET'])
def get_config():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM api_config WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"use_real_apis": False, "keys_configured": 0})
    config = dict(row)
    masked = {}
    key_count = 0
    for key, value in config.items():
        if key.endswith('_key') and value:
            masked[key] = value[:8] + "..." + value[-4:] if len(value) > 12 else "***"
            key_count += 1
        elif key.endswith('_key'):
            masked[key] = ""
        else:
            masked[key] = value
    masked['keys_configured'] = key_count
    return jsonify(masked)

@app.route('/api/config', methods=['POST'])
def save_config():
    data = request.json or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM api_config WHERE id = 1")
    exists = c.fetchone()
    fields = ['skin_analysis_key', 'makeup_vto_key', 'clothes_vto_key', 'jewelry_vto_key', 'bg_removal_key', 'enhancement_key', 'file_upload_key', 'use_real_apis']
    values = [data.get(f, '') for f in fields]
    if exists:
        set_clause = ', '.join([f"{f} = ?" for f in fields])
        c.execute(f"UPDATE api_config SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = 1", values)
    else:
        placeholders = ', '.join(['?' for _ in fields])
        c.execute(f"INSERT INTO api_config (id, {', '.join(fields)}, updated_at) VALUES (1, {placeholders}, CURRENT_TIMESTAMP)", values)
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "Configuration saved"})

@app.route('/api/config/test', methods=['POST'])
def test_config():
    data = request.json or {}
    use_real = data.get('use_real_apis', False)
    if not use_real:
        return jsonify({"success": True, "message": "Mock mode is working", "mode": "mock"})
    key = data.get('skin_analysis_key') or data.get('file_upload_key') or ''
    if not key or len(str(key)) < 8:
        return jsonify({"success": False, "error": "Please provide at least one valid API key"}), 400
    return jsonify({"success": True, "message": "Keys accepted", "mode": "real"})

@app.route('/api/patients', methods=['GET'])
def get_patients():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients ORDER BY created_at DESC")
    patients = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify(patients)

@app.route('/api/patients', methods=['POST'])
def create_patient():
    data = request.json or {}
    conn = get_db()
    c = conn.cursor()
    c.execute("INSERT INTO patients (name, email, phone, date_of_birth, skin_type, allergies) VALUES (?, ?, ?, ?, ?, ?)",
              (data.get('name'), data.get('email'), data.get('phone'), data.get('date_of_birth'), data.get('skin_type'), data.get('allergies')))
    conn.commit()
    patient_id = c.lastrowid
    conn.close()
    return jsonify({"id": patient_id, "message": "Patient created"}), 201

@app.route('/api/patients/<int:patient_id>', methods=['GET'])
def get_patient(patient_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    row = c.fetchone()
    patient = dict(row) if row else None
    c.execute("SELECT * FROM analyses WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,))
    analyses = [dict(row) for row in c.fetchall()]
    c.execute("SELECT * FROM face_changes WHERE patient_id = ? ORDER BY created_at DESC", (patient_id,))
    changes = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"patient": patient, "analyses": analyses, "face_changes": changes})

@app.route('/api/patients/<int:patient_id>/progress', methods=['GET'])
def get_progress(patient_id):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT id, created_at, overall_score, hydration_score, texture_score, pore_score, wrinkle_score, blemish_score FROM analyses WHERE patient_id = ? ORDER BY created_at ASC", (patient_id,))
    rows = c.fetchall()
    conn.close()
    return jsonify([{"analysis_id": r[0], "date": r[1], "overall": r[2], "hydration": r[3], "texture": r[4], "pores": r[5], "wrinkles": r[6], "blemishes": r[7]} for r in rows])

@app.route('/api/analyze', methods=['POST'])
def analyze_skin():
    if 'image' not in request.files:
        return jsonify({"error": "No image provided"}), 400
    file = request.files['image']
    patient_id = request.form.get('patient_id', type=int)
    if file and allowed_file(file.filename):
        filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
        filepath = UPLOAD_FOLDER / filename
        file.save(filepath)
        image_url = f"https://mock-s3.dermflow.dev/uploads/{filename}"
        analysis_result = mock_skin_analysis(image_url)
        scores = analysis_result['results']
        conn = get_db()
        c = conn.cursor()
        c.execute("""INSERT INTO analyses (patient_id, original_image, processed_image, skin_tone_hex, undertone,
            texture_score, pore_score, wrinkle_score, blemish_score, hydration_score, overall_score, raw_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, str(filepath), image_url, scores['skin_tone']['hex'], scores['skin_tone']['undertone'],
             scores['texture']['score'], scores['pore_visibility']['score'], scores['wrinkles']['score'],
             scores['blemishes']['score'], scores['hydration']['score'], scores['overall_health']['score'],
             json.dumps(analysis_result['results'])))
        analysis_id = c.lastrowid
        conn.commit()
        c.execute("SELECT * FROM analyses WHERE patient_id = ? AND id < ? ORDER BY created_at DESC LIMIT 1", (patient_id, analysis_id))
        prev_row = c.fetchone()
        face_changes = []
        if prev_row:
            previous = dict(prev_row)
            current = {
                'overall_score': scores['overall_health']['score'],
                'hydration_score': scores['hydration']['score'],
                'texture_score': scores['texture']['score'],
                'pore_score': scores['pore_visibility']['score'],
                'wrinkle_score': scores['wrinkles']['score'],
                'blemish_score': scores['blemishes']['score']
            }
            face_changes = calculate_face_changes(current, previous)
            for change in face_changes:
                c.execute("""INSERT INTO face_changes (patient_id, analysis_id, previous_analysis_id, change_type, metric_name,
                    old_value, new_value, change_percent, change_direction, notes)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (patient_id, analysis_id, previous['id'], 'metric_change', change['metric_name'],
                     change['old_value'], change['new_value'], change['change_percent'], change['direction'], change['notes']))
            conn.commit()
        treatment_plan = generate_treatment_plan(analysis_result)
        c.execute("""INSERT INTO treatment_plans (patient_id, analysis_id, am_routine, pm_routine, diet_suggestions, lifestyle_notes, follow_up_weeks)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (patient_id, analysis_id, json.dumps(treatment_plan['am_routine']),
             json.dumps(treatment_plan['pm_routine']), json.dumps(treatment_plan['diet_suggestions']),
             json.dumps(treatment_plan['lifestyle_notes']), treatment_plan['follow_up_weeks']))
        plan_id = c.lastrowid
        conn.commit()
        conn.close()
        return jsonify({
            "success": True, "analysis_id": analysis_id, "plan_id": plan_id,
            "analysis": analysis_result, "treatment_plan": treatment_plan,
            "face_changes": face_changes, "image_path": f"/uploads/{filename}"
        })
    return jsonify({"error": "Invalid file type"}), 400

@app.route('/api/dashboard/stats', methods=['GET'])
def get_dashboard_stats():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM patients")
    total_patients = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM analyses")
    total_analyses = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM treatment_plans")
    total_plans = c.fetchone()[0]
    c.execute("SELECT AVG(overall_score) FROM analyses")
    avg_score = c.fetchone()[0] or 0
    c.execute("SELECT * FROM analyses ORDER BY created_at DESC LIMIT 5")
    recent = [dict(row) for row in c.fetchall()]
    conn.close()
    return jsonify({"total_patients": total_patients, "total_analyses": total_analyses, "total_plans": total_plans,
                    "avg_skin_score": round(avg_score, 1), "recent_analyses": recent, "api_mode": "mock"})

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route('/api/reports/<int:patient_id>/<int:analysis_id>')
def get_report(patient_id, analysis_id):
    return jsonify({"message": "PDF report generation available in full version", "patient_id": patient_id, "analysis_id": analysis_id})

init_db()
