"""
trading_bot.position_manager

持仓持久化管理器：
- 负责将持仓信息保存到本地 JSON 文件
- 支持从文件加载历史持仓
- 每次持仓变更立即同步到磁盘
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional

try:
    from domain import Position
except ImportError:
    from .domain import Position


class PositionManager:
    """
    持仓持久化管理器
    
    功能：
    - 管理持仓的内存状态与磁盘持久化
    - 使用 position_id 作为唯一标识
    - 每次变更立即同步到磁盘，确保数据不丢失
    
    存储路径：项目根目录下的 data/positions.json
    """

    def __init__(self, storage_path: Optional[str] = None) -> None:
        """
        初始化 PositionManager
        
        参数：
        - storage_path: 存储文件路径，默认为项目根目录下的 data/positions.json
        """
        if storage_path is None:
            # 默认路径：项目根目录/data/positions.json
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            storage_path = os.path.join(project_root, "data", "positions.json")
        
        self.storage_path = storage_path
        self._positions: Dict[str, Position] = {}
        
        # 确保存储目录存在
        os.makedirs(os.path.dirname(self.storage_path), exist_ok=True)
        
        # 启动时加载历史持仓
        self.load_positions()

    def load_positions(self) -> List[Position]:
        """
        从磁盘加载持仓数据
        
        返回：
        - Position 对象列表
        """
        if not os.path.exists(self.storage_path):
            return []
        
        try:
            with open(self.storage_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # 期望数据结构：{"positions": {"position_id": {...}, ...}}
            positions_data = data.get("positions", {})
            
            loaded_positions = []
            for position_id, position_dict in positions_data.items():
                try:
                    position = Position.from_dict(position_dict)
                    self._positions[position_id] = position
                    loaded_positions.append(position)
                except Exception as e:
                    # 单个持仓加载失败，记录错误但继续加载其他
                    print(f"[PositionManager] failed to load position {position_id}: {e}")
            
            print(f"[PositionManager] loaded {len(loaded_positions)} positions from {self.storage_path}")
            return loaded_positions
        
        except Exception as e:
            print(f"[PositionManager] error loading positions: {e}")
            return []

    def save_positions(self) -> None:
        """
        将当前持仓保存到磁盘
        """
        try:
            # 构建序列化数据
            positions_data = {
                position_id: position.to_dict()
                for position_id, position in self._positions.items()
            }
            
            data = {
                "positions": positions_data,
                "count": len(positions_data),
            }
            
            with open(self.storage_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"[PositionManager] saved {len(positions_data)} positions to {self.storage_path}")
        
        except Exception as e:
            print(f"[PositionManager] error saving positions: {e}")

    def add_position(self, position_id: str, position: Position) -> None:
        """
        新增持仓
        
        参数：
        - position_id: 持仓唯一标识
        - position: Position 对象
        """
        self._positions[position_id] = position
        self.save_positions()
        print(f"[PositionManager] added position {position_id}")

    def update_position(self, position_id: str, position: Position) -> None:
        """
        更新持仓（如部分平仓后）
        
        参数：
        - position_id: 持仓唯一标识
        - position: 更新后的 Position 对象
        """
        if position_id not in self._positions:
            print(f"[PositionManager] warning: updating non-existent position {position_id}")
        
        self._positions[position_id] = position
        self.save_positions()
        print(f"[PositionManager] updated position {position_id}")

    def remove_position(self, position_id: str) -> None:
        """
        移除持仓（完全平仓后）
        
        参数：
        - position_id: 持仓唯一标识
        """
        if position_id in self._positions:
            del self._positions[position_id]
            self.save_positions()
            print(f"[PositionManager] removed position {position_id}")
        else:
            print(f"[PositionManager] warning: removing non-existent position {position_id}")

    def get_position(self, position_id: str) -> Optional[Position]:
        """
        获取指定持仓
        
        参数：
        - position_id: 持仓唯一标识
        
        返回：
        - Position 对象或 None
        """
        return self._positions.get(position_id)

    def get_all_positions(self) -> Dict[str, Position]:
        """
        获取所有持仓
        
        返回：
        - position_id -> Position 的字典
        """
        return dict(self._positions)

    def get_active_positions(self) -> Dict[str, Position]:
        """
        获取活跃持仓（remaining_qty > 0）
        
        返回：
        - position_id -> Position 的字典
        """
        return {
            pid: pos
            for pid, pos in self._positions.items()
            if pos.remaining_qty > 0
        }