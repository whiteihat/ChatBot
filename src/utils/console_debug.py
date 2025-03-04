from nonebot.log import logger
from nonebot import get_driver


class ConsoleDebugger:
    def __init__(self):
        self.session_cache = {}

    async def debug_flow(self):
        logger.success("进入控制台调试模式")
        while True:
            cmd = input("[DEBUG] > ")

            # 执行插件热重载
            if cmd == "reload":
                await self._reload_plugins()

            # 查看会话状态
            elif cmd == "sessions":
                print(self.session_cache)

            # 退出调试
            elif cmd == "exit":
                break

    async def _reload_plugins(self):
        from nonebot.plugin import reload_plugins

        reload_plugins()
        logger.warning("已强制重载所有插件")


# 在bot启动时挂载
driver = get_driver()
driver.on_startup(ConsoleDebugger().debug_flow)
