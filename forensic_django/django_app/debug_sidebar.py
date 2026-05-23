lines = open('templates/index.html', encoding='utf-8').readlines()
for i, line in enumerate(lines[195:210], start=196):
    print(f'{i}: {repr(line)}')