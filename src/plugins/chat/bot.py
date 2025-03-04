import asyncio
from typing import List, Dict, Any, Optional
import random
from nonebot.log import logger
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message, MessageSegment
from .lifecycle import ResourceManager
from .ai_client import get_ai_client
from .message_handler import MessageProcessor


class ChatBot:
    """聊天机器人核心逻辑"""

    def __init__(self):
        self.context_manager = None
        self.config = None
        self.group_manager = None

    async def initialize(self):
        """初始化机器人"""
        self.context_manager = await ResourceManager.get("context_manager")
        self.config = await ResourceManager.get("config")
        self.group_manager = await ResourceManager.get("group_manager")

    async def get_group_config(self, group_id: int):
        """获取群组配置"""
        if self.group_manager:
            return await self.group_manager.get_group_config(group_id)
        return None

    async def process_message(
        self, text: str, group_id: int, user_id: int, group_config=None
    ) -> Optional[str]:
        """处理消息，获取AI回复"""
        if not self.config:
            logger.error("配置未就绪")
            return None

        # 检查用户是否被屏蔽 (仍保留作为安全措施)
        if self.group_manager and self.group_manager.is_user_blocked(user_id, group_id):
            logger.debug(f"用户 {user_id} 在群 {group_id} 中被屏蔽")
            return None

        # 检查消息长度
        if not self.config.check_message_length(text):
            return None

        # 获取对话上下文
        context = []
        if self.context_manager:
            context = await self.context_manager.get_context(
                group_id=group_id, user_id=user_id
            )

        # 构建消息
        messages = context + [{"role": "user", "content": text}]

        # 获取AI客户端
        client = await get_ai_client()
        if not client:
            logger.error("AI客户端未就绪")
            return None

        # 调用AI获取回复
        response = await client.get_chat_completion(messages=messages)

        # 保存新的上下文
        if self.context_manager and response:
            await self.context_manager.add_to_context(
                group_id=group_id,
                user_id=user_id,
                message={"role": "user", "content": text},
                response={"role": "assistant", "content": response},
            )

        # 更新对话状态，记录当前话题
        if response:
            MessageProcessor.update_conversation_state(group_id, user_id, response)

        # 为回复添加人类特征
        if response:
            response = MessageProcessor.add_human_touch(response)

        return response

    def should_respond_to_message(
        self, text: str, is_at: bool = False, group_id: int = None, user_id: int = None
    ) -> bool:
        """决定是否应该回复消息"""
        if not self.config:
            return False

        # 检查消息长度
        if not self.config.check_message_length(text):
            return False

        # 使用MessageProcessor中的should_reply函数，这是为了模拟人类行为
        if group_id is not None and user_id is not None:
            return MessageProcessor.should_reply(text, is_at, group_id, user_id)

        # 基本的回复逻辑（备用）
        if is_at:
            return True
        return random.random() < 0.1

    def format_response(
        self,
        text: str,
        user_id: int,
        event: GroupMessageEvent = None,
        context_length: int = 0,
    ) -> Message:
        """
        格式化回复消息
        根据上下文消息数和@情况决定是否使用@回复

        Args:
            text: 回复文本
            user_id: 用户ID
            event: 消息事件
            context_length: 当前上下文消息数
        """
        msg = Message()

        # 决定是否需要@用户
        should_at = False

        # 条件1: 上下文消息超过10条时使用@回复
        if context_length > 10:
            should_at = True

        # 条件2: @了机器人，但上下文超过3条时才使用@回复
        if event and any(
            seg.type == "at" and str(seg.data.get("qq", "")) == str(self.config.bot.qq)
            for seg in event.message
        ):
            should_at = context_length > 3

        # 根据决策添加@或直接回复
        if should_at:
            msg.append(MessageSegment.at(user_id))
            msg.append(" ")  # 添加空格，更自然

        msg.append(text.strip())
        return msg


# 初始化机器人实例
_bot_instance = None


async def initialize_bot():
    """初始化聊天机器人"""
    global _bot_instance
    _bot_instance = ChatBot()
    await _bot_instance.initialize()
    ResourceManager.set("chat_bot", _bot_instance)


# 注册机器人
ResourceManager.register(
    name="chat_bot",
    dependencies=["config", "context_manager", "ai_client", "group_manager"],
    initializer=initialize_bot,
)


async def get_bot() -> Optional[ChatBot]:
    """获取聊天机器人实例"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = await ResourceManager.get("chat_bot")
    return _bot_instance


async def handle_group_message(event: GroupMessageEvent):
    """群组消息主处理函数"""
    bot = await get_bot()
    if not bot:
        logger.error("机器人实例未就绪")
        return

    try:
        # 获取文本和@状态
        text = MessageProcessor.extract_text(event)
        is_at = MessageProcessor.is_at_bot(event, bot.config.bot.qq)

        # 检查响应条件
        if not bot.should_respond_to_message(
            text, is_at, event.group_id, event.user_id
        ):
            return

        # 获取群组配置（如果存在）
        group_config = await bot.get_group_config(event.group_id)

        # 获取当前上下文消息数
        context_length = 0
        if bot.context_manager:
            context = await bot.context_manager.get_context(
                group_id=event.group_id, user_id=event.user_id
            )
            context_length = len(context)

        # 处理消息获取回复
        response_text = await bot.process_message(
            text=text,
            group_id=event.group_id,
            user_id=event.user_id,
            group_config=group_config,
        )

        # 如果有回复，模拟人类打字时间后发送
        if response_text:
            # 计算并等待模拟打字延迟
            typing_delay = MessageProcessor.calculate_typing_delay(response_text)
            await asyncio.sleep(typing_delay)

            # 发送回复（传入原始事件和上下文长度）
            response_msg = bot.format_response(
                response_text, event.user_id, event, context_length
            )
            await event.reply(response_msg)

            # 偶尔模拟发送后纠正错别字
            if MessageProcessor.should_correct_typo():
                await asyncio.sleep(random.uniform(1.0, 3.0))
                correction_msg = MessageProcessor.make_correction(response_msg)
                await event.reply(correction_msg)

    except Exception as e:
        logger.exception(f"处理群组消息出错: {str(e)}")
