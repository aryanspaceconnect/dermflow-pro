"""
DermFlow Pro - Enhanced Database Layer
Tracks facial changes over time with image preprocessing metadata.
"""
import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).parent / "dermflow.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_config (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            skin_analysis_key TEXT,
            makeup_vto_key TEXT,
            clothes_vto_key TEXT,
            jewelry_vto_key TEXT,
            bg_removal_key TEXT,
            enhancement_key TEXT,
            file_upload_key TEXT,
            use_real_apis BOOLEAN DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            date_of_birth TEXT,
            skin_type TEXT,
            allergies TEXT,
            baseline_photo TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            original_image TEXT,
            processed_image TEXT,
            preprocessed_image TEXT,
            skin_tone_hex TEXT,
            undertone TEXT,
            texture_score INTEGER,
            pore_score INTEGER,
            wrinkle_score INTEGER,
            blemish_score INTEGER,
            hydration_score INTEGER,
            overall_score INTEGER,
            preprocessing_applied TEXT,
            raw_data TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS face_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            analysis_id INTEGER NOT NULL,
            previous_analysis_id INTEGER,
            change_type TEXT,
            metric_name TEXT,
            old_value REAL,
            new_value REAL,
            change_percent REAL,
            change_direction TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS treatment_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            analysis_id INTEGER NOT NULL,
            am_routine TEXT,
            pm_routine TEXT,
            diet_suggestions TEXT,
            lifestyle_notes TEXT,
            follow_up_weeks INTEGER DEFAULT 4,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id),
            FOREIGN KEY (analysis_id) REFERENCES analyses(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id INTEGER NOT NULL,
            reminder_type TEXT,
            message TEXT,
            scheduled_time TEXT,
            sent BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (patient_id) REFERENCES patients(id)
        )
    """)
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def seed_demo_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM patients")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    patients = [
        ("Sarah Chen", "sarah.chen@email.com", "555-0101", "1992-03-15", "Combination", "None", None),
        ("Marcus Johnson", "mjohnson@email.com", "555-0102", "1985-07-22", "Oily", "Fragrance", None),
        ("Aisha Patel", "aisha.p@email.com", "555-0103", "1990-11-08", "Dry", "Retinol sensitivity", None),
        ("David Kim", "dkim@email.com", "555-0104", "1978-01-30", "Sensitive", "Aloe vera", None),
    ]
    c.executemany("""
        INSERT INTO patients (name, email, phone, date_of_birth, skin_type, allergies, baseline_photo)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, patients)
    conn.commit()
    conn.close()
