# 一图流攻略目录

本目录用于存放各英雄的一图流攻略图片。

## 目录结构

```
guides/
├── Dooley/       # 杜利/鸡煲
├── Jules/        # 朱尔斯/厨子
├── Mak/          # 马克
├── Pygmalien/    # 皮格马利翁/猪猪
├── Stelle/       # 斯黛拉/黑妹
└── Vanessa/      # 瓦妮莎/海盗
```

## 使用方法

1. 将收集的一图流攻略图片放入对应英雄的目录
2. 支持的图片格式：`.png`, `.jpg`, `.jpeg`, `.webp`, `.gif`
3. 图片会按文件名排序显示
4. 建议文件名使用序号前缀，如 `01_开局.png`, `02_中期.png`

## 命令

```
/tbzguide <英雄名>
```

示例：
- `/tbzguide 海盗`
- `/tbzguide Vanessa`
- `/tbzguide 杜利`

## 远程数据源

也可以配置从 GitHub 仓库远程获取攻略图片：

在 AstrBot 管理面板配置 `guide_remote_repo`，格式为：
```
用户名/仓库名/分支/目录路径
```

例如：`shitlsh/astrbot_plugin_bazaar/main/data/guides`
