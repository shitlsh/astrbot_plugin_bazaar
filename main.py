import asyncio
import inspect
import json
import os
import re
import time
import html as html_module
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, TypeVar
from functools import lru_cache

import aiohttp

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger, AstrBotConfig
import astrbot.api.message_components as Comp

T = TypeVar('T')


class LRUCache:
    """线程安全的 LRU 缓存，支持 TTL 过期和内存大小限制"""
    
    def __init__(self, max_size: int = 500, max_memory_mb: float = 50.0):
        self._cache: OrderedDict[str, tuple[float, float, Any]] = OrderedDict()  # key -> (timestamp, ttl, value)
        self._max_size = max_size
        self._max_memory = max_memory_mb * 1024 * 1024  # bytes
        self._current_memory = 0
        self._hits = 0
        self._misses = 0
    
    def _estimate_size(self, value: Any) -> int:
        """估算值的内存大小"""
        if isinstance(value, bytes):
            return len(value)
        elif isinstance(value, str):
            return len(value.encode('utf-8'))
        elif isinstance(value, (list, dict)):
            return len(json.dumps(value, ensure_ascii=False).encode('utf-8'))
        return 1024  # 默认 1KB
    
    def get(self, key: str) -> tuple[bool, Any]:
        """获取缓存值，返回 (是否命中, 值)"""
        if key not in self._cache:
            self._misses += 1
            return False, None
        
        timestamp, ttl, value = self._cache[key]
        if ttl > 0 and (time.time() - timestamp) > ttl:
            # 过期
            self._remove(key)
            self._misses += 1
            return False, None
        
        # 移动到末尾（最近使用）
        self._cache.move_to_end(key)
        self._hits += 1
        return True, value
    
    def set(self, key: str, value: Any, ttl: float = 0):
        """设置缓存值"""
        size = self._estimate_size(value)
        
        # 如果已存在，先移除旧值
        if key in self._cache:
            self._remove(key)
        
        # 检查是否需要清理
        while (len(self._cache) >= self._max_size or 
               (self._max_memory > 0 and self._current_memory + size > self._max_memory)):
            if not self._cache:
                break
            # 移除最旧的
            oldest_key = next(iter(self._cache))
            self._remove(oldest_key)
        
        self._cache[key] = (time.time(), ttl, value)
        self._current_memory += size
    
    def _remove(self, key: str):
        """移除缓存项"""
        if key in self._cache:
            _, _, value = self._cache.pop(key)
            self._current_memory -= self._estimate_size(value)
    
    def clear(self):
        """清空缓存"""
        self._cache.clear()
        self._current_memory = 0
    
    def cleanup_expired(self) -> int:
        """清理过期项，返回清理数量"""
        now = time.time()
        expired = []
        for key, (timestamp, ttl, _) in self._cache.items():
            if ttl > 0 and (now - timestamp) > ttl:
                expired.append(key)
        for key in expired:
            self._remove(key)
        return len(expired)
    
    def stats(self) -> dict:
        """返回缓存统计"""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "memory_mb": round(self._current_memory / 1024 / 1024, 2),
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total * 100, 1) if total > 0 else 0,
        }

BUILDS_API = "https://bazaar-builds.net/wp-json/wp/v2"
DEFAULT_BUILD_COUNT = 5

FORGE_SUPABASE_URL = "https://cwlgghqlqvpbmfuvkvle.supabase.co"
FORGE_ANON_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImN3bGdnaHFscXZwYm1mdXZrdmxlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjQwODIzNDYsImV4cCI6MjA3OTY1ODM0Nn0."
    "fuVBdRQ1rMPerBGnlS08FLOvZKSlICwtJq1WKEj7YA8"
)
FORGE_HEADERS = {
    "apikey": FORGE_ANON_KEY,
    "Authorization": f"Bearer {FORGE_ANON_KEY}",
}
FORGE_BUILD_URL = "https://bazaarforge.gg/builds"

# 缓存 TTL（秒）
CACHE_TTL_BUILDS = 43200      # 阵容缓存 12 小时
CACHE_TTL_TIERLIST = 43200    # Tier List 缓存 12 小时
CACHE_TTL_NEWS = 1800         # 新闻缓存 30 分钟
CACHE_TTL_ITEM_UUID = 3600    # 物品 UUID 缓存 1 小时
CACHE_TTL_IMAGE = 86400       # 图片缓存 24 小时
CACHE_TTL_RENDER = 7200       # 渲染结果缓存 2 小时

# 缓存大小限制
CACHE_MAX_SIZE = 1000         # 最大缓存条目数
CACHE_MAX_MEMORY_MB = 100     # 最大内存占用 MB

TIER_LIST_THRESHOLDS = {"S": 15.0, "A": 8.0, "B": 3.0, "C": 0.0}

HERO_EN_MAP = {
    "杜利": "Dooley", "朱尔斯": "Jules", "马克": "Mak",
    "皮格马利翁": "Pygmalien", "斯黛拉": "Stelle", "瓦妮莎": "Vanessa",
    "猪猪": "Pygmalien", "猪": "Pygmalien", "猪哥": "Pygmalien",
    "鸡煲": "Dooley", "机宝": "Dooley", "海盗": "Vanessa",
    "海盗姐": "Vanessa", "黑妹": "Stelle", "厨子": "Jules",
    "大厨": "Jules", "厨师": "Jules",
}

VICTORY_TYPE_CN = {
    "Health": "血量胜", "Kill": "击杀胜", "Income": "收入胜",
    "Level": "等级胜", "Time": "时间胜",
}

BUILD_FILTER_PATTERNS = re.compile(
    r'(?i)\b(?:patch|hotfix|update|changelog|maintenance|downtime|release\s*note|dev\s*blog|news|new\s*feature|announcement|preview|season\s*\d|guide|tutorial|tier\s*list|ranking)\b'
)
BUILD_POSITIVE_PATTERN = re.compile(
    r'(?i)(?:build|10-\d|legend|#\d{3,}|comp|lineup|loadout|deck|setup|阵容)'
)

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
    exact = [r for r in results if query.lower() in name_func(r).lower()]
    if len(exact) == 1:
        return exact[0], None
    display = exact[:15] if exact else results[:15]
    total = len(exact) if exact else len(results)
    names = [f"  {name_func(r)}" for r in display]
    return None, f"找到{total}个匹配结果，请精确输入:\n" + "\n".join(names)


def _edit_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return _edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (0 if c1 == c2 else 1)))
        prev = curr
    return prev[len(s2)]


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
    "event_detail.json": f"{GITHUB_RAW}/event_detail.json",
    "event_encounters.json": f"{GITHUB_RAW}/event_encounters.json",
}

STEAM_NEWS_API = "https://store.steampowered.com/events/ajaxgetpartnereventspageable/"
STEAM_APP_ID = 1617400
DEFAULT_NEWS_COUNT = 1

HERO_CN_MAP = {
    "Common": "通用", "Dooley": "杜利", "Jules": "朱尔斯",
    "Mak": "马克", "Pygmalien": "皮格马利翁", "Stelle": "斯黛拉", "Vanessa": "瓦妮莎",
}


