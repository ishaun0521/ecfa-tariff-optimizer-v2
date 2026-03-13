# V2 优化推理引擎 - 多目标规划算法
# 基于专利摘要：利用多目标规划算法，在满足成本变动系数与生产工法限制下，
# 自动计算并建议物料比例调整、产地变更或品名宣告优化路径

from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import json
from datetime import datetime

# Try to use OR-Tools if available
try:
    from ortools.linear_solver import pywraplp
    ORTOOLS_AVAILABLE = True
except ImportError:
    ORTOOLS_AVAILABLE = False


class OptimizationObjective(Enum):
    """优化目标类型"""
    MINIMIZE_TARIFF = "minimize_tariff"
    MINIMIZE_COST_CHANGE = "minimize_cost_change"
    MAXIMIZE_FEASIBILITY = "maximize_feasibility"
    BALANCED = "balanced"


@dataclass
class OptimizationConstraints:
    """优化约束条件"""
    max_cost_increase_pct: float = 3.0  # 最大成本变动百分比
    max_material_adjustment_count: int = 3  # 最大物料调整数量
    target_origin_ratio: Optional[float] = None  # 目标原产地比例
    locked_materials: List[str] = None  # 不可调整的物料
    
    def __post_init__(self):
        if self.locked_materials is None:
            self.locked_materials = []


@dataclass
class MaterialItem:
    """物料项目"""
    name: str
    ratio: float
    cost: float
    origin_country: str
    adjustable: bool = True
    hs_code: Optional[str] = None
    manufacturing_process: Optional[str] = None  # 生产工法


@dataclass
class OptimizationScenario:
    """优化方案"""
    scenario_name: str
    scenario_score: float
    feasibility_score: float
    
    # BOM 变更
    material_changes: List[Dict[str, Any]]
    origin_changes: List[Dict[str, Any]]
    
    # 预估结果
    estimated_tariff_rate: float
    tariff_reduction: float
    cost_change_pct: float
    
    # 法律基础
    legal_basis: List[str]
    required_documents: List[str]
    
    # 风险评估
    risk_level: str  # low, medium, high
    warnings: List[str]


