from nonebot import on_message
from nonebot.adapters.onebot.v11 import GroupMessageEvent
from nonebot.plugin import PluginMetadata

from .bot import handle_group_message

__plugin_meta__ = PluginMetadata(
    name="Chat", description="AI聊天插件", usage="自动响应群聊消息"
)

group_chat = on_message(priority=5)


@group_chat.handle()
async def _(event: GroupMessageEvent):
    # 直接调用bot中的处理函数
    await handle_group_message(event)
