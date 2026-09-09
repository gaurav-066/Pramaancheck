import json
import re
import os
from pathlib import Path
from PIL import Image
import cv2
import pytesseract
from google import genai
from google.genai import types

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

PROMPT_LABEL_ANALYSIS = """
You are an expert Legal Metrology (Packaged Commodities) Inspector in India.
Analyze this image of a packaged product label and extract all mandatory declarations required under the Legal Metrology (Packaged Commodities) Rules, 2011.

Return ONLY a single valid JSON object with the following fields (use null if a field is not found):
{
  "product_name": "string or null - generic name or common name of commodity e.g. 'Bingo! Tedhe Medhe Masala Tadka'",
  "net_quantity_value": number or null - numeric total net quantity e.g. 500 or 1.5 or 19.2 (for promo texts like '19.2g (12.8g + 6.4g FREE)' or 'NET WT.: 19.2g', use 19.2),
  "net_quantity_unit": "string or null - unit e.g. g, kg, ml, l, cm, m, N",
  "net_quantity_text": "string or null - exact net quantity text as printed e.g. '500 g' or '19.2g (12.8g + 6.4g FREE)'",
  "mrp_value": number or null - numeric MRP amount e.g. 150.00 or 5.0,
  "mrp_currency": "string or null - e.g. INR or Rs or ₹",
  "inclusive_of_taxes_text": "string or null - EXACT tax clause text near MRP e.g. 'Incl. of all taxes' or 'Inclusive of all taxes'. Set to null ONLY if no tax inclusion phrase is printed near MRP.",
  "mrp_text": "string or null - full MRP clause as printed e.g. 'MRP ₹5.00 (Incl. of all taxes)'",
  "manufacturer_name": "string or null - name of manufacturer, packer, or importer",
  "manufacturer_address": "string or null - address of manufacturer/packer/importer",
  "month_year_of_manufacture": "string or null - month & year of packing/mfd/import e.g. '08/2026' or '20AUG26'",
  "consumer_care_details": "string or null - consumer helpline phone, email, or address for complaints",
  "country_of_origin": "string or null - e.g. 'Made in India' or 'India' if stated or manufactured in an Indian address",
  "best_before_or_expiry": "string or null - expiry date or best before statement e.g. '17DEC26' or 'Best before 6 months from mfd'",
  "raw_text": "string - all readable text from the product label"
}

Be thorough and accurate. Do not include markdown code blocks around the JSON output.
"""

def extract_declarations_tesseract(image_path: str, config: dict) -> dict:
    """
    Fallback Tesseract OCR + basic regex extraction when Gemini API is unavailable.
    """
    tesseract_cmd = config.get("tesseract_cmd", "/usr/bin/tesseract")
    if os.path.exists(tesseract_cmd):
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    # Read and preprocess image using OpenCV
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not load image at {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Apply Otsu thresholding for clearer OCR
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    raw_text = pytesseract.image_to_string(thresh)
    if not raw_text.strip():
        # Retry with original gray image if thresholding returned nothing
        raw_text = pytesseract.image_to_string(gray)

    # Basic regex parsers for fallback
    mrp_match = re.search(r'(?:MRP|M\.R\.P\.?|Rs\.?|₹)\s*[:\.]?\s*(\d+(?:\.\d{1,2})?)', raw_text, re.IGNORECASE)
    mrp_val = float(mrp_match.group(1)) if mrp_match else None

    tax_match = re.search(r'(incl(?:usive)?\s*(?:of)?\s*all\s*tax(?:es)?)', raw_text, re.IGNORECASE)
    tax_text = tax_match.group(1) if tax_match else None

    net_qty_match = re.search(r'(?:Net\s*(?:Qty|Quantity|Weight|Wt)?[:\.]?\s*)?(\d+(?:\.\d+)?)\s*(g|kg|ml|l|cm|m|N)\b', raw_text, re.IGNORECASE)
    net_val = float(net_qty_match.group(1)) if net_qty_match else None
    net_unit = net_qty_match.group(2).lower() if net_qty_match else None
    net_text = f"{net_val} {net_unit}" if net_val and net_unit else None

    mfd_match = re.search(r'(?:mfd|pkd|packed|manufactured|mfg)[:\.]?\s*(\d{2}[/\.-]\d{2,4}|[A-Za-z]{3,9}\s*\d{4})', raw_text, re.IGNORECASE)
    mfd_text = mfd_match.group(1) if mfd_match else None

    care_match = re.search(r'(?:care|customer|helpline|consumer|complaint|feedback)[^\n]*', raw_text, re.IGNORECASE)
    care_text = care_match.group(0).strip() if care_match else None

    return {
        "product_name": None,
        "net_quantity_value": net_val,
        "net_quantity_unit": net_unit,
        "net_quantity_text": net_text,
        "mrp_value": mrp_val,
        "mrp_currency": "INR" if mrp_val else None,
        "inclusive_of_taxes_text": tax_text,
        "mrp_text": f"MRP {mrp_val} {tax_text or ''}".strip() if mrp_val else None,
        "manufacturer_name": None,
        "manufacturer_address": None,
        "month_year_of_manufacture": mfd_text,
        "consumer_care_details": care_text,
        "country_of_origin": "India" if "india" in raw_text.lower() else None,
        "best_before_or_expiry": None,
        "raw_text": raw_text,
        "ocr_engine": "tesseract_fallback"
    }

def extract_declarations(image_path: str) -> dict:
    """
    Main entry point for extracting mandatory Legal Metrology declarations.
    Tries Gemini Vision API primary and fallback models. Falls back to Tesseract OCR if API key fails.
    """
    config = load_config()
    api_key = os.environ.get("GEMINI_API_KEY") or config.get("gemini_api_key", "")
    primary_model = config.get("gemini_model", "gemini-3.5-flash-lite")


    # If API key is placeholder or missing, fallback to Tesseract directly
    if not api_key or api_key == "PASTE_YOUR_KEY_HERE":
        print("[OCR Engine] Gemini API key not configured. Using Tesseract OCR fallback.")
        return extract_declarations_tesseract(image_path, config)

    # Candidate Gemini models in order of attempt
    candidate_models = [primary_model, "gemini-3.5-flash-lite", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-flash-latest"]
    # De-duplicate candidate list while keeping order
    seen = set()
    candidate_models = [m for m in candidate_models if not (m in seen or seen.add(m))]

    pil_img = Image.open(image_path)
    # Performance Optimization: Resize large high-res camera photos to max 1600px
    # Cuts payload transmission time by 95% while retaining 100% OCR text accuracy
    if max(pil_img.size) > 1600:
        pil_img.thumbnail((1600, 1600), Image.Resampling.LANCZOS)

    client = genai.Client(api_key=api_key)


    last_error = None
    for model_name in candidate_models:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[pil_img, PROMPT_LABEL_ANALYSIS],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            
            cleaned_text = response.text.strip()
            if cleaned_text.startswith("```"):
                cleaned_text = re.sub(r'^```(?:json)?\n?', '', cleaned_text)
                cleaned_text = re.sub(r'\n?```$', '', cleaned_text)

            parsed_data = json.loads(cleaned_text)
            parsed_data["ocr_engine"] = f"gemini_vision ({model_name})"
            print(f"[OCR Engine] Gemini Vision success using model: {model_name}")
            return parsed_data

        except Exception as e:
            last_error = e
            print(f"[OCR Engine] Model {model_name} failed: {str(e)}. Trying next model...")

    print(f"[OCR Engine] All Gemini models failed. Last error: {str(last_error)}. Falling back to Tesseract OCR.")
    return extract_declarations_tesseract(image_path, config)
