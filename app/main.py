# ECFA Tariff Optimizer V2 - Main API
# FastAPI backend with V2 endpoints

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import json
from datetime import datetime
import os

# Import services
from app.services.database import init_db, get_db, SessionLocal
from app.services.nlp_parser import parse_bom_file, BOMParser
from app.services.tariff_knowledge import query_tariff_rate, check_ecfa_eligibility, search_hs_codes
from app.services.optimizer_v2 import optimize_bom, OptimizationConstraints

# Initialize database on startup
init_db()

app = FastAPI(
    title="ECFA Tariff Optimizer V2",
    description="V2 版本 - 包含 NLP BOM 解析、动态税则知识库、多目标优化引擎",
    version="2.0.0"
)

# Mount frontend
app.mount("/static", StaticFiles(directory="frontend"), name="static")


# =====================
# Pydantic Schemas
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
    max_cost_increase_pct: float = 3.0
    max_material_adjustment_count: int = 3
    target_origin_ratio: Optional[float] = Field(None, ge=0, le=100)
    locked_materials: List[str] = []


class V2OptimizeRequest(BaseModel):
    """V2 优化请求"""
    product_name: str
    product_category: Optional[str] = None
    current_hs_code: str
    current_tariff_rate: float
    destination_country: str = "CN"
    declared_origin_country: Optional[str] = None
    bom_items: List[V2BomItem]
    constraints: V2Constraints = V2Constraints()


class TariffQueryRequest(BaseModel):
    """税则查询请求"""
    hs_code: str
    country: str = "CN"


class ECFACheckRequest(BaseModel):
    """ECFA 检查请求"""
    product_name: str
    hs_code: Optional[str] = None


# =====================
# API Routes
# =====================

@app.get("/")
async def root():
    """Serve frontend"""
    return FileResponse("frontend/index.html")


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "ok",
        "version": "2.0.0",
        "timestamp": datetime.utcnow().isoformat()
    }


# ---------------------
# V2: BOM 解析模块
# ---------------------
@app.post("/api/v2/parse-bom")
async def parse_bom(file: UploadFile = File(...)):
    """
    V2: NLP BOM 解析
    
    支持 PDF/Excel/CSV 上传，自动提取：
    - 物料名称
    - 产地
    - 成分（比例）
    - 成本
    
    Returns:
        解析结果，包含提取的物料列表、质量指标、缺失字段
    """
    # Determine file type
    filename = file.filename.lower()
    if filename.endswith('.pdf'):
        file_type = "pdf"
    elif filename.endswith(('.xlsx', '.xls')):
        file_type = "excel"
    elif filename.endswith('.csv'):
        file_type = "csv"
    else:
        raise HTTPException(status_code=400, detail="不支持的文件格式")
    
    # Read file content
    content = await file.read()
    
    # Parse BOM
    result = parse_bom_file(content, file_type)
    
    # Add metadata
    result["filename"] = file.filename
    result["file_type"] = file_type
    result["timestamp"] = datetime.utcnow().isoformat()
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "解析失败"))
    
    return JSONResponse(content=result)


@app.post("/api/v2/parse-bom/json")
async def parse_bom_json(request: dict):
    """
    V2: JSON 格式 BOM 解析（直接输入）
    
    用于直接提交 BOM 数据（不通过文件上传）
    """
    parser = BOMParser()
    items = request.get("items", [])
    
    if not items:
        raise HTTPException(status_code=400, detail="缺少物料列表")
    
    # Convert to parser format and process
    from app.services.nlp_parser import ParsedMaterial
    
    parsed_items = []
    for item in items:
        parsed_items.append(ParsedMaterial(
            material_name=item.get("material_name", item.get("name", "")),
            ratio=item.get("ratio"),
            cost=item.get("cost"),
            origin_country=item.get("origin_country"),
            hs_code=item.get("hs_code"),
            supplier_name=item.get("supplier_name"),
            notes=item.get("notes"),
            confidence=0.8
        ))
    
    parser.last_parsed_items = parsed_items
    
    result = {
        "success": True,
        "items": [
            {
                "material_name": p.material_name,
                "ratio": p.ratio,
                "cost": p.cost,
                "origin_country": p.origin_country,
                "hs_code": p.hs_code,
                "confidence": p.confidence
            }
            for p in parsed_items
        ],
        "statistics": parser._calculate_statistics(parsed_items),
        "confidence": parser._calculate_confidence(parsed_items)
    }
    
    return JSONResponse(content=result)


