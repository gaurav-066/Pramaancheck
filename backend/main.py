# ==============================================================================
# PramaanCheck - Legal Metrology Compliance Inspection Platform
# ==============================================================================
# SCOPE DECISION & ARCHITECTURAL GAP DOCUMENTATION:
# Principle Display Panel (PDP) placement verification under Rule 6(2)
# (surface area ratios, positioning on front vs back panels) is deliberately
# out of scope for this MVP version. Surface area corner cropping and PDP positioning
# rules are reserved for future release.
# ==============================================================================

import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, UploadFile, Form, Depends, HTTPException, Response, Request, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from backend.auth import authenticate_user, create_session_token, verify_session_token, check_permission
from backend.ocr_engine import extract_declarations
from backend.rule_engine import evaluate_compliance
from backend.font_checker import verify_font_sizes
from backend.report_gen import generate_pdf_report
import backend.database as db

# Paths setup
BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

config = load_config()

if os.environ.get("VERCEL"):
    UPLOAD_DIR = Path("/tmp/uploads")
    REPORT_DIR = Path("/tmp/reports")
else:
    UPLOAD_DIR = (BASE_DIR / config.get("upload_dir", "../uploads")).resolve()
    REPORT_DIR = (BASE_DIR / config.get("report_dir", "../reports")).resolve()

FRONTEND_DIR = (BASE_DIR / "../frontend").resolve()

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)


from fastapi.middleware.gzip import GZipMiddleware

app = FastAPI(title="PramaanCheck API", version="1.0.0")

# Enable HTTP GZip compression for instant asset delivery & fast JSON payloads
app.add_middleware(GZipMiddleware, minimum_size=500)

# Initialize SQLite Database on startup
@app.on_event("startup")
def startup_event():
    db.init_db()


# Session auth dependency
def get_current_user(request: Request):
    token = request.cookies.get("session_token") or request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        return {"username": "inspector", "role": "inspector", "name": "Field Inspector"}
    payload = verify_session_token(token)
    if not payload:
        return {"username": "inspector", "role": "inspector", "name": "Field Inspector"}
    return payload

# ------------------------------------------------------------------------------
# Authentication Routes
# ------------------------------------------------------------------------------

@app.post("/api/login")
async def login(credentials: dict, response: Response):
    username = credentials.get("username", "").strip()
    password = credentials.get("password", "").strip()

    user = authenticate_user(username, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_session_token(user["username"], user["role"])
    
    # Set HTTP-only session cookie
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=config.get("session_max_age_hours", 24) * 3600,
        samesite="lax"
    )

    return {
        "status": "success",
        "user": user,
        "token": token
    }

@app.post("/api/logout")
async def logout(response: Response):
    response.delete_cookie("session_token")
    return {"status": "logged_out"}

@app.get("/api/me")
async def me(current_user: dict = Depends(get_current_user)):
    return {"user": current_user}

# ------------------------------------------------------------------------------
# Compliance Inspection Routes
# ------------------------------------------------------------------------------

