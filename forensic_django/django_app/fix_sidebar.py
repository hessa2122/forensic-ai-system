lines = open("templates/index.html", encoding="utf-8").readlines()

for i, line in enumerate(lines):
    if "forensic_best.pt</div>" in line and "v2" not in line:
        lines[i] = line.replace("forensic_best.pt</div>", "forensic_best_v2.pt</div>")
        print(f"Fixed model name at line {i+1}")
    if "Grenade" in line and "Gun" in line and "Knife" in line and "Pistol" in line:
        lines[i] = "      Gun &middot; Knife &middot; Grenade<br>Pistol &middot; Rifle &middot; Blood<br>Fingerprint &middot; Shell Casing\n"
        print(f"Fixed class list at line {i+1}")
    if "Classes: 6" in line:
        lines[i] = line.replace("Classes: 6", "Classes: 8")
        print(f"Fixed class count at line {i+1}")

open("templates/index.html", "w", encoding="utf-8").writelines(lines)
print("Done")