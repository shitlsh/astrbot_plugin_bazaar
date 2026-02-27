# Changelog

## v1.0.3

### Features

- 别名系统：新增 `/tbzalias` 命令管理别名（list/add/del），配置持久化到 `data/aliases.json`
  - 支持 7 种分类：hero, item, monster, skill, tag, tier, size
  - 后台文件和命令行两种方式修改后数据自动保持一致（文件变更自动检测重载）
- 预置社区常用英雄别名：猪猪/猪/猪哥→Pygmalien、鸡煲/机宝→Dooley、海盗/海盗姐→Vanessa、黑妹→Stelle、厨子/大厨/厨师→Jules、中立/通用→Common
- `/tbzbuild` 阵容查询支持智能分词和别名：`/tbzbuild 海盗船锚` 自动识别为 `Vanessa Anchor` 搜索
- 智能分词 CJK 模糊匹配：`/tbzsearch 杜利中型灼烧` 自动分词为英雄+尺寸+标签条件
- 搜索条件新增尺寸（size/尺寸）前缀支持

### Improvements

- 图片卡片 2x 高清渲染（SCALE=2），输出 1040px 宽卡片，文字更加清晰锐利
- 卡片中 emoji 字符替换为中文方括号标题（如【主动技能】），修复字体不支持 emoji 导致的方块显示
- 搜索结果显示"识别条件"，让用户确认系统理解是否正确
- 品质筛选中英文映射修正（青铜→Bronze、黄金→Gold 等）

## v1.0.2

### Features

- 物品卡片新增「📜 任务」区域，显示任务目标和奖励（参考 BazaarHelper 的 UnifiedItemCard 渲染方式）
- 新增 `/tbzupdate` 指令：从 BazaarHelper GitHub 仓库下载最新的 items_db、monsters_db、skills_db 数据并热重载
- 合并搜索指令：将 `/tbzsearch`、`/tbzitems`、`/tbztier`、`/tbzhero` 合并为统一的 `/tbzsearch` 多条件搜索
  - 支持 `tag:标签`、`tier:品质`、`hero:英雄` 条件前缀，可组合使用
  - 搜索结果不再截断，完整展示，使用合并转发消息格式发送
  - 无参数时显示搜索帮助，列出所有可用标签和英雄

### Improvements

- 物品/怪物图片分辨率提升：缩略图从 64x64 增大至 96px，保持原始宽高比，图像更清晰
- 物品卡片头部布局调整，适配更大的缩略图尺寸

### Removed

- 移除 `/tbzitems`、`/tbztier`、`/tbzhero` 独立指令（功能已合并至 `/tbzsearch`）

## v1.0.1

### Breaking Changes

- 所有指令前缀从 `/bz` 更改为 `/tbz`，避免在 QQ 平台中 `/bz` 被误识别为表情包
  - `/bzhelp` → `/tbzhelp`
  - `/bzmonster` → `/tbzmonster`
  - `/bzitem` → `/tbzitem`
  - `/bzskill` → `/tbzskill`
  - `/bzsearch` → `/tbzsearch`
  - `/bzitems` → `/tbzitems`
  - `/bztier` → `/tbztier`
  - `/bzhero` → `/tbzhero`
  - `/bzbuild` → `/tbzbuild`

### Bug Fixes

- 修复指令参数解析问题：`event.message_str` 在真实 AstrBot 框架中包含完整命令文本，导致命令名被当作查询参数的一部分。新增 `_extract_query()` 函数正确提取用户输入
- 修复图片发送方式：使用 `Comp.Image.fromBytes()` 配合 `event.chain_result()` 发送图片，替代不存在的 `event.image_result(bytes_data=...)` 参数

### Features

- `/tbzbuild` 阵容查询结果改为合并转发消息发送，将多条阵容信息（含截图）打包为一条转发记录，避免刷屏；不支持合并转发的平台自动回退为逐条发送
- 附魔信息不再截断，完整显示所有附魔效果

### Improvements

- 使用持久化 `aiohttp.ClientSession`，在插件初始化时创建、卸载时关闭，main.py 与 card_renderer.py 共享同一 Session，大幅减少网络连接开销
- HTML 文本清理改用正则表达式 `re.sub(r'<[^>]+>', '', text)`，替代脆弱的链式 `.replace()` 调用
- 提取通用搜索校验函数 `_resolve_search()`，消除怪物/物品/技能指令中的重复逻辑
- `_wrap_text()` 文本换行优化：中文逐字换行，英文按词换行，避免截断英文单词
- 图片卡片渲染器（card_renderer.py）中所有魔法数字提取为模块级常量，提升可维护性

## v1.0.0

- 初始版本发布
- 支持怪物、物品、技能数据查询，以图片卡片形式展示
- 支持中英文双语查询
- 社区推荐阵容查询（数据来源: bazaar-builds.net）
- 按标签、品质、英雄筛选物品和技能
