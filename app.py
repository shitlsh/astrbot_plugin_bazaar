import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot_plugin_bazaar.main import BazaarPlugin


COMMANDS = {
    "/bzhelp": "cmd_help",
    "/bzmonster": "cmd_monster",
    "/bzitem": "cmd_item",
    "/bzskill": "cmd_skill",
    "/bzsearch": "cmd_search",
    "/bzlist": "cmd_list",
    "/bzitems": "cmd_items_by_tag",
    "/bztier": "cmd_items_by_tier",
    "/bzhero": "cmd_hero",
}


async def handle_input(plugin, user_input):
    user_input = user_input.strip()
    if not user_input:
        return

    parts = user_input.split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    if cmd not in COMMANDS:
        print("❌ 未知指令。输入 /bzhelp 查看帮助。")
        return

    method_name = COMMANDS[cmd]
    method = getattr(plugin, method_name)
    event = AstrMessageEvent(message_str=args)

    async for result in method(event):
        print(result)


async def main():
    ctx = Context()
    plugin = BazaarPlugin(ctx)
    await plugin.initialize()

    print("🎮 The Bazaar 数据查询助手 - 交互模式")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print("输入 /bzhelp 查看所有可用指令")
    print("输入 quit 或 exit 退出")
    print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()

    while True:
        try:
            user_input = input(">>> ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.strip().lower() in ("quit", "exit", "q"):
            break

        await handle_input(plugin, user_input)
        print()

    await plugin.terminate()
    print("👋 再见！")


if __name__ == "__main__":
    asyncio.run(main())
