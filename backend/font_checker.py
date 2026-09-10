import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np
import pytesseract

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

# Standard ID Card Dimensions (ISO/IEC 7810 ID-1) — debit card / college ID
REF_CARD_WIDTH_MM  = 85.6
REF_CARD_HEIGHT_MM = 53.98

# ──────────────────────────────────────────────────────────────────────────────
# CARD AUTO-DETECTION ENGINE
# ──────────────────────────────────────────────────────────────────────────────

def _order_points(pts: np.ndarray) -> np.ndarray:
    """
    Order 4 points as: top-left, top-right, bottom-right, bottom-left.
    Needed so calculate_pixels_per_mm gets consistent corner ordering.
    """
    rect = np.zeros((4, 2), dtype=np.float32)
    s    = pts.sum(axis=1)
    diff = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]     # top-left: smallest x+y
    rect[2] = pts[np.argmax(s)]     # bottom-right: largest x+y
    rect[1] = pts[np.argmin(diff)]  # top-right: smallest y-x
    rect[3] = pts[np.argmax(diff)]  # bottom-left: largest y-x
    return rect


def _detect_orange_strip(img: np.ndarray) -> Optional[Tuple[List[List[float]], str]]:
    """
    Strategy 1 — HSV orange-strip detection with geometric & texture validation.
    Works for JKLU-style IDs and cards with an orange band.
    Strictly filters out orange product packaging using aspect ratio & solidity checks.
    """
    try:
        h_img, w_img = img.shape[:2]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Orange hue band: 0-25° covers warm orange → reddish-orange
        mask1 = cv2.inRange(hsv, np.array([0,  80,  80]), np.array([5,  255, 255]))
        mask2 = cv2.inRange(hsv, np.array([5,  80,  80]), np.array([25, 255, 255]))
        orange_mask = cv2.bitwise_or(mask1, mask2)

        # Morphological closing to fill gaps caused by lighting variation
        k = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 9))
        orange_mask = cv2.morphologyEx(orange_mask, cv2.MORPH_CLOSE, k)
        orange_mask = cv2.morphologyEx(orange_mask, cv2.MORPH_OPEN,  k)

        contours, _ = cv2.findContours(orange_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        total_px = h_img * w_img

        valid_strips = []
        for c in contours:
            area = cv2.contourArea(c)
            # 1. Size Filter: Strip should be between 0.3% and 15% of image area
            if not (total_px * 0.003 < area < total_px * 0.15):
                continue

            # 2. Solidity (Convexity) Filter: Card strip is a clean rectangle, not blobby packaging
            hull = cv2.convexHull(c)
            hull_area = cv2.contourArea(hull)
            if hull_area <= 0:
                continue
            solidity = area / hull_area
            if solidity < 0.82:  # Irregular orange product graphics rejected
                continue

            # 3. Aspect Ratio Filter: Strip must be elongated (narrow stripe)
            x, y, bw, bh = cv2.boundingRect(c)
            if bw == 0 or bh == 0:
                continue
            strip_ratio = max(bw, bh) / min(bw, bh)
            if strip_ratio < 2.0:  # Square/wide orange product areas rejected!
                continue

            valid_strips.append((c, area, bw, bh, x, y, strip_ratio))

        if not valid_strips:
            return None

        # Pick the largest geometrically valid strip
        best_c, area, bw, bh, x, y, strip_ratio = max(valid_strips, key=lambda item: item[1])

        rect = cv2.minAreaRect(best_c)
        rw, rh = rect[1]
        long_dim = max(rw, rh)

        if rh > rw:  # Vertical side strip
            px_per_mm = long_dim / REF_CARD_HEIGHT_MM
        else:       # Horizontal top/bottom strip
            px_per_mm = long_dim / REF_CARD_WIDTH_MM

        card_w_px = REF_CARD_WIDTH_MM  * px_per_mm
        card_h_px = REF_CARD_HEIGHT_MM * px_per_mm

        # 4. Dimension Sanity Check: Reconstructed card size must be 10%-85% of image width
        if not (w_img * 0.10 < card_w_px < w_img * 0.85):
            print("[Card Detect] Reconstructed card width unreasonable — passing to rectangle strategy")
            return None

        if rh > rw:  # vertical strip — on right edge of card
            card_left = x - (card_w_px - bw)
            card_top  = y
            corners = [
                [card_left,        card_top],
                [x + bw,           card_top],
                [x + bw,           card_top + card_h_px],
                [card_left,        card_top + card_h_px],
            ]
        else:  # horizontal strip — on bottom edge of card
            card_top  = y - (card_h_px - bh)
            card_left = x
            corners = [
                [card_left,            card_top],
                [card_left + card_w_px, card_top],
                [card_left + card_w_px, y + bh],
                [card_left,            y + bh],
            ]

        corners = [[float(c[0]), float(c[1])] for c in corners]
        print(f"[Card Detect] Validated Orange strip found — px/mm={px_per_mm:.2f}, strip_ratio={strip_ratio:.2f}")
        return corners, "orange_strip_auto"

    except Exception as e:
        print(f"[Card Detect] Orange strip strategy error: {e}")
        return None


def _detect_rectangle_contour(img: np.ndarray) -> Optional[Tuple[List[List[float]], str]]:
    """
    Strategy 2 — CLAHE-enhanced multi-parameter rectangle contour detection.
    Handles blurry, poorly lit, angled officer photos.
    Returns (4_corners, method_label) or None.
    """
    try:
        h_img, w_img = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # CLAHE: boosts local contrast — critical for dark/washed-out photos
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        gray  = clahe.apply(gray)

        # Try progressively gentler blur + different Canny thresholds
        # to handle: sharp photos, blurry photos, low-contrast photos
        params = [
            (3,  40,  120),
            (5,  30,  100),
            (7,  20,   80),
            (9,  15,   60),
            (5,  50,  150),
        ]

        for blur_k, lo, hi in params:
            blurred = cv2.GaussianBlur(gray, (blur_k, blur_k), 0)
            edges   = cv2.Canny(blurred, lo, hi)

            # Dilate edges to bridge small gaps (common in real photos)
            k     = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
            edges = cv2.dilate(edges, k, iterations=2)

            contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
            contours     = sorted(contours, key=cv2.contourArea, reverse=True)

            for cnt in contours[:15]:
                area = cv2.contourArea(cnt)
                # Card must be at least 3% of the image
                if area < h_img * w_img * 0.03:
                    break

                peri = cv2.arcLength(cnt, True)
                # Try multiple epsilon values — handles curved/rounded card corners
                for eps in [0.02, 0.03, 0.04, 0.05, 0.06]:
                    approx = cv2.approxPolyDP(cnt, eps * peri, True)
                    if len(approx) == 4:
                        pts = approx.reshape(4, 2).astype(float)
                        x, y, w, h = cv2.boundingRect(approx)
                        if w == 0 or h == 0:
                            continue
                        ratio = max(w, h) / min(w, h)
                        # ID-1 aspect ratio = 1.585 — allow ±30% for perspective distortion
                        if 1.1 < ratio < 2.1:
                            ordered = _order_points(pts)
                            corners = [[float(p[0]), float(p[1])] for p in ordered]
                            print(f"[Card Detect] Rectangle contour found — "
                                  f"blur={blur_k}, ratio={ratio:.2f}, area={int(area)}")
                            return corners, "rectangle_auto"

    except Exception as e:
        print(f"[Card Detect] Rectangle contour strategy error: {e}")

    return None


def auto_detect_card(img: np.ndarray) -> Tuple[Optional[List[List[float]]], str]:
    """
    Master card detection function.
    Tries orange strip first (fastest, most reliable for JKLU-style IDs).
    Falls back to general rectangle contour detection.
    Returns (corners_or_None, method_label).
    """
    # Strategy 1: orange strip
    result = _detect_orange_strip(img)
    if result:
        return result  # (corners, method)

    # Strategy 2: generic rectangle
    result = _detect_rectangle_contour(img)
    if result:
        return result  # (corners, method)

    print("[Card Detect] All strategies failed — using heuristic fallback")
    return None, "heuristic_fallback"


# ──────────────────────────────────────────────────────────────────────────────
# SCALE CALCULATION
# ──────────────────────────────────────────────────────────────────────────────

def calculate_pixels_per_mm(
    card_corners: Optional[List[List[float]]],
    image_shape: Tuple[int, ...]
) -> float:
    """
    Calculates pixels-per-mm scale factor.
    Uses card width (top-left → top-right Euclidean distance) when corners available.
    Falls back to heuristic (image width / 120mm assumed label width).
    """
    if card_corners and len(card_corners) == 4:
        p1 = np.array(card_corners[0], dtype=np.float32)
        p2 = np.array(card_corners[1], dtype=np.float32)
        p3 = np.array(card_corners[2], dtype=np.float32)
        p4 = np.array(card_corners[3], dtype=np.float32)

        width_top    = np.linalg.norm(p2 - p1)
        width_bottom = np.linalg.norm(p3 - p4)
        avg_width_px = (width_top + width_bottom) / 2.0

        if avg_width_px > 10:
            return float(avg_width_px / REF_CARD_WIDTH_MM)

    # Heuristic: assume label width ≈ 120mm
    img_w = image_shape[1]
    return float(img_w / 120.0)


# ──────────────────────────────────────────────────────────────────────────────
# RULE 7 THRESHOLD LOOKUP
# ──────────────────────────────────────────────────────────────────────────────

def get_required_font_height_mm(net_qty_val: Optional[float], unit: Optional[str]) -> float:
    """
    Legal Metrology (Packaged Commodities) Rules, 2011 — Rule 7 Table-I:
    - Net quantity <= 200 g or ml  →  1.0 mm
    - Net quantity 200–500 g/ml    →  2.0 mm
    - Net quantity > 500 g/ml      →  4.0 mm
    Default if quantity unknown: 2.0 mm
    """
    if net_qty_val is None:
        return 2.0

    unit_clean = (unit or "").lower().strip()
    val = net_qty_val
    if unit_clean in ["kg", "l"]:
        val = net_qty_val * 1000.0

    if val <= 200:
        return 1.0
    elif val <= 500:
        return 2.0
    else:
        return 4.0


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ──────────────────────────────────────────────────────────────────────────────

def verify_font_sizes(
    image_path: str,
    declarations: Dict[str, Any],
    card_corners: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Rule 7 font height compliance check.
    Auto-detects reference ID card if no corners supplied.
    Returns compliance breakdown with detected measurements.
    """
    config = load_config()
    tesseract_cmd = config.get("tesseract_cmd", "/usr/bin/tesseract")
    if os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    img = cv2.imread(image_path)
    if img is None:
        return {
            "status": "ERROR",
            "message": f"Could not load image at {image_path}",
            "font_checks": []
        }

    # ── Card calibration ───────────────────────────────────────────────────
    calibration_method = "manual_corners"
    if card_corners is None:
        card_corners, calibration_method = auto_detect_card(img)

    px_per_mm = calculate_pixels_per_mm(card_corners, img.shape)

    req_height_mm = get_required_font_height_mm(
        declarations.get("net_quantity_value"),
        declarations.get("net_quantity_unit")
    )

    # ── Tesseract bounding box extraction ─────────────────────────────────
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Apply CLAHE here too for consistent text detection in bad photos
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray  = clahe.apply(gray)

    try:
        ocr_data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
    except Exception as e:
        print(f"[Font Checker] Tesseract unavailable: {e}")
        return {
            "status": "SKIPPED",
            "pixels_per_mm": round(px_per_mm, 2),
            "calibration_method": calibration_method,
            "required_height_mm": req_height_mm,
            "average_font_height_mm": 0.0,
            "font_checks": [],
            "rule_7_details": (
                f"Rule 7 font check requires Tesseract OCR (unavailable in this "
                f"environment). Required height: {req_height_mm}mm."
            )
        }

    font_checks: List[Dict[str, Any]] = []
    detected_heights_mm: List[float] = []

    net_val_str = str(declarations.get("net_quantity_value") or "")
    mrp_val_str = str(declarations.get("mrp_value") or "")

    n_boxes = len(ocr_data["text"])
    for i in range(n_boxes):
        text = ocr_data["text"][i].strip()
        conf = int(ocr_data["conf"][i])
        if conf > 30 and len(text) > 0:
            h_px = ocr_data["height"][i]
            w_px = ocr_data["width"][i]
            h_mm = h_px / px_per_mm
            w_per_char_mm = (w_px / len(text)) / px_per_mm

            detected_heights_mm.append(h_mm)

            # Check MRP and net quantity text specifically
            is_target = (
                (net_val_str and net_val_str in text)
                or (mrp_val_str and mrp_val_str in text)
                or ("mrp" in text.lower())
            )
            if is_target:
                # Rule 7(3): width of character >= 1/3 of its height
                width_ratio_valid = (w_per_char_mm >= (h_mm / 3.0)) or \
                                    any(c in text for c in ["1", "i", "I", "l"])
                font_checks.append({
                    "target": text,
                    "height_mm": round(h_mm, 2),
                    "required_height_mm": req_height_mm,
                    "height_pass": h_mm >= req_height_mm,
                    "width_ratio_pass": width_ratio_valid,
                    "confidence": conf
                })

    avg_height_mm   = round(float(np.mean(detected_heights_mm)), 2) if detected_heights_mm else 0.0
    height_compliant = all(c["height_pass"] for c in font_checks) if font_checks \
                       else (avg_height_mm >= req_height_mm)

    return {
        "status": "PASS" if height_compliant else "FAIL",
        "pixels_per_mm": round(px_per_mm, 2),
        "calibration_method": calibration_method,
        "required_height_mm": req_height_mm,
        "average_font_height_mm": avg_height_mm,
        "font_checks": font_checks,
        "rule_7_details": (
            f"Calibration: {calibration_method}. "
            f"Required: {req_height_mm}mm. "
            f"Avg detected: {avg_height_mm}mm."
        )
    }
