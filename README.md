# astrbot_plugin_bazaar

<p align="center">
  <img src="logo.png" alt="Bazaar Plugin Logo" width="200">
</p>

<p align="center">
  <b>AstrBot 插件 —— The Bazaar 游戏数据查询助手</b>
</p>

<p align="center">
  查询怪物 · 物品 · 技能 · 事件 · 推荐阵容 · 物品评级 · 更新公告 · 图片卡片展示
</p>

---

## 简介

astrbot_plugin_bazaar 是一个 [AstrBot](https://github.com/Soulter/AstrBot) 聊天机器人插件，可以在 QQ / Telegram / 微信等平台中快速查询 **[The Bazaar](https://www.thebazaar.gg/)** 游戏数据，包括怪物、物品、技能、事件信息，以及来自社区的推荐阵容和 Steam 官方更新公告。

查询结果以精美的**图片卡片**形式呈现，支持中英文双语查询。

## 数据来源

### BazaarHelper

本插件的游戏数据（怪物、物品、技能、事件）来源于 **[BazaarHelper](https://github.com/Duangi/BazaarHelper)** 项目。

BazaarHelper 是一个基于 Tauri 构建的 The Bazaar 游戏辅助工具，提供了完整的中英文游戏数据库，包含物品属性、技能描述、怪物信息等。本插件使用了其 `src-tauri/resources/` 目录下的 JSON 数据文件和图片资源。

感谢 [Duangi](https://github.com/Duangi) 维护的数据库。

| 数据类型 | 数量 | 来源文件 |
|---------|------|---------|
| 怪物 | 120 | `monsters_db.json` |
| 物品 | 958 | `items_db.json` |
| 技能 | 448 | `skills_db.json` |
| 事件 | 39 | `event_detail.json` + `event_encounters.json`（英雄/品质增强） |

### BazaarForge

阵容推荐和物品评级功能的主要数据来源于 **[BazaarForge.gg](https://bazaarforge.gg/)**。

BazaarForge 提供结构化的阵容数据（包含胜场、胜利类型、等级、物品列表等），以及基于社区阵容统计的物品使用率数据，用于生成英雄物品评级（Tier List）。

### Bazaar Builds

阵容推荐功能的补充数据来源于 **[bazaar-builds.net](https://bazaar-builds.net/)**。

当 BazaarForge 结果不足时，自动从 bazaar-builds.net 补充查询。也可通过配置切换数据源优先级。

### Steam 更新公告

游戏更新公告数据来源于 **Steam Store API**，自动获取官方中文翻译的补丁说明和更新公告。

## 功能特性

- 查询怪物详情（技能、物品、血量、奖励），以图片卡片展示
- 查询物品详情（属性、品质成长、附魔、任务），以图片卡片展示
- 查询技能详情（描述、适用英雄），以图片卡片展示
- 查询事件详情（选项及描述），包含适用英雄和品质等级
- 查询游戏官方更新公告，以图片长卡片展示（中文翻译，来自 Steam）
- 统一的多条件搜索：支持关键词、标签、品质、英雄、尺寸条件组合
- 智能分词：中文连写自动识别条件，如 `/tbzsearch 杜利中型灼烧`
- 按英雄筛选事件：`/tbzsearch hero:Jules` 可过滤该英雄相关事件
- 通过物品名查询社区推荐阵容（BazaarForge + bazaar-builds.net 双数据源）
- 英雄物品评级（Tier List）：按使用率 S/A/B/C 分级，图片卡片展示
- API 响应缓存：减少重复请求，提升响应速度
- 别名系统：支持社区昵称映射，可通过 AstrBot 管理面板或命令管理
- 在线数据更新：一键从 BazaarHelper 仓库拉取最新数据
- AI 工具集成：AI 在聊天中自动调用物品查询、搜索、阵容推荐、更新公告等功能
- 支持中英文双语查询
- 图片渲染失败时自动回退为纯文本

## 安装

将本仓库克隆到 AstrBot 的插件目录：

```bash
cd /path/to/astrbot/data/plugins/
git clone https://github.com/shitlsh/astrbot_plugin_bazaar.git
```

### 依赖

- AstrBot >= 4.0
- Python >= 3.11
- Pillow >= 10.0（图片卡片渲染）
- aiohttp >= 3.9.0（网络请求）

依赖会在 AstrBot 加载插件时自动安装（参见 `requirements.txt`）。

### 字体要求

图片卡片渲染需要中文字体支持。推荐安装 **WenQuanYi Zen Hei** 字体：

```bash
# Ubuntu / Debian
sudo apt install fonts-wqy-zenhei

# CentOS / RHEL
sudo yum install wqy-zenhei-fonts
```

如果没有安装中文字体，插件仍可正常运行，但图片卡片中的中文可能显示异常。

## 指令列表

| 指令 | 说明 | 示例 |
|------|------|------|
| `/tbzhelp` | 查看帮助信息 | `/tbzhelp` |
| `/tbzmonster <名称>` | 查询怪物详情（图片卡片） | `/tbzmonster 火灵` |
| `/tbzitem <名称>` | 查询物品详情（图片卡片） | `/tbzitem 放大镜` |
| `/tbzskill <名称>` | 查询技能详情（图片卡片） | `/tbzskill 热情如火` |
| `/tbzevent <名称>` | 查询事件详情（含适用英雄和品质） | `/tbzevent 奇异蘑菇` |
| `/tbzsearch <条件>` | 多条件搜索（含事件按英雄过滤） | `/tbzsearch 杜利中型灼烧` |
| `/tbznews [数量]` | 查询游戏官方更新公告（图片） | `/tbznews` 或 `/tbznews 3` |
| `/tbzbuild <物品名> [数量]` | 查询推荐阵容 | `/tbzbuild 符文匕首 5` |
| `/tbztier <英雄名>` | 查询英雄物品评级（Tier List） | `/tbztier 海盗` |
| `/tbzalias` | 别名管理 | `/tbzalias list hero` |
| `/tbzupdate` | 从远端更新游戏数据 | `/tbzupdate` |

所有指令均支持中英文输入。

### /tbzsearch 多条件搜索

支持三种输入方式：

- **智能连写**: `/tbzsearch 杜利中型灼烧` — 自动分词为英雄+尺寸+标签
- **空格分隔**: `/tbzsearch 马克 黄金 武器`
- **前缀语法**: `/tbzsearch tag:Weapon hero:Mak tier:Gold`

可用前缀：
- `tag:` / `标签:` — 按标签筛选
- `tier:` / `品质:` — 按品质筛选（Bronze/Silver/Gold/Diamond）
- `hero:` / `英雄:` — 按英雄筛选（物品和事件均支持）
- `size:` / `尺寸:` — 按尺寸筛选

无参数调用 `/tbzsearch` 可查看所有可用标签和英雄列表。

### /tbznews 更新公告

从 Steam 获取官方中文翻译的游戏更新公告，渲染为图片长卡片展示。

- 默认显示 1 条最新公告，可在末尾指定数量（最多 20 条）
- 多条公告以合并转发消息发送
- 默认数量可在管理面板配置（`news_default_count`）
- 示例：`/tbznews` 或 `/tbznews 3`

### /tbzbuild 说明

- 输入中文物品名会自动翻译为英文进行搜索
- 支持别名和智能分词：`/tbzbuild 海盗船锚` 自动识别为 `Vanessa Anchor`
- 自动过滤非阵容内容（Patch Notes、游戏更新等推广信息）
- 默认展示前 5 条结果（可在管理面板配置），末尾指定数量可覆盖（1-10）
- 每条结果包含阵容截图和原文链接
- 示例：`/tbzbuild Runic Daggers` 或 `/tbzbuild 符文匕首 5`

### /tbzalias 别名管理

别名系统支持将社区昵称映射到游戏内名称，在搜索和阵容查询时自动识别。

**配置方式（三选一）：**

1. **AstrBot 管理面板**（推荐）：在插件配置页面直接编辑各分类别名
2. **命令管理**：
   - 查看: `/tbzalias list [分类]`
   - 添加: `/tbzalias add hero 猪猪 Pygmalien`
   - 删除: `/tbzalias del hero 猪猪`
3. **直接编辑文件**：修改 `data/aliases.json`

支持 7 种分类：`hero`(英雄)、`item`(物品)、`monster`(怪物)、`skill`(技能)、`tag`(标签)、`tier`(品质)、`size`(尺寸)

预置别名：猪猪→Pygmalien、鸡煲→Dooley、海盗→Vanessa、黑妹→Stelle、厨子→Jules、中立→Common 等。

## AI 工具集成

插件注册了 9 个 AI 工具（`@llm_tool`），当 AstrBot 配置了支持函数调用的 LLM 后，AI 可以在对话中自动调用这些功能，无需用户手动输入指令：

| 工具名 | 功能 | 触发场景示例 |
|--------|------|-------------|
| `bazaar_query_item` | 查询物品详情 | "放大镜是什么效果？" |
| `bazaar_query_monster` | 查询怪物详情 | "火灵有什么技能？" |
| `bazaar_query_skill` | 查询技能详情 | "热情如火这个技能怎么样？" |
| `bazaar_query_event` | 查询事件详情 | "奇异蘑菇事件怎么选？" |
| `bazaar_search` | 多条件搜索 | "有哪些黄金武器？" |
| `bazaar_query_build` | 查询推荐阵容 | "海盗船锚怎么搭配？" |
| `bazaar_get_news` | 查询更新公告 | "最近更新了什么？" |
| `bazaar_query_tierlist` | 查询英雄物品评级 | "海盗哪些物品好用？" |

AI 会根据用户的自然语言自动选择合适的工具调用，并将结果整合到回复中。

### 人格预设

插件启动时会自动在 AstrBot 中注册一个名为 `bazaar_helper` 的人格预设「大巴扎小助手」。

启用方式：在 AstrBot 管理面板 → 人格设定 → 选择「bazaar_helper」作为默认人格。

启用后，AI 会：
- 自动识别游戏相关问题并调用查询工具
- 以友好专业的游戏助手风格回复
- 优先使用工具获取真实数据，而非凭空编造

## 插件配置

本插件使用 AstrBot 的 `_conf_schema.json` 配置系统，别名可通过 AstrBot 管理面板直接编辑，无需手动修改文件。

配置项：

| 配置名 | 说明 | 类型 |
|--------|------|------|
| `hero_aliases` | 英雄别名 | text (JSON) |
| `item_aliases` | 物品别名 | text (JSON) |
| `monster_aliases` | 怪物别名 | text (JSON) |
| `skill_aliases` | 技能别名 | text (JSON) |
| `tag_aliases` | 标签别名 | text (JSON) |
| `tier_aliases` | 品质别名 | text (JSON) |
| `size_aliases` | 尺寸别名 | text (JSON) |
| `build_default_count` | 阵容查询默认返回数量（1-10） | int |
| `news_default_count` | 更新公告默认获取数量（1-20） | int |
| `build_source_priority` | 阵容数据源优先级 | text |

## 项目结构

```
├── main.py              # 插件主代码（指令处理器）
├── card_renderer.py     # 图片卡片渲染器（Pillow）
├── _conf_schema.json    # AstrBot 插件配置 Schema
├── metadata.yaml        # AstrBot 插件元数据
├── requirements.txt     # Python 依赖
├── logo.png             # 插件 Logo
├── README.md            # 本文件
├── CHANGELOG.md         # 更新日志
├── LICENSE              # MIT 许可证
└── data/
    ├── items_db.json       # 物品数据库
    ├── monsters_db.json    # 怪物数据库
    ├── skills_db.json      # 技能数据库
    ├── event_detail.json   # 事件数据库
    ├── event_encounters.json # 事件引擎数据（英雄/品质增强）
    ├── aliases.json        # 别名配置（向下兼容）
    └── cache/              # 图片缓存（自动创建）
```

## 更新数据

方式一：使用指令在线更新（推荐）

```
/tbzupdate
```

方式二：手动从 BazaarHelper 仓库下载

```bash
cd astrbot_plugin_bazaar/data/
curl -o items_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/items_db.json
curl -o monsters_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/monsters_db.json
curl -o skills_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/skills_db.json
curl -o event_detail.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/event_detail.json
curl -o event_encounters.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/event_encounters.json
```

## 致谢

- **[BazaarHelper](https://github.com/Duangi/BazaarHelper)** — 游戏数据来源，由 [Duangi](https://github.com/Duangi) 维护
- **[BazaarForge.gg](https://bazaarforge.gg/)** — 阵容推荐和物品评级数据来源
- **[bazaar-builds.net](https://bazaar-builds.net/)** — 社区阵容推荐数据来源
- **[Steam](https://store.steampowered.com/app/1617400/)** — 游戏更新公告数据来源
- **[AstrBot](https://github.com/Soulter/AstrBot)** — 聊天机器人框架
- **[The Bazaar](https://www.thebazaar.gg/)** — Tempo Storm 开发的游戏

## 许可证

MIT License
