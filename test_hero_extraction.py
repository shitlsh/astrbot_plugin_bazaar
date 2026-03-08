import json

# 读取 skills_db.json
with open('data/skills_db.json', 'r', encoding='utf-8') as f:
    skills = json.load(f)

# 模拟新的提取逻辑
valid_heroes = set()
cn_map = {}
all_heroes_fields = []

for skill in skills:
    raw = str(skill.get("heroes", "") or "").strip()
    
    # 记录所有字段用于分析
    all_heroes_fields.append(raw)
    
    # 排除多英雄字段
    if "|" in raw:
        continue
    
    if not raw or raw.lower() == "common" or raw.lower().startswith("common /"):
        continue
    
    # 解析格式："EnglishName" 或 "EnglishName / 中文名"
    parts = raw.split("/", 1)
    hero_en = parts[0].strip()
    hero_cn = parts[1].strip() if len(parts) > 1 else ""
    
    # 简单检查：英文名是字母开头
    if hero_en and hero_en[0].isalpha():
        valid_heroes.add(hero_en)
        if hero_cn:
            cn_map[hero_en] = hero_cn

print(f"✅ 提取到的英雄集合 ({len(valid_heroes)}):")
for h in sorted(valid_heroes):
    cn = cn_map.get(h, "（无官方中文名）")
    print(f"  • {h} / {cn}")

print(f"\n⚠️  多英雄字段统计:")
multi_hero_count = sum(1 for f in all_heroes_fields if "|" in f)
print(f"  • 排除了 {multi_hero_count} 个多英雄字段")
print(f"  • 保留了 {len(all_heroes_fields) - multi_hero_count} 个单英雄或空字段")
