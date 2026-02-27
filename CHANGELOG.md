# Changelog

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
