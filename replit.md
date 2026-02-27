# AstrBot Plugin - Bazaar 数据查询助手

## 概述
基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。查询结果以精美的图片卡片形式呈现。

## 数据规模
- 120 个怪物 (monsters_db.json)
- 958 个物品 (items_db.json)
- 448 个技能 (skills_db.json)

数据来源于 BazaarHelper 项目 `src-tauri/resources/` 目录的本地 JSON 数据库文件。支持通过 `/tbzupdate` 在线更新。

## 项目结构
```
├── main.py                # 插件主代码（指令处理器）
├── card_renderer.py       # 图片卡片渲染器（Pillow生成PNG卡片）
├── _conf_schema.json      # AstrBot 插件配置 Schema（别名配置）
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
    ├── aliases.json       # 别名配置（向下兼容，无config时使用）
    └── cache/             # 图片缓存目录（自动创建）
```

## 支持的指令
- `/tbzhelp` - 查看帮助
- `/tbzmonster <名称>` - 查询怪物信息（输出图片卡片）
- `/tbzitem <名称>` - 查询物品信息（输出图片卡片，含任务信息）
- `/tbzskill <名称>` - 查询技能信息（输出图片卡片）
- `/tbzsearch <条件>` - 多条件搜索（支持 tag:/tier:/hero:/size: 前缀组合，合并转发输出）
- `/tbzbuild <物品名> [数量]` - 查询推荐阵容（默认5条，最多10条，合并转发输出）
- `/tbzalias` - 别名管理（list/add/del）
- `/tbzupdate` - 从 BazaarHelper 仓库更新游戏数据

## AI 工具 (@llm_tool)
- 5 个 `@filter.llm_tool` 注册到 AstrBot LLM 工具链，AI 对话中自动调用：
  - `bazaar_query_item` — 查询物品详情（参数: item_name）
  - `bazaar_query_monster` — 查询怪物详情（参数: monster_name）
  - `bazaar_query_skill` — 查询技能详情（参数: skill_name）
  - `bazaar_search` — 多条件搜索（参数: query）
  - `bazaar_query_build` — 查询推荐阵容（参数: query, count）
- 工具返回纯文本格式（非图片），供 AI 整合到回复中
- 复用现有的 `_resolve_alias()`, `_search_*()`, `_filter_*()`, `_translate_build_query()` 等方法

## 别名与配置系统
- 使用 AstrBot 的 `_conf_schema.json` 配置体系，别名可通过 AstrBot 管理面板直接编辑
- 配置项: `hero_aliases`, `item_aliases`, `monster_aliases`, `skill_aliases`, `tag_aliases`, `tier_aliases`, `size_aliases`（均为 dict 类型）
- `__init__` 接收 `AstrBotConfig` 参数，通过 `self.config.get()` / `self.config.save_config()` 读写配置
- 向下兼容：无 config 时回退到 `data/aliases.json` 文件读写
- hero/tag/tier/size 别名自动注入 `_build_vocab()` 词汇表，搜索时智能分词可识别
- item/monster/skill 别名用于 `_resolve_alias()`，在查询命令中自动替换为目标名称
- `_reload_aliases_if_changed()` 在每次搜索/查询前检测配置变更并自动重载

## 图片卡片渲染
- 使用 Pillow 生成深色主题 PNG 卡片
- 2x 高清渲染（SCALE=2），输出 1040px 宽卡片，文字清晰锐利
- 缩略图 192px (96*2)，保持原始宽高比（源图来自 BazaarHelper GitHub 仓库，缓存到 `data/cache/`）
- 品质（Bronze/Silver/Gold/Diamond）使用对应颜色高亮
- 物品卡片包含：技能、属性、数值(含tier成长)、附魔、任务
- 渲染失败时自动回退到纯文本输出
- 需要中文字体支持（WenQuanYi Zen Hei）

## 多条件搜索
- `/tbzsearch` 支持智能模糊识别和前缀语法：
  - 智能连写: `/tbzsearch 杜利中型灼烧` (自动分词为 英雄+尺寸+标签)
  - 空格分隔: `/tbzsearch 马克 黄金 武器`
  - 前缀语法: `tag:` `tier:` `hero:` `size:` (中文别名: `标签:` `品质:` `英雄:` `尺寸:`)
- `_build_vocab()` 从数据构建词汇索引，`_smart_tokenize()` 用最长匹配贪心算法自动分词
- 搜索结果显示"识别条件"让用户确认理解是否正确
- 搜索结果完整展示（不截断），使用合并转发消息格式

## 阵容查询
- `/tbzbuild` 通过 bazaar-builds.net 的 WordPress REST API 搜索阵容
- 支持中文物品名自动翻译为英文进行搜索
- 支持别名和智能分词：`/tbzbuild 海盗船锚` → `Vanessa Anchor`
- 默认返回3条结果，用户可指定1-10条
- 结果以合并转发消息(Comp.Nodes)打包发送，避免刷屏；不支持的平台自动回退逐条发送
- API端点: `https://bazaar-builds.net/wp-json/wp/v2/posts?search=...`

## 数据更新
- `/tbzupdate` 从 BazaarHelper GitHub 仓库下载最新 JSON 数据
- 下载地址: `https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/{items_db,monsters_db,skills_db}.json`
- 下载后验证 JSON 格式，写入 `data/` 目录并热重载

## 架构要点
- 持久化 aiohttp.ClientSession：在 `initialize()` 创建，`terminate()` 关闭，main.py 和 card_renderer.py 共享
- HTML 清理使用 `re.sub(r'<[^>]+>', '', text)` 正则替换
- 搜索校验逻辑提取为通用 `_resolve_search()` 辅助函数
- `_wrap_text()` 对中文逐字换行，英文按词换行，避免截断单词
- card_renderer.py 中所有布局数值提取为模块级常量（PADDING, LINE_HEIGHT_*, THUMB_SIZE 等）
- 合并转发消息使用 `Comp.Nodes([Comp.Node(...)])` 构建，含异常回退逻辑

## 技术栈
- Python 3.11
- Pillow (图片生成)
- aiohttp (异步HTTP，用于获取游戏图片和阵容API)
- AstrBot 插件框架
