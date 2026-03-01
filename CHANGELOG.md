# Changelog

## v1.1.1

### Features

- BazaarForge 阵容双数据源：新增 BazaarForge.gg（Supabase API）作为阵容查询数据源
  - 默认优先从 BazaarForge 查询（结构化数据，含胜场/胜利类型/等级/血量），不足时自动补充 bazaar-builds.net
  - 支持按物品名精确搜索（物品名→UUID→包含该物品的阵容）
  - 支持按英雄名搜索（如 `/tbzbuild 海盗`）
  - 阵容结果显示来源标识（BazaarForge / bazaar-builds.net）
  - `_conf_schema.json` 新增 `build_source_priority` 配置项（forge_first / wp_first / forge_only / wp_only）
- 新增 `/tbztier <英雄名>` 命令：查询英雄物品评级（Tier List）
  - 从 BazaarForge 获取物品使用率数据，按 S/A/B/C 分级（S≥15%, A≥8%, B≥3%, C>0%）
  - 渲染为网格式图片卡片（物品缩略图 + 品质边框 + 使用率百分比叠加，各等级横向排布）
  - 自动匹配中文物品名（与 BazaarHelper 数据关联）
  - 支持中文英雄名和别名（如「海盗」→Vanessa）
- 新增 `bazaar_query_tierlist` AI 工具：LLM 可自动查询英雄物品评级
- 新增 `/tbzmerchant <名称>` 命令：查询商人和训练师信息
  - 从 BazaarForge 获取 67 个商人/训练师数据（含出售内容、品质、可遇到英雄）
  - 渲染为图片卡片（商人头像、品质徽章、描述、可用英雄）
  - 支持按名称精确查询或按关键词模糊搜索（如 Weapon、Diamond、英雄名）
  - `/tbzupdate` 同步更新商人数据
- 新增 `bazaar_query_merchant` AI 工具：LLM 可自动查询商人/训练师信息
- API 响应缓存：新增 TTL 内存缓存层，减少重复 API 请求
  - 阵容缓存 12 小时、Tier List 缓存 12 小时、Steam 新闻 30 分钟、物品 UUID 映射 60 分钟

### Improvements

- AI 人格预设增强：新增 tierlist/merchant 工具说明和触发场景，工具绑定增至 10 个
- Tier List 卡片物品缩略图尺寸现在按物品实际大小（Small/Medium/Large）显示不同宽度
- 阵容查询结果显示数据来源和结构化信息（胜场、胜利类型、等级、血量）
- `/tbzhelp` 新增 `/tbztier` 命令说明，数据来源新增 BazaarForge
- `bazaar_query_build` 工具描述更新，说明双数据源查询

## v1.1.0

### Features

- 事件数据增强：从 `event_encounters.json` 提取英雄适用性和品质等级信息，为现有39条事件补充 `heroes` 和 `tier` 字段
  - `/tbzevent` 输出新增适用英雄和品质等级显示
  - `/tbzsearch` 支持按英雄过滤事件（如 `/tbzsearch hero:Jules` 会包含该英雄的事件）
  - `bazaar_query_event` AI 工具输出包含英雄和品质信息
- 新增 `/tbznews [数量]` 命令：从 Steam Store API 获取官方中文游戏更新公告
  - 自动渲染为长图片卡片（暗色背景、标题+日期+正文+Steam链接）
  - 多条公告使用合并转发消息发送
  - 支持 BBCode 转纯文本（标题、列表、链接等）
  - 默认显示1条，可通过参数或插件配置 `news_default_count` 调整
- 新增 `bazaar_get_news` AI 工具：LLM 可自动查询最新游戏更新公告摘要
- `/tbzupdate` 同步更新 `event_encounters.json` 数据

### Improvements

- AI 人格预设增强：新增 news 工具说明，工具绑定增至 8 个
- 搜索结果中事件显示英雄标签和品质等级
- `_conf_schema.json` 新增 `news_default_count` 配置项（默认值1，最大20）

## v1.0.6

### Features

- 新增事件数据支持：加载 `event_detail.json`（39个游戏事件），包含事件选项、描述、图标
  - `/tbzevent <名称>` — 查询事件详情（选项及描述）
  - `bazaar_query_event` — 新增 AI 工具，LLM 可自动查询事件信息
  - `/tbzsearch` 搜索结果现包含事件匹配
  - `/tbzupdate` 同步更新事件数据

### Improvements

- 模糊匹配查询建议：查询未命中时，基于编辑距离和子串匹配推荐相似名称（如输入"热情似火"提示"热情如火"）
- 阵容查询过滤优化：新增 `BUILD_POSITIVE_PATTERN` 正向匹配，双重过滤（黑名单 + 正向特征检查）更准确过滤非阵容内容
- 扩展阵容黑名单词汇：新增 new feature、announcement、preview、season、guide、tutorial、tier list、ranking 等过滤词
- 智能分词实体名保护：`_smart_tokenize` 在拆分前检查完整词是否为已知实体名（物品/怪物/技能/事件），避免"装甲核心"被错误拆分为"装甲"+"核心"
- AI 工具输出优化：工具返回文本末尾附带对应命令提示（如"使用 /tbzitem 查看图片卡片"），引导用户获取图片版结果
- AI 人格预设增强：引导 AI 在回复中告知用户可使用命令查看图片卡片；工具绑定增至 6 个
- `/tbzhelp` 新增 AI 工具使用说明，提示需要支持函数调用的 LLM 模型

## v1.0.5a

### Bugfix

- 修复人格预设注册：persona_manager 的方法可能是异步的，改用 `inspect.isawaitable()` 兼容同步/异步两种 API

## v1.0.5

### Features

- 新增「大巴扎小助手」AI 人格预设：插件启动时自动注册到 AstrBot 人格管理器
  - 预设系统提示词包含游戏背景、英雄列表、物品品质、工具使用规则等上下文
  - 预设开场对话，帮助 AI 快速进入游戏助手角色
  - 绑定 5 个游戏查询工具，确保 AI 优先调用插件工具而非凭空回答
  - 用户在 AstrBot 管理面板「人格」页面选择「bazaar_helper」即可启用

### Improvements

- 优化 AI 工具描述：增加游戏上下文关键词（The Bazaar / 大巴扎 / Roguelike 卡牌对战），帮助 AI 更准确识别游戏相关查询

## v1.0.4

### Features

- AI 工具集成：注册 5 个 `@llm_tool`，让 AI 在对话中自动调用插件功能
  - `bazaar_query_item` — 查询物品详情
  - `bazaar_query_monster` — 查询怪物详情
  - `bazaar_query_skill` — 查询技能详情
  - `bazaar_search` — 多条件搜索物品/怪物/技能
  - `bazaar_query_build` — 查询社区推荐阵容

### Improvements

- `/tbzbuild` 阵容查询自动过滤非阵容内容（Patch Notes、Hotfix、Update 等推广信息）
- `/tbzbuild` 默认返回数量改为 5 条，可通过 AstrBot 管理面板配置（`build_default_count`）
- 别名配置类型从 `dict` 改为 `text`（JSON 编辑器），兼容更多 AstrBot 版本

## v1.0.3

### Features

- 别名系统：新增 `/tbzalias` 命令管理别名（list/add/del），支持 AstrBot 管理面板配置（`_conf_schema.json`）
  - 支持 7 种分类：hero, item, monster, skill, tag, tier, size
  - 配置方式：AstrBot 管理面板（推荐）/ `/tbzalias` 命令；无 AstrBotConfig 时回退到 `data/aliases.json`
  - 配置变更自动检测重载（config 模式每次查询读取最新配置，文件模式通过 mtime 检测）
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