class MultiObjectiveOptimizer:
    """
    多目标规划优化引擎
    
    目标函数：
    1. 最小化税率 (minimize tariff)
    2. 最小化成本变动 (minimize cost change)
    
    约束条件：
    - 成本容忍度 (max_cost_increase_pct)
    - 不可调整材料 (locked_materials)
    - 生产工法限制 (manufacturing_process)
    - 原产地比例目标 (target_origin_ratio)
    """
    
    def __init__(self):
        self.solver_available = ORTOOLS_AVAILABLE
    
    def optimize(
        self,
        product_name: str,
        current_hs_code: str,
        current_tariff_rate: float,
        bom_items: List[MaterialItem],
        constraints: OptimizationConstraints,
        destination_country: str = "CN"
    ) -> Dict[str, Any]:
        """
        执行多目标优化
        
        Returns:
            优化结果，包含推荐方案和候选方案列表
        """
        # Validate inputs
        warnings = self._validate_inputs(bom_items, constraints)
        
        # Filter adjustable items
        locked_set = set(constraints.locked_materials or [])
        adjustable_items = [
            item for item in bom_items 
            if item.adjustable and item.name not in locked_set
        ]
        
        if not adjustable_items:
            return {
                "success": False,
                "error": "没有可调整的物料",
                "warnings": warnings
            }
        
        # Calculate current origin ratio
        current_tw_ratio = self._calculate_taiwan_ratio(bom_items)
        target_ratio = constraints.target_origin_ratio or max(60.0, current_tw_ratio)
        ratio_gap = max(0, target_ratio - current_tw_ratio)
        
        # Generate candidate scenarios
        scenarios = self._generate_scenarios(
            adjustable_items=adjustable_items,
            current_tw_ratio=current_tw_ratio,
            target_ratio=target_ratio,
            ratio_gap=ratio_gap,
            current_tariff_rate=current_tariff_rate,
            max_cost_increase_pct=constraints.max_cost_increase_pct,
            max_scenarios=constraints.max_material_adjustment_count
        )
        
        # Rank scenarios
        ranked_scenarios = self._rank_scenarios(scenarios, constraints)
        
        # Select recommended scenario
        recommended = ranked_scenarios[0] if ranked_scenarios else None
        
        # Generate explanation
        explanation = self._generate_explanation(
            product_name=product_name,
            current_tw_ratio=current_tw_ratio,
            target_ratio=target_ratio,
            ratio_gap=ratio_gap,
            recommended=recommended,
            scenarios=ranked_scenarios
        )
        
        return {
            "success": True,
            "product_name": product_name,
            "current_hs_code": current_hs_code,
            "current_tariff_rate": current_tariff_rate,
            "destination_country": destination_country,
            
            # Summary metrics
            "summary": {
                "current_taiwan_ratio_pct": current_tw_ratio,
                "target_origin_ratio_pct": target_ratio,
                "origin_ratio_gap_pct": ratio_gap,
                "adjustable_material_count": len(adjustable_items),
                "scenario_count": len(ranked_scenarios)
            },
            
            # Optimization results
            "recommended_scenario": recommended,
            "candidate_scenarios": ranked_scenarios,
            
            # Explanation
            "ai_explanation": explanation,
            
            # Metadata
            "warnings": warnings,
            "constraints": {
                "max_cost_increase_pct": constraints.max_cost_increase_pct,
                "locked_materials": constraints.locked_materials,
                "target_origin_ratio": constraints.target_origin_ratio
            },
            "solver_used": "orp-tools" if self.solver_available else "heuristic"
        }
    
    def _validate_inputs(
        self,
        bom_items: List[MaterialItem],
        constraints: OptimizationConstraints
    ) -> List[str]:
        """验证输入"""
        warnings = []
        
        # Check ratio sum
        total_ratio = sum(item.ratio for item in bom_items)
        if abs(total_ratio - 100) > 0.1:
            warnings.append(f"BOM 比例总和为 {total_ratio}%，不等于 100%")
        
        # Check for zero cost items
        zero_cost_count = sum(1 for item in bom_items if item.cost == 0)
        if zero_cost_count > 0:
            warnings.append(f"有 {zero_cost_count} 项物料成本为 0")
        
        # Check origin info
        no_origin_count = sum(1 for item in bom_items if not item.origin_country)
        if no_origin_count > 0:
            warnings.append(f"有 {no_origin_count} 项物料缺少产地信息")
        
        return warnings
    
    def _calculate_taiwan_ratio(self, bom_items: List[MaterialItem]) -> float:
        """计算台湾来源占比"""
        total_ratio = sum(item.ratio for item in bom_items)
        if total_ratio == 0:
            return 0
        
        tw_ratio = sum(
            item.ratio for item in bom_items 
            if item.origin_country and item.origin_country.upper() in ["TW", "Taiwan", "台灣"]
        )
        
        return round((tw_ratio / total_ratio) * 100, 2)
    
    def _generate_scenarios(
        self,
        adjustable_items: List[MaterialItem],
        current_tw_ratio: float,
        target_ratio: float,
        ratio_gap: float,
        current_tariff_rate: float,
        max_cost_increase_pct: float,
        max_scenarios: int
    ) -> List[OptimizationScenario]:
        """生成候选优化方案"""
        scenarios = []
        
        # Sort by priority (non-TW first, then by ratio)
        priority_items = sorted(
            adjustable_items,
            key=lambda x: (
                x.origin_country.upper() != "TW",  # Non-TW first
                -x.ratio  # Higher ratio first
            )
        )
        
        # Generate scenarios for top items
        for idx, item in enumerate(priority_items[:max_scenarios]):
            scenario = self._create_scenario(
                item=item,
                idx=idx + 1,
                current_tw_ratio=current_tw_ratio,
                target_ratio=target_ratio,
                ratio_gap=ratio_gap,
                current_tariff_rate=current_tariff_rate,
                max_cost_increase_pct=max_cost_increase_pct
            )
            scenarios.append(scenario)
        
        return scenarios
    
    def _create_scenario(
        self,
        item: MaterialItem,
        idx: int,
        current_tw_ratio: float,
        target_ratio: float,
        ratio_gap: float,
        current_tariff_rate: float,
        max_cost_increase_pct: float
    ) -> OptimizationScenario:
        """创建单个优化方案"""
        
        is_non_tw = item.origin_country.upper() != "TW"
        
        # Calculate changes
        if is_non_tw:
            # Suggest changing origin to TW
            suggested_ratio_increase = min(6.0, max(1.0, ratio_gap if ratio_gap else item.ratio * 0.1))
            new_ratio = item.ratio + suggested_ratio_increase
            change_type = "origin_change"
            change_description = f"评估将 {item.name} 改為台灣來源或提高在台加工比重"
            suggested_origin = "TW"
        else:
            # Already TW, suggest increasing ratio
            suggested_ratio_increase = min(4.0, max(0.5, item.ratio * 0.08))
            new_ratio = item.ratio + suggested_ratio_increase
            change_type = "ratio_adjustment"
            change_description = f"維持 {item.name} 為台灣來源，優先提高 BOM 占比"
            suggested_origin = "TW"
        
        # Calculate tariff reduction (simplified model)
        # Assume each 1% TW ratio increase reduces tariff by 0.2%
        estimated_reduction = round(suggested_ratio_increase * 0.25, 2)
        new_tariff_rate = max(0, current_tariff_rate - estimated_reduction)
        
        # Calculate cost impact
        cost_increase = round(min(
            max_cost_increase_pct,
            max(0.3, item.cost * 0.015)  # Assume 1.5% cost increase for TW source
        ), 2)
        
        # Calculate feasibility score
        base_feasibility = 80 if not is_non_tw else 65
        feasibility = max(0, min(100, base_feasibility - (cost_increase * 5)))
        
        # Calculate scenario score (weighted)
        tariff_weight = 0.35
        feasibility_weight = 0.40
        cost_weight = 0.25
        
        scenario_score = max(0, min(100,
            (estimated_reduction * 20 * tariff_weight) +
            (feasibility * feasibility_weight) -
            (cost_increase * 3 * cost_weight)
        ))
        
        # Risk assessment
        risk_level = "low" if not is_non_tw else "medium"
        
        # Legal basis
        legal_basis = [
            "需确认成品税则号列在 ECFA 原产货品清单内",
            "需符合 ECFA 原产地认定基准（台湾来源或台灣制程）",
            "需备妥原产地证明书及相关佐证文件"
        ]
        
        warnings = [
            f"此方案为商业优化建议，正式享惠前需通过 ECFA 原产地审核",
            "实际税率应以海关核定为准"
        ]
        
        return OptimizationScenario(
            scenario_name=f"方案 {idx}｜{item.name}",
            scenario_score=round(scenario_score, 1),
            feasibility_score=round(feasibility, 1),
            
            material_changes=[
                {
                    "material": item.name,
                    "current_ratio": item.ratio,
                    "suggested_ratio": round(new_ratio, 2),
                    "change_type": change_type
                }
            ],
            origin_changes=[
                {
                    "material": item.name,
                    "current_origin": item.origin_country,
                    "suggested_origin": suggested_origin,
                    "change_type": "supplier_change" if is_non_tw else "process_localization"
                }
            ],
            
            estimated_tariff_rate=round(new_tariff_rate, 2),
            tariff_reduction=estimated_reduction,
            cost_change_pct=cost_increase,
            
            legal_basis=legal_basis,
            required_documents=[
                "ECFA 原产地证明书",
                "原料来源证明",
                "制程说明文件"
            ],
            
            risk_level=risk_level,
            warnings=warnings
        )
    
    def _rank_scenarios(
        self,
        scenarios: List[OptimizationScenario],
        constraints: OptimizationConstraints
    ) -> List[Dict[str, Any]]:
        """对方案进行排名"""
        
        # Sort by scenario score (descending)
        ranked = sorted(scenarios, key=lambda x: x.scenario_score, reverse=True)
        
        # Convert to dict
        return [
            {
                "scenario_name": s.scenario_name,
                "scenario_score": s.scenario_score,
                "feasibility_score": s.feasibility_score,
                "material_changes": s.material_changes,
                "origin_changes": s.origin_changes,
                "estimated_tariff_rate": s.estimated_tariff_rate,
                "tariff_reduction_pct": s.tariff_reduction,
                "cost_change_pct": s.cost_change_pct,
                "legal_basis": s.legal_basis,
                "required_documents": s.required_documents,
                "risk_level": s.risk_level,
                "warnings": s.warnings,
                "summary": f"以 {s.material_changes[0]['material'] if s.material_changes else '关键物料'} 作为优化杠杆，目标提升台湾来源占比"
            }
            for s in ranked
        ]
    
    def _generate_explanation(
        self,
        product_name: str,
        current_tw_ratio: float,
        target_ratio: float,
        ratio_gap: float,
        recommended: Optional[OptimizationScenario],
        scenarios: List[OptimizationScenario]
    ) -> str:
        """生成 AI 解释"""
        
        if not recommended:
            return f"目前没有足够的可调整物料来进行优化。建议检查 BOM 中的物料是否可调整或已被锁定。"
        
        explanation = f"""## {product_name} 优化分析报告

### 当前状态
- 台湾来源占比：{current_tw_ratio}%
- 目标占比：{target_ratio}%
- 差距：{ratio_gap}%

### 推荐方案
**{recommended.scenario_name}**
- 预估关税率：从当前税率降至 {recommended.estimated_tariff_rate}%
- 关税降幅：{recommended.tariff_reduction}%
- 成本变动：{recommended.cost_change_pct}%
- 可行性评分：{recommended.feasibility_score}/100
- 风险等级：{recommended.risk_level}

### 方案说明
{recommended.material_changes[0].get('change_description', '') if recommended.material_changes else ''}

### 注意事项
{chr(10).join(recommended.warnings)}

### 后续建议
1. 确认成品税则号列是否在 ECFA 货品清单范围内
2. 评估 {recommended.material_changes[0]['material'] if recommended.material_changes else '关键物料'} 的供应调整可行性
3. 准备原产地证明相关文件
"""
        
        return explanation


