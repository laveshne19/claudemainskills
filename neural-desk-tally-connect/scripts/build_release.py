"""Build the desktop test package:  python scripts/build_release.py  ->  dist/TallyConnect-Desktop-<version>.zip"""
import re, shutil, subprocess, sys, tempfile, zipfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = re.search(r'version = "([^"]+)"', (root / "pyproject.toml").read_text()).group(1)
dist = root / "dist"
dist.mkdir(exist_ok=True)
stage = Path(tempfile.mkdtemp()) / f"TallyConnect-Desktop-{version}"
stage.mkdir(parents=True)

# 1. wheel
wh = Path(tempfile.mkdtemp())
subprocess.run([sys.executable, "-m", "pip", "wheel", str(root), "--no-deps", "-w", str(wh), "-q"], check=True)
(stage / "wheel").mkdir()
for w in wh.glob("*.whl"):
    shutil.copy(w, stage / "wheel" / w.name)

# 2. launchers and instructions at the top level
for f in (root / "desktop").iterdir():
    shutil.copy(f, stage / f.name)
(stage / "installer").mkdir()
shutil.copy(root / "installer" / "install.ps1", stage / "installer" / "install.ps1")

# 3. templates, guides (customer facing only), plugin, source fallback
shutil.copytree(root / "templates", stage / "templates")
(stage / "docs").mkdir()
for d in ("INSTALL.md", "USER-GUIDE.md", "TALLY-SETUP.md", "HOW-IT-WORKS.md", "LIVE-TEST-CHECKLIST.md"):
    shutil.copy(root / "docs" / d, stage / "docs" / d)
shutil.copy(root / "README.md", stage / "docs" / "README.md")
shutil.copytree(root / "plugin", stage / "plugin")
(stage / ".claude-plugin").mkdir()
shutil.copy(root / ".claude-plugin" / "marketplace.json", stage / ".claude-plugin" / "marketplace.json")
shutil.copytree(root / "src", stage / "src", ignore=shutil.ignore_patterns("__pycache__", "*.egg-info"))
for f in ("pyproject.toml", "LICENSE.md", "README.md"):
    shutil.copy(root / f, stage / f)

# 4. zip
out = dist / f"TallyConnect-Desktop-{version}.zip"
if out.exists():
    out.unlink()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for p in sorted(stage.rglob("*")):
        if p.is_file():
            z.write(p, p.relative_to(stage.parent))
print(out, out.stat().st_size, "bytes")
