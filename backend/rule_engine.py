from typing import Dict, Any, List

def evaluate_compliance(declarations: Dict[str, Any]) -> Dict[str, Any]:
    """
    Evaluates extracted product declarations against Legal Metrology 
    (Packaged Commodities) Rules, 2011 (Rule 6).
    """
    rules_results: List[Dict[str, Any]] = []

    # Helper to add rule result
    def add_rule(rule_id: str, rule_name: str, status: str, severity: str, details: str, act_section: str = "Rule 6(1)"):
        rules_results.append({
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": status,  # "PASS", "FAIL", "WARNING"
            "severity": severity,  # "CRITICAL", "MEDIUM", "LOW"
            "details": details,
            "act_section": act_section
        })

    # 1. Product Name / Generic Name
    prod_name = declarations.get("product_name")
    if prod_name and str(prod_name).strip():
        add_rule(
            "RULE_6_PRODUCT_NAME",
            "Generic / Common Name of Commodity",
            "PASS",
            "CRITICAL",
            f"Declared product name: '{prod_name}'",
            "Rule 6(1)(a)"
        )
    else:
        add_rule(
            "RULE_6_PRODUCT_NAME",
            "Generic / Common Name of Commodity",
            "FAIL",
            "CRITICAL",
            "Missing generic or common name of commodity on label.",
            "Rule 6(1)(a)"
        )

    # 2. Net Quantity
    net_qty_val = declarations.get("net_quantity_value")
    net_qty_unit = declarations.get("net_quantity_unit")
    net_qty_text = declarations.get("net_quantity_text")

    if (net_qty_val is not None and net_qty_unit) or (net_qty_text and str(net_qty_text).strip()):
        add_rule(
            "RULE_6_NET_QUANTITY",
            "Net Quantity Declaration",
            "PASS",
            "CRITICAL",
            f"Declared net quantity: '{net_qty_text or f'{net_qty_val} {net_qty_unit}'}'",
            "Rule 6(1)(b)"
        )
    else:
        add_rule(
            "RULE_6_NET_QUANTITY",
            "Net Quantity Declaration",
            "FAIL",
            "CRITICAL",
            "Missing net quantity statement or unit.",
            "Rule 6(1)(b)"
        )

    # 3. MRP Declaration
    mrp_val = declarations.get("mrp_value")
    mrp_text = declarations.get("mrp_text")

    if mrp_val is not None or (mrp_text and str(mrp_text).strip()):
        add_rule(
            "RULE_6_MRP_VALUE",
            "Maximum Retail Price (MRP) Declaration",
            "PASS",
            "CRITICAL",
            f"Declared MRP: {mrp_text or f'₹{mrp_val}'}",
            "Rule 6(1)(e)"
        )
    else:
        add_rule(
            "RULE_6_MRP_VALUE",
            "Maximum Retail Price (MRP) Declaration",
            "FAIL",
            "CRITICAL",
            "Missing Maximum Retail Price (MRP) declaration.",
            "Rule 6(1)(e)"
        )

    # 4. MRP Tax Inclusion Clause ("Inclusive of all taxes")
    # SPECIAL REQUIREMENT: Issue WARNING if text is null (not FAIL), to avoid false negatives in OCR
    tax_text = declarations.get("inclusive_of_taxes_text")
    if tax_text and str(tax_text).strip():
        add_rule(
            "RULE_6_TAX_INCLUSION",
            "MRP Tax Inclusion Statement",
            "PASS",
            "MEDIUM",
            f"Tax clause found: '{tax_text}'",
            "Rule 6(1)(e)"
        )
    elif mrp_val is not None:
        add_rule(
            "RULE_6_TAX_INCLUSION",
            "MRP Tax Inclusion Statement",
            "WARNING",
            "MEDIUM",
            "MRP declared, but explicit 'Inclusive of all taxes' text was not clearly detected.",
            "Rule 6(1)(e)"
        )
    else:
        add_rule(
            "RULE_6_TAX_INCLUSION",
            "MRP Tax Inclusion Statement",
            "FAIL",
            "MEDIUM",
            "No MRP or tax inclusion clause found.",
            "Rule 6(1)(e)"
        )

    # 5. Manufacturer / Packer Details
    mfg_name = declarations.get("manufacturer_name")
    mfg_addr = declarations.get("manufacturer_address")
    if (mfg_name and str(mfg_name).strip()) or (mfg_addr and str(mfg_addr).strip()):
        mfg_str = f"{mfg_name or ''} {mfg_addr or ''}".strip()
        add_rule(
            "RULE_6_MANUFACTURER",
            "Manufacturer / Packer Name & Address",
            "PASS",
            "CRITICAL",
            f"Declared manufacturer/packer details: '{mfg_str}'",
            "Rule 6(1)(d)"
        )
    else:
        add_rule(
            "RULE_6_MANUFACTURER",
            "Manufacturer / Packer Name & Address",
            "FAIL",
            "CRITICAL",
            "Missing manufacturer, packer, or importer name and address.",
            "Rule 6(1)(d)"
        )

    # 6. Month and Year of Manufacture / Packing
    mfd_date = declarations.get("month_year_of_manufacture")
    if mfd_date and str(mfd_date).strip():
        add_rule(
            "RULE_6_MFD_DATE",
            "Month & Year of Manufacture / Packing",
            "PASS",
            "CRITICAL",
            f"Declared mfd/packing date: '{mfd_date}'",
            "Rule 6(1)(c)"
        )
    else:
        add_rule(
            "RULE_6_MFD_DATE",
            "Month & Year of Manufacture / Packing",
            "FAIL",
            "CRITICAL",
            "Date of manufacture not visible (Image may be cropped or bottom coding window cut off).",
            "Rule 6(1)(c)"
        )

    # 7. Consumer Care Details
    care_details = declarations.get("consumer_care_details")
    if care_details and str(care_details).strip():
        add_rule(
            "RULE_6_CONSUMER_CARE",
            "Consumer Care / Helpline Details",
            "PASS",
            "CRITICAL",
            f"Declared consumer care details: '{care_details}'",
            "Rule 6(1)(ac)"
        )
    else:
        add_rule(
            "RULE_6_CONSUMER_CARE",
            "Consumer Care / Helpline Details",
            "FAIL",
            "CRITICAL",
            "Missing consumer care phone number, email, or contact address for grievance redressal.",
            "Rule 6(1)(ac)"
        )

    # 8. Country of Origin
    origin = declarations.get("country_of_origin")
    mfg_addr_upper = str(declarations.get("manufacturer_address") or "").upper()
    raw_upper = str(declarations.get("raw_text") or "").upper()

    if origin and str(origin).strip():
        add_rule(
            "RULE_6_COUNTRY_ORIGIN",
            "Country of Origin",
            "PASS",
            "MEDIUM",
            f"Country of origin declared: '{origin}'",
            "Rule 6(1)(n)"
        )
    elif any(loc in mfg_addr_upper or loc in raw_upper for loc in ["INDIA", "KOLKATA", "BENGALURU", "DELHI", "MUMBAI", "CHENNAI", "FSSAI", "ITC LIMITED"]):
        add_rule(
            "RULE_6_COUNTRY_ORIGIN",
            "Country of Origin",
            "PASS",
            "MEDIUM",
            "Domestic Indian product (Inferred from manufacturer address / FSSAI registration).",
            "Rule 6(1)(n)"
        )
    else:
        add_rule(
            "RULE_6_COUNTRY_ORIGIN",
            "Country of Origin",
            "WARNING",
            "MEDIUM",
            "Country of origin statement not explicitly found (Mandatory for imported goods).",
            "Rule 6(1)(n)"
        )

    # 9. Expiry Date / Best Before
    expiry = declarations.get("best_before_or_expiry")
    if expiry and str(expiry).strip():
        add_rule(
            "RULE_6_EXPIRY_DATE",
            "Best Before / Expiry Date",
            "PASS",
            "MEDIUM",
            f"Best before/expiry declared: '{expiry}'",
            "Rule 6(1)"
        )
    else:
        add_rule(
            "RULE_6_EXPIRY_DATE",
            "Best Before / Expiry Date",
            "WARNING",
            "LOW",
            "Expiry or best before date not visible (Image may be cropped or bottom coding window cut off).",
            "Rule 6(1)"
        )

    # Calculate statistics & overall compliance status
    total_rules = len(rules_results)
    passed_count = sum(1 for r in rules_results if r["status"] == "PASS")
    failed_count = sum(1 for r in rules_results if r["status"] == "FAIL")
    warning_count = sum(1 for r in rules_results if r["status"] == "WARNING")

    compliance_score = round((passed_count / total_rules) * 100, 1) if total_rules > 0 else 0.0

    if failed_count > 0:
        overall_status = "NON_COMPLIANT"
    elif warning_count > 0:
        overall_status = "WARNING"
    else:
        overall_status = "COMPLIANT"

    return {
        "overall_status": overall_status,
        "compliance_score": compliance_score,
        "passed_count": passed_count,
        "failed_count": failed_count,
        "warning_count": warning_count,
        "rules": rules_results
    }
