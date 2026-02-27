import json
import os
import re
import html as html_module
from pathlib import Path

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
import astrbot.api.message_components as Comp

BUILDS_API = "https://bazaar-builds.net/wp-json/wp/v2"
DEFAULT_BUILD_COUNT = 3

TIER_EMOJI = {"Bronze": "🥉", "Silver": "🥈", "Gold": "🥇", "Diamond": "💎"}


def _clean_tier(raw: str) -> str:
    if not raw:
        return ""
    return raw.split("/")[0].strip().split(" ")[0].strip()


def _clean_bilingual(raw: str) -> tuple:
    if not raw:
        return ("", "")
    parts = raw.split("/", 1)
    en = parts[0].strip()
    cn = parts[1].strip() if len(parts) > 1 else ""
    return (en, cn)


def _get_skill_text(skill_entry) -> str:
    if isinstance(skill_entry, dict):
        return skill_entry.get("cn", "") or skill_entry.get("en", "")
    return str(skill_entry)


def _strip_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


def _resolve_search(results, query, name_func, not_found_msg):
    if not results:
        return None, not_found_msg
    if len(results) == 1:
        return results[0], None
    exact = [r for r in results if query in name_func(r)]
    if len(exact) == 1:
        return exact[0], None
    display = exact[:15] if exact else results[:15]
    total = len(exact) if exact else len(results)
    names = [f"  {name_func(r)}" for r in display]
    return None, f"找到{total}个匹配结果，请精确输入:\n" + "\n".join(names)


def _extract_query(message_str: str, command_name: str) -> str:
    text = message_str.strip()
    for prefix in [f"/{command_name}", command_name]:
        if text.lower().startswith(prefix.lower()):
            return text[len(prefix):].strip()
    return text


GITHUB_RAW = "https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources"
DATA_FILES = {
    "items_db.json": f"{GITHUB_RAW}/items_db.json",
    "monsters_db.json": f"{GITHUB_RAW}/monsters_db.json",
    "skills_db.json": f"{GITHUB_RAW}/skills_db.json",
}

TIER_MAP = {
    "bronze": "Bronze", "silver": "Silver", "gold": "Gold", "diamond": "Diamond",
    "铜": "Bronze", "青铜": "Bronze", "银": "Silver", "白银": "Silver",
    "金": "Gold", "黄金": "Gold", "钻石": "Diamond", "钻": "Diamond",
}


