# ECFA Tariff Optimizer V2 - Schemas
# Pydantic models for V2 API

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# =====================
# BOM Parsing Schemas
# =====================

class ParsedMaterial(BaseModel):
    """解析后的物料项"""
    material_name: str
    ratio: Optional[float] = None
    cost: Optional[float] = None
    origin_country: Optional[str] = None
    hs_code: Optional[str] = None
    supplier_name: Optional[str] = None
    confidence: float = 0.0


class BOMParseResult(BaseModel):
    """BOM 解析结果"""
    success: bool
    items: List[ParsedMaterial] = []
    statistics: Optional[dict] = None
    missing_fields: List[str] = []
    confidence: float = 0.0
    filename: Optional[str] = None
    file_type: Optional[str] = None


# =====================
# Tariff Knowledge Base Schemas
# =====================

class TariffQueryRequest(BaseModel):
    """税则查询请求"""
    hs_code: str = Field(..., description="税则号列 (如 2106.90.99)")
    country: str = Field("CN", description="目的国 (CN/TW/US/EU)")


class TariffQueryResult(BaseModel):
    """税则查询结果"""
    hs_code: str
    country: str
    tariff_rate: Optional[float]
    description: Optional[str] = None
    in_ecfa_list: bool = False
    ecfa_note: Optional[str] = None
    source: str = "database"


class ECFACheckRequest(BaseModel):
    """ECFA 检查请求"""
    product_name: str = Field(..., description="产品名称")
    hs_code: Optional[str] = Field(None, description="税则号列 (可选)")


class ECFACheckResult(BaseModel):
    """ECFA 检查结果"""
    product_name: str
    hs_code: Optional[str] = None
    in_ecfa_list: bool = False
    ecfa_category: Optional[str] = None
    item_number: Optional[str] = None
    origin_criteria: Optional[str] = None
    required_documents: Optional[str] = None
    notes: Optional[str] = None
    confidence: float = 0.0
    legal_notice: Optional[str] = None


# =====================
# Optimization Schemas
# =====================

class V2BomItem(BaseModel):
    """V2 BOM 物料项"""
    material_name: str
    ratio: float = Field(..., ge=0, le=100)
    cost: float = Field(..., ge=0)
    origin_country: str
    adjustable: bool = True
    hs_code: Optional[str] = None
    supplier_name: Optional[str] = None
    manufacturing_process: Optional[str] = None
    notes: Optional[str] = None


class V2Constraints(BaseModel):
    """V2 优化约束条件"""
    max_cost_increase_pct: float = Field(3.0, ge=0, description="最大成本变动百分比")
    max_material_adjustment_count: int = Field(3, ge=1, description="最大物料调整数量")
    target_origin_ratio: Optional[float] = Field(None, ge=0, le=100, description="目标原产地比例")
    locked_materials: List[str] = Field(default_factory=list, description="不可调整的物料")


class V2OptimizeRequest(BaseModel):
    """V2 优化请求"""
    product_name: str
    product_category: Optional[str] = None
    current_hs_code: str
    current_tariff_rate: float = Field(..., ge=0)
    destination_country: str = "CN"
    declared_origin_country: Optional[str] = None
    bom_items: List[V2BomItem]
    constraints: V2Constraints = V2Constraints()


class MaterialChange(BaseModel):
    """物料变更"""
    material: str
    current_ratio: float
    suggested_ratio: float
    change_type: str


class OriginChange(BaseModel):
    """产地变更"""
    material: str
    current_origin: str
    suggested_origin: str
    change_type: str


class OptimizationScenario(BaseModel):
    """优化方案"""
    scenario_name: str
    scenario_score: float
    feasibility_score: float
    material_changes: List[MaterialChange]
    origin_changes: List[OriginChange]
    estimated_tariff_rate: float
    tariff_reduction_pct: float
    cost_change_pct: float
    legal_basis: List[str]
    required_documents: List[str]
    risk_level: str
    warnings: List[str]
    summary: str


class OptimizationSummary(BaseModel):
    """优化摘要"""
    current_taiwan_ratio_pct: float
    target_origin_ratio_pct: float
    origin_ratio_gap_pct: float
    adjustable_material_count: int
    scenario_count: int


class V2OptimizeResponse(BaseModel):
    """V2 优化响应"""
    success: bool
    product_name: str
    current_hs_code: str
    current_tariff_rate: float
    destination_country: str
    summary: OptimizationSummary
    recommended_scenario: Optional[OptimizationScenario] = None
    candidate_scenarios: List[OptimizationScenario] = []
    ai_explanation: str
    warnings: List[str]
    constraints: dict
    solver_used: str


# =====================
# Utility Schemas
# =====================

class HSCodesSearchResult(BaseModel):
    """HS Code 搜索结果"""
    hs_code: str
    description: str
    chapter: str
    tariff_cn: Optional[float] = None
    tariff_tw: Optional[float] = None
    in_ecfa_list: bool = False


class ErrorResponse(BaseModel):
    """错误响应"""
    success: bool = False
    error: str
    details: Optional[dict] = None