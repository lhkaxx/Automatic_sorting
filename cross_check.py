import re
import pandas as pd

# 1. Read txt with auto-encoding detection
txt_content = None
for enc in ['gbk', 'gb18030', 'utf-8-sig', 'utf-16', 'utf-8']:
    try:
        with open(r'C:/Users/li/Desktop/254~255(1).txt', 'r', encoding=enc) as f:
            txt_content = f.read()
        print(f"使用编码: {enc}")
        break
    except:
        continue

if txt_content is None:
    with open(r'C:/Users/li/Desktop/254~255(1).txt', 'r', encoding='utf-8', errors='ignore') as f:
        txt_content = f.read()
    print("使用编码: utf-8 (errors ignored)")

# 2. Extract names from lines containing 智能254
txt_names = set()
for line in txt_content.split('\n'):
    if '智能254' not in line:
        continue
    line = line.strip()
    
    # Find position after 智能254
    m = re.search(r'智能254', line, re.IGNORECASE)
    if not m:
        continue
    rest = line[m.end():]
    
    # Strip leading separators: -, +, space, 班-
    rest = re.sub(r'^[-+\s班]+', '', rest)
    
    # Extract Chinese name (2-4 chars)
    nm = re.match(r'([\u4e00-\u9fff]{2,4})', rest)
    if nm:
        name = nm.group(1)
        # Filter out non-names
        if name not in ('实验', '花名', '班级', '姓名', '学号', '报告', '文档'):
            txt_names.add(name)

print(f"\n=== TXT中提取到 智能254 的名字: {len(txt_names)} 个 ===")
for n in sorted(txt_names):
    print(f"  {n}")

# 3. Read Excel
df = pd.read_excel(r'C:/Users/li/Desktop/z智能254花名册.xlsx')
print(f"\n=== Excel 列名: {list(df.columns)} ===")
print(f"=== Excel 行数: {len(df)} ===")

# Find name column
name_col = None
for col in df.columns:
    if '姓名' in str(col) or '名字' in str(col):
        name_col = col
        break
if name_col is None:
    name_col = df.columns[0]

print(f"使用列: '{name_col}'")
excel_names = set(df[name_col].dropna().astype(str).str.strip())
excel_names = {n for n in excel_names if n and n != 'nan'}

print(f"\n=== Excel 中的名字: {len(excel_names)} 个 ===")
for n in sorted(excel_names):
    print(f"  {n}")

# 4. Cross-compare
missing = excel_names - txt_names
print(f"\n{'='*60}")
print(f"=== 在花名册中但 NOT 在TXT中的名字: {len(missing)} 个 ===")
print(f"{'='*60}")
for n in sorted(missing):
    print(f"  ✗ {n}")

extra = txt_names - excel_names
if extra:
    print(f"\n=== 在TXT中但不在花名册中的名字: {len(extra)} 个 ===")
    for n in sorted(extra):
        print(f"  + {n}")
