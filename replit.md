# AstrBot Plugin - Bazaar 数据查询助手

## 概述
基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。

## 数据规模
- 120 个怪物 (monsters_db.json)
- 958 个物品 (items_db.json)
- 448 个技能 (skills_db.json)

数据来源于 BazaarHelper 项目 `src-tauri/resources/` 目录的本地 JSON 数据库文件。

## 项目结构
```
astrbot_plugin_bazaar/     # 插件主目录（可直接复制到 AstrBot 插件目录使用）
├── main.py                # 插件主代码
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖
├── README.md              # 项目说明
├── LICENSE                # MIT 许可证
├── .gitignore             # Git 忽略规则
└── data/
    ├── items_db.json      # 物品数据库 (958条)
    ├── monsters_db.json   # 怪物数据库 (120条)
    └── skills_db.json     # 技能数据库 (448条)

astrbot/                   # AstrBot API Mock（仅用于本地测试）
app.py                     # 交互式测试入口
test_plugin.py             # 自动化测试脚本
```

## 支持的指令
- `/bzhelp` - 查看帮助
- `/bzmonster <名称>` - 查询怪物信息（支持中英文）
- `/bzitem <名称>` - 查询物品信息
- `/bzskill <名称>` - 查询技能信息
- `/bzsearch <关键词>` - 搜索怪物、物品和技能
- `/bzlist` - 列出所有怪物
- `/bzitems [标签]` - 按标签筛选物品
- `/bztier <品质>` - 按品质筛选物品
- `/bzhero <英雄名>` - 查看英雄专属内容

## 技术栈
- Python 3.11
- AstrBot 插件框架