def _strip_bbcode(text: str) -> str:
    text = re.sub(r'\[previewyoutube[^\]]*\].*?\[/previewyoutube\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[img\].*?\[/img\]', '', text, flags=re.DOTALL)
    text = re.sub(r'\[url=[^\]]*\](.*?)\[/url\]', r'\1', text)
    heading_map = {"h1": "# ", "h2": "## ", "h3": "### "}
    for tag, prefix in heading_map.items():
        text = re.sub(rf'\[{tag}\]\s*\[b\](.*?)\[/b\]\s*\[/{tag}\]', rf'\n{prefix}\1\n', text)
        text = re.sub(rf'\[{tag}\](.*?)\[/{tag}\]', rf'\n{prefix}\1\n', text)
    text = re.sub(r'\[b\](.*?)\[/b\]', r'\1', text)
    text = re.sub(r'\[i\](.*?)\[/i\]', r'\1', text)
    text = re.sub(r'\[u\](.*?)\[/u\]', r'\1', text)
    text = re.sub(r'\[list\]', '\n', text)
    text = re.sub(r'\[/list\]', '\n', text)
    text = re.sub(r'\[\*\]', '\n- ', text)
    text = re.sub(r'\[/p\]', '\n', text)
    for tag in ['p', 'table', 'tr', 'td', 'th', 'strike', 'spoiler', 'noparse', 'code']:
        text = re.sub(rf'\[/?{tag}[^\]]*\]', '', text)
    text = re.sub(r'\[/?[a-zA-Z][^\]]*\]', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

TIER_MAP = {
    "bronze": "Bronze", "silver": "Silver", "gold": "Gold", "diamond": "Diamond",
    "铜": "Bronze", "青铜": "Bronze", "银": "Silver", "白银": "Silver",
    "金": "Gold", "黄金": "Gold", "钻石": "Diamond", "钻": "Diamond",
}


ALIAS_CATEGORIES = ["hero", "item", "monster", "skill", "tag", "tier", "size"]


CONFIG_KEY_MAP = {
    "hero": "hero_aliases",
    "item": "item_aliases",
    "monster": "monster_aliases",
    "skill": "skill_aliases",
    "tag": "tag_aliases",
    "tier": "tier_aliases",
    "size": "size_aliases",
}


@register("astrbot_plugin_bazaar", "大巴扎小助手", "The Bazaar 游戏数据查询，支持怪物、物品、技能、事件、阵容、更新公告、物品评级查询，图片卡片展示，AI 人格预设与工具自动调用", "v1.1.2")
class BazaarPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config
        self.monsters = {}
        self.items = []
        self.skills = []
        self.events = []
        self.merchants = []
        self.aliases: dict[str, dict[str, str]] = {}
        self._entity_names: set = set()
        self.plugin_dir = Path(os.path.dirname(os.path.abspath(__file__)))
        self.renderer = None
        self._session: aiohttp.ClientSession | None = None
        
        # 从配置读取缓存设置
        cache_max_size = CACHE_MAX_SIZE
        cache_max_memory = CACHE_MAX_MEMORY_MB
        if config:
            cache_max_size = max(100, min(int(config.get("cache_max_size", CACHE_MAX_SIZE)), 5000))
            cache_max_memory = max(10, min(int(config.get("cache_max_memory_mb", CACHE_MAX_MEMORY_MB)), 500))
        
        # 优化：使用 LRU 缓存替代普通字典
        self._cache = LRUCache(max_size=cache_max_size, max_memory_mb=cache_max_memory)
        # 搜索索引
        self._search_index: dict[str, set[str]] = {}
        self._index_built = False
        # 缓存清理计数器
        self._request_count = 0
        self._cleanup_interval = 100  # 每 100 次请求清理一次过期缓存

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=20),
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            )
        return self._session

    def _maybe_cleanup_cache(self):
        """定期清理过期缓存"""
        self._request_count += 1
        if self._request_count >= self._cleanup_interval:
            self._request_count = 0
            cleaned = self._cache.cleanup_expired()
            if cleaned > 0:
                logger.debug(f"缓存清理: 移除 {cleaned} 个过期项")

    async def _cached_request(self, key: str, ttl: int, fetch_fn: Callable) -> Any:
        """优化的缓存请求方法"""
        self._maybe_cleanup_cache()
        
        hit, value = self._cache.get(key)
        if hit:
            return value
        
        data = await fetch_fn()
        if data:
            self._cache.set(key, data, ttl)
        return data

    def _get_img_cache(self, key: str, ttl: int) -> bytes | None:
        """获取图片/渲染缓存"""
        hit, value = self._cache.get(key)
        return value if hit else None

    def _set_img_cache(self, key: str, data: bytes, ttl: int = CACHE_TTL_RENDER):
        """设置图片/渲染缓存"""
        self._cache.set(key, data, ttl)

    def _resolve_hero_name(self, query: str) -> str | None:
        ql = query.strip().lower()
        hero_map = {**{k.lower(): v for k, v in HERO_EN_MAP.items()},
                    **{v.lower(): v for v in HERO_EN_MAP.values()}}
        for alias, target in self.aliases.get("hero", {}).items():
            hero_map[alias.lower()] = target
        return hero_map.get(ql)

    async def _forge_get_item_uuids(self, search_term: str) -> list[str]:
        async def _fetch():
            session = await self._get_session()
            url = f"{FORGE_SUPABASE_URL}/rest/v1/items"
            params = {"select": "id,name", "name": f"ilike.*{search_term}*", "limit": "10"}
            try:
                async with session.get(url, params=params, headers=FORGE_HEADERS) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return data
            except Exception as e:
                logger.debug(f"BazaarForge items 查询失败: {e}")
                return []
        items = await self._cached_request(f"forge_uuid:{search_term.lower()}", CACHE_TTL_ITEM_UUID, _fetch)
        return [it["id"] for it in items if it.get("id")]

    async def _forge_query_builds(self, params: dict) -> list:
        session = await self._get_session()
        url = f"{FORGE_SUPABASE_URL}/rest/v1/builds"
        try:
            async with session.get(url, params=params, headers=FORGE_HEADERS) as resp:
                if resp.status == 200:
                    return await resp.json()
        except Exception as e:
            logger.debug(f"BazaarForge builds 查询失败: {e}")
        return []

    async def _fetch_builds_forge(self, search_term: str, count: int) -> list:
        async def _fetch():
            select_fields = "id,title,hero,wins,max_health,victory_type,level,screenshot_url,created_at,item_ids"
            fetch_limit = str(min(count + 5, 30))

            tokens = search_term.split()
            hero_name = None
            item_tokens = []
            for tok in tokens:
                resolved = self._resolve_hero_name(tok)
                if resolved and not hero_name:
                    hero_name = resolved
                else:
                    item_tokens.append(tok)

            if not hero_name:
                hero_name = self._resolve_hero_name(search_term)
                if hero_name:
                    item_tokens = []

            all_uuids = []
            if item_tokens:
                full_item = " ".join(item_tokens)
                uuids = await self._forge_get_item_uuids(full_item)
                if uuids:
                    all_uuids.extend(uuids)
                else:
                    uuid_tasks = [self._forge_get_item_uuids(tok) for tok in item_tokens]
                    results = await asyncio.gather(*uuid_tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, list):
                            all_uuids.extend(r)
            elif not hero_name:
                all_uuids = await self._forge_get_item_uuids(search_term)

            all_builds = []
            seen_ids = set()

            def _dedup_append(data):
                for b in data:
                    bid = b.get("id")
                    if bid and bid not in seen_ids:
                        all_builds.append(b)
                        seen_ids.add(bid)

            if hero_name and all_uuids:
                tasks = []
                for uuid in all_uuids[:5]:
                    tasks.append(self._forge_query_builds({
                        "select": select_fields,
                        "hero": f"eq.{hero_name}",
                        "item_ids": f"cs.{{\"{uuid}\"}}",
                        "order": "wins.desc",
                        "limit": fetch_limit,
                    }))
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        _dedup_append(r)

            if hero_name and not all_builds:
                data = await self._forge_query_builds({
                    "select": select_fields,
                    "hero": f"eq.{hero_name}",
                    "order": "wins.desc",
                    "limit": fetch_limit,
                })
                if data:
                    if all_uuids:
                        uuid_set = set(all_uuids)
                        scored = []
                        for b in data:
                            bids = set(b.get("item_ids") or [])
                            overlap = len(bids & uuid_set)
                            scored.append((overlap, b))
                        scored.sort(key=lambda x: (-x[0], -(x[1].get("wins") or 0)))
                        return [b for _, b in scored]
                    return data

            if all_uuids and not all_builds:
                tasks = []
                for uuid in all_uuids[:5]:
                    tasks.append(self._forge_query_builds({
                        "select": select_fields,
                        "item_ids": f"cs.{{\"{uuid}\"}}",
                        "order": "wins.desc",
                        "limit": fetch_limit,
                    }))
                results = await asyncio.gather(*tasks, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        _dedup_append(r)

            if not all_builds:
                all_builds = await self._forge_query_builds({
                    "select": select_fields,
                    "title": f"ilike.*{search_term}*",
                    "order": "wins.desc",
                    "limit": fetch_limit,
                })

            return all_builds
        raw = await self._cached_request(f"forge_builds:{search_term.lower()}:{count}", CACHE_TTL_BUILDS, _fetch)
        builds = []
        for b in raw[:count]:
            victory = b.get("victory_type", "")
            victory_cn = VICTORY_TYPE_CN.get(victory, victory)
            date_str = (b.get("created_at") or "")[:10]
            wins = b.get("wins", 0)
            level = b.get("level", 0)
            max_hp = b.get("max_health", 0)
            hero = b.get("hero", "")
            hero_cn = HERO_CN_MAP.get(hero, hero)

            excerpt_parts = []
            if hero:
                excerpt_parts.append(f"{hero_cn}({hero})")
            if wins:
                excerpt_parts.append(f"{wins}胜")
            if victory_cn:
                excerpt_parts.append(victory_cn)
            if level:
                excerpt_parts.append(f"Lv.{level}")
            if max_hp:
                excerpt_parts.append(f"HP:{max_hp}")

            builds.append({
                "title": b.get("title", f"{hero} Build"),
                "link": f"{FORGE_BUILD_URL}/{b.get('id', '')}",
                "date": date_str,
                "excerpt": " | ".join(excerpt_parts),
                "image_url": b.get("screenshot_url", ""),
                "source": "forge",
                "wins": wins,
                "victory_type": victory_cn,
                "level": level,
                "max_health": max_hp,
                "hero": hero,
            })
        return builds

    async def _fetch_builds_wp(self, search_term: str, count: int) -> list:
        async def _fetch():
            url = f"{BUILDS_API}/posts"
            params = {
                "search": search_term,
                "per_page": min(count + 5, 20),
                "_fields": "id,title,link,date,excerpt,featured_media",
            }
            try:
                session = await self._get_session()
                async with session.get(url, params=params) as resp:
                    if resp.status != 200:
                        return []
                    posts = await resp.json()

                filtered = []
                for post in posts:
                    if len(filtered) >= count:
                        break
                    title = html_module.unescape(post.get("title", {}).get("rendered", ""))
                    if BUILD_FILTER_PATTERNS.search(title):
                        continue
                    if not BUILD_POSITIVE_PATTERN.search(title):
                        continue
                    filtered.append(post)

                async def _resolve_media(media_id):
                    if not media_id:
                        return ""
                    media_url = f"{BUILDS_API}/media/{media_id}?_fields=source_url,media_details"
                    try:
                        async with session.get(media_url) as mresp:
                            if mresp.status == 200:
                                media = await mresp.json()
                                sizes = media.get("media_details", {}).get("sizes", {})
                                for size_key in ("large", "medium_large", "1536x1536", "medium"):
                                    if size_key in sizes:
                                        return sizes[size_key]["source_url"]
                                return media.get("source_url", "")
                    except Exception:
                        pass
                    return ""

                media_tasks = [_resolve_media(p.get("featured_media", 0)) for p in filtered]
                media_urls = await asyncio.gather(*media_tasks, return_exceptions=True)

                builds = []
                for post, img_url in zip(filtered, media_urls):
                    title = html_module.unescape(post.get("title", {}).get("rendered", ""))
                    excerpt_raw = post.get("excerpt", {}).get("rendered", "")
                    excerpt_text = html_module.unescape(_strip_html(excerpt_raw))
                    builds.append({
                        "title": title,
                        "link": post.get("link", ""),
                        "date": post.get("date", "")[:10],
                        "excerpt": excerpt_text[:200],
                        "image_url": img_url if isinstance(img_url, str) else "",
                        "source": "wp",
                    })
                return builds
            except Exception as e:
                logger.warning(f"查询阵容失败 (bazaar-builds.net): {e}")
                return []
        return await self._cached_request(f"wp_builds:{search_term.lower()}:{count}", CACHE_TTL_BUILDS, _fetch)

    async def _fetch_builds_combined(self, search_term: str, count: int) -> list:
        if self.config:
            priority = self.config.get("build_source_priority", "forge_first")
        else:
            priority = "forge_first"

        if priority == "wp_only":
            return await self._fetch_builds_wp(search_term, count)
        if priority == "forge_only":
            return await self._fetch_builds_forge(search_term, count)

        forge_task = asyncio.create_task(self._fetch_builds_forge(search_term, count))
        wp_task = asyncio.create_task(self._fetch_builds_wp(search_term, count))

        if priority == "wp_first":
            primary = await wp_task
            if len(primary) >= count:
                forge_task.cancel()
                return primary[:count]
            secondary = await forge_task
            return (primary + secondary)[:count]
        else:
            primary = await forge_task
            if len(primary) >= count:
                wp_task.cancel()
                return primary[:count]
            secondary = await wp_task
            return (primary + secondary)[:count]

    async def _fetch_tierlist(self, hero_en: str) -> list:
        async def _fetch():
            session = await self._get_session()
            url = f"{FORGE_SUPABASE_URL}/rest/v1/items"
            params = {
                "select": "id,name,build_count,hero_stats,starting_tier,size,tags,image_url",
                f"hero_stats->>{hero_en}": "gt.0",
                "order": f"hero_stats->>{hero_en}.desc",
                "limit": "60",
            }
            try:
                async with session.get(url, params=params, headers=FORGE_HEADERS) as resp:
                    if resp.status != 200:
                        logger.warning(f"BazaarForge tierlist 查询失败: HTTP {resp.status}")
                        return []
                    return await resp.json()
            except Exception as e:
                logger.warning(f"BazaarForge tierlist 查询失败: {e}")
                return []
        raw = await self._cached_request(f"tierlist:{hero_en}", CACHE_TTL_TIERLIST, _fetch)

        tier_items = {"S": [], "A": [], "B": [], "C": []}
        for item in raw:
            hero_stats = item.get("hero_stats", {})
            pct = float(hero_stats.get(hero_en, 0))
            if pct <= 0:
                continue
            cn_name = ""
            for local_item in self.items:
                if local_item.get("name_en", "").lower() == item.get("name", "").lower():
                    cn_name = local_item.get("name_cn", "")
                    break
            entry = {
                "name": item.get("name", ""),
                "name_cn": cn_name,
                "pct": pct,
                "build_count": item.get("build_count", 0),
                "tier": item.get("starting_tier", ""),
                "size": item.get("size", ""),
                "tags": item.get("tags", []),
                "image_url": item.get("image_url", ""),
            }
            if pct >= TIER_LIST_THRESHOLDS["S"]:
                tier_items["S"].append(entry)
            elif pct >= TIER_LIST_THRESHOLDS["A"]:
                tier_items["A"].append(entry)
            elif pct >= TIER_LIST_THRESHOLDS["B"]:
                tier_items["B"].append(entry)
            else:
                tier_items["C"].append(entry)

        for grade in tier_items:
            tier_items[grade].sort(key=lambda x: x["pct"], reverse=True)

        return tier_items

    def _parse_alias_value(self, val) -> dict:
        if isinstance(val, dict):
            return dict(val)
        if isinstance(val, str):
            val = val.strip()
            if val:
                try:
                    parsed = json.loads(val)
                    if isinstance(parsed, dict):
                        return parsed
                except (json.JSONDecodeError, ValueError):
                    logger.warning(f"别名配置 JSON 解析失败: {val[:100]}")
        return {}

    def _load_aliases(self):
        self.aliases = {}
        if self.config:
            for cat, config_key in CONFIG_KEY_MAP.items():
                val = self.config.get(config_key, {})
                self.aliases[cat] = self._parse_alias_value(val)
        else:
            path = self.plugin_dir / "data" / "aliases.json"
            try:
                if path.exists():
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    for cat in ALIAS_CATEGORIES:
                        self.aliases[cat] = data.get(cat, {})
                else:
                    for cat in ALIAS_CATEGORIES:
                        self.aliases[cat] = {}
            except Exception as e:
                logger.error(f"加载别名配置失败: {e}")
                for cat in ALIAS_CATEGORIES:
                    self.aliases[cat] = {}

    def _save_aliases(self):
        if self.config:
            for cat, config_key in CONFIG_KEY_MAP.items():
                self.config[config_key] = json.dumps(self.aliases.get(cat, {}), ensure_ascii=False, indent=2)
            try:
                self.config.save_config()
            except Exception as e:
                logger.error(f"保存别名配置失败: {e}")
        else:
            path = self.plugin_dir / "data" / "aliases.json"
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self.aliases, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"保存别名配置失败: {e}")

    def _reload_aliases_if_changed(self):
        if self.config:
            old = self.aliases.copy()
            self._load_aliases()
            if self.aliases != old:
                self._build_vocab()
            return
        path = self.plugin_dir / "data" / "aliases.json"
        try:
            mtime = path.stat().st_mtime if path.exists() else 0
        except OSError:
            return
        if mtime != getattr(self, "_aliases_mtime", 0):
            self._load_aliases()
            self._aliases_mtime = mtime
            self._build_vocab()

    def _resolve_alias(self, query: str) -> str:
        self._reload_aliases_if_changed()
        q = query.strip()
        ql = q.lower()
        for cat in ("item", "monster", "skill"):
            for alias, target in self.aliases.get(cat, {}).items():
                if ql == alias.lower():
                    return target
        for alias, target in self.aliases.get("hero", {}).items():
            if ql == alias.lower():
                return target
        return q

    async def initialize(self):
        self._load_data()
        self._load_aliases()
        if not self.config:
            path = self.plugin_dir / "data" / "aliases.json"
            try:
                self._aliases_mtime = path.stat().st_mtime if path.exists() else 0
            except OSError:
                self._aliases_mtime = 0
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
        await self._register_persona()
        logger.info(
            f"Bazaar 插件加载完成: {len(self.monsters)} 个怪物, "
            f"{len(self.items)} 个物品, {len(self.skills)} 个技能, "
            f"{len(self.events)} 个事件"
        )

    async def _register_persona(self):
        PERSONA_ID = "bazaar_helper"
        SYSTEM_PROMPT = (
            "你是「大巴扎小助手」，一个专门为 The Bazaar (大巴扎) 卡牌游戏提供帮助的 AI 助手。\n"
            "The Bazaar 是由 Tempo Storm 开发的 Roguelike 卡牌对战游戏（也叫大巴扎、巴扎）。\n\n"
            "你的职责：\n"
            "1. 帮助玩家查询游戏中的物品、怪物、技能信息\n"
            "2. 为玩家推荐阵容搭配和策略\n"
            "3. 解答游戏机制和玩法问题\n\n"
            "你拥有以下工具来查询游戏数据：\n"
            "- bazaar_query_item: 查询物品详情（属性、技能、附魔、任务等）\n"
            "- bazaar_query_monster: 查询怪物详情（血量、技能、掉落等）\n"
            "- bazaar_query_skill: 查询技能详情（描述、适用英雄等）\n"
            "- bazaar_query_event: 查询事件选项和奖励\n"
            "- bazaar_search: 多条件搜索物品/怪物/技能/事件\n"
            "- bazaar_query_build: 查询社区推荐阵容（来自 BazaarForge 和 bazaar-builds.net）\n"
            "- bazaar_get_news: 查询游戏最近的更新公告/补丁说明\n"
            "- bazaar_query_tierlist: 查询英雄物品评级（Tier List，各物品使用率排名）\n"
            "- bazaar_query_merchant: 查询商人/训练师信息（出售内容、品质、可遇到英雄）\n\n"
            "重要规则：\n"
            "- 当用户提到任何可能是游戏内容的名词时（如物品名、怪物名、英雄名），优先使用工具查询，不要凭空编造信息\n"
            "- 当用户问「怎么搭配」「怎么玩」「推荐阵容」时，使用 bazaar_query_build 工具\n"
            "- 当用户问某个东西「是什么」「有什么效果」时，先用 bazaar_query_item 查询\n"
            "- 当用户问「最近更新了什么」「有什么新补丁」「更新公告」时，使用 bazaar_get_news 工具\n"
            "- 当用户问「哪些物品好用」「物品推荐」「装备排名」「tier list」时，使用 bazaar_query_tierlist 工具\n"
            "- 当用户问「商人」「在哪买」「训练师」「谁卖武器」等问题时，使用 bazaar_query_merchant 工具\n"
            "- 工具返回的是纯文本信息。如果用户想看图片卡片，建议他们使用 /tbzitem、/tbzmonster、/tbzskill、/tbztier、/tbzmerchant 等命令\n"
            "- 在回复中整合工具返回的数据，并在末尾告知用户可以使用对应命令查看图片版本\n"
            "- 用中文回复玩家，语气友好专业\n"
            "- 游戏中的英雄包括：Dooley(杜利/鸡煲)、Jules(朱尔斯/厨子)、Mak(马克)、Pygmalien(皮格马利翁/猪猪)、Stelle(斯黛拉/黑妹)、Vanessa(瓦妮莎/海盗) 等\n"
            "- 物品品质分为：Bronze(铜/青铜)、Silver(银)、Gold(金/黄金)、Diamond(钻石)\n"
            "- 物品有不同尺寸：Small(小型)、Medium(中型)、Large(大型)"
        )
        BEGIN_DIALOGS = [
            "你好！我想了解一下 The Bazaar 这个游戏",
            "你好！我是大巴扎小助手，专门帮助玩家查询 The Bazaar 游戏的物品、怪物、技能信息，以及推荐阵容搭配。你可以直接问我任何关于游戏的问题，比如「船锚怎么搭配」「放大镜是什么效果」「有哪些黄金武器」等。有什么我能帮你的吗？",
        ]
        TOOLS = [
            "bazaar_query_item",
            "bazaar_query_monster",
            "bazaar_query_skill",
            "bazaar_query_event",
            "bazaar_search",
            "bazaar_query_build",
            "bazaar_get_news",
            "bazaar_query_tierlist",
            "bazaar_query_merchant",
        ]
        try:
            pm = self.context.persona_manager
            try:
                result = pm.get_persona(PERSONA_ID)
                if inspect.isawaitable(result):
                    result = await result
                if result:
                    update_result = pm.update_persona(
                        persona_id=PERSONA_ID,
                        system_prompt=SYSTEM_PROMPT,
                        begin_dialogs=BEGIN_DIALOGS,
                        tools=TOOLS,
                    )
                    if inspect.isawaitable(update_result):
                        await update_result
                    logger.info("已更新「大巴扎小助手」人格预设")
                    return
            except (ValueError, Exception):
                pass
            create_result = pm.create_persona(
                persona_id=PERSONA_ID,
                system_prompt=SYSTEM_PROMPT,
                begin_dialogs=BEGIN_DIALOGS,
                tools=TOOLS,
            )
            if inspect.isawaitable(create_result):
                await create_result
            logger.info("已创建「大巴扎小助手」人格预设")
        except Exception as e:
            logger.warning(f"人格预设注册失败（不影响插件使用）: {e}")

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
        for cat in ALIAS_CATEGORIES:
            vtype = cat
            if cat in ("item", "monster", "skill"):
                continue
            for alias, target in self.aliases.get(cat, {}).items():
                vocab[alias.lower()] = (vtype, target)
        for k, v in TIER_MAP.items():
            if len(k) >= 2:
                vocab[k] = ("tier", v)
        tier_cn_to_en = {"青铜": "Bronze", "白银": "Silver", "黄金": "Gold", "钻石": "Diamond", "传奇": "Legendary"}
        for cn, en in tier_cn_to_en.items():
            vocab[cn] = ("tier", en)
            vocab[en.lower()] = ("tier", en)
        self._vocab = vocab
        self._vocab_sorted = sorted(vocab.keys(), key=len, reverse=True)
        names = set()
        for item in self.items:
            cn = item.get("name_cn", "").strip()
            en = item.get("name_en", "").strip()
            if cn:
                names.add(cn.lower())
            if en:
                names.add(en.lower())
        for key, monster in self.monsters.items():
            names.add(key.lower())
            zh = monster.get("name_zh", "").strip()
            en = monster.get("name", "").strip()
            if zh:
                names.add(zh.lower())
            if en:
                names.add(en.lower())
        for skill in self.skills:
            cn = skill.get("name_cn", "").strip()
            en = skill.get("name_en", "").strip()
            if cn:
                names.add(cn.lower())
            if en:
                names.add(en.lower())
        for ev in self.events:
            n = ev.get("name", "").strip()
            ne = ev.get("name_en", "").strip()
            if n:
                names.add(n.lower())
            if ne:
                names.add(ne.lower())
        self._entity_names = names
        
        # 构建搜索索引
        self._build_search_index()

    def _build_search_index(self):
        """构建倒排搜索索引，加速关键词搜索"""
        index: dict[str, set[tuple[str, int]]] = {}  # keyword -> set of (type, index)
        
        def add_to_index(keyword: str, entity_type: str, entity_index: int):
            if not keyword or len(keyword) < 2:
                return
            kw = keyword.lower()
            if kw not in index:
                index[kw] = set()
            index[kw].add((entity_type, entity_index))
            # 添加子串索引（用于模糊搜索）
            if len(kw) >= 3:
                for i in range(len(kw) - 1):
                    sub = kw[i:i+2]
                    if sub not in index:
                        index[sub] = set()
                    index[sub].add((entity_type, entity_index))
        
        # 索引物品
        for i, item in enumerate(self.items):
            add_to_index(item.get("name_cn", ""), "item", i)
            add_to_index(item.get("name_en", ""), "item", i)
            for tag in item.get("tags", "").split("|"):
                for part in tag.strip().split("/"):
                    add_to_index(part.strip(), "item", i)
            for tag in item.get("hidden_tags", "").split("|"):
                for part in tag.strip().split("/"):
                    add_to_index(part.strip(), "item", i)
            for hero in item.get("heroes", "").split("/"):
                add_to_index(hero.strip(), "item", i)
        
        # 索引怪物
        for i, (key, monster) in enumerate(self.monsters.items()):
            add_to_index(key, "monster", i)
            add_to_index(monster.get("name", ""), "monster", i)
            add_to_index(monster.get("name_zh", ""), "monster", i)
        
        # 索引技能
        for i, skill in enumerate(self.skills):
            add_to_index(skill.get("name_cn", ""), "skill", i)
            add_to_index(skill.get("name_en", ""), "skill", i)
            for hero in skill.get("heroes", "").split("/"):
                add_to_index(hero.strip(), "skill", i)
        
        # 索引事件
        for i, ev in enumerate(self.events):
            add_to_index(ev.get("name", ""), "event", i)
            add_to_index(ev.get("name_en", ""), "event", i)
        
        self._search_index = index
        self._index_built = True
        logger.debug(f"搜索索引构建完成: {len(index)} 个关键词")

    def _search_by_index(self, keyword: str, entity_type: str = None) -> set[tuple[str, int]]:
        """使用索引快速搜索"""
        if not self._index_built:
            return set()
        
        kw = keyword.lower()
        results = set()
        
        # 精确匹配
        if kw in self._search_index:
            results.update(self._search_index[kw])
        
        # 子串匹配（如果精确匹配结果不够）
        if len(results) < 5 and len(kw) >= 2:
            for index_key, entries in self._search_index.items():
                if kw in index_key or index_key in kw:
                    results.update(entries)
        
        # 过滤类型
        if entity_type:
            results = {r for r in results if r[0] == entity_type}
        
        return results

    def _is_entity_name(self, text: str) -> bool:
        tl = text.lower()
        if tl in self._entity_names:
            return True
        for name in self._entity_names:
            if len(tl) >= 2 and tl in name:
                return True
        return False

    def _smart_tokenize(self, query: str) -> list:
        if self._is_entity_name(query):
            return [query]
        tokens = query.split()
        result = []
        for token in tokens:
            if ":" in token:
                result.append(token)
                continue
            if self._is_entity_name(token):
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
            ("event_detail.json", "events", []),
            ("merchants_db.json", "merchants", []),
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

        self._enrich_events(data_dir)

    def _enrich_events(self, data_dir: Path):
        enc_path = data_dir / "event_encounters.json"
        if not enc_path.exists() or not self.events:
            return
        try:
            with open(enc_path, "r", encoding="utf-8") as f:
                encounters = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"加载 event_encounters.json 失败: {e}")
            return

        enc_map = {}
        for enc in encounters:
            iname = enc.get("InternalName", "").strip().lower()
            title = enc.get("Localization", {}).get("Title", {}).get("Text", "").strip().lower()
            info = {"heroes": enc.get("Heroes", []), "tier": enc.get("StartingTier", "")}
            if iname:
                enc_map[iname] = info
            if title and title != iname:
                enc_map[title] = info

        matched = 0
        for ev in self.events:
            name_en = ev.get("name_en", "").strip().lower()
            if not name_en:
                continue
            match = enc_map.get(name_en)
            if not match:
                candidates = [(k, v) for k, v in enc_map.items() if name_en in k]
                if len(candidates) == 1:
                    match = candidates[0][1]
                elif len(candidates) > 1:
                    logger.debug(f"事件匹配歧义 '{name_en}': {[c[0] for c in candidates]}，跳过子串匹配")
            if match:
                ev["heroes"] = match["heroes"]
                ev["tier"] = match["tier"]
                matched += 1

        if matched:
            logger.info(f"事件数据增强: {matched}/{len(self.events)} 条事件已补充英雄和品质信息")

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

    def _format_event_info(self, event_data: dict) -> str:
        name = event_data.get("name", "")
        name_en = event_data.get("name_en", "")

        tier = event_data.get("tier", "")
        tier_emoji = TIER_EMOJI.get(tier, "")
        tier_str = f" {tier_emoji}{tier}" if tier else ""
        lines = [f"🎲 【{name}】({name_en}){tier_str}", ""]

        heroes = event_data.get("heroes", [])
        if heroes:
            hero_display = ", ".join(f"{HERO_CN_MAP.get(h, h)}({h})" for h in heroes)
            lines.append(f"🦸 适用英雄: {hero_display}")
            lines.append("")

        choices = event_data.get("choices", [])
        if choices:
            lines.append(f"📋 选项 ({len(choices)}个):")
            for i, choice in enumerate(choices, 1):
                c_name_zh = choice.get("name_zh", "")
                c_name_en = choice.get("name", "")
                desc_zh = choice.get("description_zh", "")
                desc_en = choice.get("description", "")
                display_name = c_name_zh if c_name_zh else c_name_en
                if c_name_zh and c_name_en:
                    display_name = f"{c_name_zh}({c_name_en})"
                lines.append(f"  {i}. {display_name}")
                desc = desc_zh if desc_zh else desc_en
                if desc:
                    lines.append(f"     {desc}")
            lines.append("")

        return "\n".join(lines)

    def _fuzzy_suggest(self, query: str, limit: int = 8) -> list:
        """优化的模糊搜索建议"""
        kw = query.lower()
        if len(kw) < 2:
            return []
        
        # 首先尝试使用索引快速查找
        if self._index_built:
            indexed_results = self._search_by_index(kw)
            if indexed_results:
                suggestions = []
                for entity_type, idx in list(indexed_results)[:limit * 2]:
                    if entity_type == "item" and idx < len(self.items):
                        item = self.items[idx]
                        suggestions.append(f"📦 {item.get('name_cn', '')}({item.get('name_en', '')})")
                    elif entity_type == "monster":
                        monsters_list = list(self.monsters.items())
                        if idx < len(monsters_list):
                            key, m = monsters_list[idx]
                            suggestions.append(f"🐉 {m.get('name_zh', key)}({m.get('name', '')})")
                    elif entity_type == "skill" and idx < len(self.skills):
                        skill = self.skills[idx]
                        suggestions.append(f"⚡ {skill.get('name_cn', '')}({skill.get('name_en', '')})")
                    elif entity_type == "event" and idx < len(self.events):
                        ev = self.events[idx]
                        suggestions.append(f"🎲 {ev.get('name', '')}({ev.get('name_en', '')})")
                if suggestions:
                    return suggestions[:limit]
        
        # 回退到传统模糊搜索
        threshold = max(1, len(kw) // 3)
        candidates = []
        
        # 使用生成器延迟计算
        def iter_entries():
            for item in self.items:
                yield (item.get("name_cn", ""), item.get("name_en", ""), "📦", item)
            for key, monster in self.monsters.items():
                yield (monster.get("name_zh", key), monster.get("name", ""), "🐉", monster)
            for skill in self.skills:
                yield (skill.get("name_cn", ""), skill.get("name_en", ""), "⚡", skill)
            for ev in self.events:
                yield (ev.get("name", ""), ev.get("name_en", ""), "🎲", ev)
        
        for cn, en, emoji, _ in iter_entries():
            best_dist = None
            for name in [cn, en]:
                if not name:
                    continue
                nl = name.lower()
                # 快速路径：完全匹配或子串匹配
                if kw in nl or nl in kw:
                    best_dist = 0
                    break
                # 长度差异太大则跳过
                if abs(len(nl) - len(kw)) > threshold:
                    continue
                dist = _edit_distance(kw, nl)
                if dist <= threshold:
                    if best_dist is None or dist < best_dist:
                        best_dist = dist
            if best_dist is not None:
                display = f"{emoji} {cn}({en})" if cn and en else f"{emoji} {cn or en}"
                candidates.append((best_dist, display))
        
        candidates.sort(key=lambda x: x[0])
        return [c[1] for c in candidates[:limit]]

    def _not_found_with_suggestions(self, query: str, entity_type: str) -> str:
        suggestions = self._fuzzy_suggest(query)
        msg = f"未找到{entity_type}「{query}」。"
        if suggestions:
            msg += "\n\n🔍 你可能在找:\n" + "\n".join(f"  {s}" for s in suggestions)
            msg += "\n\n💡 请使用精确名称重新查询，或使用 /tbzsearch 搜索。"
        else:
            msg += "\n💡 请使用 /tbzsearch 搜索。"
        return msg

    def _search_events(self, keyword: str, heroes: list = None) -> list:
        results = []
        kw = keyword.lower() if keyword else ""
        for ev in self.events:
            if heroes:
                ev_heroes = [h.lower() for h in ev.get("heroes", [])]
                if not any(h.lower() in ev_heroes for h in heroes):
                    continue
            if not kw:
                results.append(ev)
                continue
            if (kw in ev.get("name", "").lower() or
                kw in ev.get("name_en", "").lower()):
                results.append(ev)
                continue
            for choice in ev.get("choices", []):
                if (kw in choice.get("name", "").lower() or
                    kw in choice.get("name_zh", "").lower() or
                    kw in choice.get("description_zh", "").lower() or
                    kw in choice.get("description", "").lower()):
                    results.append(ev)
                    break
        return results

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

    def _search_merchants(self, keyword: str) -> list:
        results = []
        kw = keyword.lower()
        for m in self.merchants:
            if (kw in m.get("name", "").lower() or
                kw in m.get("description", "").lower() or
                kw in m.get("category", "").lower() or
                kw in m.get("tier", "").lower() or
                any(kw in h.lower() for h in m.get("heroes", []))):
                results.append(m)
        return results

    def _format_merchant_info(self, merchant: dict) -> str:
        name = merchant.get("name", "")
        desc = merchant.get("description", "")
        category = merchant.get("category", "")
        tier = merchant.get("tier", "")
        heroes = merchant.get("heroes", [])
        category_cn = "商人" if category == "Merchant" else "训练师" if category == "Trainer" else category
        tier_cn = {"Bronze": "青铜", "Silver": "白银", "Gold": "黄金", "Diamond": "钻石", "Legendary": "传说"}.get(tier, tier)
        heroes_cn = [f"{HERO_CN_MAP.get(h, h)}" for h in heroes]
        lines = [
            f"🏪 {name}",
            f"━━━━━━━━━━━━━━━━━━",
            f"📋 类型: {category_cn}",
            f"💎 品质: {tier_cn}({tier})",
            f"📝 描述: {desc}",
            f"👥 可用英雄: {' | '.join(heroes_cn)}",
        ]
        slug = merchant.get("name_slug", "")
        if slug:
            lines.append(f"🔗 https://bazaarforge.gg/merchants/{slug}")
        return "\n".join(lines)

    @filter.command("tbzhelp")
    async def cmd_help(self, event: AstrMessageEvent):
        """查看 Bazaar 插件帮助信息"""
        help_text = (
            "🎮 The Bazaar 数据查询助手\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"📊 数据: {len(self.monsters)}怪物 | {len(self.items)}物品 | {len(self.skills)}技能 | {len(self.events)}事件 | {len(self.merchants)}商人\n\n"
            "📋 可用指令:\n\n"
            "/tbzmonster <名称> - 查询怪物详情(图片卡片)\n"
            "  示例: /tbzmonster 火灵\n\n"
            "/tbzitem <名称> - 查询物品详情(图片卡片)\n"
            "  示例: /tbzitem 地下商街\n\n"
            "/tbzskill <名称> - 查询技能详情(图片卡片)\n"
            "  示例: /tbzskill 热情如火\n\n"
            "/tbzevent <名称> - 查询事件选项\n"
            "  示例: /tbzevent 奇异蘑菇\n\n"
            "/tbzsearch <条件> - 智能多条件搜索\n"
            "  直接连写: /tbzsearch 杜利中型灼烧\n"
            "  空格分隔: /tbzsearch 马克 黄金 武器\n"
            "  前缀语法: /tbzsearch tag:Weapon hero:Mak\n"
            "  英雄事件: /tbzsearch hero:Jules (含该英雄事件)\n"
            "  无参数: /tbzsearch (显示搜索帮助)\n\n"
            "/tbznews [数量] - 查询游戏官方更新公告(图片)\n"
            "  示例: /tbznews 或 /tbznews 3\n\n"
            "/tbzbuild <物品名> [数量] - 查询推荐阵容\n"
            "  示例: /tbzbuild 符文匕首\n\n"
            "/tbztier <英雄名> - 查询英雄物品评级(Tier List)\n"
            "  示例: /tbztier 海盗 或 /tbztier Vanessa\n\n"
            "/tbzmerchant <名称> - 查询商人/训练师信息\n"
            "  示例: /tbzmerchant Aila 或 /tbzmerchant Weapon\n\n"
            "/tbzalias - 别名管理(查看/添加/删除)\n"
            "  查看: /tbzalias list [分类]\n"
            "  添加: /tbzalias add hero 猪猪 Pygmalien\n"
            "  删除: /tbzalias del hero 猪猪\n\n"
            "/tbzupdate - 从远端更新游戏数据\n\n"
            "/tbzcache - 查看/清理缓存\n"
            "  /tbzcache stats - 查看缓存统计\n"
            "  /tbzcache clear - 清理内存缓存\n\n"
            "/tbzhelp - 显示此帮助信息\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "数据来源: BazaarHelper | BazaarForge | bazaar-builds.net | Steam\n\n"
            "💡 AI 工具: 本插件支持 AI 自动调用，需要 AstrBot 配置支持函数调用的 LLM 模型"
        )
        yield event.plain_result(help_text)

    @filter.command("tbzcache")
    async def cmd_cache(self, event: AstrMessageEvent):
        """缓存管理命令"""
        query = _extract_query(event.message_str, "tbzcache")
        action = query.lower().strip() if query else "stats"
        
        if action in ("stats", "status", "info", ""):
            stats = self._cache.stats()
            
            # 统计图片缓存
            img_cache_count = 0
            img_cache_size = 0
            if self.renderer:
                try:
                    cache_files = list(self.renderer.cache_dir.glob("*.webp"))
                    img_cache_count = len(cache_files)
                    img_cache_size = sum(f.stat().st_size for f in cache_files if f.exists()) / 1024 / 1024
                except Exception:
                    pass
            
            lines = [
                "📊 缓存状态统计",
                "━━━━━━━━━━━━━━━━━━",
                "",
                "【内存缓存】",
                f"  缓存条目: {stats['size']}",
                f"  内存占用: {stats['memory_mb']:.2f} MB",
                f"  命中次数: {stats['hits']}",
                f"  未命中数: {stats['misses']}",
                f"  命中率: {stats['hit_rate']}%",
                "",
                "【图片缓存】",
                f"  文件数量: {img_cache_count}",
                f"  磁盘占用: {img_cache_size:.2f} MB",
                "",
                "【搜索索引】",
                f"  索引关键词: {len(self._search_index)}",
                f"  索引状态: {'已构建' if self._index_built else '未构建'}",
                "",
                "💡 使用 /tbzcache clear 清理内存缓存",
            ]
            yield event.plain_result("\n".join(lines))
            return
        
        if action in ("clear", "clean", "reset"):
            # 清理内存缓存
            old_stats = self._cache.stats()
            self._cache.clear()
            
            # 清理渲染器内存缓存
            if self.renderer:
                self.renderer.clear_memory_cache()
            
            yield event.plain_result(
                f"✅ 缓存已清理\n"
                f"释放条目: {old_stats['size']}\n"
                f"释放内存: {old_stats['memory_mb']:.2f} MB"
            )
            return
        
        if action in ("clearimg", "clearimages", "清理图片"):
            # 清理图片缓存
            if self.renderer:
                try:
                    cache_files = list(self.renderer.cache_dir.glob("*.webp"))
                    count = len(cache_files)
                    size = sum(f.stat().st_size for f in cache_files if f.exists()) / 1024 / 1024
                    for f in cache_files:
                        try:
                            f.unlink()
                        except OSError:
                            pass
                    yield event.plain_result(f"✅ 图片缓存已清理\n删除文件: {count}\n释放空间: {size:.2f} MB")
                except Exception as e:
                    yield event.plain_result(f"❌ 清理图片缓存失败: {e}")
            else:
                yield event.plain_result("❌ 渲染器未加载")
            return
        
        yield event.plain_result(
            "用法: /tbzcache [操作]\n"
            "  stats - 查看缓存统计（默认）\n"
            "  clear - 清理内存缓存\n"
            "  clearimg - 清理图片文件缓存"
        )

    @filter.command("tbzmonster")
    async def cmd_monster(self, event: AstrMessageEvent):
        """查询怪物详细信息"""
        query = _extract_query(event.message_str, "tbzmonster")
        if not query:
            yield event.plain_result("请输入怪物名称，例如: /tbzmonster 火灵")
            return

        query = self._resolve_alias(query)
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
                self._not_found_with_suggestions(query, "怪物")
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

        query = self._resolve_alias(query)
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
            yield event.plain_result(self._not_found_with_suggestions(query, "物品"))
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

        query = self._resolve_alias(query)
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
                self._not_found_with_suggestions(query, "技能")
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

    @filter.command("tbzevent")
    async def cmd_event(self, event: AstrMessageEvent):
        """查询事件详细信息"""
        query = _extract_query(event.message_str, "tbzevent")
        if not query:
            yield event.plain_result("请输入事件名称，例如: /tbzevent 奇异蘑菇")
            return

        query = self._resolve_alias(query)
        kw = query.lower()
        found = None

        for ev in self.events:
            if (ev.get("name", "").lower() == kw or
                ev.get("name_en", "").lower() == kw):
                found = ev
                break

        if not found:
            results = self._search_events(query)
            def event_name(r):
                return f"{r.get('name', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(
                results, query, event_name,
                self._not_found_with_suggestions(query, "事件")
            )
            if msg:
                yield event.plain_result(msg)
                return

        yield event.plain_result(self._format_event_info(found))

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
        """多条件搜索怪物、物品、技能和事件"""
        self._reload_aliases_if_changed()
        query = _extract_query(event.message_str, "tbzsearch")
        if not query:
            yield event.plain_result(self._get_search_help())
            return

        conditions = self._parse_search_conditions(query)
        has_filters = conditions["tags"] or conditions["tiers"] or conditions["heroes"] or conditions.get("sizes")

        item_results = self._filter_items(conditions)
        skill_results = self._filter_skills(conditions) if not conditions["tiers"] and not conditions["tags"] and not conditions.get("sizes") else []
        monster_results = self._search_monsters(conditions["keyword"]) if conditions["keyword"] and not has_filters else []
        event_heroes = conditions["heroes"] if conditions["heroes"] else None
        event_kw = conditions["keyword"] if conditions["keyword"] else ""
        event_results = self._search_events(event_kw, event_heroes) if (event_kw or event_heroes) else []

        if not monster_results and not item_results and not skill_results and not event_results:
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

        total = len(monster_results) + len(item_results) + len(skill_results) + len(event_results)

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

        if event_results:
            lines = [f"🎲 事件 ({len(event_results)}个):"]
            for ev in event_results:
                choices_count = len(ev.get("choices", []))
                ev_heroes = ev.get("heroes", [])
                hero_tag = ""
                if ev_heroes and ev_heroes != ["Common"]:
                    hero_tag = f" [{','.join(ev_heroes)}]"
                tier = ev.get("tier", "")
                tier_emoji = TIER_EMOJI.get(tier, "")
                lines.append(f"  {tier_emoji} {ev.get('name', '')}({ev.get('name_en', '')}){hero_tag} - {choices_count}个选项")
            nodes.append(Comp.Node(
                name="大巴扎小助手", uin="0",
                content=[Comp.Plain("\n".join(lines))]
            ))

        nodes.append(Comp.Node(
            name="大巴扎小助手", uin="0",
            content=[Comp.Plain("💡 使用 /tbzitem /tbzskill /tbzevent <名称> 查看详情")]
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
        yield event.plain_result("⏳ 正在从 BazaarHelper 仓库和 BazaarForge 下载最新数据...")

        data_dir = self.plugin_dir / "data"
        session = await self._get_session()
        results = []
        success_count = 0
        total_sources = len(DATA_FILES) + 1

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

        try:
            forge_url = f"{FORGE_SUPABASE_URL}/rest/v1/merchants"
            params = {"select": "*", "limit": "200"}
            async with session.get(forge_url, params=params, headers=FORGE_HEADERS) as resp:
                if resp.status == 200:
                    merchants_data = await resp.json()
                    filepath = data_dir / "merchants_db.json"
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(merchants_data, f, ensure_ascii=False, indent=2)
                    results.append(f"✅ merchants_db.json: {len(merchants_data)}条数据 (BazaarForge)")
                    success_count += 1
                else:
                    results.append(f"❌ merchants_db.json: HTTP {resp.status}")
        except Exception as e:
            results.append(f"❌ merchants_db.json: {e}")

        if success_count > 0:
            self._load_data()
            self._build_vocab()

        summary = (
            f"📦 数据更新完成 ({success_count}/{total_sources})\n"
            + "\n".join(results) + "\n\n"
            f"📊 当前数据: {len(self.monsters)}怪物 | {len(self.items)}物品 | {len(self.skills)}技能 | "
            f"{len(self.events)}事件 | {len(self.merchants)}商人"
        )
        yield event.plain_result(summary)

    @filter.command("tbzalias")
    async def cmd_alias(self, event: AstrMessageEvent):
        """管理别名配置"""
        query = _extract_query(event.message_str, "tbzalias")
        if not query:
            lines = ["📖 别名管理\n━━━━━━━━━━━━━━━━━━"]
            lines.append("用法:")
            lines.append("  /tbzalias list [分类] - 查看别名列表")
            lines.append("  /tbzalias add <分类> <别名> <目标> - 添加别名")
            lines.append("  /tbzalias del <分类> <别名> - 删除别名")
            lines.append("")
            lines.append(f"可用分类: {', '.join(ALIAS_CATEGORIES)}")
            lines.append("")
            lines.append("示例:")
            lines.append("  /tbzalias list hero")
            lines.append("  /tbzalias add hero 猪猪 Pygmalien")
            lines.append("  /tbzalias del hero 猪猪")
            total = sum(len(v) for v in self.aliases.values())
            lines.append(f"\n当前共 {total} 条别名")
            yield event.plain_result("\n".join(lines))
            return

        parts = query.split(None, 3)
        action = parts[0].lower()

        if action == "list":
            cat = parts[1].lower() if len(parts) > 1 else None
            if cat and cat not in ALIAS_CATEGORIES:
                yield event.plain_result(f"未知分类「{cat}」，可用分类: {', '.join(ALIAS_CATEGORIES)}")
                return
            lines = ["📖 别名列表\n━━━━━━━━━━━━━━━━━━"]
            cats = [cat] if cat else ALIAS_CATEGORIES
            for c in cats:
                entries = self.aliases.get(c, {})
                if entries:
                    lines.append(f"\n【{c}】({len(entries)}条):")
                    for alias, target in sorted(entries.items()):
                        lines.append(f"  {alias} → {target}")
            if len(lines) == 1:
                lines.append("\n暂无别名配置")
            yield event.plain_result("\n".join(lines))
            return

        if action == "add":
            if len(parts) < 4:
                yield event.plain_result("用法: /tbzalias add <分类> <别名> <目标>\n示例: /tbzalias add hero 猪猪 Pygmalien")
                return
            cat = parts[1].lower()
            alias_name = parts[2]
            target = parts[3]
            if cat not in ALIAS_CATEGORIES:
                yield event.plain_result(f"未知分类「{cat}」，可用分类: {', '.join(ALIAS_CATEGORIES)}")
                return
            if cat not in self.aliases:
                self.aliases[cat] = {}
            old = self.aliases[cat].get(alias_name)
            self.aliases[cat][alias_name] = target
            self._save_aliases()
            self._build_vocab()
            if old:
                yield event.plain_result(f"✅ 已更新别名 [{cat}] {alias_name} → {target} (原: {old})")
            else:
                yield event.plain_result(f"✅ 已添加别名 [{cat}] {alias_name} → {target}")
            return

        if action in ("del", "delete", "rm", "remove"):
            if len(parts) < 3:
                yield event.plain_result("用法: /tbzalias del <分类> <别名>\n示例: /tbzalias del hero 猪猪")
                return
            cat = parts[1].lower()
            alias_name = parts[2]
            if cat not in ALIAS_CATEGORIES:
                yield event.plain_result(f"未知分类「{cat}」，可用分类: {', '.join(ALIAS_CATEGORIES)}")
                return
            if cat in self.aliases and alias_name in self.aliases[cat]:
                old_target = self.aliases[cat].pop(alias_name)
                self._save_aliases()
                self._build_vocab()
                yield event.plain_result(f"✅ 已删除别名 [{cat}] {alias_name} → {old_target}")
            else:
                yield event.plain_result(f"未找到别名 [{cat}] {alias_name}")
            return

        yield event.plain_result("未知操作，请使用 list/add/del。输入 /tbzalias 查看帮助。")

    def _translate_item_name(self, name_cn: str) -> str:
        for item in self.items:
            if item.get("name_cn", "").lower() == name_cn.lower():
                return item.get("name_en", name_cn)
        return name_cn

    def _translate_build_query(self, query: str) -> tuple[str, str]:
        self._reload_aliases_if_changed()
        tokens = self._smart_tokenize(query)
        search_parts = []
        display_parts = []
        for token in tokens:
            tl = token.lower()
            entry = self._vocab.get(tl)
            if entry:
                vtype, vval = entry
                if vtype == "hero":
                    search_parts.append(vval)
                    display_parts.append(f"英雄:{vval}")
                    continue
                elif vtype == "tag":
                    search_parts.append(vval.split("/")[0].strip())
                    display_parts.append(f"标签:{vval}")
                    continue
                elif vtype == "tier":
                    search_parts.append(vval)
                    display_parts.append(f"品质:{vval}")
                    continue
                elif vtype == "size":
                    search_parts.append(vval.split("/")[0].strip())
                    display_parts.append(f"尺寸:{vval}")
                    continue
            en = self._translate_item_name(token)
            search_parts.append(en)
            if en != token:
                display_parts.append(f"{token}→{en}")
            else:
                display_parts.append(token)
        search_term = " ".join(search_parts)
        display = " + ".join(display_parts)
        return search_term, display

    async def _download_image(self, url: str) -> bytes | None:
        try:
            session = await self._get_session()
            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.read()
        except Exception as e:
            logger.debug(f"图片下载失败: {url}: {e}")
        return None

    async def _fetch_news(self, count: int = 1) -> list:
        async def _fetch():
            session = await self._get_session()
            params = {
                "clan_accountid": 0,
                "appid": STEAM_APP_ID,
                "offset": 0,
                "count": count,
                "l": "schinese",
            }
            try:
                async with session.get(STEAM_NEWS_API, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status != 200:
                        logger.warning(f"Steam 新闻 API 返回 HTTP {resp.status}")
                        return []
                    data = await resp.json(content_type=None)
            except Exception as e:
                logger.warning(f"获取 Steam 新闻失败: {e}")
                return []

            events_list = data.get("events", [])
            articles = []
            for ev_data in events_list:
                gid = ev_data.get("gid", "")
                title = ev_data.get("event_name", "")
                announcement = ev_data.get("announcement_body", {})
                if not title:
                    title = announcement.get("headline", "")
                body_bbcode = announcement.get("body", "")
                body_text = _strip_bbcode(body_bbcode)
                post_time = ev_data.get("rtime32_start_time", 0)
                date_str = datetime.utcfromtimestamp(post_time).strftime("%Y-%m-%d") if post_time else ""
                url = f"https://store.steampowered.com/news/app/{STEAM_APP_ID}/view/{gid}?l=schinese"
                articles.append({
                    "title": title,
                    "date": date_str,
                    "body": body_text,
                    "url": url,
                    "gid": gid,
                })
            return articles
        return await self._cached_request(f"news:{count}", CACHE_TTL_NEWS, _fetch)

    @filter.command("tbznews")
    async def cmd_news(self, event: AstrMessageEvent):
        """查询游戏官方更新公告"""
        query = _extract_query(event.message_str, "tbznews")

        if self.config:
            default_count = max(1, min(int(self.config.get("news_default_count", DEFAULT_NEWS_COUNT)), 20))
        else:
            default_count = DEFAULT_NEWS_COUNT

        count = default_count
        if query and query.strip().isdigit():
            count = max(1, min(int(query.strip()), 20))

        yield event.plain_result(f"⏳ 正在从 Steam 获取最新 {count} 条公告...")

        articles = await self._fetch_news(count)
        if not articles:
            yield event.plain_result("❌ 暂时无法获取游戏更新公告，请稍后再试。")
            return

        if len(articles) == 1:
            article = articles[0]
            try:
                img_bytes = await self.renderer.render_news_card(
                    article["title"], article["date"], article["body"], article["url"]
                )
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
            except Exception as e:
                logger.warning(f"新闻卡片渲染失败: {e}")
                preview = article["body"][:1000]
                yield event.plain_result(
                    f"📰 {article['title']}\n📅 {article['date']}\n\n{preview}\n\n🔗 {article['url']}"
                )
            return

        nodes = []
        nodes.append(Comp.Node(
            name="大巴扎小助手", uin="0",
            content=[Comp.Plain(f"📰 The Bazaar 最新公告 (共{len(articles)}条)")]
        ))

        for i, article in enumerate(articles, 1):
            try:
                img_bytes = await self.renderer.render_news_card(
                    article["title"], article["date"], article["body"], article["url"]
                )
                nodes.append(Comp.Node(
                    name="大巴扎小助手", uin="0",
                    content=[
                        Comp.Image.fromBytes(img_bytes),
                        Comp.Plain(f"━━ {i}. {article['title']} ({article['date']}) ━━"),
                    ]
                ))
            except Exception as e:
                logger.warning(f"新闻卡片渲染失败 ({article['title']}): {e}")
                preview = article["body"][:500]
                nodes.append(Comp.Node(
                    name="大巴扎小助手", uin="0",
                    content=[Comp.Plain(
                        f"━━ {i}. {article['title']} ━━\n📅 {article['date']}\n\n{preview}\n\n🔗 {article['url']}"
                    )]
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
        if self.config:
            count = max(1, min(int(self.config.get("build_default_count", DEFAULT_BUILD_COUNT)), 10))
        else:
            count = DEFAULT_BUILD_COUNT
        if len(parts) == 2 and parts[1].isdigit():
            count = max(1, min(int(parts[1]), 10))
            query = parts[0].strip()

        search_term, display = self._translate_build_query(query)

        builds = await self._fetch_builds_combined(search_term, count)

        if not builds:
            hint = f"\n📋 识别: {display}" if display != query else ""
            yield event.plain_result(
                f"未找到与「{query}」相关的阵容。{hint}\n"
                f"🔍 搜索词: {search_term}\n"
                f"请尝试使用英文物品名搜索，或访问:\n"
                f"https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
            )
            return

        forge_count = sum(1 for b in builds if b.get("source") == "forge")
        wp_count = sum(1 for b in builds if b.get("source") == "wp")
        source_parts = []
        if forge_count:
            source_parts.append(f"BazaarForge:{forge_count}")
        if wp_count:
            source_parts.append(f"bazaar-builds:{wp_count}")
        source_hint = " | ".join(source_parts)

        header = f"🏗️ 「{query}」推荐阵容 (共{len(builds)}条)"
        if search_term != query:
            header += f"\n🔍 搜索: {search_term}"
        if display != query and display != search_term:
            header += f"\n📋 识别: {display}"
        if source_hint:
            header += f"\n📊 来源: {source_hint}"

        nodes = []
        nodes.append(Comp.Node(
            name="大巴扎小助手",
            uin="0",
            content=[Comp.Plain(header)]
        ))

        img_results = await asyncio.gather(*[
            self._download_image(b["image_url"]) if b.get("image_url") else asyncio.sleep(0)
            for b in builds
        ], return_exceptions=True)

        for i, (build, img_data) in enumerate(zip(builds, img_results), 1):
            caption = f"━━ {i}. {build['title']} ━━\n📅 {build['date']}"
            if build.get("source") == "forge" and build.get("excerpt"):
                caption += f"\n📊 {build['excerpt']}"
            caption += f"\n🔗 {build['link']}"
            node_content = []

            if isinstance(img_data, bytes) and img_data:
                node_content.append(Comp.Image.fromBytes(img_data))

            if not node_content and build.get("excerpt") and build.get("source") != "forge":
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
            content=[Comp.Plain(f"💡 更多阵容: {more_url}\n💡 BazaarForge: {FORGE_BUILD_URL}")]
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

    @filter.llm_tool(name="bazaar_query_item")
    async def tool_query_item(self, event: AstrMessageEvent, item_name: str):
        '''查询 The Bazaar (大巴扎) 卡牌游戏中的物品详细信息，包括技能、属性、数值、附魔和任务。The Bazaar 是一款由 Tempo Storm 开发的 Roguelike 卡牌对战游戏。当用户提到 The Bazaar / 大巴扎 游戏中的物品名称，或者询问游戏物品的效果、属性时，请调用此工具。游戏中的物品例如：放大镜、符文匕首、船锚(Anchor)、热力长枪(Thermal Lance)、地下商街(Bazaar) 等。

        Args:
            item_name(string): The Bazaar 游戏物品名称，支持中文或英文。例如：放大镜、Magnifying Glass、符文匕首、船锚
        '''
        query = self._resolve_alias(item_name)
        kw = query.lower()
        found = None

        for item in self.items:
            if (item.get("name_cn", "").lower() == kw or
                item.get("name_en", "").lower() == kw):
                found = item
                break

        if not found:
            results = self._search_items(query)
            def item_name_fn(r):
                return f"{r.get('name_cn', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(results, query, item_name_fn, None)
            if msg:
                yield event.plain_result(msg)
                return

        if not found:
            yield event.plain_result(self._not_found_with_suggestions(item_name, "物品"))
            return

        info = self._format_item_info(found)
        info += "\n\n💡 使用 /tbzitem " + (found.get("name_cn") or found.get("name_en", "")) + " 可查看图片卡片"
        yield event.plain_result(info)

    @filter.llm_tool(name="bazaar_query_monster")
    async def tool_query_monster(self, event: AstrMessageEvent, monster_name: str):
        '''查询 The Bazaar (大巴扎) 卡牌游戏中的怪物/敌人详细信息，包括技能、掉落物品、血量和奖励。The Bazaar 是一款 Roguelike 卡牌对战游戏，玩家在 PvE 回合中对战各种怪物。当用户询问游戏中某个怪物/敌人/boss 的信息时，请调用此工具。

        Args:
            monster_name(string): The Bazaar 游戏怪物名称，支持中文或英文。例如：火灵、Tree Treant、暗影猎手
        '''
        query = self._resolve_alias(monster_name)
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
            def monster_name_fn(r):
                k, m = r
                return f"{m.get('name_zh', k)}({m.get('name', '')})"
            found, msg = _resolve_search(results, query, monster_name_fn,
                self._not_found_with_suggestions(monster_name, "怪物"))
            if msg:
                yield event.plain_result(msg)
                return
            found_key, found_monster = found

        info = self._format_monster_info(found_key, found_monster)
        name = found_monster.get("name_zh") or found_monster.get("name", found_key)
        info += "\n\n💡 使用 /tbzmonster " + name + " 可查看图片卡片"
        yield event.plain_result(info)

    @filter.llm_tool(name="bazaar_query_skill")
    async def tool_query_skill(self, event: AstrMessageEvent, skill_name: str):
        '''查询 The Bazaar (大巴扎) 卡牌游戏中的技能详细信息，包括描述和适用英雄。The Bazaar 游戏中每个英雄和物品都有独特的技能。当用户询问游戏中某个技能的效果或信息时，请调用此工具。

        Args:
            skill_name(string): The Bazaar 游戏技能名称，支持中文或英文。例如：热情如火、Burning Passion
        '''
        query = self._resolve_alias(skill_name)
        kw = query.lower()
        found = None

        for skill in self.skills:
            if (skill.get("name_cn", "").lower() == kw or
                skill.get("name_en", "").lower() == kw):
                found = skill
                break

        if not found:
            results = self._search_skills(query)
            def skill_name_fn(r):
                return f"{r.get('name_cn', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(results, query, skill_name_fn,
                self._not_found_with_suggestions(skill_name, "技能"))
            if msg:
                yield event.plain_result(msg)
                return

        info = self._format_skill_info(found)
        info += "\n\n💡 使用 /tbzskill " + (found.get("name_cn") or found.get("name_en", "")) + " 可查看图片卡片"
        yield event.plain_result(info)

    @filter.llm_tool(name="bazaar_query_event")
    async def tool_query_event(self, event: AstrMessageEvent, event_name: str):
        '''查询 The Bazaar (大巴扎) 卡牌游戏中的事件/随机事件详情。The Bazaar 游戏中玩家在对战间隙会遇到各种事件，每个事件有多个选项可以选择，不同选项会获得不同的奖励。当用户询问某个游戏内事件的选项、奖励时，请调用此工具。

        Args:
            event_name(string): The Bazaar 游戏事件名称，支持中文或英文。例如：奇异蘑菇、A Strange Mushroom
        '''
        query = self._resolve_alias(event_name)
        kw = query.lower()
        found = None

        for ev in self.events:
            if (ev.get("name", "").lower() == kw or
                ev.get("name_en", "").lower() == kw):
                found = ev
                break

        if not found:
            results = self._search_events(query)
            def ev_name_fn(r):
                return f"{r.get('name', '')}({r.get('name_en', '')})"
            found, msg = _resolve_search(results, query, ev_name_fn,
                self._not_found_with_suggestions(event_name, "事件"))
            if msg:
                yield event.plain_result(msg)
                return

        info = self._format_event_info(found)
        info += "\n💡 使用 /tbzevent " + (found.get("name") or found.get("name_en", "")) + " 查看详情"
        yield event.plain_result(info)

    @filter.llm_tool(name="bazaar_get_news")
    async def tool_get_news(self, event: AstrMessageEvent, count: int = 1):
        '''查询 The Bazaar (大巴扎) 游戏的最新官方更新公告和补丁说明。当用户询问游戏最近更新了什么、有什么新补丁、改动内容、版本更新、changelog 时，请调用此工具。返回 Steam 官方中文翻译的更新公告摘要。

        Args:
            count(int): 返回公告数量，默认1，范围1-5
        '''
        count = max(1, min(count, 5))
        articles = await self._fetch_news(count)
        if not articles:
            yield event.plain_result("暂时无法获取游戏更新公告，请稍后再试。")
            return

        lines = []
        for i, article in enumerate(articles, 1):
            lines.append(f"{i}. {article['title']}")
            lines.append(f"   日期: {article['date']}")
            body_preview = article['body'][:500]
            lines.append(f"   内容摘要:\n{body_preview}")
            lines.append(f"   链接: {article['url']}")
            lines.append("")

        lines.append("💡 使用 /tbznews 查看完整图片版公告")
        yield event.plain_result("\n".join(lines))

    @filter.llm_tool(name="bazaar_search")
    async def tool_search(self, event: AstrMessageEvent, query: str):
        '''在 The Bazaar (大巴扎) 卡牌游戏数据库中搜索物品、怪物、技能和事件。支持按关键词、英雄(如 Vanessa/Pygmalien/Dooley/Stelle/Jules/Mak)、标签(如 Weapon/Shield/Food)、品质(Bronze/Silver/Gold/Diamond) 等多条件搜索。当用户想要查找游戏中某一类物品、按条件筛选、或者问"有哪些xxx"时，请调用此工具。

        Args:
            query(string): 搜索条件。可以是关键词、英雄名、标签名等。例如：灼烧、武器、黄金护盾、Vanessa Weapon。支持前缀语法如 tag:Weapon hero:Mak tier:Gold
        '''
        self._reload_aliases_if_changed()
        conditions = self._parse_search_conditions(query)
        has_filters = conditions["tags"] or conditions["tiers"] or conditions["heroes"] or conditions.get("sizes")

        item_results = self._filter_items(conditions)
        skill_results = self._filter_skills(conditions) if not conditions["tiers"] and not conditions["tags"] and not conditions.get("sizes") else []
        monster_results = self._search_monsters(conditions["keyword"]) if conditions["keyword"] and not has_filters else []
        event_heroes = conditions["heroes"] if conditions["heroes"] else None
        event_kw = conditions["keyword"] if conditions["keyword"] else ""
        event_results = self._search_events(event_kw, event_heroes) if (event_kw or event_heroes) else []

        if not monster_results and not item_results and not skill_results and not event_results:
            yield event.plain_result(f"未找到与「{query}」相关的结果。")
            return

        lines = []
        total = len(monster_results) + len(item_results) + len(skill_results) + len(event_results)
        lines.append(f"搜索「{query}」的结果 (共{total}条):")

        if monster_results:
            lines.append(f"\n怪物 ({len(monster_results)}个):")
            for key, m in monster_results[:10]:
                lines.append(f"  - {m.get('name_zh', key)}({m.get('name', '')})")
            if len(monster_results) > 10:
                lines.append(f"  ... 还有{len(monster_results) - 10}个")

        if item_results:
            lines.append(f"\n物品 ({len(item_results)}个):")
            for it in item_results[:15]:
                tier = _clean_tier(it.get("starting_tier", ""))
                hero = it.get("heroes", "").split("/")[0].strip()
                lines.append(f"  - {it.get('name_cn', '')}({it.get('name_en', '')}) [{tier}] - {hero}")
            if len(item_results) > 15:
                lines.append(f"  ... 还有{len(item_results) - 15}个")

        if skill_results:
            lines.append(f"\n技能 ({len(skill_results)}个):")
            for sk in skill_results[:10]:
                lines.append(f"  - {sk.get('name_cn', '')}({sk.get('name_en', '')})")
            if len(skill_results) > 10:
                lines.append(f"  ... 还有{len(skill_results) - 10}个")

        if event_results:
            lines.append(f"\n事件 ({len(event_results)}个):")
            for ev in event_results[:10]:
                ev_heroes = ev.get("heroes", [])
                hero_tag = f" [{','.join(ev_heroes)}]" if ev_heroes and ev_heroes != ["Common"] else ""
                tier = ev.get("tier", "")
                tier_str = f" {tier}" if tier else ""
                lines.append(f"  - {ev.get('name', '')}({ev.get('name_en', '')}){hero_tag}{tier_str}")
            if len(event_results) > 10:
                lines.append(f"  ... 还有{len(event_results) - 10}个")

        yield event.plain_result("\n".join(lines))

    @filter.llm_tool(name="bazaar_query_build")
    async def tool_query_build(self, event: AstrMessageEvent, query: str, count: int = 5):
        '''查询 The Bazaar 游戏的社区推荐阵容。根据物品名、英雄名等关键词从 BazaarForge 和 bazaar-builds.net 搜索玩家分享的通关阵容。当用户询问某个物品的阵容搭配、某个英雄怎么玩、推荐阵容时使用此工具。

        Args:
            query(string): 搜索关键词，可以是物品名、英雄名或组合。支持中文，会自动翻译为英文搜索。例如：符文匕首、海盗船锚、Vanessa Anchor
            count(int): 返回结果数量，默认5，范围1-10
        '''
        count = max(1, min(count, 10))
        search_term, display = self._translate_build_query(query)
        builds = await self._fetch_builds_combined(search_term, count)

        if not builds:
            yield event.plain_result(
                f"未找到与「{query}」相关的阵容。\n搜索词: {search_term}\n"
                f"可访问: https://bazaar-builds.net/?s={search_term.replace(' ', '+')}"
            )
            return

        lines = [f"「{query}」推荐阵容 (共{len(builds)}条):"]
        if search_term != query:
            lines.append(f"搜索词: {search_term}")
        lines.append("")
        for i, build in enumerate(builds, 1):
            lines.append(f"{i}. {build['title']}")
            lines.append(f"   日期: {build['date']}")
            if build.get("source") == "forge" and build.get("excerpt"):
                lines.append(f"   数据: {build['excerpt']}")
            lines.append(f"   链接: {build['link']}")
            if build.get("source") == "wp" and build.get("excerpt"):
                lines.append(f"   简介: {build['excerpt'][:100]}")
            lines.append("")

        lines.append(f"更多阵容: https://bazaar-builds.net/?s={search_term.replace(' ', '+')} 或 {FORGE_BUILD_URL}")

        yield event.plain_result("\n".join(lines))

    @filter.command("tbztier")
    async def cmd_tier(self, event: AstrMessageEvent):
        """查询英雄物品 Tier List"""
        query = _extract_query(event.message_str, "tbztier")
        if not query:
            yield event.plain_result(
                "请输入英雄名称查询物品评级，例如:\n"
                "  /tbztier 海盗\n"
                "  /tbztier Vanessa\n"
                "  /tbztier 杜利\n\n"
                "可用英雄: Dooley(杜利) | Jules(朱尔斯) | Mak(马克) | Pygmalien(皮格马利翁) | Stelle(斯黛拉) | Vanessa(瓦妮莎)"
            )
            return

        query = self._resolve_alias(query)
        hero_en = self._resolve_hero_name(query)
        if not hero_en:
            hero_en = query.strip().capitalize()
            valid_heroes = ["Dooley", "Jules", "Mak", "Pygmalien", "Stelle", "Vanessa"]
            if hero_en not in valid_heroes:
                yield event.plain_result(
                    f"未识别英雄「{query}」。\n\n"
                    "可用英雄: Dooley(杜利) | Jules(朱尔斯) | Mak(马克) | Pygmalien(皮格马利翁) | Stelle(斯黛拉) | Vanessa(瓦妮莎)"
                )
                return

        hero_cn = HERO_CN_MAP.get(hero_en, hero_en)

        img_cache_key = f"img:tierlist:{hero_en}"
        cached_img = self._get_img_cache(img_cache_key, CACHE_TTL_TIERLIST)
        if cached_img and self.renderer:
            yield event.chain_result([Comp.Image.fromBytes(cached_img)])
            return

        yield event.plain_result(f"⏳ 正在从 BazaarForge 获取 {hero_cn}({hero_en}) 物品评级...")

        tier_items = await self._fetch_tierlist(hero_en)

        total = sum(len(v) for v in tier_items.values())
        if total == 0:
            yield event.plain_result(f"未找到 {hero_cn}({hero_en}) 的物品评级数据。")
            return

        if self.renderer:
            try:
                img_bytes = await self.renderer.render_tierlist_card(hero_en, hero_cn, tier_items)
                self._set_img_cache(img_cache_key, img_bytes)
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
                return
            except Exception as e:
                logger.warning(f"Tier List 卡片渲染失败，回退文本: {e}")

        lines = [f"📊 {hero_cn}({hero_en}) 物品评级 (共{total}个)", ""]
        grade_emoji = {"S": "🏆", "A": "🥇", "B": "🥈", "C": "🥉"}
        for grade in ["S", "A", "B", "C"]:
            items = tier_items.get(grade, [])
            if not items:
                continue
            lines.append(f"{grade_emoji.get(grade, '')} {grade} 级 ({len(items)}个):")
            for it in items[:15]:
                name_display = f"{it['name_cn']}({it['name']})" if it.get("name_cn") else it["name"]
                lines.append(f"  {name_display} - {it['pct']:.1f}% ({it['build_count']}局)")
            if len(items) > 15:
                lines.append(f"  ... 还有{len(items) - 15}个")
            lines.append("")
        lines.append(f"数据来源: BazaarForge.gg | 阈值 S≥15% A≥8% B≥3% C>0%")
        yield event.plain_result("\n".join(lines))

    @filter.llm_tool(name="bazaar_query_tierlist")
    async def tool_query_tierlist(self, event: AstrMessageEvent, hero_name: str):
        '''查询 The Bazaar 游戏中某个英雄的物品评级（Tier List），显示该英雄最常用的物品及其使用率。当用户询问某个英雄哪些物品好用、物品推荐、装备排名、Tier List 时使用此工具。

        Args:
            hero_name(string): 英雄名称，支持中文或英文。例如：海盗、Vanessa、杜利、Dooley
        '''
        query = self._resolve_alias(hero_name)
        hero_en = self._resolve_hero_name(query)
        if not hero_en:
            hero_en = query.strip().capitalize()
            valid_heroes = ["Dooley", "Jules", "Mak", "Pygmalien", "Stelle", "Vanessa"]
            if hero_en not in valid_heroes:
                yield event.plain_result(
                    f"未识别英雄「{hero_name}」。可用英雄: Dooley(杜利), Jules(朱尔斯), Mak(马克), Pygmalien(皮格马利翁), Stelle(斯黛拉), Vanessa(瓦妮莎)"
                )
                return

        hero_cn = HERO_CN_MAP.get(hero_en, hero_en)
        tier_items = await self._fetch_tierlist(hero_en)

        total = sum(len(v) for v in tier_items.values())
        if total == 0:
            yield event.plain_result(f"未找到 {hero_cn}({hero_en}) 的物品评级数据。")
            return

        lines = [f"{hero_cn}({hero_en}) 物品评级 (共{total}个):"]
        for grade in ["S", "A", "B", "C"]:
            items = tier_items.get(grade, [])
            if not items:
                continue
            lines.append(f"\n{grade} 级 ({len(items)}个):")
            for it in items[:10]:
                name_display = f"{it['name_cn']}({it['name']})" if it.get("name_cn") else it["name"]
                lines.append(f"  {name_display} - {it['pct']:.1f}% ({it['build_count']}局)")
            if len(items) > 10:
                lines.append(f"  ... 还有{len(items) - 10}个")

        lines.append(f"\n数据来源: BazaarForge.gg")
        lines.append(f"💡 使用 /tbztier {hero_name} 查看图片版评级")
        yield event.plain_result("\n".join(lines))

    @filter.command("tbzmerchant")
    async def cmd_merchant(self, event: AstrMessageEvent):
        """查询商人/训练师信息"""
        if not self.merchants:
            yield event.plain_result(
                "⚠️ 商人数据尚未加载。请先运行 /tbzupdate 更新数据。"
            )
            return
        query = _extract_query(event.message_str, "tbzmerchant")
        if not query:
            merchant_count = len([m for m in self.merchants if m.get("category") == "Merchant"])
            trainer_count = len([m for m in self.merchants if m.get("category") == "Trainer"])
            yield event.plain_result(
                f"请输入商人名称查询，例如:\n"
                f"  /tbzmerchant Aila\n"
                f"  /tbzmerchant Chronos\n\n"
                f"📊 当前数据: {merchant_count}个商人 | {trainer_count}个训练师\n\n"
                f"💡 也可按条件搜索:\n"
                f"  /tbzmerchant Weapon (搜索卖武器的商人)\n"
                f"  /tbzmerchant Diamond (搜索钻石品质商人)\n"
                f"  /tbzmerchant Vanessa (搜索某英雄可遇到的商人)"
            )
            return

        query = self._resolve_alias(query)
        kw = query.lower()
        found = None

        for m in self.merchants:
            if m.get("name", "").lower() == kw:
                found = m
                break

        if not found:
            results = self._search_merchants(query)
            def merchant_name(r):
                cat_cn = "商人" if r.get("category") == "Merchant" else "训练师"
                return f"{r.get('name', '')} ({cat_cn}/{r.get('tier', '')})"
            found, msg = _resolve_search(
                results, query, merchant_name,
                f"未找到商人「{query}」。"
            )
            if msg:
                yield event.plain_result(msg)
                return

        if self.renderer:
            merchant_id = found.get("id") or found.get("name_slug", "")
            img_cache_key = f"img:merchant:{merchant_id}"
            cached_img = self._get_img_cache(img_cache_key, CACHE_TTL_BUILDS)
            if cached_img:
                yield event.chain_result([Comp.Image.fromBytes(cached_img)])
                return
            try:
                img_bytes = await self.renderer.render_merchant_card(found)
                self._set_img_cache(img_cache_key, img_bytes)
                yield event.chain_result([Comp.Image.fromBytes(img_bytes)])
                return
            except Exception as e:
                logger.warning(f"商人卡片渲染失败，回退文本: {e}")
        yield event.plain_result(self._format_merchant_info(found))

    @filter.llm_tool(name="bazaar_query_merchant")
    async def tool_query_merchant(self, event: AstrMessageEvent, merchant_name: str):
        '''查询 The Bazaar 游戏中的商人或训练师信息，包括出售/教授内容、品质等级和可遇到的英雄。当用户询问商人、NPC、在哪买东西、训练师等问题时使用此工具。

        Args:
            merchant_name(string): 商人名称或搜索关键词，例如：Aila、Weapon、Diamond
        '''
        if not self.merchants:
            yield event.plain_result("商人数据尚未加载，请先运行 /tbzupdate 更新数据。")
            return
        query = self._resolve_alias(merchant_name)
        kw = query.lower()
        found = None

        for m in self.merchants:
            if m.get("name", "").lower() == kw:
                found = m
                break

        if not found:
            results = self._search_merchants(query)
            if len(results) == 1:
                found = results[0]
            elif len(results) > 1:
                lines = [f"找到 {len(results)} 个相关商人:"]
                for m in results[:10]:
                    cat_cn = "商人" if m.get("category") == "Merchant" else "训练师"
                    lines.append(f"  {m.get('name', '')} ({cat_cn}/{m.get('tier', '')}) - {m.get('description', '')}")
                if len(results) > 10:
                    lines.append(f"  ... 还有 {len(results) - 10} 个")
                lines.append(f"\n💡 使用 /tbzmerchant <名称> 查看详情")
                yield event.plain_result("\n".join(lines))
                return
            else:
                yield event.plain_result(f"未找到商人「{merchant_name}」。")
                return

        yield event.plain_result(self._format_merchant_info(found))

    async def terminate(self):
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Bazaar 插件已卸载")
