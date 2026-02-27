# astrbot_plugin_bazaar

<p align="center">
  <img src="logo.png" alt="Bazaar Plugin Logo" width="200">
</p>

<p align="center">
  <b>AstrBot 插件 —— The Bazaar 游戏数据查询助手</b>
</p>

<p align="center">
  查询怪物 · 物品 · 技能 · 推荐阵容 · 图片卡片展示
</p>

---

## 简介

astrbot_plugin_bazaar 是一个 [AstrBot](https://github.com/Soulter/AstrBot) 聊天机器人插件，可以在 QQ / Telegram / 微信等平台中快速查询 **[The Bazaar](https://www.thebazaar.gg/)** 游戏数据，包括怪物、物品、技能信息，以及来自社区的推荐阵容。

查询结果以精美的**图片卡片**形式呈现，支持中英文双语查询。

## 数据来源

### BazaarHelper

本插件的游戏数据（怪物、物品、技能）来源于 **[BazaarHelper](https://github.com/Duangi/BazaarHelper)** 项目。

BazaarHelper 是一个基于 Tauri 构建的 The Bazaar 游戏辅助工具，提供了完整的中英文游戏数据库，包含物品属性、技能描述、怪物信息等。本插件使用了其 `src-tauri/resources/` 目录下的 JSON 数据文件和图片资源。

感谢 [Duangi](https://github.com/Duangi) 维护的数据库。

| 数据类型 | 数量 | 来源文件 |
|---------|------|---------|
| 怪物 | 120 | `monsters_db.json` |
| 物品 | 958 | `items_db.json` |
| 技能 | 448 | `skills_db.json` |

### Bazaar Builds

阵容推荐功能的数据来源于 **[bazaar-builds.net](https://bazaar-builds.net/)**。

Bazaar Builds 是一个由社区驱动的 The Bazaar 阵容分享网站，玩家可以在上面分享自己的通关阵容截图和心得。本插件通过其公开的 WordPress REST API 搜索相关阵容，并将阵容截图直接发送给用户。

访问 [bazaar-builds.net/tag/billboard/](https://bazaar-builds.net/tag/billboard/) 可以浏览精选阵容。

## 功能特性

- 查询怪物详情（技能、物品、血量、奖励），以图片卡片展示
- 查询物品详情（属性、品质成长、附魔），以图片卡片展示
- 查询技能详情（描述、适用英雄），以图片卡片展示
- 按关键词全局搜索怪物、物品和技能
- 按标签、品质筛选物品
- 按英雄查看专属物品和技能
- 通过物品名查询社区推荐阵容（展示阵容截图）
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
| `/bzhelp` | 查看帮助信息 | `/bzhelp` |
| `/bzmonster <名称>` | 查询怪物详情（图片卡片） | `/bzmonster 火灵` |
| `/bzitem <名称>` | 查询物品详情（图片卡片） | `/bzitem 放大镜` |
| `/bzskill <名称>` | 查询技能详情（图片卡片） | `/bzskill 热情如火` |
| `/bzsearch <关键词>` | 搜索怪物、物品和技能 | `/bzsearch 灼烧` |
| `/bzitems [标签]` | 按标签筛选物品 | `/bzitems Weapon` |
| `/bztier <品质>` | 按品质筛选物品 | `/bztier Gold` |
| `/bzhero <英雄名>` | 查看英雄专属内容 | `/bzhero 朱尔斯` |
| `/bzbuild <物品名> [数量]` | 查询推荐阵容 | `/bzbuild 符文匕首 5` |

所有指令均支持中英文输入。

### /bzbuild 说明

- 输入中文物品名会自动翻译为英文进行搜索
- 默认展示前 3 条结果，可在末尾指定数量（1-10）
- 每条结果包含阵容截图和原文链接
- 示例：`/bzbuild Runic Daggers` 或 `/bzbuild 符文匕首 5`

## 项目结构

```
├── main.py              # 插件主代码（指令处理器）
├── card_renderer.py     # 图片卡片渲染器（Pillow）
├── metadata.yaml        # AstrBot 插件元数据
├── requirements.txt     # Python 依赖
├── logo.png             # 插件 Logo
├── README.md            # 本文件
├── LICENSE              # MIT 许可证
└── data/
    ├── items_db.json    # 物品数据库
    ├── monsters_db.json # 怪物数据库
    ├── skills_db.json   # 技能数据库
    └── cache/           # 图片缓存（自动创建）
```

## 更新数据

游戏数据可从 BazaarHelper 仓库获取最新版本：

```bash
cd astrbot_plugin_bazaar/data/
curl -o items_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/items_db.json
curl -o monsters_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/monsters_db.json
curl -o skills_db.json https://raw.githubusercontent.com/Duangi/BazaarHelper/main/src-tauri/resources/skills_db.json
```

## 致谢

- **[BazaarHelper](https://github.com/Duangi/BazaarHelper)** — 游戏数据来源，由 [Duangi](https://github.com/Duangi) 维护
- **[bazaar-builds.net](https://bazaar-builds.net/)** — 社区阵容推荐数据来源
- **[AstrBot](https://github.com/Soulter/AstrBot)** — 聊天机器人框架
- **[The Bazaar](https://www.thebazaar.gg/)** — Tempo Storm 开发的游戏

## 许可证

MIT License
