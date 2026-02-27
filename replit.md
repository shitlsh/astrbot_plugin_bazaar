# AstrBot Plugin - Bazaar 数据查询助手

## 概述
基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。查询结果以精美的图片卡片形式呈现。

## 数据规模
- 120 个怪物 (monsters_db.json)
- 958 个物品 (items_db.json)
- 448 个技能 (skills_db.json)

数据来源于 BazaarHelper 项目 `src-tauri/resources/` 目录的本地 JSON 数据库文件。

## 项目结构
```
├── main.py                # 插件主代码（指令处理器）
├── card_renderer.py       # 图片卡片渲染器（Pillow生成PNG卡片）
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖 (Pillow, aiohttp)
├── README.md              # 项目说明
├── LICENSE                # MIT 许可证
├── logo.png               # 插件 Logo
└── data/
    ├── items_db.json      # 物品数据库 (958条)
    ├── monsters_db.json   # 怪物数据库 (120条)
    ├── skills_db.json     # 技能数据库 (448条)
    └── cache/             # 图片缓存目录（自动创建）
```

## 支持的指令
- `/bzhelp` - 查看帮助
- `/bzmonster <名称>` - 查询怪物信息（输出图片卡片）
- `/bzitem <名称>` - 查询物品信息（输出图片卡片）
- `/bzskill <名称>` - 查询技能信息（输出图片卡片）
- `/bzsearch <关键词>` - 搜索怪物、物品和技能
- `/bzitems [标签]` - 按标签筛选物品
- `/bztier <品质>` - 按品质筛选物品
- `/bzhero <英雄名>` - 查看英雄专属内容
- `/bzbuild <物品名> [数量]` - 查询推荐阵容（默认3条，最多10条）

## 图片卡片渲染
- 使用 Pillow 生成深色主题 PNG 卡片
- 怪物/物品图片从 BazaarHelper GitHub 仓库拉取并缓存到 `data/cache/`
- 品质（Bronze/Silver/Gold/Diamond）使用对应颜色高亮
- 渲染失败时自动回退到纯文本输出
- 需要中文字体支持（WenQuanYi Zen Hei）

## 阵容查询
- `/bzbuild` 通过 bazaar-builds.net 的 WordPress REST API 搜索阵容
- 支持中文物品名自动翻译为英文进行搜索
- 默认返回3条结果，用户可指定1-10条
- API端点: `https://bazaar-builds.net/wp-json/wp/v2/posts?search=...`

## 架构要点
- 持久化 aiohttp.ClientSession：在 `initialize()` 创建，`terminate()` 关闭，main.py 和 card_renderer.py 共享
- HTML 清理使用 `re.sub(r'<[^>]+>', '', text)` 正则替换
- 搜索校验逻辑提取为通用 `_resolve_search()` 辅助函数
- `_wrap_text()` 对中文逐字换行，英文按词换行，避免截断单词
- card_renderer.py 中所有布局数值提取为模块级常量（PADDING, LINE_HEIGHT_* 等）
- `@register` 装饰器保留用于兼容旧版 AstrBot，新版会自动识别 Star 子类

## 技术栈
- Python 3.11
- Pillow (图片生成)
- aiohttp (异步HTTP，用于获取游戏图片和阵容API)
- AstrBot 插件框架
