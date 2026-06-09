import re
import os

# 1. Read txt
txt_content = None
for enc in ['gbk', 'gb18030', 'utf-8-sig', 'utf-8']:
    try:
        with open(r'C:/Users/li/Desktop/254~255(1).txt', 'r', encoding=enc) as f:
            txt_content = f.read()
        break
    except:
        continue

if txt_content is None:
    with open(r'C:/Users/li/Desktop/254~255(1).txt', 'r', encoding='utf-8', errors='ignore') as f:
        txt_content = f.read()

# 2. Filter z智能254 lines and group by experiment number
lines_254 = []
for line in txt_content.split('\n'):
    line = line.strip()
    if not line or '智能254' not in line:
        continue
    # Skip lines that aren't actual filenames (like directory names)
    # 只保留看起来像文件名的行
    if line.endswith('.docx') or line.endswith('.doc') or line.endswith('.xls') or line.endswith('.xlsx'):
        lines_254.append(line)

print(f"总计 z智能254 文件行: {len(lines_254)}")

# 3. Group by experiment number
groups = {}
no_exp = []

for line in lines_254:
    # Extract experiment number: 实验四, 实验八, 实验九, 实验10, 实验十二 etc.
    # Also handle: 实验1, 实验一, 实验01 etc.
    m = re.search(r'实验\s*(\d+|[一二三四五六七八九十]+)', line)
    if m:
        exp_num = m.group(1)
        # Convert Chinese numerals to digits
        cn_map = {'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}
        if exp_num in cn_map:
            exp_num = cn_map[exp_num]
        key = f"实验{exp_num}"
    else:
        # Try to find just 实验 without number
        m2 = re.search(r'实验', line)
        if m2:
            key = "实验(未识别编号)"
        else:
            key = "无实验标记"
    
    groups.setdefault(key, []).append(line)

# Sort groups by experiment number
def sort_key(k):
    m = re.search(r'\d+', k)
    return int(m.group()) if m else 999

# 4. Output to file
output_path = r'C:/Users/li/Desktop/z智能254_按实验分类.txt'
with open(output_path, 'w', encoding='utf-8-sig') as out:
    out.write(f"z智能254 文件按实验分类汇总\n")
    out.write(f"总计: {len(lines_254)} 个文件\n")
    out.write(f"分组: {len(groups)} 个实验\n")
    out.write("=" * 80 + "\n\n")
    
    for key in sorted(groups.keys(), key=sort_key):
        items = groups[key]
        out.write(f"【{key}】 ({len(items)} 个文件)\n")
        out.write("-" * 60 + "\n")
        for item in sorted(items):
            out.write(f"  {item}\n")
        out.write("\n")

print(f"已保存到: {output_path}")

# Print summary
for key in sorted(groups.keys(), key=sort_key):
    print(f"  {key}: {len(groups[key])} 个")
