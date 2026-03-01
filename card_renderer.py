import io
import os
import re
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
    "Legendary": (255, 165, 0),
}

SCALE = 2

CARD_WIDTH = 520 * SCALE
BUILD_CARD_WIDTH = 560 * SCALE
PADDING = 20 * SCALE
HEADER_RADIUS = 12 * SCALE
BADGE_RADIUS = 4 * SCALE
TAG_RADIUS = 4 * SCALE

LINE_HEIGHT_TITLE = 34 * SCALE
LINE_HEIGHT_SUBTITLE = 22 * SCALE
LINE_HEIGHT_BODY = 22 * SCALE
LINE_HEIGHT_SMALL = 18 * SCALE
LINE_HEIGHT_LINK = 16 * SCALE
LINE_HEIGHT_EXCERPT = 17 * SCALE
LINE_HEIGHT_DETAIL = 22 * SCALE
LINE_HEIGHT_STAT = 22 * SCALE
LINE_HEIGHT_ITEM = 26 * SCALE
LINE_HEIGHT_SKILL = 26 * SCALE

SECTION_GAP = 10 * SCALE
INDENT = 10 * SCALE
INDENT_DEEP = 20 * SCALE
DESC_GAP = 4 * SCALE
SKILL_DESC_GAP = 6 * SCALE
THUMB_SIZE = 96 * SCALE
THUMB_MARGIN = 108 * SCALE

FONT_SIZE_TITLE = 28 * SCALE
FONT_SIZE_TITLE_SMALL = 26 * SCALE
FONT_SIZE_SUBTITLE = 18 * SCALE
FONT_SIZE_BODY = 16 * SCALE
FONT_SIZE_SMALL = 14 * SCALE
FONT_SIZE_TAG = 13 * SCALE
FONT_SIZE_LINK = 12 * SCALE

_CJK_RANGES = re.compile(r'[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]')


def _clean_tier(raw: str) -> str:
    if not raw:
        return ""
    return raw.split("/")[0].strip().split(" ")[0].strip()


def _get_skill_text(skill_entry) -> str:
    if isinstance(skill_entry, dict):
        return skill_entry.get("cn", "") or skill_entry.get("en", "")
    return str(skill_entry)


