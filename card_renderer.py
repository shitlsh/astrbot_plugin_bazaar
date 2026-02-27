import io
import os
import hashlib
import aiohttp
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from astrbot.api import logger

FONT_PATHS = [
    "/nix/store/r7w3sysqxkrpjjcjkrhdmxcinl7wiiay-wqy-zenhei-0.9.45/share/fonts/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
]

GITHUB_RAW = "https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources"

COLORS = {
    "bg": (30, 30, 40),
    "card_bg": (40, 42, 54),
    "header_bg": (60, 63, 80),
    "text": (248, 248, 242),
    "text_dim": (160, 165, 180),
    "accent": (139, 233, 253),
    "gold": (255, 215, 0),
    "green": (80, 250, 123),
    "orange": (255, 184, 108),
    "red": (255, 85, 85),
    "purple": (189, 147, 249),
    "pink": (255, 121, 198),
    "tier_bronze": (205, 127, 50),
    "tier_silver": (192, 192, 192),
    "tier_gold": (255, 215, 0),
    "tier_diamond": (185, 242, 255),
    "divider": (68, 71, 90),
}

TIER_COLORS = {
    "Bronze": COLORS["tier_bronze"],
    "Silver": COLORS["tier_silver"],
    "Gold": COLORS["tier_gold"],
    "Diamond": COLORS["tier_diamond"],
}


def _clean_tier(raw: str) -> str:
    if not raw:
        return ""
    return raw.split("/")[0].strip().split(" ")[0].strip()


def _get_skill_text(skill_entry) -> str:
    if isinstance(skill_entry, dict):
        return skill_entry.get("cn", "") or skill_entry.get("en", "")
    return str(skill_entry)