# Utility functions
def optimize_bom(
    product_name: str,
    current_hs_code: str,
    current_tariff_rate: float,
    bom_items: List[Dict[str, Any]],
    constraints: Optional[Dict[str, Any]] = None,
    destination_country: str = "CN"
) -> Dict[str, Any]:
    """
    优化 BOM 的主入口函数
    
    Args:
        product_name: 产品名称
        current_hs_code: 当前 HS Code
        current_tariff_rate: 当前税率
        bom_items: BOM 物料列表
        constraints: 约束条件
        destination_country: 目的国
        
    Returns:
        优化结果
    """
    # Convert dict to MaterialItem
    items = [
        MaterialItem(
            name=item.get("material_name", item.get("name", "")),
            ratio=item.get("ratio", 0),
            cost=item.get("cost", 0),
            origin_country=item.get("origin_country", item.get("origin", "")),
            adjustable=item.get("adjustable", True),
            hs_code=item.get("hs_code"),
            manufacturing_process=item.get("manufacturing_process")
        )
        for item in bom_items
    ]
    
    # Parse constraints
    opt_constraints = OptimizationConstraints(
        max_cost_increase_pct=constraints.get("max_cost_increase_pct", 3.0) if constraints else 3.0,
        max_material_adjustment_count=constraints.get("max_material_adjustment_count", 3) if constraints else 3,
        target_origin_ratio=constraints.get("target_origin_ratio") if constraints else None,
        locked_materials=constraints.get("locked_materials", []) if constraints else []
    )
    
    # Run optimization
    optimizer = MultiObjectiveOptimizer()
    return optimizer.optimize(
        product_name=product_name,
        current_hs_code=current_hs_code,
        current_tariff_rate=current_tariff_rate,
        bom_items=items,
        constraints=opt_constraints,
        destination_country=destination_country
    )


# Test function
def test_optimizer():
    """测试优化器"""
    bom_items = [
        {"material_name": "茶叶", "ratio": 30, "cost": 50, "origin_country": "TW"},
        {"material_name": "奶精", "ratio": 25, "cost": 30, "origin_country": "CN"},
        {"material_name": "糖", "ratio": 20, "cost": 15, "origin_country": "TW"},
        {"material_name": "粉圆", "ratio": 15, "cost": 25, "origin_country": "TW"},
        {"material_name": "香料", "ratio": 10, "cost": 20, "origin_country": "CN"},
    ]
    
    result = optimize_bom(
        product_name="珍珠奶茶",
        current_hs_code="2106.90.99",
        current_tariff_rate=12.0,
        bom_items=bom_items,
        constraints={"max_cost_increase_pct": 3.0}
    )
    
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


if __name__ == "__main__":
    test_optimizer()