# ECFA Tariff Optimizer V2 - Database Models
# SQLite database for V2, separate from V1

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os

# Create V2 specific database (separate from V1)
V2_DB_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
V2_DB_PATH = os.path.join(V2_DB_DIR, "ecfa_v2.db")

# Ensure data directory exists
os.makedirs(V2_DB_DIR, exist_ok=True)

engine = create_engine(f"sqlite:///{V2_DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# =====================
# HS Code Database
# =====================
class HSCode(Base):
    __tablename__ = "hs_codes"
    
    id = Column(Integer, primary_key=True, index=True)
    hs_code = Column(String(20), unique=True, index=True, nullable=False)
    description = Column(Text, nullable=False)
    chapter = Column(String(2), index=True)
    heading = Column(String(4))
    subheading = Column(String(6))
    
    # Tariff rates for different countries
    tariff_cn = Column(Float, nullable=True)  # China
    tariff_tw = Column(Float, nullable=True)  # Taiwan
    tariff_us = Column(Float, nullable=True)  # USA
    tariff_eu = Column(Float, nullable=True)  # EU
    
    # ECFA status
    in_ecfa_list = Column(Boolean, default=False)
    ecfa_note = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    ecfa_items = relationship("ECFAGoodsItem", back_populates="hs_code_ref")


# =====================
# ECFA 货品清单 Database
# =====================
class ECFAGoodsItem(Base):
    __tablename__ = "ecfa_goods_items"
    
    id = Column(Integer, primary_key=True, index=True)
    hs_code_id = Column(Integer, ForeignKey("hs_codes.id"))
    
    # ECFA list details
    ecfa_category = Column(String(50))  # 货品分类
    ecfa_item_number = Column(String(20))  # 项别
    product_name = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    
    # Origin requirements
    origin_criteria = Column(Text)  # 原产地认定基准
    required_documents = Column(Text)  # 所需文件
    
    # Validation
    effective_date = Column(DateTime, nullable=True)
    expiry_date = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    hs_code_ref = relationship("HSCode", back_populates="ecfa_items")


# =====================
# BOM 解析结果存储
# =====================
class BOMParseResult(Base):
    __tablename__ = "bom_parse_results"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Source file info
    filename = Column(String(255))
    file_type = Column(String(20))  # pdf, excel, csv
    original_content = Column(Text)  # 原始内容（JSON存储）
    
    # Parsed BOM items
    parsed_items = Column(Text)  # JSON - 解析后的物料列表
    
    # NLP extraction results
    extracted_materials = Column(Text)  # JSON - NLP提取的物料
    extracted_origins = Column(Text)  # JSON - 提取的产地信息
    extracted_costs = Column(Text)  # JSON - 提取的成本信息
    
    # Quality metrics
    confidence_score = Column(Float, default=0.0)
    missing_fields = Column(Text)  # JSON - 缺失的字段
    
    # Status
    status = Column(String(20), default="pending")  # pending, parsed, validated, error
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =====================
# 优化历史记录
# =====================
class OptimizationHistory(Base):
    __tablename__ = "optimization_history"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Input parameters
    product_name = Column(String(255))
    current_hs_code = Column(String(20))
    destination_country = Column(String(10))
    
    # BOM info
    bom_items = Column(Text)  # JSON
    constraints = Column(Text)  # JSON
    
    # Results
    recommended_scenario = Column(Text)  # JSON
    candidate_scenarios = Column(Text)  # JSON
    optimization_result = Column(Text)  # JSON - full result
    
    # Metrics
    tariff_reduction = Column(Float)
    cost_change = Column(Float)
    feasibility_score = Column(Float)
    
    # Status
    status = Column(String(20), default="completed")
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# =====================
# 税则查询历史
# =====================
class TariffQueryHistory(Base):
    __tablename__ = "tariff_query_history"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Query parameters
    hs_code = Column(String(20), index=True)
    country = Column(String(10))
    
    # Result
    tariff_rate = Column(Float)
    source = Column(String(100))
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)


# =====================
# Database Functions
# =====================
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Initialize database and create tables"""
    Base.metadata.create_all(bind=engine)
    
    # Add some sample HS codes if empty
    db = SessionLocal()
    try:
        if db.query(HSCode).count() == 0:
            # Add sample HS codes for testing
            sample_codes = [
                HSCode(
                    hs_code="2106.90.99",
                    description="其他未列名食品",
                    chapter="21",
                    heading="2106",
                    tariff_cn=12.0,
                    tariff_tw=0.0,
                    in_ecfa_list=True,
                    ecfa_note="部分项别享惠，需确认具体货号"
                ),
                HSCode(
                    hs_code="1905.90.90",
                    description="其他面包、糕点、饼干",
                    chapter="19",
                    heading="1905",
                    tariff_cn=10.0,
                    tariff_tw=0.0,
                    in_ecfa_list=True,
                    ecfa_note="需符合原产地认定基准"
                ),
                HSCode(
                    hs_code="2202.99",
                    description="其他饮料",
                    chapter="22",
                    heading="2202",
                    tariff_cn=15.0,
                    tariff_tw=0.0,
                    in_ecfa_list=False,
                    ecfa_note="部分项别在清单内"
                ),
            ]
            db.add_all(sample_codes)
            db.commit()
    finally:
        db.close()