@app.post("/api/scan")
async def process_scan(
    file: UploadFile = File(...),
    card_corners: Optional[str] = Form(None),
    current_user: dict = Depends(get_current_user)
):
    """
    Accepts product label image upload, performs OCR extraction,
    evaluates Legal Metrology Rule 6 compliance, performs Rule 7 font check,
    and stores scan in database.
    """
    try:
        # Check max file size
        max_mb = config.get("max_upload_size_mb", 10)
        contents = await file.read()
        if len(contents) > max_mb * 1024 * 1024:
            raise HTTPException(status_code=400, detail=f"File exceeds maximum allowed size of {max_mb} MB")

        # Generate unique filename & save file
        file_ext = Path(file.filename).suffix or ".jpg"
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        saved_image_path = UPLOAD_DIR / unique_filename

        with open(saved_image_path, "wb") as f:
            f.write(contents)

        # Parse optional card corners JSON
        parsed_corners = None
        if card_corners:
            try:
                parsed_corners = json.loads(card_corners)
            except Exception:
                parsed_corners = None

        # Step 1: OCR Extraction
        declarations = extract_declarations(str(saved_image_path))

        # Step 2: Rule 6 Compliance Evaluation
        rule_results = evaluate_compliance(declarations)

        # Step 3: Rule 7 Font Size Check
        font_check = verify_font_sizes(str(saved_image_path), declarations, parsed_corners)

        # Step 4: Save result to Database
        scan_id = db.save_scan(
            image_name=file.filename,
            image_path=f"/uploads/{unique_filename}",
            overall_status=rule_results["overall_status"],
            compliance_score=rule_results["compliance_score"],
            declarations=declarations,
            rule_results=rule_results,
            font_check=font_check,
            user_role=current_user.get("role", "inspector")
        )

        return {
            "status": "success",
            "scan_id": scan_id,
            "image_url": f"/uploads/{unique_filename}",
            "overall_status": rule_results["overall_status"],
            "compliance_score": rule_results["compliance_score"],
            "declarations": declarations,
            "rule_results": rule_results,
            "font_check": font_check
        }
    except HTTPException:
        raise
    except Exception as err:
        print(f"Error during scan processing: {err}")
        return JSONResponse(
            status_code=500,
            content={"detail": f"Scan processing error: {str(err)}"}
        )

@app.get("/api/dashboard/stats")
async def dashboard_stats(current_user: dict = Depends(get_current_user)):
    return db.get_dashboard_stats()

@app.get("/api/scans/recent")
async def recent_scans(current_user: dict = Depends(get_current_user)):
    return db.get_recent_scans(limit=10)

@app.get("/api/scans/{scan_id}")
async def get_scan_details(scan_id: int, current_user: dict = Depends(get_current_user)):
    scan = db.get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return scan

@app.get("/api/reports/download/{scan_id}")
async def download_report(scan_id: int, current_user: dict = Depends(get_current_user)):
    scan = db.get_scan_by_id(scan_id)
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")

    pdf_filename = f"scan_report_{scan_id}.pdf"
    pdf_path = REPORT_DIR / pdf_filename

    generate_pdf_report(scan, str(pdf_path))

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=pdf_filename
    )

# ------------------------------------------------------------------------------
# Serve Frontend Pages & Static Files
# ------------------------------------------------------------------------------

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    js_dir = FRONTEND_DIR / "js"
    if js_dir.exists():
        app.mount("/frontend/js", StaticFiles(directory=str(js_dir)), name="frontend_js")
        app.mount("/js", StaticFiles(directory=str(js_dir)), name="js")

    assets_dir = FRONTEND_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    fonts_dir = FRONTEND_DIR / "fonts"
    if fonts_dir.exists():
        app.mount("/fonts", StaticFiles(directory=str(fonts_dir)), name="fonts")

if UPLOAD_DIR.exists():
    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

if REPORT_DIR.exists():
    app.mount("/reports", StaticFiles(directory=str(REPORT_DIR)), name="reports")

@app.get("/styles.css")
async def serve_styles_css():
    css_file = FRONTEND_DIR / "styles.css"
    if css_file.exists():
        return FileResponse(css_file, media_type="text/css")
    raise HTTPException(status_code=404, detail="styles.css not found")

@app.get("/main.js")
async def serve_main_javascript():
    js_file = FRONTEND_DIR / "main.js"
    if js_file.exists():
        return FileResponse(js_file, media_type="application/javascript")
    raise HTTPException(status_code=404, detail="main.js not found")


@app.get("/")
async def serve_index():
    index_file = FRONTEND_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "PramaanCheck API Running"}

@app.get("/login")
async def serve_login():
    login_file = FRONTEND_DIR / "login.html"
    if login_file.exists():
        return FileResponse(login_file)
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/scan")
async def serve_scan():
    scan_file = FRONTEND_DIR / "scan.html"
    if scan_file.exists():
        return FileResponse(scan_file)
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/dashboard")
async def serve_dashboard():
    dashboard_file = FRONTEND_DIR / "dashboard.html"
    if dashboard_file.exists():
        return FileResponse(dashboard_file)
    return FileResponse(FRONTEND_DIR / "index.html")

