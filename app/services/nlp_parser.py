# NLP BOM Parser Service
# Parses BOM (Bill of Materials) from PDF/Excel/CSV files

import json
import re
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import pandas as pd
import io

# For PDF/Excel parsing (optional dependencies)
try:
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import openpyxl
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False


@dataclass
class ParsedMaterial:
    """Extracted material from BOM"""
    material_name: str
    ratio: Optional[float] = None
    cost: Optional[float] = None
    origin_country: Optional[str] = None
    hs_code: Optional[str] = None
    supplier_name: Optional[str] = None
    notes: Optional[str] = None
    confidence: float = 0.0


class BOMParser:
    """NLP-based BOM parser with field mapping engine"""
    
    # Common field name mappings for different file formats
    FIELD_MAPPINGS = {
        "material_name": [
            "物料名称", "材料名称", "品名", "物料", "材料", "item", "material", 
            "component", "part_name", "product", "name", "名称"
        ],
        "ratio": [
            "比例", "占比", "比率", "百分比", "ratio", "percentage", "content",
            "%", "weight", "quantity"
        ],
        "cost": [
            "成本", "单价", "价格", "price", "cost", "unit_price", "amount",
            "金额", "單價"
        ],
        "origin_country": [
            "产地", "原产地", "来源地", "origin", "country", "来源",
            "原產地", "供應國"
        ],
        "hs_code": [
            "税则号列", "HS编码", "HS Code", "税号", "tariff", "hs_code",
            "海關編號", "稅則號別"
        ],
        "supplier_name": [
            "供应商", "供应商名称", "供货商", "supplier", "vendor", "廠商"
        ]
    }
    
    # Country code mappings
    COUNTRY_MAPPINGS = {
        "台灣": "TW", "台湾": "TW", "台": "TW", "Taiwan": "TW", "ROC": "TW",
        "中国大陆": "CN", "中国": "CN", "大陸": "CN", "China": "CN", "CN": "CN",
        "美国": "US", "美国": "US", "USA": "US", "US": "US",
        "日本": "JP", "日本": "JP", "Japan": "JP", "JP": "JP",
        "韩国": "KR", "韩国": "KR", "Korea": "KR", "KR": "KR",
        "越南": "VN", "越南": "VN", "Vietnam": "VN", "VN": "VN",
        "泰国": "TH", "泰国": "TH", "Thailand": "TH", "TH": "TH",
    }
    
    def __init__(self):
        self.last_parsed_items: List[ParsedMaterial] = []
    
    def parse_file(self, file_content: bytes, file_type: str) -> Dict[str, Any]:
        """
        Parse BOM from file (PDF/Excel/CSV)
        
        Args:
            file_content: Raw file bytes
            file_type: 'pdf', 'excel', 'csv'
            
        Returns:
            Dictionary with parsed results
        """
        try:
            if file_type == "pdf":
                return self._parse_pdf(file_content)
            elif file_type in ["excel", "xlsx"]:
                return self._parse_excel(file_content)
            elif file_type == "csv":
                return self._parse_csv(file_content)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported file type: {file_type}",
                    "items": []
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "items": []
            }
    
    def _parse_pdf(self, file_content: bytes) -> Dict[str, Any]:
        """Parse PDF BOM file"""
        if not PDF_AVAILABLE:
            # Fallback: treat as text extraction simulation
            return self._parse_text_fallback(file_content.decode("utf-8", errors="ignore"))
        
        with pdfplumber.open(io.BytesIO(file_content)) as pdf:
            text = ""
            for page in pdf.pages:
                text += page.extract_text() or ""
        
        return self._parse_text_fallback(text)
    
    def _parse_excel(self, file_content: bytes) -> Dict[str, Any]:
        """Parse Excel BOM file"""
        if not EXCEL_AVAILABLE:
            return {"success": False, "error": "openpyxl not installed", "items": []}
        
        df = pd.read_excel(io.BytesIO(file_content))
        return self._parse_dataframe(df)
    
    def _parse_csv(self, file_content: bytes) -> Dict[str, Any]:
        """Parse CSV BOM file"""
        # Try different encodings
        for encoding in ["utf-8", "big5", "gb2312", "gbk"]:
            try:
                text = file_content.decode(encoding)
                break
            except:
                continue
        else:
            text = file_content.decode("utf-8", errors="ignore")
        
        import csv
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        df = pd.DataFrame(rows)
        return self._parse_dataframe(df)
    
    def _parse_dataframe(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Parse pandas DataFrame"""
        # Normalize column names
        df.columns = [self._normalize_column_name(col) for col in df.columns]
        
        # Find column mappings
        column_mapping = self._find_column_mapping(df.columns)
        
        items = []
        for idx, row in df.iterrows():
            item = self._extract_item_from_row(row, column_mapping)
            if item.material_name:  # Only add if material name exists
                items.append(item)
        
        self.last_parsed_items = items
        
        return {
            "success": True,
            "items": [self._material_to_dict(item) for item in items],
            "statistics": self._calculate_statistics(items),
            "missing_fields": self._identify_missing_fields(items),
            "confidence": self._calculate_confidence(items)
        }
    
    def _parse_text_fallback(self, text: str) -> Dict[str, Any]:
        """Fallback text parsing using regex patterns"""
        items = []
        
        # Common BOM patterns
        # Pattern 1: Material, Ratio, Cost, Origin
        pattern1 = re.compile(
            r"([^,\n]+)[,\t\s]+(\d+(?:\.\d+)?%?)[\s,]*(\d+(?:\.\d+)?)?[\s,]*([^\n,]+)?",
            re.MULTILINE
        )
        
        # Pattern 2: Material | Ratio | Cost | Origin (table-like)
        pattern2 = re.compile(
            r"([^|\n]+)\|([^|\n]+)\|([^|\n]+)\|?([^\n]*)?",
            re.MULTILINE
        )
        
        # Try pattern 1
        matches = pattern1.findall(text)
        for match in matches:
            material = match[0].strip()
            if material and len(material) > 1:
                ratio = self._extract_number(match[1])
                cost = self._extract_number(match[2]) if len(match) > 2 else None
                origin = match[3].strip() if len(match) > 3 else None
                
                item = ParsedMaterial(
                    material_name=material,
                    ratio=ratio,
                    cost=cost,
                    origin_country=self._map_country(origin) if origin else None,
                    confidence=0.6
                )
                items.append(item)
        
        if not items:
            # Try to extract line by line
            lines = text.split("\n")
            for line in lines:
                if len(line.strip()) > 3:
                    parts = re.split(r"[\t,]+", line.strip())
                    if len(parts) >= 1:
                        item = ParsedMaterial(
                            material_name=parts[0].strip(),
                            ratio=self._extract_number(parts[1]) if len(parts) > 1 else None,
                            cost=self._extract_number(parts[2]) if len(parts) > 2 else None,
                            confidence=0.4
                        )
                        items.append(item)
        
        self.last_parsed_items = items
        
        return {
            "success": True,
            "items": [self._material_to_dict(item) for item in items],
            "statistics": self._calculate_statistics(items),
            "missing_fields": self._identify_missing_fields(items),
            "confidence": self._calculate_confidence(items),
            "note": "Text fallback parsing - results may be incomplete"
        }
    
    def _normalize_column_name(self, col_name: str) -> str:
        """Normalize column name to standard field"""
        col_lower = col_name.lower().strip()
        
        for field, aliases in self.FIELD_MAPPINGS.items():
            for alias in aliases:
                if alias.lower() in col_lower:
                    return field
        
        return col_name
    
    def _find_column_mapping(self, columns) -> Dict[str, str]:
        """Find mapping from DataFrame columns to standard fields"""
        mapping = {}
        
        for col in columns:
            normalized = self._normalize_column_name(col)
            if normalized in self.FIELD_MAPPINGS:
                mapping[normalized] = col
        
        return mapping
    
    def _extract_item_from_row(self, row, mapping: Dict[str, str]) -> ParsedMaterial:
        """Extract material item from DataFrame row"""
        material_name = ""
        ratio = None
        cost = None
        origin = None
        hs_code = None
        supplier = None
        
        # Material name (most important)
        for field in ["material_name", "name"]:
            if field in mapping:
                val = str(row.get(mapping[field], "")).strip()
                if val and val != "nan":
                    material_name = val
                    break
        
        # Ratio
        for field in ["ratio", "percentage"]:
            if field in mapping:
                val = row.get(mapping[field])
                if pd.notna(val):
                    ratio = self._extract_number(str(val))
                    break
        
        # Cost
        for field in ["cost", "price"]:
            if field in mapping:
                val = row.get(mapping[field])
                if pd.notna(val):
                    cost = self._extract_number(str(val))
                    break
        
        # Origin country
        for field in ["origin_country", "origin"]:
            if field in mapping:
                val = row.get(mapping[field])
                if pd.notna(val):
                    origin = self._map_country(str(val))
                    break
        
        # HS Code
        if "hs_code" in mapping:
            val = row.get(mapping["hs_code"])
            if pd.notna(val):
                hs_code = str(val).strip()
        
        # Supplier
        if "supplier_name" in mapping:
            val = row.get(mapping["supplier_name"])
            if pd.notna(val):
                supplier = str(val).strip()
        
        confidence = self._calculate_item_confidence(
            material_name, ratio, cost, origin, hs_code
        )
        
        return ParsedMaterial(
            material_name=material_name,
            ratio=ratio,
            cost=cost,
            origin_country=origin,
            hs_code=hs_code,
            supplier_name=supplier,
            confidence=confidence
        )
    
    def _map_country(self, text: str) -> Optional[str]:
        """Map country text to country code"""
        if not text:
            return None
        
        text = text.strip()
        
        # Direct mapping
        if text.upper() in self.COUNTRY_MAPPINGS.values():
            return text.upper()
        
        # Text mapping
        for name, code in self.COUNTRY_MAPPINGS.items():
            if name in text:
                return code
        
        return None
    
    def _extract_number(self, text: str) -> Optional[float]:
        """Extract number from text"""
        if not text:
            return None
        
        # Remove percentage
        text = text.replace("%", "").strip()
        
        try:
            return float(text)
        except:
            # Try to find number in text
            match = re.search(r"[\d.]+", text)
            if match:
                try:
                    return float(match.group())
                except:
                    pass
        
        return None
    
    def _calculate_item_confidence(self, material: str, ratio: Optional[float], 
                                   cost: Optional[float], origin: Optional[str],
                                   hs_code: Optional[str]) -> float:
        """Calculate confidence score for an item"""
        score = 0.0
        
        if material and len(material) > 1:
            score += 0.3
        
        if ratio is not None:
            score += 0.25
        
        if cost is not None:
            score += 0.2
        
        if origin:
            score += 0.15
        
        if hs_code:
            score += 0.1
        
        return min(score, 1.0)
    
    def _calculate_confidence(self, items: List[ParsedMaterial]) -> float:
        """Calculate overall confidence score"""
        if not items:
            return 0.0
        
        return sum(item.confidence for item in items) / len(items)
    
    def _calculate_statistics(self, items: List[ParsedMaterial]) -> Dict[str, Any]:
        """Calculate statistics from parsed items"""
        total_ratio = sum(item.ratio for item in items if item.ratio)
        total_cost = sum(item.cost for item in items if item.cost)
        
        origins = {}
        for item in items:
            if item.origin_country:
                origins[item.origin_country] = origins.get(item.origin_country, 0) + 1
        
        return {
            "total_items": len(items),
            "total_ratio": round(total_ratio, 2),
            "total_cost": round(total_cost, 2),
            "ratio_complete": total_ratio > 0,
            "origin_distribution": origins
        }
    
    def _identify_missing_fields(self, items: List[ParsedMaterial]) -> List[str]:
        """Identify missing fields across all items"""
        missing = []
        
        has_ratio = any(item.ratio is not None for item in items)
        has_cost = any(item.cost is not None for item in items)
        has_origin = any(item.origin_country is not None for item in items)
        
        if not has_ratio:
            missing.append("ratio (比例)")
        if not has_cost:
            missing.append("cost (成本)")
        if not has_origin:
            missing.append("origin_country (产地)")
        
        return missing


# Utility function for API
def parse_bom_file(file_content: bytes, file_type: str) -> Dict[str, Any]:
    """Main entry point for BOM parsing"""
    parser = BOMParser()
    return parser.parse_file(file_content, file_type)


# Test function
def test_parser():
    """Test the parser with sample data"""
    parser = BOMParser()
    
    # Test CSV
    csv_content = b"""物料名称,比例,成本,产地
茶叶,30,50,台湾
奶精,25,30,中国大陆
糖,20,15,台湾
粉圆,15,25,台湾
香料,10,20,中国大陆
"""
    
    result = parser.parse_file(csv_content, "csv")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    return result


if __name__ == "__main__":
    test_parser()