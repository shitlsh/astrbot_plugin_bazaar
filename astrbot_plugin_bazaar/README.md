# astrbot_plugin_bazaar

基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。

## 功能

- 查询怪物详细信息（技能、物品、血量、奖励）
- 查询物品详细信息（属性、品质成长、附魔）
- 查询技能详细信息（描述、适用英雄）
- 按关键词全局搜索怪物、物品和技能
- 按标签、品质筛选物品
- 按英雄查看专属物品和技能
- 支持中英文双语查询

## 数据规模

| 数据类型 | 数量 |
|---------|------|
| 怪物 | 120 |
| 物品 | 958 |
| 技能 | 448 |

数据来源于 BazaarHelper 项目的本地资源数据库（`items_db.json`、`monsters_db.json`、`skills_db.json`）。

## 安装

将本仓库克隆到 AstrBot 的插件目录：

```bash
cd /path/to/astrbot/data/plugins/
git clone https://github.com/你的用户名/astrbot_plugin_bazaar.git
```

重启 AstrBot 即可自动加载插件。

## 指令列表

| 指令 | 说明 | 示例 |
|------|------|------|
| `/bzhelp` | 查看帮助信息 | `/bzhelp` |
| `/bzmonster <名称>` | 查询怪物详情 | `/bzmonster 火灵` 或 `/bzmonster Pyro` |
| `/bzitem <名称>` | 查询物品详情 | `/bzitem 地下商街` 或 `/bzitem Toolbox` |
| `/bzskill <名称>` | 查询技能详情 | `/bzskill 热情如火` |
| `/bzsearch <关键词>` | 搜索怪物、物品和技能 | `/bzsearch 灼烧` 或 `/bzsearch poison` |
| `/bzlist` | 列出所有怪物 | `/bzlist` |
| `/bzitems [标签]` | 按标签筛选物品 | `/bzitems Weapon` |
| `/bztier <品质>` | 按品质筛选物品 | `/bztier Gold` 或 `/bztier 钻石` |
| `/bzhero <英雄名>` | 查看英雄专属内容 | `/bzhero 朱尔斯` |

## 数据结构

### 怪物数据 (`data/monsters_db.json`)

```json
{
  "怪物中文名": {
    "name": "英文名",
    "name_zh": "中文名",
    "available": "Day 1",
    "health": 100,
    "level": 1,
    "combat": { "gold": "2 Gold", "exp": "3 XP" },
    "skills": [...],
    "items": [...]
  }
}
```

### 物品数据 (`data/items_db.json`)

```json
[
  {
    "id": "uuid",
    "name_en": "英文名",
    "name_cn": "中文名",
    "starting_tier": "Gold / 黄金",
    "available_tiers": "Gold/Diamond",
    "heroes": "Jules / 朱尔斯",
    "tags": "Property / 地产",
    "size": "Large / 大型",
    "cooldown": 7.0,
    "skills": [{ "en": "...", "cn": "..." }],
    "skills_passive": [{ "en": "...", "cn": "..." }],
    "enchantments": { ... }
  }
]
```

### 技能数据 (`data/skills_db.json`)

```json
[
  {
    "id": "uuid",
    "name_en": "英文名",
    "name_cn": "中文名",
    "description_en": "英文描述",
    "description_cn": "中文描述",
    "heroes": "Jules / 朱尔斯",
    "starting_tier": "Diamond / 钻石"
  }
]
```

## 更新数据

数据文件可从 BazaarHelper 仓库的 `src-tauri/resources/` 目录获取最新版本：

```bash
curl -o data/items_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/items_db.json
curl -o data/monsters_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/monsters_db.json
curl -o data/skills_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/skills_db.json
```

## 依赖

- AstrBot >= 4.0
- aiohttp >= 3.9.0

## 致谢

- [BazaarHelper](https://github.com/Duangi/BazaarHelper) - 游戏数据来源
- [AstrBot](https://github.com/Soulter/AstrBot) - 聊天机器人框架

## 许可证

MIT License