class CardRenderer:
    def __init__(self, plugin_dir: Path):
        self.plugin_dir = plugin_dir
        self.cache_dir = plugin_dir / "data" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._font_path = None
        self._find_font()

    def _find_font(self):
        for p in FONT_PATHS:
            if os.path.exists(p):
                self._font_path = p
                return
        try:
            from PIL import ImageFont as IF
            self._font_path = None
            logger.warning("未找到中文字体，将使用默认字体")
        except Exception:
            pass

    def _font(self, size: int) -> ImageFont.FreeTypeFont:
        if self._font_path:
            return ImageFont.truetype(self._font_path, size)
        return ImageFont.load_default()

    async def _fetch_image(self, url: str) -> Image.Image | None:
        cache_name = hashlib.md5(url.encode()).hexdigest() + ".webp"
        cache_path = self.cache_dir / cache_name

        if cache_path.exists():
            try:
                return Image.open(cache_path).convert("RGBA")
            except Exception:
                pass

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        with open(cache_path, "wb") as f:
                            f.write(data)
                        return Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as e:
            logger.debug(f"获取图片失败: {url}: {e}")
        return None

    def _wrap_text(self, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list:
        lines = []
        for paragraph in text.split("\n"):
            if not paragraph.strip():
                lines.append("")
                continue
            current = ""
            for char in paragraph:
                test = current + char
                bbox = font.getbbox(test)
                w = bbox[2] - bbox[0]
                if w > max_width and current:
                    lines.append(current)
                    current = char
                else:
                    current = test
            if current:
                lines.append(current)
        return lines

    def _draw_rounded_rect(self, draw: ImageDraw.ImageDraw, xy, radius, fill):
        x0, y0, x1, y1 = xy
        draw.rounded_rectangle(xy, radius=radius, fill=fill)

    async def render_monster_card(self, key: str, monster: dict) -> bytes:
        name_zh = monster.get("name_zh", key)
        name_en = monster.get("name", "")

        font_title = self._font(28)
        font_subtitle = self._font(18)
        font_body = self._font(16)
        font_small = self._font(14)
        font_tag = self._font(13)

        card_width = 520
        padding = 20
        content_width = card_width - padding * 2

        sections = []

        monster_img = await self._fetch_image(
            f"{GITHUB_RAW}/assets/monsters/characters/{name_zh}.webp"
        )

        header_height = 80 if not monster_img else 100
        sections.append(("header", header_height))

        info_lines = []
        if monster.get("available"):
            info_lines.append(f"出现: {monster['available']}")
        if monster.get("health"):
            info_lines.append(f"生命值: {monster['health']}")
        if monster.get("level"):
            info_lines.append(f"等级: {monster['level']}")
        if monster.get("combat"):
            c = monster["combat"]
            parts = []
            if c.get("gold"):
                parts.append(c["gold"])
            if c.get("exp"):
                parts.append(c["exp"])
            if parts:
                info_lines.append(f"奖励: {' | '.join(parts)}")
        if info_lines:
            sections.append(("info", 20 + len(info_lines) * 22))

        skills = monster.get("skills", [])
        if skills:
            skill_height = 30
            for s in skills[:6]:
                skill_height += 26
                tiers = s.get("tiers", {})
                if tiers:
                    current = s.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        for desc in tier_data["description"][:2]:
                            wrapped = self._wrap_text(desc, font_small, content_width - 30)
                            skill_height += len(wrapped) * 18
                        skill_height += 4
            sections.append(("skills", skill_height))

        items = monster.get("items", [])
        if items:
            seen = set()
            unique_items = []
            for it in items:
                iid = it.get("id", it.get("name", ""))
                if iid not in seen:
                    seen.add(iid)
                    unique_items.append(it)
            item_height = 30
            for it in unique_items[:6]:
                item_height += 26
                tiers = it.get("tiers", {})
                if tiers:
                    current = it.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        desc = tier_data["description"][0]
                        wrapped = self._wrap_text(desc, font_small, content_width - 30)
                        item_height += len(wrapped) * 18
                        item_height += 4
            if len(unique_items) > 6:
                item_height += 22
            sections.append(("items", item_height))

        total_height = sum(h for _, h in sections) + padding * 2 + (len(sections) - 1) * 10 + 20
        img = Image.new("RGBA", (card_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = padding

        self._draw_rounded_rect(draw, (0, 0, card_width, header_height + padding), 12, COLORS["header_bg"])

        if monster_img:
            thumb = monster_img.resize((64, 64), Image.LANCZOS)
            img.paste(thumb, (padding, y + 8), thumb)
            text_x = padding + 76
        else:
            text_x = padding

        draw.text((text_x, y + 8), name_zh, font=font_title, fill=COLORS["text"])
        draw.text((text_x, y + 42), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        tags = monster.get("tags", [])
        if isinstance(tags, list) and tags:
            tag_x = text_x
            for tag in tags[:4]:
                bbox = font_tag.getbbox(tag)
                tw = bbox[2] - bbox[0] + 12
                if tag_x + tw > card_width - padding:
                    break
                draw.rounded_rectangle(
                    (tag_x, y + 64, tag_x + tw, y + 82), radius=4, fill=COLORS["divider"]
                )
                draw.text((tag_x + 6, y + 65), tag, font=font_tag, fill=COLORS["accent"])
                tag_x += tw + 6

        y = header_height + padding + 10

        for section_name, section_height in sections:
            if section_name == "header":
                continue

            if section_name == "info":
                for line in info_lines:
                    draw.text((padding, y), line, font=font_body, fill=COLORS["text_dim"])
                    y += 22
                draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
                y += 10

            elif section_name == "skills":
                draw.text((padding, y), "⚔ 技能", font=font_subtitle, fill=COLORS["accent"])
                y += 28
                for s in skills[:6]:
                    name = s.get("name", s.get("name_en", ""))
                    tier_str = s.get("tier", s.get("current_tier", ""))
                    tier_clean = _clean_tier(tier_str)
                    tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
                    draw.text((padding + 8, y), f"● {name}", font=font_body, fill=tier_color)
                    bbox = font_body.getbbox(f"● {name}")
                    name_w = bbox[2] - bbox[0]
                    draw.text(
                        (padding + 8 + name_w + 8, y + 2), f"[{tier_str}]",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                    y += 26
                    tiers = s.get("tiers", {})
                    if tiers:
                        current = s.get("current_tier", "").lower()
                        tier_data = tiers.get(current) or next(
                            (v for v in tiers.values() if v), None
                        )
                        if tier_data and tier_data.get("description"):
                            for desc in tier_data["description"][:2]:
                                for wl in self._wrap_text(desc, font_small, content_width - 30):
                                    draw.text((padding + 20, y), wl, font=font_small, fill=COLORS["text_dim"])
                                    y += 18
                            y += 4
                draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
                y += 10

            elif section_name == "items":
                draw.text((padding, y), "🎒 物品", font=font_subtitle, fill=COLORS["green"])
                y += 28
                seen2 = set()
                count = 0
                for it in items:
                    iid = it.get("id", it.get("name", ""))
                    if iid in seen2:
                        continue
                    seen2.add(iid)
                    count += 1
                    if count > 6:
                        remaining = len(set(i.get("id", i.get("name", "")) for i in items)) - 6
                        draw.text(
                            (padding + 8, y), f"... 还有{remaining}个物品",
                            font=font_small, fill=COLORS["text_dim"]
                        )
                        y += 22
                        break
                    name = it.get("name", "")
                    tier_str = it.get("tier", it.get("current_tier", ""))
                    tier_clean = _clean_tier(tier_str)
                    tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
                    draw.text((padding + 8, y), f"● {name}", font=font_body, fill=tier_color)
                    bbox = font_body.getbbox(f"● {name}")
                    name_w = bbox[2] - bbox[0]
                    draw.text(
                        (padding + 8 + name_w + 8, y + 2), f"[{tier_str}]",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                    y += 26
                    tiers_data = it.get("tiers", {})
                    if tiers_data:
                        current = it.get("current_tier", "").lower()
                        tier_data = tiers_data.get(current) or next(
                            (v for v in tiers_data.values() if v), None
                        )
                        if tier_data and tier_data.get("description"):
                            desc = tier_data["description"][0]
                            for wl in self._wrap_text(desc, font_small, content_width - 30):
                                draw.text((padding + 20, y), wl, font=font_small, fill=COLORS["text_dim"])
                                y += 18
                            y += 4

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_item_card(self, item: dict) -> bytes:
        name_cn = item.get("name_cn", "")
        name_en = item.get("name_en", "")
        tier_raw = item.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)

        font_title = self._font(26)
        font_subtitle = self._font(18)
        font_body = self._font(16)
        font_small = self._font(14)
        font_tag = self._font(13)

        card_width = 520
        padding = 20
        content_width = card_width - padding * 2

        item_img = await self._fetch_image(
            f"{GITHUB_RAW}/images/{item.get('id', '')}.webp"
        )

        sections_height = 0

        header_h = 90
        sections_height += header_h

        active_skills = item.get("skills", [])
        passive_skills = item.get("skills_passive", [])
        skills_h = 0
        if active_skills:
            skills_h += 28
            for sk in active_skills[:4]:
                txt = _get_skill_text(sk)
                wrapped = self._wrap_text(txt, font_small, content_width - 20)
                skills_h += len(wrapped) * 18 + 6
        if passive_skills:
            skills_h += 28
            for sk in passive_skills[:4]:
                txt = _get_skill_text(sk)
                wrapped = self._wrap_text(txt, font_small, content_width - 20)
                skills_h += len(wrapped) * 18 + 6
        if skills_h:
            sections_height += skills_h + 10

        details = []
        hero_str = item.get("heroes", "")
        if hero_str:
            details.append(f"英雄: {hero_str}")
        if item.get("tags"):
            details.append(f"标签: {item['tags']}")
        size_str = item.get("size", "")
        if size_str:
            details.append(f"尺寸: {size_str}")
        cd = item.get("cooldown")
        if cd is not None:
            details.append(f"冷却: {'被动' if cd == 0 else f'{cd}秒'}")
        if item.get("available_tiers"):
            details.append(f"品质: {item['available_tiers']}")
        if details:
            sections_height += len(details) * 22 + 10

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
                stats.append((label, val, tiers_str))
        if stats:
            sections_height += 28 + len(stats) * 22 + 10

        enchantments = item.get("enchantments", {})
        ench_list = []
        if enchantments and isinstance(enchantments, dict):
            ench_list = list(enchantments.items())[:6]
            ench_h = 28
            for ench_key, ench_data in ench_list:
                if isinstance(ench_data, dict):
                    effect = ench_data.get("effect_cn", ench_data.get("effect_en", ""))
                    wrapped = self._wrap_text(effect, font_small, content_width - 20)
                    ench_h += 20 + len(wrapped) * 18
            if len(enchantments) > 6:
                ench_h += 20
            sections_height += ench_h + 10

        total_height = sections_height + padding * 2 + 20
        img = Image.new("RGBA", (card_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = padding

        tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
        self._draw_rounded_rect(draw, (0, 0, card_width, header_h + padding), 12, COLORS["header_bg"])

        if item_img:
            thumb = item_img.resize((64, 64), Image.LANCZOS)
            img.paste(thumb, (padding, y + 8), thumb)
            text_x = padding + 76
        else:
            text_x = padding

        draw.text((text_x, y + 8), name_cn, font=font_title, fill=COLORS["text"])
        draw.text((text_x, y + 38), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        tier_badge = f" {tier_raw} "
        bbox = font_tag.getbbox(tier_badge)
        tw = bbox[2] - bbox[0] + 12
        badge_x = card_width - padding - tw
        draw.rounded_rectangle(
            (badge_x, y + 10, badge_x + tw, y + 28), radius=4, fill=tier_color
        )
        draw.text(
            (badge_x + 6, y + 11), tier_badge.strip(), font=font_tag,
            fill=COLORS["bg"] if tier_clean in ("Gold", "Diamond") else COLORS["text"]
        )

        y = header_h + padding + 10

        if active_skills:
            draw.text((padding, y), "⚔ 主动技能", font=font_subtitle, fill=COLORS["accent"])
            y += 28
            for sk in active_skills[:4]:
                txt = _get_skill_text(sk)
                for wl in self._wrap_text(txt, font_small, content_width - 20):
                    draw.text((padding + 10, y), wl, font=font_small, fill=COLORS["text"])
                    y += 18
                y += 6

        if passive_skills:
            draw.text((padding, y), "🛡 被动技能", font=font_subtitle, fill=COLORS["purple"])
            y += 28
            for sk in passive_skills[:4]:
                txt = _get_skill_text(sk)
                for wl in self._wrap_text(txt, font_small, content_width - 20):
                    draw.text((padding + 10, y), wl, font=font_small, fill=COLORS["text"])
                    y += 18
                y += 6

        if active_skills or passive_skills:
            draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
            y += 10

        if details:
            for d in details:
                draw.text((padding, y), d, font=font_small, fill=COLORS["text_dim"])
                y += 22
            draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
            y += 10

        if stats:
            draw.text((padding, y), "📈 数值", font=font_subtitle, fill=COLORS["orange"])
            y += 28
            for label, val, tiers_str in stats:
                val_text = f"{label}: {val}"
                draw.text((padding + 10, y), val_text, font=font_body, fill=COLORS["text"])
                if tiers_str:
                    bbox = font_body.getbbox(val_text)
                    vw = bbox[2] - bbox[0]
                    draw.text(
                        (padding + 10 + vw + 8, y + 2), f"({tiers_str})",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                y += 22
            draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
            y += 10

        if ench_list:
            draw.text((padding, y), f"✨ 附魔 ({len(enchantments)}种)", font=font_subtitle, fill=COLORS["pink"])
            y += 28
            for ench_key, ench_data in ench_list:
                if isinstance(ench_data, dict):
                    ench_cn = ench_data.get("name_cn", ench_key)
                    draw.text((padding + 10, y), f"● {ench_cn}({ench_key})", font=font_body, fill=COLORS["gold"])
                    y += 20
                    effect = ench_data.get("effect_cn", ench_data.get("effect_en", ""))
                    for wl in self._wrap_text(effect, font_small, content_width - 20):
                        draw.text((padding + 22, y), wl, font=font_small, fill=COLORS["text_dim"])
                        y += 18
            if len(enchantments) > 6:
                draw.text(
                    (padding + 10, y), f"... 还有{len(enchantments) - 6}种附魔",
                    font=font_small, fill=COLORS["text_dim"]
                )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_skill_card(self, skill: dict) -> bytes:
        name_cn = skill.get("name_cn", "")
        name_en = skill.get("name_en", "")
        tier_raw = skill.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)

        font_title = self._font(26)
        font_subtitle = self._font(18)
        font_body = self._font(16)
        font_small = self._font(14)
        font_tag = self._font(13)

        card_width = 520
        padding = 20
        content_width = card_width - padding * 2

        header_h = 70
        body_h = 20

        desc_cn = skill.get("description_cn", "")
        desc_en = skill.get("description_en", "")
        if desc_cn:
            wrapped = self._wrap_text(desc_cn, font_body, content_width)
            body_h += len(wrapped) * 22 + 10
        if desc_en:
            wrapped = self._wrap_text(desc_en, font_small, content_width)
            body_h += len(wrapped) * 18 + 10

        details = []
        hero_str = skill.get("heroes", "")
        if hero_str:
            details.append(f"英雄: {hero_str}")
        if skill.get("available_tiers"):
            details.append(f"品质: {skill['available_tiers']}")
        size_str = skill.get("size", "")
        if size_str:
            details.append(f"尺寸: {size_str}")
        if skill.get("tags"):
            details.append(f"标签: {skill['tags']}")
        if skill.get("hidden_tags"):
            details.append(f"隐藏标签: {skill['hidden_tags']}")
        if details:
            body_h += len(details) * 22 + 10

        descriptions = skill.get("descriptions", [])
        if descriptions and len(descriptions) > 1:
            body_h += 28
            for desc in descriptions[:4]:
                cn = desc.get("cn", "")
                if cn:
                    wrapped = self._wrap_text(cn, font_small, content_width - 20)
                    body_h += len(wrapped) * 18 + 4

        total_height = header_h + body_h + padding * 3
        img = Image.new("RGBA", (card_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = padding
        tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
        self._draw_rounded_rect(draw, (0, 0, card_width, header_h + padding), 12, COLORS["header_bg"])

        draw.text((padding, y + 8), name_cn, font=font_title, fill=COLORS["text"])
        draw.text((padding, y + 40), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        tier_badge = f" {tier_raw} "
        bbox = font_tag.getbbox(tier_badge)
        tw = bbox[2] - bbox[0] + 12
        badge_x = card_width - padding - tw
        draw.rounded_rectangle((badge_x, y + 10, badge_x + tw, y + 28), radius=4, fill=tier_color)
        draw.text(
            (badge_x + 6, y + 11), tier_badge.strip(), font=font_tag,
            fill=COLORS["bg"] if tier_clean in ("Gold", "Diamond") else COLORS["text"]
        )

        y = header_h + padding + 10

        if desc_cn:
            for wl in self._wrap_text(desc_cn, font_body, content_width):
                draw.text((padding, y), wl, font=font_body, fill=COLORS["text"])
                y += 22
            y += 10
        if desc_en:
            for wl in self._wrap_text(desc_en, font_small, content_width):
                draw.text((padding, y), wl, font=font_small, fill=COLORS["text_dim"])
                y += 18
            y += 10

        draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
        y += 10

        if details:
            for d in details:
                draw.text((padding, y), d, font=font_small, fill=COLORS["text_dim"])
                y += 22
            draw.line((padding, y, card_width - padding, y), fill=COLORS["divider"], width=1)
            y += 10

        if descriptions and len(descriptions) > 1:
            draw.text((padding, y), "📋 各品质描述", font=font_subtitle, fill=COLORS["purple"])
            y += 28
            for desc in descriptions[:4]:
                cn = desc.get("cn", "")
                if cn:
                    for wl in self._wrap_text(cn, font_small, content_width - 20):
                        draw.text((padding + 10, y), wl, font=font_small, fill=COLORS["text"])
                        y += 18
                    y += 4

        buf_skill = io.BytesIO()
        img.save(buf_skill, format="PNG")
        return buf_skill.getvalue()

    async def render_build_card(self, query: str, search_term: str, builds: list) -> bytes:
        font_title = self._font(24)
        font_subtitle = self._font(18)
        font_body = self._font(15)
        font_small = self._font(13)
        font_link = self._font(12)

        card_width = 560
        padding = 20
        content_width = card_width - padding * 2

        header_h = 60
        body_h = 0

        for build in builds:
            bh = 0
            title_lines = self._wrap_text(build["title"], font_subtitle, content_width - 10)
            bh += len(title_lines) * 22
            bh += 20
            if build.get("excerpt"):
                excerpt_lines = self._wrap_text(build["excerpt"], font_small, content_width - 10)
                bh += len(excerpt_lines) * 17
                bh += 6
            bh += 18
            bh += 16
            body_h += bh

        body_h += (len(builds) - 1) * 10
        footer_h = 30

        total_height = header_h + body_h + footer_h + padding * 3
        img = Image.new("RGBA", (card_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = padding
        self._draw_rounded_rect(draw, (0, 0, card_width, header_h + padding), 12, COLORS["header_bg"])

        title_text = f"🏗️ 「{query}」推荐阵容"
        draw.text((padding, y + 6), title_text, font=font_title, fill=COLORS["text"])
        sub = f"来源: bazaar-builds.net | 共{len(builds)}条结果"
        if search_term != query:
            sub = f"搜索: {search_term} | " + sub
        draw.text((padding, y + 34), sub, font=font_small, fill=COLORS["text_dim"])

        y = header_h + padding + 10

        for i, build in enumerate(builds):
            num_badge = f" {i + 1} "
            bbox = font_body.getbbox(num_badge)
            bw = bbox[2] - bbox[0] + 10
            draw.rounded_rectangle(
                (padding, y, padding + bw, y + 22), radius=4, fill=COLORS["accent"]
            )
            draw.text((padding + 5, y + 2), num_badge.strip(), font=font_body, fill=COLORS["bg"])

            title_x = padding + bw + 8
            title_lines = self._wrap_text(build["title"], font_subtitle, content_width - bw - 10)
            for j, tl in enumerate(title_lines):
                draw.text((title_x if j == 0 else padding + 10, y), tl, font=font_subtitle, fill=COLORS["text"])
                y += 22

            y += 4
            draw.text((padding + 10, y), f"📅 {build['date']}", font=font_small, fill=COLORS["text_dim"])
            y += 16

            if build.get("excerpt"):
                excerpt_lines = self._wrap_text(build["excerpt"], font_small, content_width - 10)
                for el in excerpt_lines:
                    draw.text((padding + 10, y), el, font=font_small, fill=COLORS["text_dim"])
                    y += 17
                y += 6

            draw.text((padding + 10, y), f"🔗 {build['link']}", font=font_link, fill=COLORS["accent"])
            y += 18

            if i < len(builds) - 1:
                y += 4
                draw.line((padding + 10, y, card_width - padding - 10, y), fill=COLORS["divider"], width=1)
                y += 6

        y += 10
        more_url = f"https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
        more_text = f"💡 更多阵容: {more_url}"
        more_lines = self._wrap_text(more_text, font_link, content_width)
        for ml in more_lines:
            draw.text((padding, y), ml, font=font_link, fill=COLORS["green"])
            y += 16

        buf_build = io.BytesIO()
        img.save(buf_build, format="PNG")
        return buf_build.getvalue()
