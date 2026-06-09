import re
import pandas as pd
from collections import defaultdict

# 1. Read Excel roster
df = pd.read_excel(r'C:/Users/li/Desktop/z智能254花名册.xlsx')
name_col = None
for col in df.columns:
    if '姓名' in str(col):
        name_col = col
        break
if name_col is None:
    name_col = df.columns[0]
roster = set(df[name_col].dropna().astype(str).str.strip())
roster = {n for n in roster if n and n != 'nan'}
print(f"花名册: {len(roster)} 人")

# 2. Parse classified file - extract names per experiment
exp_files = defaultdict(set)
current_exp = None

with open(r'C:/Users/li/Desktop/z智能254_按实验分类_v2.txt', 'r', encoding='utf-8-sig') as f:
    for line in f:
        line = line.rstrip('\n\r')
        
        # Match section header: 【实验N】 ...
        m = re.match(r'【实验(\d+)[^】]*】', line.strip())
        if m:
            current_exp = f"实验{m.group(1)}"
            continue
        
        # Skip non-file lines
        if not current_exp:
            continue
        if not line.strip():
            continue
        if line.strip().startswith('=') or line.strip().startswith('-'):
            continue
        if line.strip().startswith('z智能254 文件'):
            continue
        
        # This should be a filename line (indented with 2 spaces)
        fname = line.strip()
        if '智能254' not in fname:
            continue
        
        # Extract name from filename
        idx = fname.find('智能254')
        rest = fname[idx+5:]  # after 智能254 (5 chars)
        rest = re.sub(r'^[-+\s班]+', '', rest)
        nm = re.match(r'([\u4e00-\u9fff]{2,4})', rest)
        if nm:
            name = nm.group(1)
            if name not in ('实验', '花名', '班级', '姓名', '学号', '报告', '文档'):
                exp_files[current_exp].add(name)

print(f"识别到 {len(exp_files)} 个实验")

# 3. Print detailed missing report
def exp_sort_key(exp_name):
    m = re.search(r'\d+', exp_name)
    return int(m.group()) if m else 999

total_never = roster.copy()

print(f"\n{'='*70}")
print(f"  📋 各实验缺交名单（全班 {len(roster)} 人）")
print(f"{'='*70}")

for exp_name in sorted(exp_files.keys(), key=exp_sort_key):
    submitted = exp_files[exp_name]
    total_never -= submitted
    missing = roster - submitted
    
    print(f"\n{'─'*60}")
    print(f"【{exp_name}】已交: {len(submitted)}/{len(roster)} 人")
    if missing:
        print(f"  ❌ 缺交 {len(missing)} 人:")
        for n in sorted(missing):
            print(f"     - {n}")
    else:
        print(f"  ✅ 全部交齐！")

# 4. Never submitted
print(f"\n{'='*70}")
if total_never:
    print(f"⚠️  从未交过任何实验: {len(total_never)} 人")
    for n in sorted(total_never):
        print(f"   - {n}")
else:
    print(f"✅ 所有人都至少交过一次实验")

# 5. Summary table
print(f"\n{'='*70}")
print(f"  📊 汇总表")
print(f"{'='*70}")
print(f"{'实验':<8} {'已交':<6} {'缺交':<6} {'提交率':<8}")
print(f"{'-'*30}")
for exp_name in sorted(exp_files.keys(), key=exp_sort_key):
    submitted = len(exp_files[exp_name])
    missing = len(roster - exp_files[exp_name])
    rate = submitted / len(roster) * 100
    print(f"{exp_name:<8} {submitted:<6} {missing:<6} {rate:.0f}%")

# 6. Save to file
output_path = r'C:/Users/li/Desktop/z智能254_缺交名单.txt'
with open(output_path, 'w', encoding='utf-8-sig') as out:
    out.write(f"z智能254 各实验缺交名单\n")
    out.write(f"全班 {len(roster)} 人\n")
    out.write("=" * 60 + "\n\n")
    
    for exp_name in sorted(exp_files.keys(), key=exp_sort_key):
        submitted = exp_files[exp_name]
        missing = roster - submitted
        out.write(f"【{exp_name}】已交 {len(submitted)}/{len(roster)}\n")
        out.write("-" * 40 + "\n")
        if missing:
            for n in sorted(missing):
                out.write(f"  ✗ {n}\n")
        else:
            out.write(f"  ✅ 全部交齐\n")
        out.write("\n")
    
    out.write("=" * 60 + "\n")
    if total_never:
        out.write(f"⚠ 从未交过任何实验: {len(total_never)} 人\n")
        for n in sorted(total_never):
            out.write(f"  - {n}\n")

print(f"\n已保存到: {output_path}")