# ---------------------
# V2: 动态税则知识库
# ---------------------
@app.post("/api/v2/tariff-query")
async def tariff_query(request: TariffQueryRequest):
    """
    V2: 查询特定 HS Code 的税率
    
    Args:
        hs_code: 税则号列 (如 "2106.90.99")
        country: 目的国 (CN/TW/US/EU)
        
    Returns:
        税率信息，包含各目的国税率、ECFA 状态
    """
    result = query_tariff_rate(request.hs_code, request.country)
    
    return JSONResponse(content={
        "success": True,
        "data": result,
        "timestamp": datetime.utcnow().isoformat()
    })


@app.post("/api/v2/ecfa-check")
async def ecfa_check(request: ECFACheckRequest):
    """
    V2: 检查产品是否在 ECFA 货品清单范围内
    
    Args:
        product_name: 产品名称
        hs_code: 税则号列 (可选)
        
    Returns:
        ECFA 适用性检查结果，包含法律声明
    """
    result = check_ecfa_eligibility(request.product_name, request.hs_code)
    
    return JSONResponse(content={
        "success": True,
        "data": result,
        "timestamp": datetime.utcnow().isoformat()
    })


@app.get("/api/v2/hs-codes/search")
async def hs_codes_search(q: str = "", limit: int = 20):
    """
    V2: 搜索 HS Code
    
    Args:
        q: 搜索关键词
        limit: 返回数量限制
        
    Returns:
        HS Code 列表
    """
    if not q:
        return JSONResponse(content={"success": True, "data": []})
    
    results = search_hs_codes(q, limit)
    
    return JSONResponse(content={
        "success": True,
        "data": results,
        "count": len(results)
    })


@app.get("/api/v2/ecfa-goods-list")
async def ecfa_goods_list(chapter: Optional[str] = None, limit: int = 50):
    """
    V2: 获取 ECFA 货品清单
    
    Args:
        chapter: 章节筛选 (可选)
        limit: 返回数量限制
        
    Returns:
        ECFA 货品列表
    """
    from app.services.tariff_knowledge import TariffKnowledgeBase
    
    with TariffKnowledgeBase() as kb:
        items = kb.get_ecfa_goods_list(chapter, limit)
    
    return JSONResponse(content={
        "success": True,
        "data": items,
        "count": len(items)
    })


