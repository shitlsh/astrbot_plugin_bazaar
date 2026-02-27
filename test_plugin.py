import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from astrbot.api.event import AstrMessageEvent
from astrbot.api.star import Context
from astrbot_plugin_bazaar.main import BazaarPlugin


async def test_command(plugin, cmd_func, message_str, label):
    event = AstrMessageEvent(message_str=message_str)
    results = []
    async for result in cmd_func(event):
        results.append(result)
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print(f"{'='*60}")
    for r in results:
        print(r)
    return results


async def main():
    print("🎮 Bazaar 插件测试")
    print("=" * 60)

    ctx = Context()
    plugin = BazaarPlugin(ctx)
    await plugin.initialize()

    await test_command(plugin, plugin.cmd_help, "", "/bzhelp")

    await test_command(plugin, plugin.cmd_list, "", "/bzlist")

    await test_command(plugin, plugin.cmd_monster, "火灵", "/bzmonster 火灵")

    await test_command(plugin, plugin.cmd_monster, "pyro", "/bzmonster pyro")

    await test_command(plugin, plugin.cmd_monster, "blizzard", "/bzmonster blizzard")

    await test_command(plugin, plugin.cmd_item, "短剑", "/bzitem 短剑")

    await test_command(plugin, plugin.cmd_item, "Fire Staff", "/bzitem Fire Staff")

    await test_command(plugin, plugin.cmd_item, "余烬", "/bzitem 余烬 (monster item)")

    await test_command(plugin, plugin.cmd_search, "灼烧", "/bzsearch 灼烧")

    await test_command(plugin, plugin.cmd_search, "poison", "/bzsearch poison")

    await test_command(plugin, plugin.cmd_items_by_tag, "", "/bzitems (no tag)")

    await test_command(plugin, plugin.cmd_items_by_tag, "Weapon", "/bzitems Weapon")

    await test_command(plugin, plugin.cmd_items_by_tier, "Gold", "/bztier Gold")

    await test_command(plugin, plugin.cmd_items_by_tier, "", "/bztier (no tier)")

    await test_command(plugin, plugin.cmd_monster, "不存在", "/bzmonster 不存在")

    await test_command(plugin, plugin.cmd_item, "", "/bzitem (empty)")

    await test_command(plugin, plugin.cmd_monster, "灵", "/bzmonster 灵 (partial)")

    await plugin.terminate()
    print("\n" + "=" * 60)
    print("✅ 所有测试完成")


if __name__ == "__main__":
    asyncio.run(main())
