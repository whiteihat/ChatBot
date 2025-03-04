import os
import tomli
from typing import Dict, List, Any, Optional
from pathlib import Path
from pydantic import BaseModel
from .lifecycle import ResourceManager


class APIConfig(BaseModel):
    """API相关配置"""

    deepseek_api_key: str = ""
    deepseek_api_base: str = ""
    siliconflow_api_key: str = ""
    siliconflow_api_base: str = ""


class BotConfig(BaseModel):
    """机器人基础配置"""

    name: str = "MyChatBot"
    qq: str = ""


class MessageConfig(BaseModel):
    """消息处理配置"""

    min_text_length: int = 2
    max_text_length: int = 500
    max_context_size: int = 15
    allowed_types: List[str] = ["text", "image"]


class ResponseConfig(BaseModel):
    """回复配置"""

    api_using: str = "siliconflow"
    model_probabilities: Dict[str, float] = {"r1": 0.5, "v3": 0.3, "r1_distill": 0.2}


class ConfigLoader:
    """配置加载器"""

    @staticmethod
    def load_env_config() -> dict:
        """加载环境变量配置"""
        return {
            "api": {
                "deepseek_api_key": os.getenv("DEEPSEEK_API_KEY", ""),
                "deepseek_api_base": os.getenv("DEEPSEEK_API_BASE", ""),
                "siliconflow_api_key": os.getenv("SILICONFLOW_API_KEY", ""),
                "siliconflow_api_base": os.getenv("SILICONFLOW_API_BASE", ""),
            }
        }

    @staticmethod
    def load_toml_config(file_path: str = None) -> dict:
        """加载TOML配置文件"""
        if file_path is None:
            # 默认配置文件路径
            project_root = Path(
                os.path.dirname(os.path.abspath(__file__))
            ).parent.parent.parent
            file_path = project_root / "config.toml"

        if not os.path.exists(file_path):
            return {}

        with open(file_path, "rb") as f:
            return tomli.load(f)

    @classmethod
    def load_config(cls) -> dict:
        """加载所有配置"""
        # 先加载配置文件
        config = cls.load_toml_config()
        # 再加载环境变量(会覆盖配置文件中的同名配置)
        env_config = cls.load_env_config()

        # 合并配置
        for key, value in env_config.items():
            if key in config:
                if isinstance(value, dict) and isinstance(config[key], dict):
                    config[key].update(value)
                else:
                    config[key] = value
            else:
                config[key] = value

        return config


class Config:
    """配置访问类"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 加载配置
        config_data = ConfigLoader.load_config()

        # 解析各模块配置
        self.api = APIConfig(**config_data.get("api", {}))
        self.bot = BotConfig(**config_data.get("bot", {}))
        self.message = MessageConfig(**config_data.get("message", {}))
        self.response = ResponseConfig(**config_data.get("response", {}))

        self._initialized = True

    def check_message_length(self, text: str) -> bool:
        """检查消息长度是否符合要求"""
        return self.message.min_text_length <= len(text) <= self.message.max_text_length

    def get_current_api_info(self) -> tuple:
        """获取当前使用的API信息"""
        api_type = self.response.api_using

        if api_type == "deepseek":
            return self.api.deepseek_api_base, self.api.deepseek_api_key
        elif api_type == "siliconflow":
            return self.api.siliconflow_api_base, self.api.siliconflow_api_key
        else:
            return "", ""

    def get_random_model(self) -> str:
        """根据概率随机选择模型"""
        import random

        models = list(self.response.model_probabilities.keys())
        probabilities = list(self.response.model_probabilities.values())
        return random.choices(models, weights=probabilities, k=1)[0]


# 全局配置实例
config = Config()


async def initialize_config():
    """初始化配置资源"""
    ResourceManager.set("config", config)


# 注册配置资源
ResourceManager.register(name="config", initializer=initialize_config)


async def get_config() -> Config:
    """获取配置，等待配置就绪"""
    return await ResourceManager.get("config")
