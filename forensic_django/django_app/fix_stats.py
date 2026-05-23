lines = open("cases/views.py", encoding="utf-8").readlines()

for i, line in enumerate(lines):
    if "from reconstruction.models import SceneReconstruction" in line:
        lines[i] = ""
        print(f"Removed bad import at line {i+1}")

for i, line in enumerate(lines):
    if "reconstructions" in line and "SceneReconstruction" in line:
        lines[i] = '            "reconstructions":  0,\n'
        print(f"Fixed reconstructions count at line {i+1}")

open("cases/views.py", "w", encoding="utf-8").writelines(lines)
print("Done")