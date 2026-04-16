import re

def parse_time(s):
    h,m,rest = s.split(':')
    s2,ms = rest.split(',')
    return int(h)*3600+int(m)*60+int(s2)+int(ms)/1000

blocks=[]
with open('en.srt','r',encoding='utf-8',errors='ignore') as f:
    data=f.read()
for m in re.finditer(r"(?ms)^\s*(\d+)\s*\n(\d\d:\d\d:\d\d,\d\d\d)\s*-->\s*(\d\d:\d\d:\d\d,\d\d\d)\s*\n(.*?)(?=\n\s*\n|\Z)", data):
    idx=int(m.group(1))
    st=m.group(2); et=m.group(3)
    txt=m.group(4).strip()
    blocks.append((idx, st, et, txt))

sel=[b for b in blocks if parse_time(b[1]) < 60.0]
print(len(sel))
for idx,st,et,txt in sel:
    print('---BLOCK---')
    print(idx)
    print(st,'-->',et)
    print(txt.replace('\r',''))
