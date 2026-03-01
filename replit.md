# AstrBot Plugin - Bazaar 数据查询助手

## 概述
基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能、事件等）。查询结果以精美的图片卡片形式呈现。

## 数据规模
- 120 个怪物 (monsters_db.json)
- 958 个物品 (items_db.json)
- 448 个技能 (skills_db.json)
- 39 个事件 (event_detail.json + event_encounters.json 英雄/品质增强)

数据来源于 BazaarHelper 项目 `src-tauri/resources/` 目录的本地 JSON 数据库文件。支持通过 `/tbzupdate` 在线更新。

## 项目结构
```
├── main.py                # 插件主代码（指令处理器）
├── card_renderer.py       # 图片卡片渲染器（Pillow生成PNG卡片）
├── _conf_schema.json      # AstrBot 插件配置 Schema（别名配置、默认数量、数据源优先级）
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖 (Pillow, aiohttp)
├── README.md              # 项目说明
├── CHANGELOG.md           # 更新日志
├── LICENSE                # MIT 许可证
├── logo.png               # 插件 Logo
├── tests/
│   └── app.py             # 交互式测试工具
└── data/
    ├── items_db.json      # 物品数据库 (958条)
    ├── monsters_db.json   # 怪物数据库 (120条)
    ├── skills_db.json     # 技能数据库 (448条)
    ├── event_detail.json  # 事件数据库 (39条)
    ├── event_encounters.json # 事件引擎数据 (373条，用于增强event_detail)
    ├── aliases.json       # 别名配置（向下兼容，无config时使用）
    └── cache/             # 图片缓存目录（自动创建）
```

## 支持的指令
- `/tbzhelp` - 查看帮助
- `/tbzmonster <名称>` - 查询怪物信息（输出图片卡片）
- `/tbzitem <名称>` - 查询物品信息（输出图片卡片，含任务信息）
- `/tbzskill <名称>` - 查询技能信息（输出图片卡片）
- `/tbzevent <名称>` - 查询事件详情（选项及描述，含适用英雄和品质）
- `/tbzsearch <条件>` - 多条件搜索（支持 tag:/tier:/hero:/size: 前缀组合，合并转发输出，含事件结果，事件支持按英雄过滤）
- `/tbznews [数量]` - 查询游戏官方更新公告（Steam 中文翻译，图片卡片输出）
- `/tbzbuild <物品名> [数量]` - 查询推荐阵容（默认5条，最多10条，双数据源，合并转发输出）
- `/tbztier <英雄名>` - 查询英雄物品评级 Tier List（图片卡片输出，S/A/B/C 分级）
- `/tbzalias` - 别名管理（list/add/del）
- `/tbzupdate` - 从 BazaarHelper 仓库更新游戏数据

## AI 工具 (@llm_tool)
- 9 个 `@filter.llm_tool` 注册到 AstrBot LLM 工具链，AI 对话中自动调用：
  - `bazaar_query_item` — 查询物品详情（参数: item_name）
  - `bazaar_query_monster` — 查询怪物详情（参数: monster_name）
  - `bazaar_query_skill` — 查询技能详情（参数: skill_name）
  - `bazaar_query_event` — 查询事件详情（参数: event_name）
  - `bazaar_search` — 多条件搜索（参数: query）
  - `bazaar_query_build` — 查询推荐阵容（参数: query, count）
  - `bazaar_get_news` — 查询游戏更新公告（参数: count）
  - `bazaar_query_tierlist` — 查询英雄物品评级（参数: hero_name）
- 工具返回纯文本格式（非图片），供 AI 整合到回复中
- 需要 AstrBot 配置支持函数调用的 LLM 模型才能使用 AI 工具

## AI 人格预设
- `_register_persona()` 在 `initialize()` 中调用，通过 `self.context.persona_manager` 注册
- persona_id: `bazaar_helper`，包含游戏背景、英雄列表、工具使用规则的系统提示词
- begin_dialogs: 2 条开场对话（user/assistant 交替）
- tools: 绑定 9 个 bazaar_* 工具（含 bazaar_query_tierlist），确保人格模式下优先调用
- 幂等注册：已存在则 update_persona，不存在则 create_persona

