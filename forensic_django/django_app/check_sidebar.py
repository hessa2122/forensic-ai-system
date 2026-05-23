content = open('templates/index.html', encoding='utf-8').read()
for i, line in enumerate(content.split('\n')):
    if 'forensic_best' in line or 'Grenade' in line or 'Shell' in line:
        print(f'Line {i+1}: {repr(line)}')