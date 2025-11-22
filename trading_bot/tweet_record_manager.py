"""
trading_bot.tweet_record_manager

推文处理记录管理系统：

核心功能：
- 记录每条推文的完整处理生命周期
- 支持去重判断（基于 tweet_id）
- 实时持久化到 JSON 文件
- 存储 AI 分析结果（成功/失败、原始数据/解析数据）
- 预留实盘交易信息扩展

设计原则：
- 职责单一：只负责记录管理，不耦合业务逻辑
- 内存+文件双存储：内存快速查询，文件持久化
- 实时保存：处理完成后立即保存，防止数据丢失
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any, List
from collections import OrderedDict

try:
    from config import load_config
except ImportError:
    from .config import load_config


@dataclass
class TweetProcessingRecord:
    """
    推文处理记录数据结构
    
    字段说明：
    - tweet_id: 推文唯一ID（主键）
    - username: 推文作者账号
    - tweet_time: 推文发布时间（UTC+8，格式：YYYY-MM-DD HH:MM:SS）
    - tweet_preview: 推文前100个字符（快速预览）
    - ai_success: AI分析是否成功解析为JSON
    - ai_raw_result: 失败时存储原始返回数据
    - ai_parsed_result: 成功时存储解析后的结构化数据
    - trade_info: 实盘交易信息（可选，后续扩展）
    - retry_count: 重试次数
    - last_error: 最后一次错误信息
    """
    tweet_id: str
    username: str
    tweet_time: str
    tweet_preview: str
    ai_success: bool
    ai_raw_result: Optional[str] = None
    ai_parsed_result: Optional[Dict[str, Any]] = None
    trade_info: Optional[Dict[str, Any]] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化的字典"""
        data = asdict(self)
        # 过滤 None 值，减少文件体积
        return {k: v for k, v in data.items() if v is not None}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TweetProcessingRecord":
        """从字典创建实例"""
        return cls(**data)


class TweetRecordManager:
    """
    推文记录管理器
    
    核心职责：
    1. 管理内存中的记录集合（tweet_id -> record）
    2. 提供快速查询（是否已处理）
    3. 添加新记录
    4. 更新记录（如AI结果、交易信息）
    5. 加载和保存到文件
    """
    
    def __init__(self, records_file: Optional[Path] = None) -> None:
        """
        初始化管理器
        
        参数：
        - records_file: 记录文件路径（可选，默认使用标准路径）
        """
        self.records: Dict[str, TweetProcessingRecord] = {}
        self.records_file = records_file or self._get_default_records_path()
        self._load_from_file()
    
    def _get_default_records_path(self) -> Path:
        """获取默认记录文件路径"""
        base_dir = Path(__file__).resolve().parent.parent
        media_dir = base_dir / "推特抢跑" / "twitter_media"
        media_dir.mkdir(parents=True, exist_ok=True)
        return media_dir / "tweet_records.json"
    
    def _load_from_file(self) -> None:
        """从文件加载记录到内存"""
        if not self.records_file.exists():
            return
        
        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 兼容旧格式（如果存在）
            if isinstance(data, list):
                # 旧格式：直接是记录列表
                records_list = data
            elif isinstance(data, dict) and "records" in data:
                # 新格式：{"records": [...]}
                records_list = data.get("records", [])
            else:
                records_list = []
            
            for record_data in records_list:
                try:
                    record = TweetProcessingRecord.from_dict(record_data)
                    self.records[record.tweet_id] = record
                except Exception as e:
                    print(f"[TweetRecordManager] 加载记录失败: {e}")
        
        except Exception as e:
            print(f"[TweetRecordManager] 加载文件失败: {e}")
            self.records = {}
    
    def save_to_file(self) -> None:
        """将记录保存到文件（实时持久化）"""
        try:
            # 按 tweet_id 排序，保证文件内容有序
            sorted_records = sorted(
                self.records.values(),
                key=lambda r: r.tweet_id
            )
            
            data = {
                "records": [record.to_dict() for record in sorted_records]
            }
            
            with open(self.records_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        except Exception as e:
            print(f"[TweetRecordManager] 保存文件失败: {e}")
    
    def is_processed(self, tweet_id: str) -> bool:
        """检查推文是否已处理"""
        return tweet_id in self.records
    
    def get_record(self, tweet_id: str) -> Optional[TweetProcessingRecord]:
        """获取单条记录"""
        return self.records.get(tweet_id)
    
    def add_record(self, record: TweetProcessingRecord) -> None:
        """添加新记录（覆盖已存在的）"""
        self.records[record.tweet_id] = record
    
    def update_ai_result(
        self,
        tweet_id: str,
        success: bool,
        raw_result: Optional[str] = None,
        parsed_result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """
        更新AI分析结果
        
        参数：
        - tweet_id: 推文ID
        - success: 是否成功解析
        - raw_result: 失败时的原始数据
        - parsed_result: 成功时的解析结果
        - error: 错误信息（如果有）
        """
        if tweet_id not in self.records:
            print(f"[TweetRecordManager] 记录不存在: {tweet_id}")
            return
        
        record = self.records[tweet_id]
        record.ai_success = success
        record.ai_raw_result = raw_result
        record.ai_parsed_result = parsed_result
        record.last_error = error
    
    def update_retry_count(self, tweet_id: str, retry_count: int) -> None:
        """更新重试次数"""
        if tweet_id in self.records:
            self.records[tweet_id].retry_count = retry_count
    
    def update_trade_info(self, tweet_id: str, trade_info: Dict[str, Any]) -> None:
        """更新实盘交易信息"""
        if tweet_id in self.records:
            self.records[tweet_id].trade_info = trade_info
    
    def get_all_records(self) -> List[TweetProcessingRecord]:
        """获取所有记录"""
        return list(self.records.values())
    
    def get_failed_records(self) -> List[TweetProcessingRecord]:
        """获取AI分析失败的记录"""
        return [
            record for record in self.records.values()
            if not record.ai_success
        ]
    
    def get_success_records(self) -> List[TweetProcessingRecord]:
        """获取AI分析成功的记录"""
        return [
            record for record in self.records.values()
            if record.ai_success
        ]


def get_tweet_preview(text: str, max_length: int = 100) -> str:
    """
    获取推文预览（前N个字符）
    
    参数：
    - text: 推文完整内容
    - max_length: 最大长度（默认100）
    
    返回：
    - 处理后的预览字符串（去除换行、截断）
    """
    if not text:
        return ""
    
    # 移除换行符和多余空格
    preview = text.replace("\n", " ").replace("\r", " ").strip()
    
    # 截断到指定长度
    if len(preview) > max_length:
        preview = preview[:max_length] + "..."
    
    return preview


def format_time_simple(timestamp: Optional[float] = None) -> str:
    """
    简单时间格式化（默认使用当前时间）
    
    参数：
    - timestamp: 时间戳（秒），如果为 None 使用当前时间
    
    返回：
    - UTC+8 格式的字符串（注意：这只是格式化，没有实际时区转换）
    """
    if timestamp is None:
        timestamp = datetime.now().timestamp()
    
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y-%m-%d %H:%M:%S")