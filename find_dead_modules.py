# save as find_dead_modules.py at repo root
import os
from modulefinder import ModuleFinder

# 1. load your list of files
with open('all_py.txt') as f:
    scripts = [line.strip() for line in f if line.strip().endswith('.py')]

finder = ModuleFinder()

# 2. treat each script with a shebang or a known entry‑point as a root
#    (adjust this list to your real entry scripts)
entry_points = [s for s in scripts if os.path.basename(s) in ('main.py','cli.py')]
for ep in entry_points:
    finder.run_script(ep)

# 3. modules seen by ModuleFinder
used_modules = set(m.__file__ for m in finder.modules.values() if m.__file__ and m.__file__.startswith(os.getcwd()))

# 4. everything else is “dead”
all_paths = {os.path.abspath(s) for s in scripts}
dead = sorted(all_paths - used_modules)

print("Potentially unused modules:")
for p in dead:
    print(" ", os.path.relpath(p))