class CardRenderer:
    def __init__(self, plugin_dir: Path, session: aiohttp.ClientSession | None = None):
        self.plugin_dir = plugin_dir
        self._session = session
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

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is not None and not self._session.closed:
            return self._session
        self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def _fetch_image(self, url: str) -> Image.Image | None:
        cache_name = hashlib.md5(url.encode()).hexdigest() + ".webp"
        cache_path = self.cache_dir / cache_name

        if cache_path.exists():
            try:
                return Image.open(cache_path).convert("RGBA")
            except Exception:
                pass

        try:
            session = await self._get_session()
            async with session.get(url) as resp:
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
            has_cjk = bool(_CJK_RANGES.search(paragraph))
            if has_cjk:
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
            else:
                words = paragraph.split(" ")
                current = ""
                for word in words:
                    test = f"{current} {word}" if current else word
                    bbox = font.getbbox(test)
                    w = bbox[2] - bbox[0]
                    if w > max_width and current:
                        lines.append(current)
                        current = word
                    else:
                        current = test
                if current:
                    lines.append(current)
        return lines

    def _draw_rounded_rect(self, draw: ImageDraw.ImageDraw, xy, radius, fill):
        draw.rounded_rectangle(xy, radius=radius, fill=fill)

    def _draw_divider(self, draw, y, card_width):
        draw.line((PADDING, y, card_width - PADDING, y), fill=COLORS["divider"], width=SCALE)

    def _draw_tier_badge(self, draw, tier_raw, tier_clean, y, card_width, font_tag):
        tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
        tier_badge = f" {tier_raw} "
        bbox = font_tag.getbbox(tier_badge)
        tw = bbox[2] - bbox[0] + 12 * SCALE
        badge_x = card_width - PADDING - tw
        draw.rounded_rectangle(
            (badge_x, y + SECTION_GAP, badge_x + tw, y + 28 * SCALE), radius=BADGE_RADIUS, fill=tier_color
        )
        draw.text(
            (badge_x + 6 * SCALE, y + 11 * SCALE), tier_badge.strip(), font=font_tag,
            fill=COLORS["bg"] if tier_clean in ("Gold", "Diamond") else COLORS["text"]
        )

    async def render_monster_card(self, key: str, monster: dict) -> bytes:
        name_zh = monster.get("name_zh", key)
        name_en = monster.get("name", "")

        font_title = self._font(FONT_SIZE_TITLE)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(FONT_SIZE_BODY)
        font_small = self._font(FONT_SIZE_SMALL)
        font_tag = self._font(FONT_SIZE_TAG)

        content_width = CARD_WIDTH - PADDING * 2

        sections = []

        monster_img = await self._fetch_image(
            f"{GITHUB_RAW}/assets/monsters/characters/{name_zh}.webp"
        )

        header_height = 80 * SCALE if not monster_img else 120 * SCALE
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
            sections.append(("info", PADDING + len(info_lines) * LINE_HEIGHT_DETAIL))

        skills = monster.get("skills", [])
        if skills:
            skill_height = 30
            for s in skills[:6]:
                skill_height += LINE_HEIGHT_SKILL
                tiers = s.get("tiers", {})
                if tiers:
                    current = s.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        for desc in tier_data["description"][:2]:
                            wrapped = self._wrap_text(desc, font_small, content_width - INDENT_DEEP - INDENT)
                            skill_height += len(wrapped) * LINE_HEIGHT_SMALL
                        skill_height += DESC_GAP
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
                item_height += LINE_HEIGHT_ITEM
                tiers = it.get("tiers", {})
                if tiers:
                    current = it.get("current_tier", "").lower()
                    tier_data = tiers.get(current) or next(
                        (v for v in tiers.values() if v), None
                    )
                    if tier_data and tier_data.get("description"):
                        desc = tier_data["description"][0]
                        wrapped = self._wrap_text(desc, font_small, content_width - INDENT_DEEP - INDENT)
                        item_height += len(wrapped) * LINE_HEIGHT_SMALL
                        item_height += DESC_GAP
            if len(unique_items) > 6:
                item_height += LINE_HEIGHT_DETAIL
            sections.append(("items", item_height))

        total_height = sum(h for _, h in sections) + PADDING * 2 + (len(sections) - 1) * SECTION_GAP + PADDING
        img = Image.new("RGBA", (CARD_WIDTH, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING

        self._draw_rounded_rect(draw, (0, 0, CARD_WIDTH, header_height + PADDING), HEADER_RADIUS, COLORS["header_bg"])

        if monster_img:
            orig_w, orig_h = monster_img.size
            ratio = min(THUMB_SIZE / orig_w, THUMB_SIZE / orig_h)
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            thumb = monster_img.resize((new_w, new_h), Image.LANCZOS)
            thumb_y = y + 8 * SCALE + (THUMB_SIZE - new_h) // 2
            thumb_x = PADDING + (THUMB_SIZE - new_w) // 2
            img.paste(thumb, (thumb_x, thumb_y), thumb)
            text_x = PADDING + THUMB_MARGIN
        else:
            text_x = PADDING

        draw.text((text_x, y + 12 * SCALE), name_zh, font=font_title, fill=COLORS["text"])
        draw.text((text_x, y + 46 * SCALE), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        tags = monster.get("tags", [])
        if isinstance(tags, list) and tags:
            tag_x = text_x
            for tag in tags[:4]:
                bbox = font_tag.getbbox(tag)
                tw = bbox[2] - bbox[0] + 12 * SCALE
                if tag_x + tw > CARD_WIDTH - PADDING:
                    break
                draw.rounded_rectangle(
                    (tag_x, y + 64 * SCALE, tag_x + tw, y + 82 * SCALE), radius=TAG_RADIUS, fill=COLORS["divider"]
                )
                draw.text((tag_x + 6 * SCALE, y + 65 * SCALE), tag, font=font_tag, fill=COLORS["accent"])
                tag_x += tw + 6 * SCALE

        y = header_height + PADDING + SECTION_GAP

        for section_name, section_height in sections:
            if section_name == "header":
                continue

            if section_name == "info":
                for line in info_lines:
                    draw.text((PADDING, y), line, font=font_body, fill=COLORS["text_dim"])
                    y += LINE_HEIGHT_DETAIL
                self._draw_divider(draw, y, CARD_WIDTH)
                y += SECTION_GAP

            elif section_name == "skills":
                draw.text((PADDING, y), "【技能】", font=font_subtitle, fill=COLORS["accent"])
                y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
                for s in skills[:6]:
                    name = s.get("name", s.get("name_en", ""))
                    tier_str = s.get("tier", s.get("current_tier", ""))
                    tier_clean = _clean_tier(tier_str)
                    tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
                    draw.text((PADDING + 8 * SCALE, y), f"● {name}", font=font_body, fill=tier_color)
                    bbox = font_body.getbbox(f"● {name}")
                    name_w = bbox[2] - bbox[0]
                    draw.text(
                        (PADDING + 8 * SCALE + name_w + 8 * SCALE, y + 2 * SCALE), f"[{tier_str}]",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                    y += LINE_HEIGHT_SKILL
                    tiers = s.get("tiers", {})
                    if tiers:
                        current = s.get("current_tier", "").lower()
                        tier_data = tiers.get(current) or next(
                            (v for v in tiers.values() if v), None
                        )
                        if tier_data and tier_data.get("description"):
                            for desc in tier_data["description"][:2]:
                                for wl in self._wrap_text(desc, font_small, content_width - INDENT_DEEP - INDENT):
                                    draw.text((PADDING + INDENT_DEEP, y), wl, font=font_small, fill=COLORS["text_dim"])
                                    y += LINE_HEIGHT_SMALL
                            y += DESC_GAP
                self._draw_divider(draw, y, CARD_WIDTH)
                y += SECTION_GAP

            elif section_name == "items":
                draw.text((PADDING, y), "【物品】", font=font_subtitle, fill=COLORS["green"])
                y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
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
                            (PADDING + 8 * SCALE, y), f"... 还有{remaining}个物品",
                            font=font_small, fill=COLORS["text_dim"]
                        )
                        y += LINE_HEIGHT_DETAIL
                        break
                    name = it.get("name", "")
                    tier_str = it.get("tier", it.get("current_tier", ""))
                    tier_clean = _clean_tier(tier_str)
                    tier_color = TIER_COLORS.get(tier_clean, COLORS["text_dim"])
                    draw.text((PADDING + 8 * SCALE, y), f"● {name}", font=font_body, fill=tier_color)
                    bbox = font_body.getbbox(f"● {name}")
                    name_w = bbox[2] - bbox[0]
                    draw.text(
                        (PADDING + 8 * SCALE + name_w + 8 * SCALE, y + 2 * SCALE), f"[{tier_str}]",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                    y += LINE_HEIGHT_ITEM
                    tiers_data = it.get("tiers", {})
                    if tiers_data:
                        current = it.get("current_tier", "").lower()
                        tier_data = tiers_data.get(current) or next(
                            (v for v in tiers_data.values() if v), None
                        )
                        if tier_data and tier_data.get("description"):
                            desc = tier_data["description"][0]
                            for wl in self._wrap_text(desc, font_small, content_width - INDENT_DEEP - INDENT):
                                draw.text((PADDING + INDENT_DEEP, y), wl, font=font_small, fill=COLORS["text_dim"])
                                y += LINE_HEIGHT_SMALL
                            y += DESC_GAP

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_item_card(self, item: dict) -> bytes:
        name_cn = item.get("name_cn", "")
        name_en = item.get("name_en", "")
        tier_raw = item.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)

        font_title = self._font(FONT_SIZE_TITLE_SMALL)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(FONT_SIZE_BODY)
        font_small = self._font(FONT_SIZE_SMALL)
        font_tag = self._font(FONT_SIZE_TAG)

        content_width = CARD_WIDTH - PADDING * 2

        item_img = await self._fetch_image(
            f"{GITHUB_RAW}/images/{item.get('id', '')}.webp"
        )

        sections_height = 0

        header_h = 110 * SCALE
        sections_height += header_h

        active_skills = item.get("skills", [])
        passive_skills = item.get("skills_passive", [])
        skills_h = 0
        if active_skills:
            skills_h += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for sk in active_skills[:4]:
                txt = _get_skill_text(sk)
                wrapped = self._wrap_text(txt, font_small, content_width - INDENT_DEEP)
                skills_h += len(wrapped) * LINE_HEIGHT_SMALL + SKILL_DESC_GAP
        if passive_skills:
            skills_h += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for sk in passive_skills[:4]:
                txt = _get_skill_text(sk)
                wrapped = self._wrap_text(txt, font_small, content_width - INDENT_DEEP)
                skills_h += len(wrapped) * LINE_HEIGHT_SMALL + SKILL_DESC_GAP
        if skills_h:
            sections_height += skills_h + SECTION_GAP

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
            sections_height += len(details) * LINE_HEIGHT_DETAIL + SECTION_GAP

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
            sections_height += LINE_HEIGHT_SUBTITLE + SECTION_GAP + len(stats) * LINE_HEIGHT_STAT + SECTION_GAP

        enchantments = item.get("enchantments", {})
        ench_list = []
        if enchantments and isinstance(enchantments, dict):
            ench_list = list(enchantments.items())
            ench_h = LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for ench_key, ench_data in ench_list:
                if isinstance(ench_data, dict):
                    effect = ench_data.get("effect_cn", ench_data.get("effect_en", ""))
                    wrapped = self._wrap_text(effect, font_small, content_width - INDENT_DEEP)
                    ench_h += PADDING + len(wrapped) * LINE_HEIGHT_SMALL
            sections_height += ench_h + SECTION_GAP

        quests = item.get("quests") or []
        if quests and not isinstance(quests, list):
            quests = [quests]
        quests_h = 0
        if quests:
            quests_h = LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for q in quests:
                target = q.get("cn_target") or q.get("en_target", "")
                reward = q.get("cn_reward") or q.get("en_reward", "")
                if target:
                    wrapped_t = self._wrap_text(f"→ {target}", font_small, content_width - INDENT_DEEP)
                    quests_h += len(wrapped_t) * LINE_HEIGHT_SMALL
                if reward:
                    wrapped_r = self._wrap_text(f"=> {reward}", font_small, content_width - INDENT_DEEP)
                    quests_h += len(wrapped_r) * LINE_HEIGHT_SMALL
                quests_h += SKILL_DESC_GAP
            sections_height += quests_h + SECTION_GAP

        total_height = sections_height + PADDING * 2 + PADDING
        img = Image.new("RGBA", (CARD_WIDTH, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING

        self._draw_rounded_rect(draw, (0, 0, CARD_WIDTH, header_h + PADDING), HEADER_RADIUS, COLORS["header_bg"])

        if item_img:
            orig_w, orig_h = item_img.size
            ratio = min(THUMB_SIZE / orig_w, THUMB_SIZE / orig_h)
            new_w = max(1, int(orig_w * ratio))
            new_h = max(1, int(orig_h * ratio))
            thumb = item_img.resize((new_w, new_h), Image.LANCZOS)
            thumb_y = y + 8 * SCALE + (THUMB_SIZE - new_h) // 2
            thumb_x = PADDING + (THUMB_SIZE - new_w) // 2
            img.paste(thumb, (thumb_x, thumb_y), thumb)
            text_x = PADDING + THUMB_MARGIN
        else:
            text_x = PADDING

        draw.text((text_x, y + 12 * SCALE), name_cn, font=font_title, fill=COLORS["text"])
        draw.text((text_x, y + 46 * SCALE), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        self._draw_tier_badge(draw, tier_raw, tier_clean, y, CARD_WIDTH, font_tag)

        y = header_h + PADDING + SECTION_GAP

        if active_skills:
            draw.text((PADDING, y), "【主动技能】", font=font_subtitle, fill=COLORS["accent"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for sk in active_skills[:4]:
                txt = _get_skill_text(sk)
                for wl in self._wrap_text(txt, font_small, content_width - INDENT_DEEP):
                    draw.text((PADDING + INDENT, y), wl, font=font_small, fill=COLORS["text"])
                    y += LINE_HEIGHT_SMALL
                y += SKILL_DESC_GAP

        if passive_skills:
            draw.text((PADDING, y), "【被动技能】", font=font_subtitle, fill=COLORS["purple"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for sk in passive_skills[:4]:
                txt = _get_skill_text(sk)
                for wl in self._wrap_text(txt, font_small, content_width - INDENT_DEEP):
                    draw.text((PADDING + INDENT, y), wl, font=font_small, fill=COLORS["text"])
                    y += LINE_HEIGHT_SMALL
                y += SKILL_DESC_GAP

        if active_skills or passive_skills:
            self._draw_divider(draw, y, CARD_WIDTH)
            y += SECTION_GAP

        if details:
            for d in details:
                draw.text((PADDING, y), d, font=font_small, fill=COLORS["text_dim"])
                y += LINE_HEIGHT_DETAIL
            self._draw_divider(draw, y, CARD_WIDTH)
            y += SECTION_GAP

        if stats:
            draw.text((PADDING, y), "【数值】", font=font_subtitle, fill=COLORS["orange"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for label, val, tiers_str in stats:
                val_text = f"{label}: {val}"
                draw.text((PADDING + INDENT, y), val_text, font=font_body, fill=COLORS["text"])
                if tiers_str:
                    bbox = font_body.getbbox(val_text)
                    vw = bbox[2] - bbox[0]
                    draw.text(
                        (PADDING + INDENT + vw + 8 * SCALE, y + 2 * SCALE), f"({tiers_str})",
                        font=font_small, fill=COLORS["text_dim"]
                    )
                y += LINE_HEIGHT_STAT
            self._draw_divider(draw, y, CARD_WIDTH)
            y += SECTION_GAP

        if ench_list:
            draw.text((PADDING, y), f"【附魔】({len(enchantments)}种)", font=font_subtitle, fill=COLORS["pink"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for ench_key, ench_data in ench_list:
                if isinstance(ench_data, dict):
                    ench_cn = ench_data.get("name_cn", ench_key)
                    draw.text((PADDING + INDENT, y), f"● {ench_cn}({ench_key})", font=font_body, fill=COLORS["gold"])
                    y += PADDING
                    effect = ench_data.get("effect_cn", ench_data.get("effect_en", ""))
                    for wl in self._wrap_text(effect, font_small, content_width - INDENT_DEEP):
                        draw.text((PADDING + INDENT_DEEP + 2 * SCALE, y), wl, font=font_small, fill=COLORS["text_dim"])
                        y += LINE_HEIGHT_SMALL
            if quests:
                self._draw_divider(draw, y + SECTION_GAP, CARD_WIDTH)
                y += SECTION_GAP * 2

        if quests:
            draw.text((PADDING, y), f"【任务】({len(quests)}个)", font=font_subtitle, fill=COLORS["green"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for qi, q in enumerate(quests, 1):
                target = q.get("cn_target") or q.get("en_target", "")
                reward = q.get("cn_reward") or q.get("en_reward", "")
                if target:
                    for wl in self._wrap_text(f"→ {target}", font_small, content_width - INDENT_DEEP):
                        draw.text((PADDING + INDENT, y), wl, font=font_small, fill=COLORS["text_dim"])
                        y += LINE_HEIGHT_SMALL
                if reward:
                    for wl in self._wrap_text(f"=> {reward}", font_small, content_width - INDENT_DEEP):
                        draw.text((PADDING + INDENT, y), wl, font=font_small, fill=COLORS["accent"])
                        y += LINE_HEIGHT_SMALL
                y += SKILL_DESC_GAP

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_skill_card(self, skill: dict) -> bytes:
        name_cn = skill.get("name_cn", "")
        name_en = skill.get("name_en", "")
        tier_raw = skill.get("starting_tier", "")
        tier_clean = _clean_tier(tier_raw)

        font_title = self._font(FONT_SIZE_TITLE_SMALL)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(FONT_SIZE_BODY)
        font_small = self._font(FONT_SIZE_SMALL)
        font_tag = self._font(FONT_SIZE_TAG)

        content_width = CARD_WIDTH - PADDING * 2

        header_h = 70 * SCALE
        body_h = PADDING

        desc_cn = skill.get("description_cn", "")
        desc_en = skill.get("description_en", "")
        if desc_cn:
            wrapped = self._wrap_text(desc_cn, font_body, content_width)
            body_h += len(wrapped) * LINE_HEIGHT_BODY + SECTION_GAP
        if desc_en:
            wrapped = self._wrap_text(desc_en, font_small, content_width)
            body_h += len(wrapped) * LINE_HEIGHT_SMALL + SECTION_GAP

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
            body_h += len(details) * LINE_HEIGHT_DETAIL + SECTION_GAP

        descriptions = skill.get("descriptions", [])
        if descriptions and len(descriptions) > 1:
            body_h += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for desc in descriptions[:4]:
                cn = desc.get("cn", "")
                if cn:
                    wrapped = self._wrap_text(cn, font_small, content_width - INDENT_DEEP)
                    body_h += len(wrapped) * LINE_HEIGHT_SMALL + DESC_GAP

        total_height = header_h + body_h + PADDING * 3
        img = Image.new("RGBA", (CARD_WIDTH, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING
        self._draw_rounded_rect(draw, (0, 0, CARD_WIDTH, header_h + PADDING), HEADER_RADIUS, COLORS["header_bg"])

        draw.text((PADDING, y + 8 * SCALE), name_cn, font=font_title, fill=COLORS["text"])
        draw.text((PADDING, y + 40 * SCALE), name_en, font=font_subtitle, fill=COLORS["text_dim"])

        self._draw_tier_badge(draw, tier_raw, tier_clean, y, CARD_WIDTH, font_tag)

        y = header_h + PADDING + SECTION_GAP

        if desc_cn:
            for wl in self._wrap_text(desc_cn, font_body, content_width):
                draw.text((PADDING, y), wl, font=font_body, fill=COLORS["text"])
                y += LINE_HEIGHT_BODY
            y += SECTION_GAP
        if desc_en:
            for wl in self._wrap_text(desc_en, font_small, content_width):
                draw.text((PADDING, y), wl, font=font_small, fill=COLORS["text_dim"])
                y += LINE_HEIGHT_SMALL
            y += SECTION_GAP

        self._draw_divider(draw, y, CARD_WIDTH)
        y += SECTION_GAP

        if details:
            for d in details:
                draw.text((PADDING, y), d, font=font_small, fill=COLORS["text_dim"])
                y += LINE_HEIGHT_DETAIL
            self._draw_divider(draw, y, CARD_WIDTH)
            y += SECTION_GAP

        if descriptions and len(descriptions) > 1:
            draw.text((PADDING, y), "【各品质描述】", font=font_subtitle, fill=COLORS["purple"])
            y += LINE_HEIGHT_SUBTITLE + SECTION_GAP
            for desc in descriptions[:4]:
                cn = desc.get("cn", "")
                if cn:
                    for wl in self._wrap_text(cn, font_small, content_width - INDENT_DEEP):
                        draw.text((PADDING + INDENT, y), wl, font=font_small, fill=COLORS["text"])
                        y += LINE_HEIGHT_SMALL
                    y += DESC_GAP

        buf_skill = io.BytesIO()
        img.save(buf_skill, format="PNG")
        return buf_skill.getvalue()

    async def render_news_card(self, title: str, date_str: str, body: str, url: str) -> bytes:
        font_title = self._font(24 * SCALE)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(15 * SCALE)
        font_small = self._font(FONT_SIZE_SMALL)
        font_link = self._font(FONT_SIZE_LINK)

        news_width = BUILD_CARD_WIDTH
        content_width = news_width - PADDING * 2

        header_h = 70 * SCALE

        body_lines = self._wrap_text(body, font_body, content_width - INDENT)
        max_body_lines = 200
        if len(body_lines) > max_body_lines:
            body_lines = body_lines[:max_body_lines]
            body_lines.append("...")
        body_h = len(body_lines) * LINE_HEIGHT_BODY + SECTION_GAP

        footer_h = LINE_HEIGHT_LINK + PADDING

        total_height = header_h + body_h + footer_h + PADDING * 3
        img = Image.new("RGBA", (news_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING
        self._draw_rounded_rect(draw, (0, 0, news_width, header_h + PADDING), HEADER_RADIUS, COLORS["header_bg"])

        title_lines = self._wrap_text(title, font_title, content_width - 10 * SCALE)
        for tl in title_lines[:2]:
            draw.text((PADDING, y + 6 * SCALE), tl, font=font_title, fill=COLORS["text"])
            y += 30 * SCALE

        draw.text((PADDING, y + 4 * SCALE), f"{date_str}", font=font_small, fill=COLORS["text_dim"])

        y = header_h + PADDING + SECTION_GAP

        section_color_map = {
            "h1": COLORS["accent"],
            "h2": COLORS["green"],
            "h3": COLORS["orange"],
        }
        current_color = COLORS["text"]

        for line in body_lines:
            stripped = line.strip()
            is_heading = False
            for prefix, color in [("## ", "h2"), ("### ", "h3"), ("# ", "h1")]:
                if stripped.startswith(prefix):
                    heading_text = stripped[len(prefix):]
                    draw.text((PADDING + INDENT, y), heading_text, font=font_subtitle, fill=section_color_map[color])
                    y += LINE_HEIGHT_BODY
                    is_heading = True
                    break
            if is_heading:
                continue

            if stripped.startswith("- ") or stripped.startswith("* "):
                draw.text((PADDING + INDENT, y), stripped, font=font_body, fill=COLORS["text"])
            elif stripped == "":
                pass
            else:
                draw.text((PADDING + INDENT, y), stripped, font=font_body, fill=COLORS["text"])
            y += LINE_HEIGHT_BODY

        y += SECTION_GAP
        self._draw_divider(draw, y, news_width)
        y += SECTION_GAP

        url_lines = self._wrap_text(url, font_link, content_width)
        for ul in url_lines[:2]:
            draw.text((PADDING, y), ul, font=font_link, fill=COLORS["accent"])
            y += LINE_HEIGHT_LINK

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_tierlist_card(self, hero_en: str, hero_cn: str, tier_items: dict) -> bytes:
        import asyncio

        font_title = self._font(24 * SCALE)
        font_grade = self._font(32 * SCALE)
        font_small = self._font(FONT_SIZE_TAG)
        font_link = self._font(FONT_SIZE_LINK)
        font_pct = self._font(10 * SCALE)

        grade_colors = {
            "S": (255, 69, 58),
            "A": (255, 159, 10),
            "B": (50, 215, 75),
            "C": (100, 210, 255),
        }

        tier_border_colors = {
            "Bronze": (205, 127, 50),
            "Silver": (192, 192, 192),
            "Gold": (255, 215, 0),
            "Diamond": (185, 242, 255),
            "Legendary": (255, 121, 198),
        }

        thumb_h = 80 * SCALE
        size_widths = {
            "Small": int(thumb_h * 0.55),
            "Medium": thumb_h,
            "Large": int(thumb_h * 1.45),
        }
        thumb_gap = 6 * SCALE
        label_w = 60 * SCALE
        row_pad = 8 * SCALE
        border_w = 2 * SCALE

        all_items = []
        for grade in ["S", "A", "B", "C"]:
            for it in tier_items.get(grade, []):
                all_items.append(it)

        image_tasks = {}
        for idx, it in enumerate(all_items):
            url = it.get("image_url", "")
            if url:
                key = f"{idx}:{it['name']}"
                image_tasks[key] = self._fetch_image(url)
                it["_img_key"] = key
        fetched = {}
        if image_tasks:
            results = await asyncio.gather(*image_tasks.values(), return_exceptions=True)
            for key, result in zip(image_tasks.keys(), results):
                if isinstance(result, Image.Image):
                    fetched[key] = result

        content_x = label_w + row_pad
        avail_w = BUILD_CARD_WIDTH - content_x - PADDING
        card_width = BUILD_CARD_WIDTH

        def _layout_rows(items_list):
            rows = []
            row = []
            row_w = 0
            for it in items_list:
                tw = size_widths.get(it.get("size", "Medium"), thumb_h)
                needed = tw + thumb_gap
                if row and row_w + needed > avail_w:
                    rows.append(row)
                    row = [it]
                    row_w = needed
                else:
                    row.append(it)
                    row_w += needed
            if row:
                rows.append(row)
            return rows

        header_h = 70 * SCALE
        body_h = 0
        grade_rows = {}
        for grade in ["S", "A", "B", "C"]:
            items = tier_items.get(grade, [])
            if not items:
                continue
            rows = _layout_rows(items)
            grade_rows[grade] = rows
            row_h = len(rows) * (thumb_h + thumb_gap) + row_pad * 2
            body_h += row_h + 2 * SCALE

        footer_h = LINE_HEIGHT_LINK * 2 + PADDING
        total_height = header_h + body_h + footer_h + PADDING * 3

        img = Image.new("RGBA", (card_width, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING
        self._draw_rounded_rect(draw, (0, 0, card_width, header_h + PADDING), HEADER_RADIUS, COLORS["header_bg"])
        total_items = sum(len(v) for v in tier_items.values())
        draw.text((PADDING, y + 6 * SCALE), f"{hero_cn}({hero_en}) 物品评级", font=font_title, fill=COLORS["text"])
        draw.text((PADDING, y + 38 * SCALE), f"共{total_items}个物品 | 数据来源: BazaarForge.gg", font=font_small, fill=COLORS["text_dim"])

        y = header_h + PADDING + SECTION_GAP

        for grade in ["S", "A", "B", "C"]:
            if grade not in grade_rows:
                continue
            rows = grade_rows[grade]
            items = tier_items[grade]

            color = grade_colors.get(grade, COLORS["text"])
            row_h = len(rows) * (thumb_h + thumb_gap) + row_pad * 2

            draw.rounded_rectangle(
                (0, y, label_w, y + row_h),
                radius=0, fill=color
            )
            grade_bbox = font_grade.getbbox(grade)
            gw = grade_bbox[2] - grade_bbox[0]
            gh = grade_bbox[3] - grade_bbox[1]
            draw.text(
                ((label_w - gw) // 2, y + (row_h - gh) // 2),
                grade, font=font_grade, fill=(30, 30, 40)
            )

            draw.rectangle(
                (label_w, y, card_width, y + row_h),
                fill=(50, 52, 65)
            )

            iy = y + row_pad
            for row in rows:
                ix = content_x
                for it in row:
                    tw = size_widths.get(it.get("size", "Medium"), thumb_h)

                    border_color = tier_border_colors.get(it.get("tier", ""), COLORS["text_dim"])
                    draw.rounded_rectangle(
                        (ix - border_w, iy - border_w, ix + tw + border_w, iy + thumb_h + border_w),
                        radius=4 * SCALE, fill=border_color
                    )

                    item_img = fetched.get(it.get("_img_key", ""))
                    if item_img:
                        resized = item_img.resize((tw, thumb_h), Image.LANCZOS)
                        img.paste(resized, (ix, iy), resized if resized.mode == "RGBA" else None)
                    else:
                        draw.rectangle((ix, iy, ix + tw, iy + thumb_h), fill=(60, 63, 80))
                        name_short = (it.get("name_cn") or it["name"])[:3]
                        draw.text((ix + 2 * SCALE, iy + thumb_h // 2 - 8 * SCALE), name_short, font=font_small, fill=COLORS["text"])

                    pct_text = f"{it['pct']:.0f}%"
                    pct_bbox = font_pct.getbbox(pct_text)
                    pw = pct_bbox[2] - pct_bbox[0]
                    ph = pct_bbox[3] - pct_bbox[1]
                    pct_bg_x = ix + tw - pw - 4 * SCALE
                    pct_bg_y = iy + thumb_h - ph - 4 * SCALE
                    draw.rounded_rectangle(
                        (pct_bg_x - 2 * SCALE, pct_bg_y - 2 * SCALE, pct_bg_x + pw + 4 * SCALE, pct_bg_y + ph + 4 * SCALE),
                        radius=2 * SCALE, fill=(0, 0, 0, 180)
                    )
                    draw.text((pct_bg_x, pct_bg_y), pct_text, font=font_pct, fill=(255, 255, 255))

                    ix += tw + thumb_gap

                iy += thumb_h + thumb_gap

            y += row_h + 2 * SCALE

        y += SECTION_GAP
        draw.text(
            (PADDING, y), "S≥15% | A≥8% | B≥3% | C>0%",
            font=font_link, fill=COLORS["text_dim"]
        )
        y += LINE_HEIGHT_LINK
        draw.text(
            (PADDING, y), "bazaarforge.gg",
            font=font_link, fill=COLORS["accent"]
        )

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    async def render_merchant_card(self, merchant: dict) -> bytes:
        font_title = self._font(FONT_SIZE_TITLE)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(FONT_SIZE_BODY)
        font_small = self._font(FONT_SIZE_TAG)
        font_link = self._font(FONT_SIZE_LINK)

        name = merchant.get("name", "")
        desc = merchant.get("description", "")
        category = merchant.get("category", "")
        tier = merchant.get("tier", "")
        heroes = merchant.get("heroes", [])
        slug = merchant.get("name_slug", "")

        category_cn = "商人" if category == "Merchant" else "训练师" if category == "Trainer" else category
        tier_cn = {"Bronze": "青铜", "Silver": "白银", "Gold": "黄金", "Diamond": "钻石", "Legendary": "传说"}.get(tier, tier)
        hero_cn_map = {"Common": "通用", "Dooley": "杜利", "Jules": "朱尔斯", "Mak": "马克", "Pygmalien": "皮格马利翁", "Stelle": "斯黛拉", "Vanessa": "瓦妮莎"}

        content_width = CARD_WIDTH - PADDING * 2
        header_h = THUMB_SIZE + PADDING * 2

        body_lines = []
        body_lines.append(("📋 类型", category_cn))
        body_lines.append(("💎 品质", f"{tier_cn}({tier})"))
        body_lines.append(("📝 描述", desc))
        heroes_str = " | ".join(hero_cn_map.get(h, h) for h in heroes)
        body_lines.append(("👥 可用英雄", heroes_str))

        body_h = 0
        for label, value in body_lines:
            wrapped = self._wrap_text(f"{label}: {value}", font_body, content_width)
            body_h += len(wrapped) * LINE_HEIGHT_BODY + SECTION_GAP

        link_h = LINE_HEIGHT_LINK + PADDING if slug else PADDING
        total_height = header_h + body_h + link_h + PADDING * 2

        img_card = Image.new("RGBA", (CARD_WIDTH, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img_card)

        self._draw_rounded_rect(draw, (0, 0, CARD_WIDTH, header_h), HEADER_RADIUS, COLORS["header_bg"])

        thumb_img = None
        img_url = merchant.get("image_url_fg") or merchant.get("image_url", "")
        if img_url:
            thumb_img = await self._fetch_image(img_url)
        if thumb_img:
            thumb_img = thumb_img.resize((THUMB_SIZE, THUMB_SIZE), Image.LANCZOS)
            img_card.paste(thumb_img, (PADDING, PADDING), thumb_img if thumb_img.mode == "RGBA" else None)

        text_x = THUMB_MARGIN + PADDING
        tier_color = TIER_COLORS.get(tier, COLORS["text"])
        draw.text((text_x, PADDING + 8 * SCALE), name, font=font_title, fill=COLORS["text"])
        draw.text((text_x, PADDING + 8 * SCALE + LINE_HEIGHT_TITLE), category_cn, font=font_subtitle, fill=COLORS["text_dim"])

        badge_text = f" {tier_cn} "
        bbox = font_small.getbbox(badge_text)
        bw = bbox[2] - bbox[0] + 8 * SCALE
        badge_y = PADDING + 8 * SCALE + LINE_HEIGHT_TITLE + LINE_HEIGHT_SUBTITLE + 4 * SCALE
        draw.rounded_rectangle(
            (text_x, badge_y, text_x + bw, badge_y + LINE_HEIGHT_SMALL),
            radius=BADGE_RADIUS, fill=tier_color
        )
        draw.text((text_x + 4 * SCALE, badge_y + 2 * SCALE), badge_text.strip(), font=font_small, fill=COLORS["bg"])

        y = header_h + PADDING
        for label, value in body_lines:
            full_text = f"{label}: {value}"
            wrapped = self._wrap_text(full_text, font_body, content_width)
            for line in wrapped:
                draw.text((PADDING, y), line, font=font_body, fill=COLORS["text"])
                y += LINE_HEIGHT_BODY
            y += SECTION_GAP

        if slug:
            link_url = f"https://bazaarforge.gg/merchants/{slug}"
            draw.text((PADDING, y), link_url, font=font_link, fill=COLORS["accent"])

        buf = io.BytesIO()
        img_card.save(buf, format="PNG")
        return buf.getvalue()

    async def render_build_card(self, query: str, search_term: str, builds: list) -> bytes:
        font_title = self._font(24 * SCALE)
        font_subtitle = self._font(FONT_SIZE_SUBTITLE)
        font_body = self._font(15 * SCALE)
        font_small = self._font(FONT_SIZE_TAG)
        font_link = self._font(FONT_SIZE_LINK)

        content_width = BUILD_CARD_WIDTH - PADDING * 2

        header_h = 60 * SCALE
        body_h = 0

        for build in builds:
            bh = 0
            title_lines = self._wrap_text(build["title"], font_subtitle, content_width - INDENT)
            bh += len(title_lines) * LINE_HEIGHT_SUBTITLE
            bh += PADDING
            if build.get("excerpt"):
                excerpt_lines = self._wrap_text(build["excerpt"], font_small, content_width - INDENT)
                bh += len(excerpt_lines) * LINE_HEIGHT_EXCERPT
                bh += SKILL_DESC_GAP
            bh += LINE_HEIGHT_SMALL
            bh += LINE_HEIGHT_LINK
            body_h += bh

        body_h += (len(builds) - 1) * SECTION_GAP
        footer_h = 30 * SCALE

        total_height = header_h + body_h + footer_h + PADDING * 3
        img = Image.new("RGBA", (BUILD_CARD_WIDTH, total_height), COLORS["bg"])
        draw = ImageDraw.Draw(img)

        y = PADDING
        self._draw_rounded_rect(draw, (0, 0, BUILD_CARD_WIDTH, header_h + PADDING), HEADER_RADIUS, COLORS["header_bg"])

        title_text = f"「{query}」推荐阵容"
        draw.text((PADDING, y + 6 * SCALE), title_text, font=font_title, fill=COLORS["text"])
        sub = f"来源: bazaar-builds.net | 共{len(builds)}条结果"
        if search_term != query:
            sub = f"搜索: {search_term} | " + sub
        draw.text((PADDING, y + 34 * SCALE), sub, font=font_small, fill=COLORS["text_dim"])

        y = header_h + PADDING + SECTION_GAP

        for i, build in enumerate(builds):
            num_badge = f" {i + 1} "
            bbox = font_body.getbbox(num_badge)
            bw = bbox[2] - bbox[0] + INDENT
            draw.rounded_rectangle(
                (PADDING, y, PADDING + bw, y + LINE_HEIGHT_SUBTITLE), radius=BADGE_RADIUS, fill=COLORS["accent"]
            )
            draw.text((PADDING + 5 * SCALE, y + 2 * SCALE), num_badge.strip(), font=font_body, fill=COLORS["bg"])

            title_x = PADDING + bw + 8 * SCALE
            title_lines = self._wrap_text(build["title"], font_subtitle, content_width - bw - INDENT)
            for j, tl in enumerate(title_lines):
                draw.text((title_x if j == 0 else PADDING + INDENT, y), tl, font=font_subtitle, fill=COLORS["text"])
                y += LINE_HEIGHT_SUBTITLE

            y += DESC_GAP
            draw.text((PADDING + INDENT, y), f"{build['date']}", font=font_small, fill=COLORS["text_dim"])
            y += LINE_HEIGHT_LINK

            if build.get("excerpt"):
                excerpt_lines = self._wrap_text(build["excerpt"], font_small, content_width - INDENT)
                for el in excerpt_lines:
                    draw.text((PADDING + INDENT, y), el, font=font_small, fill=COLORS["text_dim"])
                    y += LINE_HEIGHT_EXCERPT
                y += SKILL_DESC_GAP

            draw.text((PADDING + INDENT, y), f"{build['link']}", font=font_link, fill=COLORS["accent"])
            y += LINE_HEIGHT_SMALL

            if i < len(builds) - 1:
                y += DESC_GAP
                self._draw_divider(draw, y, BUILD_CARD_WIDTH)
                y += SKILL_DESC_GAP

        y += SECTION_GAP
        more_url = f"https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
        more_text = f"更多阵容: {more_url}"
        more_lines = self._wrap_text(more_text, font_link, content_width)
        for ml in more_lines:
            draw.text((PADDING, y), ml, font=font_link, fill=COLORS["green"])
            y += LINE_HEIGHT_LINK

        buf_build = io.BytesIO()
        img.save(buf_build, format="PNG")
        return buf_build.getvalue()
