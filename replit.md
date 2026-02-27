# AstrBot Plugin - Bazaar 数据查询助手

## 概述
基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。

## 项目结构
```
astrbot_plugin_bazaar/     # 插件主目录（可直接复制到 AstrBot 插件目录使用）
├── main.py                # 插件主代码
├── metadata.yaml          # 插件元数据
├── requirements.txt       # 依赖
└── data/
    ├── monsters.json      # 怪物数据
    └── items.json         # 物品数据

astrbot/                   # AstrBot API Mock（仅用于本地测试）
├── api/
│   ├── __init__.py        # logger mock
│   ├── event/__init__.py  # 事件/过滤器 mock
│   └── star/__init__.py   # Star/Context mock

app.py                     # 交互式测试入口
test_plugin.py             # 自动化测试脚本
```

## 支持的指令
- `/bzhelp` - 查看帮助
- `/bzmonster <名称>` - 查询怪物信息（支持中英文）
- `/bzitem <名称>` - 查询物品信息
- `/bzsearch <关键词>` - 搜索怪物和物品
- `/bzlist` - 列出所有怪物
- `/bzitems [标签]` - 按标签筛选物品
- `/bztier <品质>` - 按品质筛选物品

## 技术栈
- Python 3.11
- AstrBot 插件框架

## 使用方法
将 `astrbot_plugin_bazaar/` 目录复制到 AstrBot 的插件目录即可使用。
