import json
import os
from pathlib import Path

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


TIER_ORDER = {"Bronze": 1, "Silver": 2, "Gold": 3, "Diamond": 4}
TIER_EMOJI = {"Bronze": "🥉", "Silver": "🥈", "Gold": "🥇", "Diamond": "💎"}


@register("astrbot_plugin_bazaar", "BazaarHelper", "The Bazaar 游戏数据查询插件，支持怪物、物品、技能搜索", "1.0.0")
class BazaarPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.monsters = {}
        self.items = []
        self.plugin_dir = Path(os.path.dirname(os.path.abspath(__file__)))

    async def initialize(self):
        self._load_data()
        logger.info(f"Bazaar 插件加载完成: {len(self.monsters)} 个怪物, {len(self.items)} 个物品")

    def _load_data(self):
        monsters_path = self.plugin_dir / "data" / "monsters.json"
        items_path = self.plugin_dir / "data" / "items.json"

        try:
            if monsters_path.exists():
                with open(monsters_path, "r", encoding="utf-8") as f:
                    self.monsters = json.load(f)
            else:
                logger.warning(f"怪物数据文件不存在: {monsters_path}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载怪物数据失败: {e}")
            self.monsters = {}

        try:
            if items_path.exists():
                with open(items_path, "r", encoding="utf-8") as f:
                    self.items = json.load(f)
            else:
                logger.warning(f"物品数据文件不存在: {items_path}")
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"加载物品数据失败: {e}")
            self.items = []

    def _format_monster_info(self, key: str, monster: dict) -> str:
        name_zh = monster.get("name_zh", key)
        name_en = monster.get("name", "")

        lines = [f"🐉 【{name_zh}】({name_en})", ""]

        skills = monster.get("skills", [])
        if skills:
            lines.append("⚔️ 技能:")
            for s in skills:
                tier_emoji = TIER_EMOJI.get(s.get("tier", ""), "")
                lines.append(f"  {tier_emoji} {s['name']}({s.get('name_en', '')})")
                lines.append(f"    {s.get('description', '')}")
            lines.append("")

        items = monster.get("items", [])
        if items:
            lines.append("🎒 专属物品:")
            seen = set()
            for item in items:
                item_key = item.get("id", item["name"])
                if item_key in seen:
                    continue
                seen.add(item_key)
                tier_emoji = TIER_EMOJI.get(item.get("tier", ""), "")
                lines.append(f"  {tier_emoji} {item['name']}({item.get('name_en', '')})")
                lines.append(f"    {item.get('description', '')}")

        return "\n".join(lines)

    def _format_item_info(self, item: dict) -> str:
        name_cn = item.get("name_cn", "")
        name_en = item.get("name_en", "")
        tier = item.get("tier", "")
        tier_emoji = TIER_EMOJI.get(tier, "")

        lines = [f"📦 【{name_cn}】({name_en}) {tier_emoji}{tier}", ""]

        desc = item.get("description", "")
        if desc:
            lines.append(f"📝 {desc}")
            lines.append("")

        details = []
        if item.get("heroes"):
            details.append(f"英雄: {item['heroes']}")
        if item.get("tags"):
            details.append(f"标签: {item['tags']}")
        if item.get("size"):
            details.append(f"尺寸: {item['size']}")
        if "cooldown" in item:
            cd = item["cooldown"]
            details.append(f"冷却: {'被动/无冷却' if cd == 0 else f'{cd}秒'}")
        if item.get("available_tiers"):
            details.append(f"可用品质: {item['available_tiers']}")

        if details:
            lines.append("📊 属性:")
            for d in details:
                lines.append(f"  {d}")
            lines.append("")

        stats = []
        stat_fields = [
            ("damage_tiers", "伤害"),
            ("heal_tiers", "治疗"),
            ("shield_tiers", "护盾"),
            ("burn_tiers", "灼烧"),
            ("poison_tiers", "中毒"),
            ("regen_tiers", "再生"),
            ("lifesteal_tiers", "吸血"),
            ("ammo_tiers", "弹药"),
            ("crit_tiers", "暴击"),
            ("multicast_tiers", "多重施放"),
        ]
        for field, label in stat_fields:
            if item.get(field):
                stats.append(f"  {label}: {item[field]}")

        if stats:
            lines.append("📈 品质成长:")
            lines.extend(stats)

        return "\n".join(lines)

    def _search_monsters(self, keyword: str) -> list:
        results = []
        kw = keyword.lower()
        for key, monster in self.monsters.items():
            if (kw in key.lower() or
                kw in monster.get("name", "").lower() or
                kw in monster.get("name_zh", "").lower()):
                results.append((key, monster))
                continue
            for skill in monster.get("skills", []):
                if (kw in skill.get("name", "").lower() or
                    kw in skill.get("name_en", "").lower() or
                    kw in skill.get("description", "").lower()):
                    results.append((key, monster))
                    break
            else:
                for item in monster.get("items", []):
                    if (kw in item.get("name", "").lower() or
                        kw in item.get("name_en", "").lower() or
                        kw in item.get("description", "").lower()):
                        results.append((key, monster))
                        break
        return results

    def _search_items(self, keyword: str) -> list:
        results = []
        kw = keyword.lower()
        for item in self.items:
            if (kw in item.get("name_cn", "").lower() or
                kw in item.get("name_en", "").lower() or
                kw in item.get("tags", "").lower() or
                kw in item.get("heroes", "").lower() or
                kw in item.get("description", "").lower()):
                results.append(item)
        return results

    @filter.command("bzhelp")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看 Bazaar 插件帮助信息"""
        help_text = (
            "🎮 The Bazaar 数据查询助手\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📋 可用指令:\n\n"
            "/bzmonster <名称> - 查询怪物信息\n"
            "  示例: /bzmonster 火灵\n"
            "  示例: /bzmonster pyro\n\n"
            "/bzitem <名称> - 查询物品信息\n"
            "  示例: /bzitem 短剑\n"
            "  示例: /bzitem sword\n\n"
            "/bzsearch <关键词> - 搜索怪物和物品\n"
            "  示例: /bzsearch 灼烧\n"
            "  示例: /bzsearch poison\n\n"
            "/bzlist - 列出所有怪物\n\n"
            "/bzitems [标签] - 按标签筛选物品\n"
            "  示例: /bzitems Weapon\n"
            "  示例: /bzitems Poison\n\n"
            "/bztier <品质> - 按品质筛选物品\n"
            "  示例: /bztier Gold\n\n"
            "/bzhelp - 显示此帮助信息\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "数据来源: BazaarHelper"
        )
        yield event.plain_result(help_text)

    @filter.command("bzmonster")
    async def cmd_monster(self, event: AstrMessageEvent):
        """查询怪物详细信息"""
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请输入怪物名称，例如: /bzmonster 火灵")
            return

        kw = query.lower()
        found_key = None
        found_monster = None

        for key, monster in self.monsters.items():
            if (key == query or
                monster.get("name", "").lower() == kw or
                monster.get("name_zh", "").lower() == kw):
                found_key = key
                found_monster = monster
                break

        if not found_monster:
            results = self._search_monsters(query)
            if len(results) == 1:
                found_key, found_monster = results[0]
            elif len(results) > 1:
                names = [f"  {m.get('name_zh', k)}({m.get('name', '')})" for k, m in results[:10]]
                yield event.plain_result(
                    f"找到多个匹配结果，请精确输入:\n" + "\n".join(names)
                )
                return
            else:
                yield event.plain_result(f"未找到怪物「{query}」，请使用 /bzlist 查看所有怪物。")
                return

        yield event.plain_result(self._format_monster_info(found_key, found_monster))

    @filter.command("bzitem")
    async def cmd_item(self, event: AstrMessageEvent):
        """查询物品详细信息"""
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请输入物品名称，例如: /bzitem 短剑")
            return

        kw = query.lower()
        found = None

        for item in self.items:
            if (item.get("name_cn", "").lower() == kw or
                item.get("name_en", "").lower() == kw):
                found = item
                break

        if not found:
            results = self._search_items(query)
            if len(results) == 1:
                found = results[0]
            elif len(results) > 1:
                names = [f"  {it.get('name_cn', '')}({it.get('name_en', '')})" for it in results[:10]]
                yield event.plain_result(
                    f"找到多个匹配结果，请精确输入:\n" + "\n".join(names)
                )
                return

        if not found:
            for key, monster in self.monsters.items():
                for mitem in monster.get("items", []):
                    if (mitem.get("name", "").lower() == kw or
                        mitem.get("name_en", "").lower() == kw):
                        tier_emoji = TIER_EMOJI.get(mitem.get("tier", ""), "")
                        result = (
                            f"📦 【{mitem['name']}】({mitem.get('name_en', '')}) {tier_emoji}{mitem.get('tier', '')}\n\n"
                            f"📝 {mitem.get('description', '')}\n\n"
                            f"🐉 所属怪物: {monster.get('name_zh', key)}({monster.get('name', '')})"
                        )
                        yield event.plain_result(result)
                        return

        if not found:
            yield event.plain_result(f"未找到物品「{query}」，请使用 /bzsearch 搜索。")
            return

        yield event.plain_result(self._format_item_info(found))

    @filter.command("bzsearch")
    async def cmd_search(self, event: AstrMessageEvent):
        """搜索怪物和物品"""
        query = event.message_str.strip()
        if not query:
            yield event.plain_result("请输入搜索关键词，例如: /bzsearch 灼烧")
            return

        monster_results = self._search_monsters(query)
        item_results = self._search_items(query)

        if not monster_results and not item_results:
            yield event.plain_result(f"未找到与「{query}」相关的结果。")
            return

        lines = [f"🔍 搜索「{query}」的结果:", ""]

        if monster_results:
            lines.append(f"🐉 怪物 ({len(monster_results)}个):")
            for key, m in monster_results[:5]:
                lines.append(f"  • {m.get('name_zh', key)}({m.get('name', '')})")
            if len(monster_results) > 5:
                lines.append(f"  ... 还有{len(monster_results) - 5}个结果")
            lines.append("")

        if item_results:
            lines.append(f"📦 物品 ({len(item_results)}个):")
            for it in item_results[:8]:
                tier_emoji = TIER_EMOJI.get(it.get("tier", ""), "")
                lines.append(f"  • {tier_emoji} {it.get('name_cn', '')}({it.get('name_en', '')})")
            if len(item_results) > 8:
                lines.append(f"  ... 还有{len(item_results) - 8}个结果")

        lines.append("")
        lines.append("💡 使用 /bzmonster 或 /bzitem 查看详情")

        yield event.plain_result("\n".join(lines))

    @filter.command("bzlist")
    async def cmd_list(self, event: AstrMessageEvent):
        """列出所有怪物"""
        if not self.monsters:
            yield event.plain_result("暂无怪物数据。")
            return

        lines = ["🐉 所有怪物列表:", "━━━━━━━━━━━━━━━━━━"]
        for key, monster in self.monsters.items():
            name_zh = monster.get("name_zh", key)
            name_en = monster.get("name", "")
            skill_count = len(monster.get("skills", []))
            item_count = len(set(it.get("id", it["name"]) for it in monster.get("items", [])))
            lines.append(f"  • {name_zh}({name_en}) - {skill_count}技能/{item_count}物品")

        lines.append(f"\n共 {len(self.monsters)} 个怪物")
        lines.append("💡 使用 /bzmonster <名称> 查看详情")

        yield event.plain_result("\n".join(lines))

    @filter.command("bzitems")
    async def cmd_items_by_tag(self, event: AstrMessageEvent):
        """按标签筛选物品"""
        tag = event.message_str.strip()

        if not tag:
            all_tags = set()
            for item in self.items:
                for t in item.get("tags", "").split(","):
                    t = t.strip()
                    if t:
                        all_tags.add(t)
            sorted_tags = sorted(all_tags)
            yield event.plain_result(
                "🏷️ 可用标签:\n" +
                ", ".join(sorted_tags) +
                "\n\n💡 使用 /bzitems <标签> 筛选物品"
            )
            return

        results = []
        kw = tag.lower()
        for item in self.items:
            tags = item.get("tags", "").lower()
            if kw in tags:
                results.append(item)

        if not results:
            yield event.plain_result(f"未找到标签包含「{tag}」的物品。使用 /bzitems 查看所有标签。")
            return

        lines = [f"🏷️ 标签「{tag}」的物品 ({len(results)}个):", ""]
        for it in results[:15]:
            tier_emoji = TIER_EMOJI.get(it.get("tier", ""), "")
            lines.append(f"  {tier_emoji} {it.get('name_cn', '')}({it.get('name_en', '')}) - {it.get('tier', '')}")
        if len(results) > 15:
            lines.append(f"  ... 还有{len(results) - 15}个结果")
        lines.append("\n💡 使用 /bzitem <名称> 查看详情")

        yield event.plain_result("\n".join(lines))

    @filter.command("bztier")
    async def cmd_items_by_tier(self, event: AstrMessageEvent):
        """按品质筛选物品"""
        tier = event.message_str.strip()

        if not tier:
            yield event.plain_result(
                "📊 可用品质等级:\n"
                "  🥉 Bronze (铜)\n"
                "  🥈 Silver (银)\n"
                "  🥇 Gold (金)\n"
                "  💎 Diamond (钻石)\n\n"
                "💡 使用 /bztier <品质> 筛选物品"
            )
            return

        tier_lower = tier.lower()
        tier_map = {"bronze": "Bronze", "silver": "Silver", "gold": "Gold", "diamond": "Diamond",
                     "铜": "Bronze", "银": "Silver", "金": "Gold", "钻石": "Diamond"}
        normalized = tier_map.get(tier_lower, tier.capitalize())

        results = [it for it in self.items if it.get("tier", "") == normalized]

        if not results:
            yield event.plain_result(f"未找到品质为「{normalized}」的物品。")
            return

        tier_emoji = TIER_EMOJI.get(normalized, "")
        lines = [f"{tier_emoji} {normalized} 品质物品 ({len(results)}个):", ""]
        for it in results[:15]:
            lines.append(f"  • {it.get('name_cn', '')}({it.get('name_en', '')}) - {it.get('heroes', 'Common')}")
        if len(results) > 15:
            lines.append(f"  ... 还有{len(results) - 15}个结果")
        lines.append("\n💡 使用 /bzitem <名称> 查看详情")

        yield event.plain_result("\n".join(lines))

    async def terminate(self):
        logger.info("Bazaar 插件已卸载")
