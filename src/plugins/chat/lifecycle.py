from typing import Dict, Any, Optional, Callable, List, TypeVar
import asyncio
from nonebot import get_driver
from nonebot.log import logger

T = TypeVar("T")


class ResourceManager:
    """集中化的资源管理器"""

    _resources: Dict[str, Any] = {}
    _ready_events: Dict[str, asyncio.Event] = {}
    _dependencies: Dict[str, List[str]] = {}
    _initialized = False
    _initializing = False

    @classmethod
    async def initialize(cls):
        """初始化所有资源"""
        if cls._initialized or cls._initializing:
            return

        cls._initializing = True
        logger.info("开始初始化资源...")

        # 按依赖顺序初始化
        for name in cls._get_initialization_order():
            init_func = cls._resources.get(f"{name}_initializer")
            if init_func and callable(init_func):
                try:
                    logger.debug(f"初始化资源: {name}")
                    result = init_func()
                    if asyncio.iscoroutine(result):
                        await result

                    # 设置资源就绪事件
                    if name in cls._ready_events:
                        cls._ready_events[name].set()
                except Exception as e:
                    logger.error(f"初始化资源 {name} 失败: {str(e)}")

        cls._initialized = True
        cls._initializing = False
        logger.info("资源初始化完成")

    @classmethod
    def _get_initialization_order(cls) -> List[str]:
        """获取基于依赖关系的初始化顺序"""
        # 简单的拓扑排序实现
        visited = set()
        order = []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            for dep in cls._dependencies.get(name, []):
                visit(dep)
            order.append(name)

        for name in cls._resources:
            if name.endswith("_initializer"):
                resource_name = name[:-12]  # 去掉"_initializer"后缀
                visit(resource_name)

        return order

    @classmethod
    def register(
        cls,
        name: str,
        resource: Any = None,
        dependencies: List[str] = None,
        initializer: Callable = None,
    ):
        """注册资源和它的依赖关系"""
        if resource is not None:
            cls._resources[name] = resource

        if initializer is not None:
            cls._resources[f"{name}_initializer"] = initializer

        if dependencies:
            cls._dependencies[name] = dependencies

        # 创建资源就绪事件
        if name not in cls._ready_events:
            cls._ready_events[name] = asyncio.Event()

    @classmethod
    async def get(cls, name: str, timeout: float = 10.0) -> Optional[T]:
        """获取资源，如果资源不可用会等待指定时间"""
        # 如果资源已存在，直接返回
        if name in cls._resources:
            return cls._resources[name]

        # 如果资源有就绪事件，等待它
        if name in cls._ready_events:
            try:
                await asyncio.wait_for(cls._ready_events[name].wait(), timeout)
                return cls._resources.get(name)
            except asyncio.TimeoutError:
                logger.warning(f"等待资源 {name} 超时")
                return None

        return None

    @classmethod
    def set(cls, name: str, resource: Any):
        """设置资源值并标记为就绪"""
        cls._resources[name] = resource
        if name in cls._ready_events:
            cls._ready_events[name].set()


# 在NoneBot启动时初始化资源
driver = get_driver()


@driver.on_startup
async def initialize_resources():
    await ResourceManager.initialize()
