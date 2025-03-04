from typing import Dict, Any, Optional
import json
import os
from pathlib import Path
from nonebot.log import logger
from .lifecycle import ResourceManager

class GroupConfig:
    """群组特定配置"""
    
    def __init__(self, group_id: int, data: Dict[str, Any] = None):
        self.group_id = group_id
        self.enabled = True
        self.random_reply_rate = 0.1  # 默认随机回复率
        self.trigger_keywords = []    # 群特定触发词
        self.blacklist_users = []     # 群内黑名单用户
        
        # 加载提供的数据
        if data:
            self.__dict__.update(data)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "group_id": self.group_id,
            "enabled": self.enabled,
            "random_reply_rate": self.random_reply_rate,
            "trigger_keywords": self.trigger_keywords,
            "blacklist_users": self.blacklist_users
        }

class GroupManager:
    """群组管理器"""
    
    def __init__(self, config_dir: str = None):
        """初始化群组管理器"""
        if not config_dir:
            self.config_dir = Path(os.path.dirname(os.path.abspath(__file__))) / "group_configs"
        else:
            self.config_dir = Path(config_dir)
            
        self.config_dir.mkdir(exist_ok=True)
        self.groups: Dict[int, GroupConfig] = {}
        self.default_config = None
        self.global_blacklist = []
        self.whitelist_groups = []  # 如果不为空，则只响应这些群
        
    async def load_configs(self):
        """加载所有群组配置"""
        # 加载默认配置
        default_path = self.config_dir / "default.json"
        if default_path.exists():
            try:
                with open(default_path, "r", encoding="utf-8") as f:
                    self.default_config = json.load(f)
                logger.info("已加载默认群组配置")
            except Exception as e:
                logger.error(f"加载默认群组配置失败: {e}")
        
        # 加载全局设置
        global_path = self.config_dir / "global.json"
        if global_path.exists():
            try:
                with open(global_path, "r", encoding="utf-8") as f:
                    global_config = json.load(f)
                    self.global_blacklist = global_config.get("blacklist", [])
                    self.whitelist_groups = global_config.get("whitelist_groups", [])
                logger.info("已加载全局群组设置")
            except Exception as e:
                logger.error(f"加载全局群组设置失败: {e}")
        
        # 加载具体群组配置
        for file in self.config_dir.glob("group_*.json"):
            try:
                group_id = int(file.stem.split("_")[1])
                with open(file, "r", encoding="utf-8") as f:
                    group_data = json.load(f)
                    self.groups[group_id] = GroupConfig(group_id, group_data)
                logger.debug(f"已加载群 {group_id} 的配置")
            except Exception as e:
                logger.error(f"加载群组配置失败 {file.name}: {e}")
    
    async def get_group_config(self, group_id: int) -> Optional[GroupConfig]:
        """获取指定群的配置"""
        # 检查群是否在白名单中（如果有白名单）
        if self.whitelist_groups and group_id not in self.whitelist_groups:
            return None
            
        # 返回已存在的配置或创建新配置
        if group_id not in self.groups:
            # 使用默认配置创建
            if self.default_config:
                self.groups[group_id] = GroupConfig(group_id, self.default_config)
            else:
                self.groups[group_id] = GroupConfig(group_id)
                
        return self.groups[group_id]
    
    async def save_group_config(self, group_id: int):
        """保存群组配置"""
        if group_id in self.groups:
            file_path = self.config_dir / f"group_{group_id}.json"
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.groups[group_id].to_dict(), f, ensure_ascii=False, indent=4)
                logger.debug(f"已保存群 {group_id} 的配置")
            except Exception as e:
                logger.error(f"保存群 {group_id} 配置失败: {e}")
    
    def is_user_blocked(self, user_id: int, group_id: int = None) -> bool:
        """检查用户是否被屏蔽"""
        # 检查全局黑名单
        if user_id in self.global_blacklist:
            return True
            
        # 检查群组特定黑名单
        if group_id and group_id in self.groups:
            return user_id in self.groups[group_id].blacklist_users
            
        return False

# 初始化群组管理器
async def initialize_group_manager():
    """初始化群组管理器"""
    manager = GroupManager()
    await manager.load_configs()
    ResourceManager.set("group_manager", manager)

# 注册群组管理器
ResourceManager.register(
    name="group_manager", 
    initializer=initialize_group_manager
)

# 获取群组管理器实例
async def get_group_manager() -> Optional[GroupManager]:
    """获取群组管理器实例"""
    return await ResourceManager.get("group_manager")