@register("astrbot_plugin_bazaar", "大巴扎小助手", "The Bazaar 游戏数据查询，支持怪物、物品、技能、阵容查询，图片卡片展示", "v1.0.2")
class BazaarPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.monsters = {}
        self.items = []
        self.skills = []
        self.plugin_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        self.renderer = None
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self._session

    async def initialize(self):
        self._load_data()
        self._build_vocab()
        try:
            try:
                from .card_renderer import CardRenderer
            except ImportError:
                from card_renderer import CardRenderer
            session = await self._get_session()
            self.renderer = CardRenderer(self.plugin_dir, session)
            logger.info("图片卡片渲染器已加载")
        except Exception as e:
            logger.warning(f"图片渲染器加载失败，将使用纯文本模式: {e}")
            self.renderer = None
        logger.info(
            f"Bazaar 插件加载完成: {len(self.monsters)} 个怪物, "
            f"{len(self.items)} 个物品, {len(self.skills)} 个技能"
        )

    def _build_vocab(self):
        vocab = {}
        for item in self.items:
            h = item.get("heroes", "")
            for p in h.split("/"):
                p = p.strip()
                if " | " in p:
                    p = p.split(" | ")[0].strip()
                if p and len(p) >= 2:
                    vocab[p.lower()] = ("hero", p)
            s = item.get("size", "")
            for p in s.split("/"):
                p = p.strip()
                if p and len(p) >= 2:
                    vocab[p.lower()] = ("size", p)
            for field in ("tags", "hidden_tags"):
                tv = item.get(field, "")
                for t in tv.split("|"):
                    for p in t.strip().split("/"):
                        p = p.strip()
                        if p and len(p) >= 2:
                            vocab[p.lower()] = ("tag", p)
        hero_aliases = {"中立": "Common", "通用": "Common", "common": "Common"}
        for alias, canonical in hero_aliases.items():
            vocab[alias] = ("hero", canonical)
        for k, v in TIER_MAP.items():
            if len(k) >= 2:
                vocab[k] = ("tier", v)
        tier_cn_to_en = {"青铜": "Bronze", "白银": "Silver", "黄金": "Gold", "钻石": "Diamond", "传奇": "Legendary"}
        for cn, en in tier_cn_to_en.items():
            vocab[cn] = ("tier", en)
            vocab[en.lower()] = ("tier", en)
        self._vocab = vocab
        self._vocab_sorted = sorted(vocab.keys(), key=len, reverse=True)

    def _smart_tokenize(self, query: str) -> list:
        tokens = query.split()
        result = []
        for token in tokens:
            if ":" in token:
                result.append(token)
                continue
            has_cjk = any('\u4e00' <= c <= '\u9fff' for c in token)
            if has_cjk and len(token) >= 4:
                remaining = token.lower()
                extracted = []
                while remaining:
                    matched = False
                    for term in self._vocab_sorted:
                        if remaining.startswith(term):
                            extracted.append(term)
                            remaining = remaining[len(term):]
                            matched = True
                            break
                    if not matched:
                        for term in self._vocab_sorted:
                            idx = remaining.find(term)
                            if idx > 0:
                                extracted.append(remaining[:idx])
                                extracted.append(term)
                                remaining = remaining[idx + len(term):]
                                matched = True
                                break
                    if not matched:
                        extracted.append(remaining)
                        break
                result.extend(extracted)
            else:
                result.append(token)
        return result

    def _load_data(self):
        data_dir = self.plugin_dir / "data"

        for name, attr, default in [
            ("monsters_db.json", "monsters", {}),
            ("items_db.json", "items", []),
            ("skills_db.json", "skills", []),
        ]:
            path = data_dir / name
            try:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        setattr(self, attr, json.load(f))
                else:
                    logger.warning(f"数据文件不存在: {path}")
                    setattr(self, attr, default)
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载数据失败 ({name}): {e}")
                setattr(self, attr, default)

    def _format_monster_info(self, key: str, monster: dict) -> str:
        name_zh = monster.get("name_zh", key)
        name_en = monster.get("name", "")

        lines = [f"🐉 【{name_zh}】({name_en})", ""]

        if monster.get("available"):
            lines.append(f"📅 出现时间: {monster['available']}")
        if monster.get("health"):
            lines.append(f"❤️ 生命值: {monster['health']}")
        if monster.get("level"):
            lines.append(f"⭐ 等级: {monster['level']}")
        if monster.get("combat"):
            combat = monster["combat"]
            combat_info = []
            if combat.get("gold"):
                combat_info.append(f"💰{combat['gold']}")
            if combat.get("exp"):
                combat_info.append(f"📊{combat['exp']}")
            if combat_info:
                lines.append(f"🎁 奖励: {' | '.join(combat_info)}")
        if monster.get("tags"):
            tags = monster["tags"]
            if isinstance(tags, list):
                lines.append(f"🏷️ 标签: {', '.join(tags)}")
        lines.append("")

        skills = monster.get("skills", [])
        if skills:
            lines.append("⚔️ 技能:")
            for s in skills[:8]:
                name = s.get("name", s.get("name_en", ""))
                name_en = s.get("name_en", "")
                tier_str = s.get("tier", s.get("current_tier", ""))
                tier_clean = _clean_tier(tier_str)
                tier_emoji = TIER_EMOJI.get(tier_clean, "")
                display_name = name
                if name_en and name_en != name:
                    display_name = f"{name}({name_en})"
                lines.append(f"  {tier_emoji} {display_name} [{tier_str}]")
                tiers = s.get("tiers", {})
                if tiers:
                    current = s.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        for desc_line in tier_data["description"][:2]:
                            lines.append(f"    {desc_line}")
            if len(skills) > 8:
                lines.append(f"  ... 还有{len(skills) - 8}个技能")
            lines.append("")

        items = monster.get("items", [])
        if items:
            lines.append("🎒 物品:")
            seen = set()
            count = 0
            for item in items:
                item_id = item.get("id", item.get("name", ""))
                if item_id in seen:
                    continue
                seen.add(item_id)
                count += 1
                if count > 8:
                    lines.append(f"  ... 还有{len(set(it.get('id', it.get('name','')) for it in items)) - 8}个物品")
                    break
                name = item.get("name", "")
                name_en = item.get("name_en", "")
                tier_str = item.get("tier", item.get("current_tier", ""))
                tier_clean = _clean_tier(tier_str)
                tier_emoji = TIER_EMOJI.get(tier_clean, "")
                display_name = name
                if name_en and name_en != name:
                    display_name = f"{name}({name_en})"
                lines.append(f"  {tier_emoji} {display_name} [{tier_str}]")
                tiers = item.get("tiers", {})
                if tiers:
                    current = item.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        lines.append(f"    {tier_data['description'][0]}")

        return "\n".join(lines)

    def _format_item_info(self, item: dict) -> str:
        name_cn = item.get("name_cn", "")
        name_en = item.get("name_en", "")
        tier_raw = item.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)
        tier_emoji = TIER_EMOJI.get(tier_clean, "")

        lines = [f"📦 【{name_cn}】({name_en}) {tier_emoji}{tier_raw}", ""]

        active_skills = item.get("skills", [])
        if active_skills:
            lines.append("⚔️ 主动技能:")
            for sk in active_skills[:5]:
                lines.append(f"  {_get_skill_text(sk)}")
            lines.append("")

        passive_skills = item.get("skills_passive", [])
        if passive_skills:
            lines.append("🛡️ 被动技能:")
            for sk in passive_skills[:5]:
                lines.append(f"  {_get_skill_text(sk)}")
            lines.append("")

        details = []
        hero_en, hero_cn = _clean_bilingual(item.get("heroes", ""))
        if hero_cn:
            details.append(f"英雄: {hero_cn}({hero_en})")
        elif hero_en:
            details.append(f"英雄: {hero_en}")

        if item.get("tags"):
            details.append(f"标签: {item['tags']}")
        if item.get("hidden_tags"):
            details.append(f"隐藏标签: {item['hidden_tags']}")

        size_en, size_cn = _clean_bilingual(item.get("size", ""))
        if size_cn:
            details.append(f"尺寸: {size_cn}({size_en})")
        elif size_en:
            details.append(f"尺寸: {size_en}")

        cd = item.get("cooldown")
        if cd is not None:
            details.append(f"冷却: {'被动/无冷却' if cd == 0 else f'{cd}秒'}")
        if item.get("available_tiers"):
            details.append(f"可用品质: {item['available_tiers']}")
        if item.get("buy_price"):
            details.append(f"购买价格: {item['buy_price']}")
        if item.get("sell_price"):
            details.append(f"出售价格: {item['sell_price']}")

        if details:
            lines.append("📊 属性:")
            for d in details:
                lines.append(f"  {d}")
            lines.append("")

        stat_fields = [
            ("damage", "damage_tiers", "伤害"),
            ("heal", "heal_tiers", "治疗"),
            ("shield", "shield_tiers", "护盾"),
            ("burn", "burn_tiers", "灼烧"),
            ("poison", "poison_tiers", "中毒"),
            ("regen", "regen_tiers", "再生"),
            ("lifesteal", "lifesteal_tiers", "吸血"),
            ("ammo", "ammo_tiers", "弹药"),
            ("crit", "crit_tiers", "暴击"),
            ("multicast", "multicast_tiers", "多重触发"),
        ]
        stats = []
        for val_key, tier_key, label in stat_fields:
            val = item.get(val_key)
            tiers_str = item.get(tier_key, "")
            if val and val != 0:
                if tiers_str:
                    stats.append(f"  {label}: {val} (成长: {tiers_str})")
                else:
                    stats.append(f"  {label}: {val}")

        if stats:
            lines.append("📈 数值:")
            lines.extend(stats)
            lines.append("")

        enchantments = item.get("enchantments", {})
        if enchantments and isinstance(enchantments, dict):
            lines.append(f"✨ 附魔 ({len(enchantments)}种):")
            for ench_key, ench_data in enchantments.items():
                if isinstance(ench_data, dict):
                    ench_cn = ench_data.get("name_cn", ench_key)
                    effect = ench_data.get("effect_cn", ench_data.get("effect_en", ""))
                    lines.append(f"  • {ench_cn}({ench_key}): {effect}")
            lines.append("")

        quests = item.get("quests") or []
        if quests and not isinstance(quests, list):
            quests = [quests]
        if quests:
            lines.append(f"📜 任务 ({len(quests)}个):")
            for qi, q in enumerate(quests, 1):
                target = q.get("cn_target") or q.get("en_target", "")
                reward = q.get("cn_reward") or q.get("en_reward", "")
                if target:
                    lines.append(f"  → {target}")
                if reward:
                    lines.append(f"  ✨ {reward}")

        return "\n".join(lines)

    def _format_skill_info(self, skill: dict) -> str:
        name_cn = skill.get("name_cn", "")
        name_en = skill.get("name_en", "")
        tier_raw = skill.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)
        tier_emoji = TIER_EMOJI.get(tier_clean, "")

        lines = [f"🎯 【{name_cn}】({name_en}) {tier_emoji}{tier_raw}", ""]

        desc_cn = skill.get("description_cn", "")
        desc_en = skill.get("description_en", "")
        if desc_cn:
            lines.append(f"📝 {desc_cn}")
        if desc_en:
            lines.append(f"📝 {desc_en}")
        lines.append("")

        hero_en, hero_cn = _clean_bilingual(skill.get("heroes", ""))
        if hero_cn:
            lines.append(f"🦸 英雄: {hero_cn}({hero_en})")
        elif hero_en:
            lines.append(f"🦸 英雄: {hero_en}")

        if skill.get("available_tiers"):
            lines.append(f"📊 可用品质: {skill['available_tiers']}")

        size_en, size_cn = _clean_bilingual(skill.get("size", ""))
        if size_cn:
            lines.append(f"📏 尺寸: {size_cn}({size_en})")

        if skill.get("tags"):
            lines.append(f"🏷️ 标签: {skill['tags']}")
        if skill.get("hidden_tags"):
            lines.append(f"🏷️ 隐藏标签: {skill['hidden_tags']}")

        descriptions = skill.get("descriptions", [])
        if descriptions and len(descriptions) > 1:
            lines.append("")
            lines.append("📋 各品质描述:")
            for desc in descriptions[:4]:
                cn = desc.get("cn", "")
                if cn:
                    lines.append(f"  • {cn}")

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
                    kw in skill.get("name_en", "").lower()):
                    results.append((key, monster))
                    break
            else:
                for item in monster.get("items", []):
                    if (kw in item.get("name", "").lower() or
                        kw in item.get("name_en", "").lower()):
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
                kw in item.get("hidden_tags", "").lower() or
                kw in item.get("heroes", "").lower()):
                results.append(item)
        return results

    def _search_skills(self, keyword: str) -> list:
        results = []
        kw = keyword.lower()
        for skill in self.skills:
            if (kw in skill.get("name_cn", "").lower() or
                kw in skill.get("name_en", "").lower() or
                kw in skill.get("description_cn", "").lower() or
                kw in skill.get("description_en", "").lower() or
                kw in skill.get("heroes", "").lower()):
                results.append(skill)
        return results

    @filter.command("tbzhelp")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看 Bazaar 插件帮助信息"""
        help_text = (
            "🎮 The Bazaar 数据查询助手\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📊 数据: {len(self.monsters)}怪物 | {len(self.items)}物品 | {len(self.skills)}技能\n\n"
            "📋 可用指令:\n\n"
            "/tbzmonster <名称> - 查询怪物详情(图片卡片)\n"
            "  示例: /tbzmonster 火灵\n\n"
            "/tbzitem <名称> - 查询物品详情(图片卡片)\n"
            "  示例: /tbzitem 地下商街\n\n"
            "/tbzskill <名称> - 查询技能详情(图片卡片)\n"
            "  示例: /tbzskill 热情如火\n\n"
            "/tbzsearch <条件> - 智能多条件搜索\n"
            "  直接连写: /tbzsearch 杜利中型灼烧\n"
            "  空格分隔: /tbzsearch 马克 黄金 武器\n"
            "  前缀语法: /tbzsearch tag:Weapon hero:Mak\n"
            "  无参数: /tbzsearch (显示搜索帮助)\n\n"
            "/tbzbuild <物品名> [数量] - 查询推荐阵容\n"
            "  示例: /tbzbuild 符文匕首\n\n"
            "/tbzupdate - 从远端更新游戏数据\n\n"
            "/tbzhelp - 显示此帮助信息\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "数据来源: BazaarHelper | bazaar-builds.net"
        )
        yield event.plain_result(help_text)

    @filter.command("tbzmonster")
    async def cmd_monster(self, event: AstrMessageEvent):
        """查询怪物详细信息"""
        query = _extract_query(event.message_str, "tbzmonster")
        if not query:
            yield event.plain_result("请输入怪物名称，例如: /tbzmonster 火灵")
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
            def monster_name(r):
                k, m = r
                return f"{m.get('name_zh', k)}({m.get('name', '')})"
            found, msg = _resolve_search(
                results, query, monster_name,
                f"未找到怪物「{query}」，请使用 /tbzsearch 搜索。"
            )
            if msg:
                yield event.plain_result(msg)
                return
            found_key, found_monster = found

        if self.renderer:
            try:
                img_bytes = await self.renderer.render_monster_card(found_key, found_monster)
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
                return
            except Exception as e:
                logger.warning(f"怪物卡片渲染失败，回退文本: {e}")
        yield event.plain_result(self._format_monster_info(found_key, found_monster))

    @filter.command("tbzitem")
    async def cmd_item(self, event: AstrMessageEvent):
        """查询物品详细信息"""
        query = _extract_query(event.message_str, "tbzitem")
        if not query:
            yield event.plain_result("请输入物品名称，例如: /tbzitem 短剑")
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
            def item_name(r):
                return f"{r.get('name_cn', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(
                results, query, item_name,
                None
            )
            if msg:
                yield event.plain_result(msg)
                return

        if not found:
            for key, monster in self.monsters.items():
                for mitem in monster.get("items", []):
                    if (mitem.get("name", "").lower() == kw or
                        mitem.get("name_en", "").lower() == kw):
                        tier_str = mitem.get("tier", mitem.get("current_tier", ""))
                        tier_clean = _clean_tier(tier_str)
                        tier_emoji = TIER_EMOJI.get(tier_clean, "")
                        desc_parts = []
                        tiers = mitem.get("tiers", {})
                        if tiers:
                            current = mitem.get("current_tier", "").lower()
                            tier_data = tiers.get(current) or next(
                                (v for v in tiers.values() if v), None
                            )
                            if tier_data and tier_data.get("description"):
                                desc_parts = tier_data["description"]
                        desc_text = "\n".join(desc_parts) if desc_parts else "暂无描述"
                        result = (
                            f"📦 【{mitem['name']}】 {tier_emoji}{tier_str}\n\n"
                            f"📝 {desc_text}\n\n"
                            f"🐉 所属怪物: {monster.get('name_zh', key)}({monster.get('name', '')})"
                        )
                        yield event.plain_result(result)
                        return

        if not found:
            yield event.plain_result(f"未找到物品「{query}」，请使用 /tbzsearch 搜索。")
            return

        if self.renderer:
            try:
                img_bytes = await self.renderer.render_item_card(found)
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
                return
            except Exception as e:
                logger.warning(f"物品卡片渲染失败，回退文本: {e}")
        yield event.plain_result(self._format_item_info(found))

    @filter.command("tbzskill")
    async def cmd_skill(self, event: AstrMessageEvent):
        """查询技能详细信息"""
        query = _extract_query(event.message_str, "tbzskill")
        if not query:
            yield event.plain_result("请输入技能名称，例如: /tbzskill 热情如火")
            return

        kw = query.lower()
        found = None

        for skill in self.skills:
            if (skill.get("name_cn", "").lower() == kw or
                skill.get("name_en", "").lower() == kw):
                found = skill
                break

        if not found:
            results = self._search_skills(query)
            def skill_name(r):
                return f"{r.get('name_cn', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(
                results, query, skill_name,
                f"未找到技能「{query}」，请使用 /tbzsearch 搜索。"
            )
            if msg:
                yield event.plain_result(msg)
                return

        if self.renderer:
            try:
                img_bytes = await self.renderer.render_skill_card(found)
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
                return
            except Exception as e:
                logger.warning(f"技能卡片渲染失败，回退文本: {e}")
        yield event.plain_result(self._format_skill_info(found))

    def _parse_search_conditions(self, query: str) -> dict:
        conditions = {"keyword": "", "tags": [], "tiers": [], "heroes": [], "sizes": []}
        keywords = []

        tokens = self._smart_tokenize(query)

        for part in tokens:
            lower = part.lower().strip()
            if not lower:
                continue
            if ":" in part:
                prefix, value = part.split(":", 1)
                prefix = prefix.lower()
                if prefix in ("tag", "标签"):
                    conditions["tags"].append(value)
                elif prefix in ("tier", "品质"):
                    normalized = TIER_MAP.get(value.lower(), value.capitalize())
                    conditions["tiers"].append(normalized)
                elif prefix in ("hero", "英雄"):
                    conditions["heroes"].append(value)
                elif prefix in ("size", "尺寸"):
                    conditions["sizes"].append(value)
                else:
                    keywords.append(part)
            elif lower in self._vocab:
                vtype, vval = self._vocab[lower]
                if vtype == "hero":
                    conditions["heroes"].append(vval)
                elif vtype == "tier":
                    conditions["tiers"].append(vval)
                elif vtype == "tag":
                    conditions["tags"].append(vval)
                elif vtype == "size":
                    conditions["sizes"].append(vval)
            else:
                keywords.append(part)
        conditions["keyword"] = " ".join(keywords)
        return conditions

    def _filter_items(self, conditions: dict) -> list:
        results = self.items
        if conditions["tags"]:
            filtered = []
            for item in results:
                item_tags = (item.get("tags", "") + " " + item.get("hidden_tags", "")).lower()
                if all(t.lower() in item_tags for t in conditions["tags"]):
                    filtered.append(item)
            results = filtered
        if conditions["tiers"]:
            filtered = []
            for item in results:
                tier = _clean_tier(item.get("starting_tier", ""))
                if tier in conditions["tiers"]:
                    filtered.append(item)
            results = filtered
        if conditions["heroes"]:
            filtered = []
            for item in results:
                hero_str = item.get("heroes", "").lower()
                if all(h.lower() in hero_str for h in conditions["heroes"]):
                    filtered.append(item)
            results = filtered
        if conditions.get("sizes"):
            filtered = []
            for item in results:
                size_str = item.get("size", "").lower()
                if any(s.lower() in size_str for s in conditions["sizes"]):
                    filtered.append(item)
            results = filtered
        if conditions["keyword"]:
            kw = conditions["keyword"].lower()
            filtered = []
            for item in results:
                searchable = " ".join([
                    item.get("name_cn", ""), item.get("name_en", ""),
                    item.get("tags", ""), item.get("hidden_tags", ""),
                    item.get("heroes", ""), item.get("size", ""),
                ]).lower()
                if kw in searchable:
                    filtered.append(item)
            results = filtered
        return results

    def _filter_skills(self, conditions: dict) -> list:
        results = self.skills
        if conditions["heroes"]:
            filtered = []
            for skill in results:
                hero_str = skill.get("heroes", "").lower()
                if all(h.lower() in hero_str for h in conditions["heroes"]):
                    filtered.append(skill)
            results = filtered
        if conditions["keyword"]:
            kw = conditions["keyword"].lower()
            filtered = []
            for skill in results:
                if (kw in skill.get("name_cn", "").lower() or
                    kw in skill.get("name_en", "").lower() or
                    kw in skill.get("description_cn", "").lower() or
                    kw in skill.get("description_en", "").lower() or
                    kw in skill.get("heroes", "").lower()):
                    filtered.append(skill)
            results = filtered
        return results

    def _get_search_help(self) -> str:
        all_tags = set()
        for item in self.items:
            for t in item.get("tags", "").split("|"):
                for p in t.strip().split("/"):
                    p = p.strip()
                    if p:
                        all_tags.add(p)
        heroes = set()
        for item in self.items:
            hero_str = item.get("heroes", "")
            if hero_str:
                for p in hero_str.split("/"):
                    p = p.strip()
                    if p:
                        heroes.add(p)
        sorted_tags = sorted(all_tags)
        sorted_heroes = sorted(heroes)
        return (
            "🔍 多条件搜索帮助\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "用法: /tbzsearch [条件...]\n\n"
            "支持智能识别，可直接连写条件，无需前缀:\n"
            "  /tbzsearch 杜利中型灼烧\n"
            "  /tbzsearch 马克黄金武器\n"
            "  /tbzsearch 青铜食物\n\n"
            "也支持前缀语法:\n"
            "  tag:标签名 / 标签:标签名\n"
            "  tier:品质 / 品质:品质名\n"
            "  hero:英雄 / 英雄:英雄名\n"
            "  size:尺寸 / 尺寸:尺寸名\n\n"
            "示例:\n"
            "  /tbzsearch 灼烧\n"
            "  /tbzsearch tag:Weapon hero:Mak\n"
            "  /tbzsearch tier:Gold tag:Weapon\n\n"
            f"🏷️ 可用标签 ({len(sorted_tags)}个):\n"
            f"  {', '.join(sorted_tags)}\n\n"
            f"🦸 可用英雄 ({len(sorted_heroes)}个):\n"
            f"  {', '.join(sorted_heroes)}\n\n"
            "📊 品质: Bronze(青铜), Silver(白银), Gold(黄金), Diamond(钻石)"
        )

    @filter.command("tbzsearch")
    async def cmd_search(self, event: AstrMessageEvent):
        """多条件搜索怪物、物品和技能"""
        query = _extract_query(event.message_str, "tbzsearch")
        if not query:
            yield event.plain_result(self._get_search_help())
            return

        conditions = self._parse_search_conditions(query)
        has_filters = conditions["tags"] or conditions["tiers"] or conditions["heroes"] or conditions.get("sizes")

        item_results = self._filter_items(conditions)
        skill_results = self._filter_skills(conditions) if not conditions["tiers"] and not conditions["tags"] and not conditions.get("sizes") else []
        monster_results = self._search_monsters(conditions["keyword"]) if conditions["keyword"] and not has_filters else []

        if not monster_results and not item_results and not skill_results:
            yield event.plain_result(f"未找到与「{query}」相关的结果。\n使用 /tbzsearch 查看搜索帮助。")
            return

        parsed_parts = []
        if conditions["heroes"]:
            parsed_parts.append(f"英雄:{','.join(conditions['heroes'])}")
        if conditions["tiers"]:
            parsed_parts.append(f"品质:{','.join(conditions['tiers'])}")
        if conditions["tags"]:
            parsed_parts.append(f"标签:{','.join(conditions['tags'])}")
        if conditions.get("sizes"):
            parsed_parts.append(f"尺寸:{','.join(conditions['sizes'])}")
        if conditions["keyword"]:
            parsed_parts.append(f"关键词:{conditions['keyword']}")
        parsed_hint = " | ".join(parsed_parts)

        total = len(monster_results) + len(item_results) + len(skill_results)

        nodes = []
        header = f"🔍 搜索「{query}」的结果 (共{total}条)"
        if parsed_hint != query:
            header += f"\n📋 识别条件: {parsed_hint}"
        nodes.append(Comp.Node(
            name="大巴扎小助手", uin="0",
            content=[Comp.Plain(header)]
        ))

        if monster_results:
            lines = [f"🐉 怪物 ({len(monster_results)}个):"]
            for key, m in monster_results:
                lines.append(f"  • {m.get('name_zh', key)}({m.get('name', '')})")
            nodes.append(Comp.Node(
                name="大巴扎小助手", uin="0",
                content=[Comp.Plain("\n".join(lines))]
            ))

        if item_results:
            page_size = 30
            for page_start in range(0, len(item_results), page_size):
                page = item_results[page_start:page_start + page_size]
                page_num = page_start // page_size + 1
                total_pages = (len(item_results) + page_size - 1) // page_size
                if total_pages > 1:
                    lines = [f"📦 物品 (第{page_num}/{total_pages}页, 共{len(item_results)}个):"]
                else:
                    lines = [f"📦 物品 ({len(item_results)}个):"]
                for it in page:
                    tier = _clean_tier(it.get("starting_tier", ""))
                    tier_emoji = TIER_EMOJI.get(tier, "")
                    hero = it.get("heroes", "").split("/")[0].strip()
                    lines.append(f"  {tier_emoji} {it.get('name_cn', '')}({it.get('name_en', '')}) - {hero}")
                nodes.append(Comp.Node(
                    name="大巴扎小助手", uin="0",
                    content=[Comp.Plain("\n".join(lines))]
                ))

        if skill_results:
            page_size = 30
            for page_start in range(0, len(skill_results), page_size):
                page = skill_results[page_start:page_start + page_size]
                page_num = page_start // page_size + 1
                total_pages = (len(skill_results) + page_size - 1) // page_size
                if total_pages > 1:
                    lines = [f"🎯 技能 (第{page_num}/{total_pages}页, 共{len(skill_results)}个):"]
                else:
                    lines = [f"🎯 技能 ({len(skill_results)}个):"]
                for sk in page:
                    lines.append(f"  • {sk.get('name_cn', '')}({sk.get('name_en', '')})")
                nodes.append(Comp.Node(
                    name="大巴扎小助手", uin="0",
                    content=[Comp.Plain("\n".join(lines))]
                ))

        nodes.append(Comp.Node(
            name="大巴扎小助手", uin="0",
            content=[Comp.Plain("💡 使用 /tbzitem <名称> 或 /tbzskill <名称> 查看详情")]
        ))

        try:
            yield event.chain_result([Comp.Nodes(nodes)])
        except Exception as e:
            logger.warning(f"合并转发发送失败，回退逐条发送: {e}")
            for node in nodes:
                for item in node.content:
                    if isinstance(item, Comp.Plain):
                        yield event.plain_result(item.text)
                    else:
                        yield event.chain_result([item])

    @filter.command("tbzupdate")
    async def cmd_update(self, event: AstrMessageEvent):
        """从远端更新游戏数据"""
        yield event.plain_result("⏳ 正在从 BazaarHelper 仓库下载最新数据...")

        data_dir = self.plugin_dir / "data"
        session = await self._get_session()
        results = []
        success_count = 0

        for filename, url in DATA_FILES.items():
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        results.append(f"❌ {filename}: HTTP {resp.status}")
                        continue
                    raw = await resp.text()
                    data = json.loads(raw)
                    filepath = data_dir / filename
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(raw)
                    count = len(data) if isinstance(data, (list, dict)) else 0
                    results.append(f"✅ {filename}: {count}条数据")
                    success_count += 1
            except json.JSONDecodeError:
                results.append(f"❌ {filename}: JSON 解析失败")
            except Exception as e:
                results.append(f"❌ {filename}: {e}")

        if success_count > 0:
            self._load_data()
            self._build_vocab()

        summary = (
            f"📦 数据更新完成 ({success_count}/{len(DATA_FILES)})\n"
            + "\n".join(results) + "\n\n"
            f"📊 当前数据: {len(self.monsters)}怪物 | {len(self.items)}物品 | {len(self.skills)}技能"
        )
        yield event.plain_result(summary)

    def _translate_item_name(self, name_cn: str) -> str:
        for item in self.items:
            if item.get("name_cn", "").lower() == name_cn.lower():
                return item.get("name_en", name_cn)
        return name_cn

    async def _download_image(self, url: str) -> bytes | None:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.debug(f"图片下载失败: {url}: {e}")
        return None

    async def _fetch_builds(self, search_term: str, count: int) -> list:
        url = f"{BUILDS_API}/posts"
        params = {
            "search": search_term,
            "per_page": count,
            "_fields": "id,title,link,date,excerpt,featured_media",
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    return []
                posts = await resp.json()

            builds = []
            for post in posts:
                title = html_module.unescape(post.get("title", {}).get("rendered", ""))
                excerpt_raw = post.get("excerpt", {}).get("rendered", "")
                excerpt_text = html_module.unescape(_strip_html(excerpt_raw))

                image_url = ""
                media_id = post.get("featured_media", 0)
                if media_id:
                    media_url = f"{BUILDS_API}/media/{media_id}?_fields=source_url,media_details"
                    try:
                        async with session.get(media_url) as mresp:
                            if mresp.status == 200:
                                media = await mresp.json()
                                sizes = media.get("media_details", {}).get("sizes", {})
                                for size_key in ("large", "medium_large", "1536x1536", "medium"):
                                    if size_key in sizes:
                                        image_url = sizes[size_key]["source_url"]
                                        break
                                if not image_url:
                                    image_url = media.get("source_url", "")
                    except Exception:
                        pass

                builds.append({
                    "title": title,
                    "link": post.get("link", ""),
                    "date": post.get("date", "")[:10],
                    "excerpt": excerpt_text[:200],
                    "image_url": image_url,
                })
            return builds
        except Exception as e:
            logger.warning(f"查询阵容失败: {e}")
            return []

    @filter.command("tbzbuild")
    async def cmd_build(self, event: AstrMessageEvent):
        """查询物品推荐阵容"""
        query = _extract_query(event.message_str, "tbzbuild")
        if not query:
            yield event.plain_result(
                "请输入物品名称查询推荐阵容，例如:\n"
                "  /tbzbuild 符文匕首\n"
                "  /tbzbuild Runic Daggers\n"
                "  /tbzbuild 放大镜 5\n\n"
                "默认显示前3个结果，可在末尾指定数量(1-10)。"
            )
            return

        parts = query.rsplit(maxsplit=1)
        count = DEFAULT_BUILD_COUNT
        if len(parts) == 2 and parts[1].isdigit():
            count = max(1, min(int(parts[1]), 10))
            query = parts[0].strip()

        search_term = query
        is_cn = any('\u4e00' <= c <= '\u9fff' for c in query)
        if is_cn:
            en_name = self._translate_item_name(query)
            if en_name != query:
                search_term = en_name

        builds = await self._fetch_builds(search_term, count)

        if not builds:
            hint = f"（已翻译为: {search_term}）" if search_term != query else ""
            yield event.plain_result(
                f"未找到与「{query}」{hint}相关的阵容。\n"
                f"请尝试使用英文物品名搜索，或访问:\n"
                f"https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
            )
            return

        header = f"🏗️ 「{query}」推荐阵容 (共{len(builds)}条)"
        if search_term != query:
            header += f"\n🔍 搜索: {search_term}"

        nodes = []
        nodes.append(Comp.Node(
            name="大巴扎小助手",
            uin="0",
            content=[Comp.Plain(header)]
        ))

        for i, build in enumerate(builds, 1):
            caption = f"━━ {i}. {build['title']} ━━\n📅 {build['date']}\n🔗 {build['link']}"
            node_content = []

            if build.get("image_url"):
                try:
                    img_bytes = await self._download_image(build["image_url"])
                    if img_bytes:
                        node_content.append(Comp.Image.fromBytes(img_bytes))
                except Exception as e:
                    logger.debug(f"阵容图片下载失败: {e}")

            if not node_content and build.get("excerpt"):
                caption += f"\n💬 {build['excerpt']}"

            node_content.append(Comp.Plain(caption))
            nodes.append(Comp.Node(
                name="大巴扎小助手",
                uin="0",
                content=node_content
            ))

        more_url = f"https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
        nodes.append(Comp.Node(
            name="大巴扎小助手",
            uin="0",
            content=[Comp.Plain(f"💡 更多阵容: {more_url}")]
        ))

        try:
            yield event.chain_result([Comp.Nodes(nodes)])
        except Exception as e:
            logger.warning(f"合并转发发送失败，回退逐条发送: {e}")
            for node in nodes:
                for item in node.content:
                    if isinstance(item, Comp.Plain):
                        yield event.plain_result(item.text)
                    else:
                        yield event.chain_result([item])

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Bazaar 插件已卸载")
