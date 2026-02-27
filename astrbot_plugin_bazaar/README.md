# astrbot_plugin_bazaar

基于 [BazaarHelper](https://github.com/Duangi/BazaarHelper) 的 AstrBot 插件，用于在聊天中查询 The Bazaar 游戏数据（怪物、物品、技能等）。

## 功能

- 查询怪物详细信息（技能、专属物品）
- 查询物品详细信息（属性、品质成长）
- 按关键词全局搜索怪物和物品
- 按标签、品质筛选物品
- 支持中英文双语查询

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
| `/bzmonster <名称>` | 查询怪物详情 | `/bzmonster 火灵` 或 `/bzmonster pyro` |
| `/bzitem <名称>` | 查询物品详情 | `/bzitem 短剑` 或 `/bzitem sword` |
| `/bzsearch <关键词>` | 搜索怪物和物品 | `/bzsearch 灼烧` 或 `/bzsearch poison` |
| `/bzlist` | 列出所有怪物 | `/bzlist` |
| `/bzitems [标签]` | 按标签筛选物品 | `/bzitems Weapon` |
| `/bztier <品质>` | 按品质筛选物品 | `/bztier Gold` |

## 数据结构

### 怪物数据 (`data/monsters.json`)

```json
{
  "怪物中文名": {
    "name": "英文名",
    "name_zh": "中文名",
    "skills": [
      {
        "id": "技能ID",
        "name": "技能中文名",
        "name_en": "技能英文名",
        "tier": "品质",
        "description": "技能描述"
      }
    ],
    "items": [
      {
        "id": "物品ID",
        "name": "物品中文名",
        "name_en": "物品英文名",
        "tier": "品质",
        "description": "物品描述"
      }
    ]
  }
}
```

### 物品数据 (`data/items.json`)

```json
[
  {
    "id": "物品ID",
    "name_en": "英文名",
    "name_cn": "中文名",
    "tier": "品质 (Bronze/Silver/Gold/Diamond)",
    "available_tiers": "可用品质",
    "heroes": "适用英雄",
    "tags": "标签 (逗号分隔)",
    "size": "尺寸 (Small/Medium/Large)",
    "cooldown": 5,
    "description": "物品描述",
    "damage_tiers": "伤害成长",
    "heal_tiers": "治疗成长"
  }
]
```

## 扩展数据

你可以通过编辑 `data/monsters.json` 和 `data/items.json` 来添加更多游戏数据。插件会在启动时自动加载这些文件。

## 依赖

- AstrBot >= 4.0
- aiohttp >= 3.9.0

## 致谢

- [BazaarHelper](https://github.com/Duangi/BazaarHelper) - 游戏数据模型参考
- [AstrBot](https://github.com/Soulter/AstrBot) - 聊天机器人框架

## 许可证

MIT License
