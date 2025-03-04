from typing import Dict, List, Any
import time
import asyncio
from collections import defaultdict
from nonebot.log import logger
from .lifecycle import ResourceManager


class ContextManager:
    """对话上下文管理器"""

    def __init__(self, max_context_size=10, expiration_time=1800):
        self._group_contexts = defaultdict(lambda: defaultdict(list))
        self._timestamps = defaultdict(lambda: defaultdict(float))
        self.max_context_size = max_context_size
        self.expiration_time = expiration_time  # 秒

    async def get_context(self, group_id: int, user_id: int) -> List[Dict[str, str]]:
        """获取特定用户的对话上下文"""
        if self._is_context_expired(group_id, user_id):
            self._clear_context(group_id, user_id)
            return []

        self._update_timestamp(group_id, user_id)
        return self._group_contexts[group_id][user_id]

    async def add_to_context(
        self,
        group_id: int,
        user_id: int,
        message: Dict[str, str],
        response: Dict[str, str],
    ):
        """添加新对话到上下文"""
        context_list = self._group_contexts[group_id][user_id]

        # 添加消息对
        context_list.append(message)
        context_list.append(response)

        # 保持上下文长度限制
        while len(context_list) > self.max_context_size * 2:
            context_list.pop(0)
            if context_list:
                context_list.pop(0)

        self._update_timestamp(group_id, user_id)

    def _update_timestamp(self, group_id: int, user_id: int):
        """更新特定用户的时间戳"""
        self._timestamps[group_id][user_id] = time.time()

    def _is_context_expired(self, group_id: int, user_id: int) -> bool:
        """检查特定用户的上下文是否过期"""
        last_time = self._timestamps[group_id][user_id]
        return (time.time() - last_time) > self.expiration_time

    def _clear_context(self, group_id: int, user_id: int):
        """清除特定用户的上下文"""
        if (
            group_id in self._group_contexts
            and user_id in self._group_contexts[group_id]
        ):
            self._group_contexts[group_id][user_id] = []

    async def clear_expired_contexts(self):
        """清理过期上下文"""
        count = 0
        for group_id in list(self._timestamps.keys()):
            for user_id in list(self._timestamps[group_id].keys()):
                if self._is_context_expired(group_id, user_id):
                    self._clear_context(group_id, user_id)
                    count += 1
        if count > 0:
            logger.debug(f"已清理 {count} 个过期上下文")


async def initialize_context_manager():
    """初始化上下文管理器"""
    config = await ResourceManager.get("config")
    max_size = getattr(config.message, "max_context_size", 10) if config else 10

    context_manager = ContextManager(max_context_size=max_size)
    ResourceManager.set("context_manager", context_manager)

    # 启动定期清理任务
    asyncio.create_task(periodic_cleanup(context_manager))


async def periodic_cleanup(context_manager: ContextManager):
    """定期清理过期上下文"""
    while True:
        await asyncio.sleep(300)  # 5分钟
        await context_manager.clear_expired_contexts()


# 注册上下文管理器 - 改为使用注册清单
ResourceManager.add_to_registry(
    name="context_manager",
    dependencies=["config"],
    initializer=initialize_context_manager,
)
