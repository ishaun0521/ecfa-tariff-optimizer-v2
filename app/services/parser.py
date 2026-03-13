"""
BOM Parser Module - Parse CSV/Excel files and extract material information
"""
import pandas as pd
import io
from typing import List, Optional
from fastapi import UploadFile, HTTPException
from app.schemas import BomItem, ParseBomResponse


# Common column name mappings for BOM files
COLUMN_MAPPINGS = {
    'material_name': ['material_name', 'material', 'name', '品名', '物料名稱', 'item', 'product', '產品', 'product_name'],
    'origin_country': ['origin_country', 'origin', 'country', '产地', '產地', 'country_of_origin', 'source'],
    'composition': ['composition', '成分', 'material_composition', 'content'],
    'unit_cost': ['unit_cost', 'cost', 'price', '單價', '单价', 'unit_price', 'cost_per_unit'],
    'quantity': ['quantity', 'qty', '数量', '數量', 'amount', 'count'],
    'hs_code': ['hs_code', 'hs', 'hscode', '税则号列', '稅則號列', 'tariff_code'],
}


def _find_column(df_columns: list, possible_names: List[str]) -> Optional[str]:
    """Find matching column from possible names (case-insensitive)"""
    df_lower = {col.lower(): col for col in df_columns}
    for name in possible_names:
        if name.lower() in df_lower:
            return df_lower[name.lower()]
    return None


def _extract_column(df: pd.DataFrame, possible_names: List[str], default=None):
    """Extract column with fallback to default"""
    col = _find_column(df.columns.tolist(), possible_names)
    if col is None:
        return default
    return df[col].tolist()


def parse_bom_file(file: UploadFile) -> ParseBomResponse:
    """
    Parse uploaded BOM file (CSV or Excel) and extract structured data
    """
    try:
        contents = file.file.read()
        
        # Determine file type and parse
        if file.filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(contents), encoding='utf-8-sig')
        elif file.filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(contents))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use CSV or Excel.")
        
        # Extract columns with fuzzy matching
        material_names = _extract_column(df, COLUMN_MAPPINGS['material_name'])
        origin_countries = _extract_column(df, COLUMN_MAPPINGS['origin_country'], ['Unknown'] * len(df))
        compositions = _extract_column(df, COLUMN_MAPPINGS['composition'])
        unit_costs = _extract_column(df, COLUMN_MAPPINGS['unit_cost'], [0.0] * len(df))
        quantities = _extract_column(df, COLUMN_MAPPINGS['quantity'], [1] * len(df))
        hs_codes = _extract_column(df, COLUMN_MAPPINGS['hs_code'])
        
        # Build BOM items
        items = []
        total_cost = 0.0
        
        for i in range(len(df)):
            try:
                material = str(material_names[i]) if i < len(material_names) and pd.notna(material_names[i]) else f"Material_{i+1}"
                origin = str(origin_countries[i]) if i < len(origin_countries) and pd.notna(origin_countries[i]) else "Unknown"
                
                # Get composition if available
                comp = None
                if compositions and i < len(compositions) and pd.notna(compositions[i]):
                    comp = str(compositions[i])
                
                # Get unit cost
                cost = 0.0
                if unit_costs and i < len(unit_costs):
                    try:
                        cost = float(unit_costs[i]) if pd.notna(unit_costs[i]) else 0.0
                    except (ValueError, TypeError):
                        cost = 0.0
                
                # Get quantity
                qty = 1
                if quantities and i < len(quantities):
                    try:
                        qty = int(quantities[i]) if pd.notna(quantities[i]) else 1
                    except (ValueError, TypeError):
                        qty = 1
                
                # Get HS code if available
                hs = None
                if hs_codes and i < len(hs_codes) and pd.notna(hs_codes[i]):
                    hs = str(hs_codes[i])
                
                item = BomItem(
                    row_number=i+1,
                    material_name=material,
                    origin_country=origin,
                    composition=comp,
                    unit_cost=cost,
                    quantity=qty,
                    hs_code=hs
                )
                items.append(item)
                total_cost += cost * qty
                
            except Exception as e:
                # Skip problematic rows but continue
                continue
        
        if not items:
            return ParseBomResponse(
                success=False,
                items=[],
                total_items=0,
                total_cost=0.0,
                message="No valid BOM items found in file. Please check column headers."
            )
        
        return ParseBomResponse(
            success=True,
            items=items,
            total_items=len(items),
            total_cost=total_cost,
            message=f"Successfully parsed {len(items)} items from BOM"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error parsing BOM file: {str(e)}")