## 数据源架构
### BazaarHelper（游戏数据主源，中英文）
- 物品/怪物/技能/事件的完整中英文数据
- 不可替代：BazaarForge 全英文无中文翻译

### BazaarForge（阵容+评级，英文）
- Supabase API: `https://cwlgghqlqvpbmfuvkvle.supabase.co`
- 用于：阵容搜索（按物品UUID/英雄/标题）、物品评级（hero_stats字段）
- 物品名→UUID 查找 → builds 表按 item_ids 过滤
- Tier List: items 表 hero_stats->>HeroName 降序排列

### bazaar-builds.net（阵容补充源）
- WordPress REST API
- 作为 BazaarForge 的回退/补充数据源

## API 缓存
- `_cached_request(key, ttl, fetch_fn)` 通用 TTL 内存缓存
- 阵容: 12小时、Tier List: 12小时、Steam新闻: 30分钟、物品UUID映射: 60分钟
- 纯内存，不落盘

## 事件数据增强
- `_enrich_events()` 在 `_load_data()` 末尾调用
- 从 `event_encounters.json`（373条引擎原始数据）提取 `Heroes` 和 `StartingTier` 字段
- 通过 InternalName / Title 与 event_detail.json 的 name_en 匹配（精确+子串回退）
- 39/39 条事件全部匹配成功，补充英雄适用性和品质信息

## 游戏更新公告
- `/tbznews` 从 Steam Store API 获取官方中文翻译公告
- API: `https://store.steampowered.com/events/ajaxgetpartnereventspageable/?clan_accountid=0&appid=1617400&l=schinese`
- BBCode 转纯文本：`_strip_bbcode()` 处理 h1/h3/list/url/img/previewyoutube 等标签
- `render_news_card()` 渲染为长图片（暗色背景、标题+日期+正文+Steam链接）
- 配置项: `news_default_count`（默认1，最大20）

## 别名与配置系统
- 使用 AstrBot 的 `_conf_schema.json` 配置体系，别名可通过 AstrBot 管理面板直接编辑
- 配置项: `hero_aliases`, `item_aliases`, `monster_aliases`, `skill_aliases`, `tag_aliases`, `tier_aliases`, `size_aliases`（均为 dict 类型）
- `build_default_count`（默认5）, `news_default_count`（默认1）, `build_source_priority`（默认forge_first）
- 向下兼容：无 config 时回退到 `data/aliases.json` 文件读写

## 图片卡片渲染
- 使用 Pillow 生成深色主题 PNG 卡片
- 2x 高清渲染（SCALE=2），输出 1040px 宽卡片，文字清晰锐利
- 缩略图 192px (96*2)，保持原始宽高比
- 品质（Bronze/Silver/Gold/Diamond）使用对应颜色高亮
- 物品卡片包含：技能、属性、数值(含tier成长)、附魔、任务
- 新闻卡片：标题+日期+BBCode正文+Steam链接
- Tier List 卡片：S/A/B/C 彩色分级、使用率百分比、进度条、阵容数
- 渲染失败时自动回退到纯文本输出
- 需要中文字体支持（WenQuanYi Zen Hei）

## 架构要点
- 持久化 aiohttp.ClientSession：在 `initialize()` 创建，`terminate()` 关闭，main.py 和 card_renderer.py 共享
- `_wrap_text()` 对中文逐字换行，英文按词换行
- 合并转发消息使用 `Comp.Nodes([Comp.Node(...)])` 构建，含异常回退逻辑

## 技术栈
- Python 3.11
- Pillow (图片生成)
- aiohttp (异步HTTP，用于获取游戏图片、BazaarForge API、阵容API、Steam新闻API)
- AstrBot 插件框架
