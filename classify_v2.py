import re
from collections import Counter

# 1. Read file
txt_content = None
for enc in ['gbk', 'gb18030', 'utf-8-sig', 'utf-8']:
    try:
        with open(r'C:/Users/li/Desktop/254~255(1).txt', 'r', encoding=enc) as f:
            txt_content = f.read()
        break
    except:
        continue

lines = txt_content.split('\n')

# 2. Parse tree:
#   Lines starting with ├─ or └─ → directory (the entry itself IS the dir)
#   Lines starting with │ → file
#   Depth = column where text starts: ~3=root, ~7=subdir1, ~11=subdir2

def parse_line(line):
    """Return (depth, content, is_dir) or None"""
    s = line.rstrip('\n\r')
    if not s:
        return None
    
    # Determine if dir or file by the tree character
    # After the leading tree-drawing chars, we get the content
    tree_chars = set('│ ├└─')
    i = 0
    while i < len(s) and s[i] in tree_chars:
        i += 1
    
    if i == 0:
        return None
    
    content = s[i:].strip()
    if not content:
        return None
    
    # Is it a directory? The original line starts with ├─ or └─
    is_dir = s.lstrip()[0] in ('├', '└')
    
    # Depth from indent level
    if i <= 3:
        depth = 0
    elif i <= 7:
        depth = 1
    elif i <= 11:
        depth = 2
    elif i <= 15:
        depth = 3
    else:
        depth = 4
    
    return (depth, content, is_dir)

entries = []
for line in lines:
    r = parse_line(line)
    if r:
        entries.append(r)

print(f"解析条目: {len(entries)} 个")

# 3. Build directory stack and assign files to directories
dir_stack = []  # [(depth, dir_name)]
file_to_dir = []  # [(filename, dir_path)]

for depth, content, is_dir in entries:
    if is_dir:
        # Pop deeper directories
        while dir_stack and dir_stack[-1][0] >= depth:
            dir_stack.pop()
        dir_stack.append((depth, content))
    else:
        # File — find parent (dir at depth-1 or less)
        parent_depth = depth - 1
        while dir_stack and dir_stack[-1][0] > parent_depth:
            dir_stack.pop()
        parent_path = '/'.join(d[1] for d in dir_stack)
        file_to_dir.append((content, parent_path))

print(f"文件条目: {len(file_to_dir)}")

# 4. Filter z智能254
def extract_experiment(filename):
    m = re.search(r'实验\s*(\d+|[一二三四五六七八九十]+)', filename)
    if m:
        num = m.group(1)
        cn_map = {'一':'1','二':'2','三':'3','四':'4','五':'5','六':'6','七':'7','八':'8','九':'9','十':'10'}
        return (int(cn_map.get(num, num)), True)
    return (None, False)

dir_exps = {}
dir_unknown = {}
z254_files = []

for fname, dir_path in file_to_dir:
    if '智能254' not in fname:
        continue
    z254_files.append((fname, dir_path))
    exp_num, known = extract_experiment(fname)
    if known:
        dir_exps.setdefault(dir_path, []).append(exp_num)
    else:
        dir_unknown.setdefault(dir_path, []).append(fname)

# Determine experiment for each directory
dir_to_exp = {}
for d, exps in dir_exps.items():
    c = Counter(exps)
    dir_to_exp[d] = c.most_common(1)[0][0]

print(f"\n目录 → 实验 映射 ({len(dir_to_exp)} 个目录):")
for d in sorted(dir_to_exp.keys(), key=lambda x: (len(dir_exps.get(x,[])), x), reverse=True):
    e = dir_to_exp[d]
    kn = len(dir_exps.get(d, []))
    un = len(dir_unknown.get(d, []))
    label = d if d else '(根目录)'
    print(f"  [{label}] → 实验{e} (已知{kn}个, 未知{un}个)")

# 5. Assign unknowns
inferred = 0
still_unknown = []
for d, files in dir_unknown.items():
    if d in dir_to_exp:
        inferred += len(files)
    else:
        still_unknown.extend(files)

print(f"\n推断成功: {inferred} 个, 仍未知: {len(still_unknown)}")

# 6. Build final groups
all_groups = {}
for fname, dir_path in z254_files:
    exp_num, known = extract_experiment(fname)
    if known:
        key = f"实验{exp_num}"
    elif dir_path in dir_to_exp:
        key = f"实验{dir_to_exp[dir_path]} (推断)"
    else:
        key = "无实验标记"
    all_groups.setdefault(key, []).append(fname)

def sort_key(k):
    m = re.search(r'\d+', k)
    return int(m.group()) if m else 999

# 7. Save
output_path = r'C:/Users/li/Desktop/z智能254_按实验分类_v2.txt'
with open(output_path, 'w', encoding='utf-8-sig') as out:
    out.write(f"z智能254 文件按实验分类汇总 (含目录上下文推断)\n")
    out.write(f"总计: {len(z254_files)} 个文件\n")
    out.write("=" * 80 + "\n\n")
    
    for key in sorted(all_groups.keys(), key=sort_key):
        items = sorted(all_groups[key])
        out.write(f"【{key}】 ({len(items)} 个)\n")
        out.write("-" * 60 + "\n")
        for f in items:
            out.write(f"  {f}\n")
        out.write("\n")

print(f"\n已保存到: {output_path}")
print(f"\n=== 最终分类 ===")
for key in sorted(all_groups.keys(), key=sort_key):
    print(f"  {key}: {len(all_groups[key])} 个")
