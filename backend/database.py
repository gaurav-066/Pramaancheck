import sqlite3
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

import os

def get_db_path() -> Path:
    if os.environ.get("VERCEL"):
        return Path("/tmp/pramaancheck.db")
    config = load_config()
    relative_path = config.get("db_path", "../pramaancheck.db")
    # Resolve relative to backend directory
    return (Path(__file__).parent / relative_path).resolve()


def init_db():
    """
    Initializes SQLite database schema for scans table.
    """
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_name TEXT NOT NULL,
                image_path TEXT NOT NULL,
                overall_status TEXT NOT NULL,
                compliance_score REAL NOT NULL,
                declarations_json TEXT NOT NULL,
                rule_results_json TEXT NOT NULL,
                font_check_json TEXT NOT NULL,
                user_role TEXT DEFAULT 'inspector',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def save_scan(
    image_name: str,
    image_path: str,
    overall_status: str,
    compliance_score: float,
    declarations: Dict[str, Any],
    rule_results: Dict[str, Any],
    font_check: Dict[str, Any],
    user_role: str = "inspector"
) -> int:
    """
    Saves scan result to SQLite database. Returns inserted scan ID.
    Auto-initializes schema if database file does not exist on Vercel serverless.
    """
    try:
        init_db()
        db_path = get_db_path()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO scans (
                    image_name, image_path, overall_status, compliance_score,
                    declarations_json, rule_results_json, font_check_json, user_role
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                image_name,
                image_path,
                overall_status,
                compliance_score,
                json.dumps(declarations),
                json.dumps(rule_results),
                json.dumps(font_check),
                user_role
            ))
            conn.commit()
            return cursor.lastrowid
    except Exception as err:
        print(f"[Database Error] save_scan failed: {err}")
        return 0

def get_recent_scans(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieves most recent scans (up to limit) for dashboard display.
    """
    try:
        init_db()
        db_path = get_db_path()
        if not db_path.exists():
            return []

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, image_name, image_path, overall_status, compliance_score,
                       user_role, created_at
                FROM scans
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
    except Exception as err:
        print(f"[Database Error] get_recent_scans failed: {err}")
        return []

def get_scan_by_id(scan_id: int) -> Optional[Dict[str, Any]]:
    """
    Retrieves full scan details by scan ID.
    """
    try:
        init_db()
        db_path = get_db_path()
        if not db_path.exists():
            return None

        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
            row = cursor.fetchone()
            if not row:
                return None
            res = dict(row)
            res["declarations"] = json.loads(res["declarations_json"])
            res["rule_results"] = json.loads(res["rule_results_json"])
            res["font_check"] = json.loads(res["font_check_json"])
            return res
    except Exception as err:
        print(f"[Database Error] get_scan_by_id failed: {err}")
        return None

def get_dashboard_stats() -> Dict[str, Any]:
    """
    Calculates summary metrics: Total Scans, Compliance Rate %, Violations Found.
    """
    try:
        init_db()
        db_path = get_db_path()
        if not db_path.exists():
            return {"total_scans": 0, "compliance_rate": 0.0, "violations_found": 0}

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM scans")
            total_scans = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM scans WHERE overall_status = 'COMPLIANT'")
            compliant_scans = cursor.fetchone()[0] or 0

            cursor.execute("SELECT COUNT(*) FROM scans WHERE overall_status = 'NON_COMPLIANT'")
            violations_found = cursor.fetchone()[0] or 0

            compliance_rate = round((compliant_scans / total_scans * 100), 1) if total_scans > 0 else 0.0

            return {
                "total_scans": total_scans,
                "compliance_rate": compliance_rate,
                "violations_found": violations_found
            }
    except Exception as err:
        print(f"[Database Error] get_dashboard_stats failed: {err}")
        return {"total_scans": 0, "compliance_rate": 0.0, "violations_found": 0}
