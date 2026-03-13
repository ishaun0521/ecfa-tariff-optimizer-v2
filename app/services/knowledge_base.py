"""
Knowledge Base Module - HS Code database and ECFA product list
"""
import json
import os
from typing import Optional, Dict, List
from app.schemas import TariffInfo, EcfaCheckResponse


# In-memory data (can be loaded from JSON files in production)
HS_CODE_DB = {
    # Chapter 84 - Nuclear reactors, boilers, machinery
    "8471": {
        "description": "Automatic data processing machines",
        "mfn_rate": 0.0,
        "unit": "units",
        "notes": "Free import for Taiwan"
    },
    "8473": {
        "description": "Parts and accessories of computers",
        "mfn_rate": 0.0,
        "unit": "kg",
        "notes": "Free for parts"
    },
    # Chapter 85 - Electrical machinery
    "8501": {
        "description": "Electric motors and generators",
        "mfn_rate": 5.0,
        "unit": "units"
    },
    "8507": {
        "description": "Electric accumulators",
        "mfn_rate": 3.0,
        "unit": "units"
    },
    "8517": {
        "description": "Telephone sets, smartphones",
        "mfn_rate": 0.0,
        "unit": "units",
        "notes": "Free for communication devices"
    },
    "8528": {
        "description": "Television receivers",
        "mfn_rate": 10.0,
        "unit": "units"
    },
    # Chapter 90 - Optical, photographic, medical equipment
    "9001": {
        "description": "Optical fibers and optical fiber bundles",
        "mfn_rate": 5.0,
        "unit": "kg"
    },
    "9018": {
        "description": "Medical instruments",
        "mfn_rate": 5.0,
        "unit": "units"
    },
    # Chapter 39 - Plastics
    "3901": {
        "description": "Polymers of ethylene",
        "mfn_rate": 6.5,
        "unit": "kg"
    },
    "3902": {
        "description": "Polymers of propylene",
        "mfn_rate": 6.5,
        "unit": "kg"
    },
    # Chapter 40 - Rubber
    "4001": {
        "description": "Natural rubber",
        "mfn_rate": 0.0,
        "unit": "kg",
        "notes": "Free for natural rubber"
    },
    # Chapter 48 - Paper
    "4801": {
        "description": "Newsprint",
        "mfn_rate": 0.0,
        "unit": "kg"
    },
    # Chapter 72 - Iron and steel
    "7208": {
        "description": "Flat-rolled iron products",
        "mfn_rate": 5.0,
        "unit": "kg"
    },
    # Default fallback
    "default": {
        "description": "General goods",
        "mfn_rate": 10.0,
        "unit": "units",
        "notes": "Standard MFN rate"
    }
}

# ECFA Early Harvest Product List (simplified sample)
# Full list would contain hundreds of items
ECFA_PRODUCT_LIST = {
    # Chemical products
    "2805": {"name": "Rare earths", "category": "Chemicals", "preferential_tariff": 0.0},
    "2806": {"name": "Hydrogen chloride", "category": "Chemicals", "preferential_tariff": 0.0},
    
    # Plastics and rubber
    "3901": {"name": "Polyethylene", "category": "Plastics", "preferential_tariff": 0.0},
    "3902": {"name": "Polypropylene", "category": "Plastics", "preferential_tariff": 0.0},
    "3903": {"name": "Polystyrene", "category": "Plastics", "preferential_tariff": 0.0},
    
    # Textiles
    "5208": {"name": "Cotton fabrics", "category": "Textiles", "preferential_tariff": 5.0},
    "5209": {"name": "Cotton woven fabrics", "category": "Textiles", "preferential_tariff": 5.0},
    
    # Machinery
    "8401": {"name": "Nuclear reactors", "category": "Machinery", "preferential_tariff": 0.0},
    "8408": {"name": "Compression-ignition engines", "category": "Machinery", "preferential_tariff": 0.0},
    "8415": {"name": "Air conditioning machines", "category": "Machinery", "preferential_tariff": 5.0},
    "8418": {"name": "Refrigerators", "category": "Machinery", "preferential_tariff": 5.0},
    
    # Electrical machinery
    "8501": {"name": "Electric motors", "category": "Electrical", "preferential_tariff": 0.0},
    "8502": {"name": "Electric generators", "category": "Electrical", "preferential_tariff": 0.0},
    "8507": {"name": "Electric accumulators", "category": "Electrical", "preferential_tariff": 0.0},
    "8517": {"name": "Telephone sets", "category": "Electrical", "preferential_tariff": 0.0},
    "8525": {"name": "Television cameras", "category": "Electrical", "preferential_tariff": 0.0},
    "8528": {"name": "Television receivers", "category": "Electrical", "preferential_tariff": 5.0},
    
    # Vehicles
    "8703": {"name": "Motor vehicles", "category": "Vehicles", "preferential_tariff": 10.0},
    
    # Optical/Medical
    "9001": {"name": "Optical fibers", "category": "Optical", "preferential_tariff": 0.0},
    "9018": {"name": "Medical instruments", "category": "Medical", "preferential_tariff": 0.0},
    
    # Default for ECFA products not in list (generally 5%)
    "_default": {"name": "Other ECFA products", "category": "General", "preferential_tariff": 5.0}
}


