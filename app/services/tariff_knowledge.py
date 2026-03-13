# 动态税则知识库服务
# 提供 HS Code 查询、ECFA 货品清单检查功能

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.database import HSCode, ECFAGoodsItem, TariffQueryHistory, SessionLocal


class TariffKnowledgeBase:
    """动态税则知识库"""
    
    def __init__(self):
        self.db = SessionLocal()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.db.close()
    
    def query_tariff(self, hs_code: str, country: str = "CN") -> Dict[str, Any]:
        """
        查询特定 HS Code 的税率
        
        Args:
            hs_code: 税则号列 (如 "2106.90.99")
            country: 目的国 (CN/TW/US/EU)
            
        Returns:
            税率信息
        """
        # Keep original format for query but try both with and without dots
        hs_code_normalized = hs_code.replace(".", "").strip()
        
        # Query database - try both formats
        hs_record = self.db.query(HSCode).filter(
            (HSCode.hs_code == hs_code) | 
            (HSCode.hs_code == hs_code_normalized) |
            (HSCode.hs_code.like(f"{hs_code_normalized}%"))
        ).first()
        
        # If not found, try just the first 6 digits
        if not hs_record:
            hs_record = self.db.query(HSCode).filter(
                HSCode.hs_code.like(f"{hs_code_normalized[:6]}%")
            ).first()
        
        # Get tariff rate
        tariff_col = f"tariff_{country.lower()}"
        if hs_record and hasattr(hs_record, tariff_col):
            tariff_rate = getattr(hs_record, tariff_col)
        else:
            tariff_rate = None
        
        # Record query history
        self._record_query(hs_code, country, tariff_rate)
        
        return {
            "hs_code": hs_code,
            "country": country,
            "tariff_rate": tariff_rate,
            "description": hs_record.description if hs_record else None,
            "in_ecfa_list": hs_record.in_ecfa_list if hs_record else False,
            "ecfa_note": hs_record.ecfa_note if hs_record else None,
            "source": "database"
        }
    
    def ecfa_check(self, product_name: str, hs_code: Optional[str] = None) -> Dict[str, Any]:
        """
        检查产品是否在 ECFA 货品清单范围内
        
        Args:
            product_name: 产品名称
            hs_code: 税则号列 (可选)
            
        Returns:
            ECFA 适用性检查结果
        """
        results = {
            "product_name": product_name,
            "hs_code": hs_code,
            "in_ecfa_list": False,
            "ecfa_category": None,
            "item_number": None,
            "origin_criteria": None,
            "required_documents": None,
            "notes": None,
            "confidence": 0.0
        }
        
        # If HS code provided, check directly
        if hs_code:
            hs_code_normalized = hs_code.replace(".", "").strip()
            hs_record = self.db.query(HSCode).filter(
                HSCode.hs_code.like(f"{hs_code_normalized}%")
            ).first()
            
            if hs_record:
                results["in_ecfa_list"] = hs_record.in_ecfa_list
                results["notes"] = hs_record.ecfa_note
                results["confidence"] = 0.9 if hs_record.in_ecfa_list else 0.7
                
                # Get ECFA details
                ecfa_item = self.db.query(ECFAGoodsItem).filter(
                    ECFAGoodsItem.hs_code_id == hs_record.id
                ).first()
                
                if ecfa_item:
                    results["ecfa_category"] = ecfa_item.ecfa_category
                    results["item_number"] = ecfa_item.item_number
                    results["origin_criteria"] = ecfa_item.origin_criteria
                    results["required_documents"] = ecfa_item.required_documents
        
        # If no HS code, search by product name
        if not results["in_ecfa_list"] and not hs_code:
            # Search ECFA items by name
            ecfa_items = self.db.query(ECFAGoodsItem).filter(
                ECFAGoodsItem.product_name.like(f"%{product_name}%")
            ).all()
            
            if ecfa_items:
                results["in_ecfa_list"] = True
                results["confidence"] = 0.7
                results["notes"] = f"找到 {len(ecfa_items)} 项相关货品"
        
        # Default ECFA check rules for common products
        results["legal_notice"] = self._get_legal_notice(results)
        
        return results
    
    def search_hs_codes(self, keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        搜索 HS Code
        
        Args:
            keyword: 搜索关键词
            limit: 返回数量限制
            
        Returns:
            HS Code 列表
        """
        hs_codes = self.db.query(HSCode).filter(
            (HSCode.hs_code.like(f"%{keyword}%")) |
            (HSCode.description.like(f"%{keyword}%"))
        ).limit(limit).all()
        
        return [
            {
                "hs_code": hs.hs_code,
                "description": hs.description,
                "chapter": hs.chapter,
                "tariff_cn": hs.tariff_cn,
                "tariff_tw": hs.tariff_tw,
                "in_ecfa_list": hs.in_ecfa_list
            }
            for hs in hs_codes
        ]
    
    def get_ecfa_goods_list(self, chapter: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取 ECFA 货品清单
        
        Args:
            chapter: 章节筛选 (可选)
            limit: 返回数量限制
            
        Returns:
            ECFA 货品列表
        """
        query = self.db.query(ECFAGoodsItem)
        
        if chapter:
            hs_codes = self.db.query(HSCode).filter(HSCode.chapter == chapter).all()
            hs_ids = [hs.id for hs in hs_codes]
            query = query.filter(ECFAGoodsItem.hs_code_id.in_(hs_ids))
        
        items = query.limit(limit).all()
        
        results = []
        for item in items:
            hs = self.db.query(HSCode).get(item.hs_code_id)
            results.append({
                "hs_code": hs.hs_code if hs else None,
                "product_name": item.product_name,
                "ecfa_category": item.ecfa_category,
                "item_number": item.item_number,
                "origin_criteria": item.origin_criteria,
                "notes": item.notes
            })
        
        return results
    
    def get_chapter_summary(self) -> List[Dict[str, Any]]:
        """获取各章节 ECFA 货品统计"""
        chapters = self.db.query(
            HSCode.chapter,
            HSCode.description
        ).filter(
            HSCode.in_ecfa_list == True
        ).distinct().all()
        
        summary = []
        for chapter, desc in chapters:
            count = self.db.query(HSCode).filter(
                HSCode.chapter == chapter,
                HSCode.in_ecfa_list == True
            ).count()
            
            summary.append({
                "chapter": chapter,
                "description": desc,
                "ecfa_item_count": count
            })
        
        return sorted(summary, key=lambda x: x["chapter"])
    
    def _record_query(self, hs_code: str, country: str, tariff_rate: Optional[float]):
        """记录查询历史"""
        try:
            history = TariffQueryHistory(
                hs_code=hs_code,
                country=country,
                tariff_rate=tariff_rate,
                source="api"
            )
            self.db.add(history)
            self.db.commit()
        except:
            self.db.rollback()
    
    def _get_legal_notice(self, check_result: Dict[str, Any]) -> str:
        """获取法律声明"""
        if check_result["in_ecfa_list"]:
            return (
                "本系统仅提供 ECFA 货品清单的初步筛选参考。"
                "是否真正享有 ECFA 零关税优惠，需满足以下条件："
                "1) 货品确实在 ECFA 原产货品清单范围内；"
                "2) 符合 ECFA 原产地认定基准（台湾来源或台湾制程）；"
                "3) 备妥 ECFA 原产地证明书及相关佐证文件。"
                "最终是否享惠，应以海关实际核定为准。"
            )
        else:
            return (
                "本产品经初步筛选不在 ECFA 零关税货品清单范围内。"
                "如需确认，请提供完整产品描述和税则号列，由专业人员进一步核查。"
                "本声明仅供参考，不构成法律意见。"
            )


# Utility functions for API
def query_tariff_rate(hs_code: str, country: str = "CN") -> Dict[str, Any]:
    """查询税率"""
    with TariffKnowledgeBase() as kb:
        return kb.query_tariff(hs_code, country)


def check_ecfa_eligibility(product_name: str, hs_code: Optional[str] = None) -> Dict[str, Any]:
    """检查 ECFA 资格"""
    with TariffKnowledgeBase() as kb:
        return kb.ecfa_check(product_name, hs_code)


def search_hs_codes(keyword: str, limit: int = 20) -> List[Dict[str, Any]]:
    """搜索 HS Code"""
    with TariffKnowledgeBase() as kb:
        return kb.search_hs_codes(keyword, limit)


# Test function
def test_knowledge_base():
    """测试税则知识库"""
    with TariffKnowledgeBase() as kb:
        # Test tariff query
        print("=== 测试税率查询 ===")
        result = kb.query_tariff("2106.90.99", "CN")
        print(result)
        
        print("\n=== 测试 ECFA 检查 ===")
        result = kb.ecfa_check("珍珠奶茶", "2106.90.99")
        print(result)
        
        print("\n=== 测试 HS Code 搜索 ===")
        result = kb.search_hs_codes("食品")
        print(result)


if __name__ == "__main__":
    test_knowledge_base()