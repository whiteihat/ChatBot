from typing import Dict, List, Any, Optional, Callable, TypeVar, Set, Tuple
import asyncio
import time
from collections import defaultdict, deque
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
    _lock = asyncio.Lock()
    _registry: List[Dict[str, Any]] = []

    # 精简的状态跟踪 - 仅保留最基本的指标
    _start_time: float = 0
    _init_failures: List[str] = []  # 仅记录失败的资源

    @classmethod
    async def initialize(cls):
        """初始化所有资源"""
        async with cls._lock:
            if cls._initialized or cls._initializing:
                return
            cls._initializing = True
            cls._start_time = time.time()
            cls._init_failures = []

        logger.info("开始初始化资源...")
        initialization_order, cyclic_nodes = await cls._get_initialization_order()

        # 输出简化的依赖信息
        if initialization_order:
            logger.info(f"将初始化 {len(initialization_order)} 个资源")

        if cyclic_nodes:
            logger.warning(f"检测到循环依赖: {', '.join(cyclic_nodes)}")

        # 按顺序初始化非循环依赖资源
        for name in initialization_order:
            await cls._init_single(name)

        # 处理循环依赖资源组
        if cyclic_nodes:
            logger.info(f"处理 {len(cyclic_nodes)} 个循环依赖资源")
            await cls._initialize_cyclic_group(cyclic_nodes)

        # 简化的初始化总结
        total_time = time.time() - cls._start_time
        logger.info(f"资源初始化完成，总耗时: {total_time:.2f}秒")

        if cls._init_failures:
            logger.warning(f"初始化失败的资源: {', '.join(cls._init_failures)}")

        async with cls._lock:
            cls._initialized = True
            cls._initializing = False

    @classmethod
    async def _init_single(cls, name: str) -> bool:
        """初始化单个资源，返回是否成功"""
        async with cls._lock:
            init_func = cls._resources.get(f"{name}_initializer")

        if not init_func or not callable(init_func):
            return False

        try:
            logger.debug(f"初始化资源: {name}")
            start_time = time.time()

            result = init_func()
            if asyncio.iscoroutine(result):
                await result

            elapsed = time.time() - start_time

            async with cls._lock:
                if name in cls._ready_events:
                    cls._ready_events[name].set()

            # 仅对耗时较长的资源记录日志
            if elapsed > 0.5:
                logger.info(f"资源 {name} 初始化耗时: {elapsed:.2f}秒")
            return True

        except Exception as e:
            logger.error(f"初始化资源 {name} 失败: {str(e)}")
            async with cls._lock:
                cls._init_failures.append(name)
            return False

    @classmethod
    async def _initialize_cyclic_group(cls, group: Set[str]):
        """并行初始化循环依赖组"""
        for name in group:
            # 对于小应用，简化为顺序初始化，避免过多异步任务开销
            success = await cls._init_single(name)
            if success:
                logger.debug(f"循环依赖资源 {name} 成功初始化")

        failed = [name for name in group if name in cls._init_failures]
        if failed:
            logger.warning(f"循环依赖组中 {len(failed)} 个资源初始化失败")

    @classmethod
    async def _get_initialization_order(cls) -> Tuple[List[str], Set[str]]:
        """使用Kahn算法获取资源初始化顺序并检测循环依赖"""
        async with cls._lock:
            # 获取所有资源名称和依赖关系副本
            resource_names = {
                name[:-12] for name in cls._resources if name.endswith("_initializer")
            }
            deps_copy = {k: v.copy() if v else [] for k, v in cls._dependencies.items()}

        # 构建依赖图
        graph = defaultdict(list)
        in_degree = {node: 0 for node in resource_names}

        for node, deps in deps_copy.items():
            if node not in resource_names:
                continue

            # 过滤无效依赖
            valid_deps = [dep for dep in deps if dep in resource_names and dep != node]
            for dep in valid_deps:
                graph[dep].append(node)
                in_degree[node] += 1

        # Kahn算法
        queue = deque([node for node in resource_names if in_degree[node] == 0])
        order = []

        while queue:
            node = queue.popleft()
            order.append(node)

            for neighbor in graph[node]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 检测循环依赖
        cyclic_nodes = {node for node in resource_names if in_degree[node] > 0}
        return order, cyclic_nodes

    @classmethod
    async def is_ready(cls, name: str) -> bool:
        """检查资源是否已准备就绪"""
        async with cls._lock:
            if name not in cls._ready_events:
                return False
            return cls._ready_events[name].is_set()

    @classmethod
    async def register(
        cls, name: str, resource=None, dependencies=None, initializer=None
    ):
        """注册资源和依赖关系"""
        async with cls._lock:
            if resource is not None:
                cls._resources[name] = resource

            if initializer is not None:
                cls._resources[f"{name}_initializer"] = initializer

            if dependencies:
                cls._dependencies[name] = [dep for dep in dependencies if dep != name]

            if name not in cls._ready_events:
                cls._ready_events[name] = asyncio.Event()

    @classmethod
    def add_to_registry(
        cls, name: str, resource=None, dependencies=None, initializer=None
    ):
        """添加资源到注册清单，将在启动时统一注册"""
        cls._registry.append(
            {
                "name": name,
                "resource": resource,
                "dependencies": dependencies,
                "initializer": initializer,
            }
        )

    @classmethod
    async def register_all_resources(cls):
        """注册所有在清单中的资源"""
        if not cls._registry:
            return

        logger.info(f"注册 {len(cls._registry)} 个资源")
        for item in cls._registry:
            await cls.register(**item)

        cls._registry.clear()

    @classmethod
    async def get(cls, name: str, timeout: float = 10.0) -> Optional[T]:
        """获取资源，如果不可用则等待指定时间"""
        async with cls._lock:
            if name in cls._resources:
                return cls._resources[name]
            event = cls._ready_events.get(name)

        if not event:
            return None

        try:
            await asyncio.wait_for(event.wait(), timeout)
            async with cls._lock:
                return cls._resources.get(name)
        except asyncio.TimeoutError:
            logger.warning(f"等待资源 {name} 超时")
            return None

    @classmethod
    async def set(cls, name: str, resource: Any):
        """设置资源值并标记为就绪"""
        async with cls._lock:
            cls._resources[name] = resource
            if name in cls._ready_events:
                cls._ready_events[name].set()


# 在NoneBot启动时初始化资源
driver = get_driver()


@driver.on_startup
async def initialize_resources():
    await ResourceManager.register_all_resources()
    await ResourceManager.initialize()