def _normalize_hs_code(hs_code: str) -> str:
    """Normalize HS code (remove dots, whitespace)"""
    return hs_code.replace(".", "").strip().upper()


def query_tariff(hs_code: str, destination: str = "TW") -> TariffInfo:
    """
    Query tariff rate for a given HS code
    
    Args:
        hs_code: Harmonized System code (4-6 digits)
        destination: Destination country code (default: TW)
    
    Returns:
        TariffInfo with rate details
    """
    normalized = _normalize_hs_code(hs_code)
    
    # Try exact match first
    if normalized in HS_CODE_DB:
        data = HS_CODE_DB[normalized]
        return TariffInfo(
            hs_code=normalized,
            description=data["description"],
            mfn_rate=data["mfn_rate"],
            preferential_rate=None,  # Would need separate ECFA lookup
            unit=data["unit"],
            notes=data.get("notes")
        )
    
    # Try prefix match (first 4 digits)
    prefix = normalized[:4] if len(normalized) >= 4 else normalized
    if prefix in HS_CODE_DB:
        data = HS_CODE_DB[prefix]
        return TariffInfo(
            hs_code=normalized,
            description=data["description"],
            mfn_rate=data["mfn_rate"],
            preferential_rate=None,
            unit=data["unit"],
            notes=f"Matched prefix {prefix}"
        )
    
    # Return default
    data = HS_CODE_DB["default"]
    return TariffInfo(
        hs_code=normalized,
        description=data["description"],
        mfn_rate=data["mfn_rate"],
        preferential_rate=None,
        unit=data["unit"],
        notes="Default rate - HS code not found in database"
    )


def check_ecfa_eligibility(hs_code: str) -> EcfaCheckResponse:
    """
    Check if a product is in the ECFA Early Harvest list
    
    Args:
        hs_code: Harmonized System code
    
    Returns:
        EcfaCheckResponse with eligibility details
    """
    normalized = _normalize_hs_code(hs_code)
    
    # Try exact match first
    if normalized in ECFA_PRODUCT_LIST:
        data = ECFA_PRODUCT_LIST[normalized]
        return EcfaCheckResponse(
            hs_code=normalized,
            in_ecfa_list=True,
            product_name=data["name"],
            ecfa_category=data["category"],
            preferential_tariff=data["preferential_tariff"],
            notes=f"Eligible for ECFA preferential tariff"
        )
    
    # Try prefix match
    prefix = normalized[:4] if len(normalized) >= 4 else normalized
    if prefix in ECFA_PRODUCT_LIST:
        data = ECFA_PRODUCT_LIST[prefix]
        return EcfaCheckResponse(
            hs_code=normalized,
            in_ecfa_list=True,
            product_name=data["name"],
            ecfa_category=data["category"],
            preferential_tariff=data["preferential_tariff"],
            notes=f"Matched ECFA category: {data['category']}"
        )
    
    # Not in ECFA list
    return EcfaCheckResponse(
        hs_code=normalized,
        in_ecfa_list=False,
        product_name=None,
        ecfa_category=None,
        preferential_tariff=None,
        notes="Not in ECFA Early Harvest product list"
    )


def get_effective_rate(hs_code: str, destination: str = "TW") -> float:
    """
    Get the effective tariff rate (MFN or ECFA preferential)
    """
    # Check ECFA eligibility first
    ecfa = check_ecfa_eligibility(hs_code)
    if ecfa.in_ecfa_list and ecfa.preferential_tariff is not None:
        return ecfa.preferential_tariff
    
    # Fall back to MFN rate
    tariff = query_tariff(hs_code, destination)
    return tariff.mfn_rate