# ---------------------
# V2: 多目标优化引擎
# ---------------------
@app.post("/api/v2/optimize")
async def optimize(request: V2OptimizeRequest):
    """
    V2: 多目标规划优化
    
    基于专利摘要要求：
    - 目标函数：最小化税率 + 最小化成本变动
    - 约束条件：成本容忍度、不可调整材料、生产工法
    
    Args:
        request: 优化请求
        
    Returns:
        优化结果，包含推荐方案和候选方案列表
    """
    # Convert to optimizer format
    bom_items = [
        {
            "material_name": item.material_name,
            "ratio": item.ratio,
            "cost": item.cost,
            "origin_country": item.origin_country,
            "adjustable": item.adjustable,
            "hs_code": item.hs_code,
            "manufacturing_process": item.manufacturing_process
        }
        for item in request.bom_items
    ]
    
    constraints = {
        "max_cost_increase_pct": request.constraints.max_cost_increase_pct,
        "max_material_adjustment_count": request.constraints.max_material_adjustment_count,
        "target_origin_ratio": request.constraints.target_origin_ratio,
        "locked_materials": request.constraints.locked_materials
    }
    
    # Run optimization
    result = optimize_bom(
        product_name=request.product_name,
        current_hs_code=request.current_hs_code,
        current_tariff_rate=request.current_tariff_rate,
        bom_items=bom_items,
        constraints=constraints,
        destination_country=request.destination_country
    )
    
    # Add HS Code, CCC Code, and tariff info to result
    if result.get("success"):
        # Query tariff info for original HS Code
        original_tariff = query_tariff_rate(request.current_hs_code, request.destination_country)
        
        # Generate CCC Code (HS Code without dots)
        original_ccc_code = request.current_hs_code.replace(".", "").strip()
        
        # Build original tariff info
        original_tariff_info = {
            "hs_code": request.current_hs_code,
            "taiwan_ccc_code": original_ccc_code,
            "tariff_rate": f"{original_tariff.get('tariff_rate', request.current_tariff_rate)}%",
            "ecfa_eligible": original_tariff.get("in_ecfa_list", False),
            "ecfa_note": original_tariff.get("ecfa_note") or ("在 ECFA 免税清单内" if original_tariff.get("in_ecfa_list") else "不在 ECFA 免税清单内")
        }
        
        # Get optimized HS Code from recommended scenario
        optimized_hs_code = request.current_hs_code  # Default to current
        if result.get("recommended_scenario"):
            # Try to infer optimized HS Code from scenario changes
            # For now, use the current HS code as the optimization is about BOM changes
            # In a real scenario, this could change based on product name declaration
            rec = result["recommended_scenario"]
            
            # If there are material changes that could affect HS Code
            if rec.get("material_changes"):
                # Keep current HS code as base, but note that
                # the optimization is about BOM composition
                optimized_hs_code = request.current_hs_code
        
        # Query optimized tariff info
        optimized_tariff = query_tariff_rate(optimized_hs_code, request.destination_country)
        optimized_ccc_code = optimized_hs_code.replace(".", "").strip()
        
        optimized_tariff_info = {
            "hs_code": optimized_hs_code,
            "taiwan_ccc_code": optimized_ccc_code,
            "tariff_rate": f"{optimized_tariff.get('tariff_rate', rec.get('estimated_tariff_rate', 0))}%",
            "ecfa_eligible": optimized_tariff.get("in_ecfa_list", False),
            "ecfa_note": optimized_tariff.get("ecfa_note") or ("在 ECFA 免税清单内" if optimized_tariff.get("in_ecfa_list") else "不在 ECFA 免税清单内")
        }
        
        # Add to result
        result["tariff_info"] = {
            "original": original_tariff_info,
            "optimized": optimized_tariff_info
        }
    
    # Save to history
    _save_optimization_history(request, result)
    
    return JSONResponse(content={
        "success": result.get("success", False),
        "data": result,
        "timestamp": datetime.utcnow().isoformat()
    })


def _save_optimization_history(request, result):
    """保存优化历史到数据库"""
    try:
        from app.services.database import OptimizationHistory, SessionLocal
        
        db = SessionLocal()
        history = OptimizationHistory(
            product_name=request.product_name,
            current_hs_code=request.current_hs_code,
            destination_country=request.destination_country,
            bom_items=json.dumps([item.model_dump() for item in request.bom_items]),
            constraints=json.dumps(request.constraints.model_dump()),
            recommended_scenario=json.dumps(result.get("recommended_scenario", {})),
            candidate_scenarios=json.dumps(result.get("candidate_scenarios", [])),
            optimization_result=json.dumps(result),
            tariff_reduction=result.get("recommended_scenario", {}).get("tariff_reduction_pct"),
            cost_change=result.get("recommended_scenario", {}).get("cost_change_pct"),
            feasibility_score=result.get("recommended_scenario", {}).get("feasibility_score"),
            status="completed"
        )
        db.add(history)
        db.commit()
        db.close()
    except Exception as e:
        print(f"Failed to save optimization history: {e}")


# =====================
# Legacy Routes (from V1)
# =====================

@app.get("/tariff-guide")
async def tariff_guide():
    return FileResponse("frontend/tariff-guide.html")


@app.get("/legal-sources")
async def legal_sources():
    return FileResponse("frontend/legal-sources.html")


@app.get("/changelog")
async def changelog():
    return FileResponse("frontend/changelog.html")


# =====================
# Run the app
# =====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)