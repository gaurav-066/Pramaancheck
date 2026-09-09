import os
import json
import math
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple
import cv2
import numpy as np
import pytesseract

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# Standard ID Card Dimensions (ISO/IEC 7810 ID-1)
REF_CARD_WIDTH_MM = 85.6
REF_CARD_HEIGHT_MM = 53.98

def calculate_pixels_per_mm(card_corners: Optional[List[List[float]]], image_shape: Tuple[int, ...]) -> float:
    """
    Calculates scale factor (pixels per millimeter).
    If card_corners [[x1,y1], [x2,y2], [x3,y3], [x4,y4]] is provided:
        Computes Euclidean distance between top-left and top-right corner to get card width in pixels.
        pixels_per_mm = width_px / 85.6 mm.
    If no corners provided:
        Uses heuristic: assumes image width represents ~120 mm label width.
    """
    if card_corners and len(card_corners) == 4:
        p1 = np.array(card_corners[0], dtype=np.float32)
        p2 = np.array(card_corners[1], dtype=np.float32)
        p3 = np.array(card_corners[2], dtype=np.float32)
        p4 = np.array(card_corners[3], dtype=np.float32)

        # Top width and bottom width
        width_top = np.linalg.norm(p2 - p1)
        width_bottom = np.linalg.norm(p3 - p4)
        avg_width_px = (width_top + width_bottom) / 2.0

        if avg_width_px > 10:
            return float(avg_width_px / REF_CARD_WIDTH_MM)

    # Heuristic fallback: image_width / 120 mm
    img_h, img_w = image_shape[:2]
    estimated_label_width_mm = 120.0
    return float(img_w / estimated_label_width_mm)

def get_required_font_height_mm(net_qty_val: Optional[float], unit: Optional[str]) -> float:
    """
    Legal Metrology (Packaged Commodities) Rules, 2011 - Rule 7 Table-I:
    - Net quantity <= 200g or 200ml: 1.0 mm
    - Net quantity > 200g/ml up to 500g/ml: 2.0 mm
    - Net quantity > 500g/ml: 4.0 mm
    Default fallback if quantity is missing: 2.0 mm
    """
    if net_qty_val is None:
        return 2.0

    unit_clean = (unit or "").lower().strip()
    # Convert kg to g, L to ml
    val_in_base = net_qty_val
    if unit_clean in ["kg", "l"]:
        val_in_base = net_qty_val * 1000.0

    if val_in_base <= 200:
        return 1.0
    elif val_in_base <= 500:
        return 2.0
    else:
        return 4.0

def verify_font_sizes(
    image_path: str,
    declarations: Dict[str, Any],
    card_corners: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Evaluates font heights and width ratios for declarations according to Rule 7.
    Returns detailed compliance breakdown and detected font measurements.
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

    px_per_mm = calculate_pixels_per_mm(card_corners, img.shape)
    req_height_mm = get_required_font_height_mm(
        declarations.get("net_quantity_value"),
        declarations.get("net_quantity_unit")
    )

    # Perform pytesseract word bounding box extraction
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    ocr_data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)

    font_checks: List[Dict[str, Any]] = []

    # Target terms to check for font height
    target_terms = []
    if declarations.get("net_quantity_text"):
        target_terms.append(("Net Quantity", str(declarations["net_quantity_text"])))
    if declarations.get("mrp_value"):
        target_terms.append(("MRP", str(declarations["mrp_value"])))

    # Collect detected word boxes
    n_boxes = len(ocr_data["text"])
    detected_heights_mm: List[float] = []

    for i in range(n_boxes):
        text = ocr_data["text"][i].strip()
        conf = int(ocr_data["conf"][i])
        if conf > 30 and len(text) > 0:
            h_px = ocr_data["height"][i]
            w_px = ocr_data["width"][i]
            h_mm = h_px / px_per_mm
            w_per_char_mm = (w_px / len(text)) / px_per_mm

            detected_heights_mm.append(h_mm)

            # Check if this box matches net qty or MRP numbers
            net_val_str = str(declarations.get("net_quantity_value") or "")
            mrp_val_str = str(declarations.get("mrp_value") or "")

            if (net_val_str and net_val_str in text) or (mrp_val_str and mrp_val_str in text) or ("mrp" in text.lower()):
                # Rule 7(3): Letter width >= 1/3 of height (except 1, i, I, l)
                width_ratio_valid = (w_per_char_mm >= (h_mm / 3.0)) or any(c in text for c in ["1", "i", "I", "l"])

                font_checks.append({
                    "target": text,
                    "height_mm": round(h_mm, 2),
                    "required_height_mm": req_height_mm,
                    "height_pass": h_mm >= req_height_mm,
                    "width_ratio_pass": width_ratio_valid,
                    "confidence": conf
                })

    # Summary evaluation
    avg_height_mm = round(float(np.mean(detected_heights_mm)), 2) if detected_heights_mm else 0.0
    height_compliant = all(c["height_pass"] for c in font_checks) if font_checks else (avg_height_mm >= req_height_mm)

    return {
        "status": "PASS" if height_compliant else "FAIL",
        "pixels_per_mm": round(px_per_mm, 2),
        "calibration_method": "card_corners" if card_corners else "heuristic_fallback",
        "required_height_mm": req_height_mm,
        "average_font_height_mm": avg_height_mm,
        "font_checks": font_checks,
        "rule_7_details": (
            f"Required height: {req_height_mm}mm based on net quantity. "
            f"Detected avg font height: {avg_height_mm}mm."
        )
    }
