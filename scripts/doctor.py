"""Print non-sensitive setup information; never installs or changes tools."""
import platform
import shutil
import subprocess
import sys

print("DRIFT environment check (not an application test)")
print(f"Python: {platform.python_version()} ({sys.executable})")
print("Python >= 3.11:", "OK" if sys.version_info >= (3, 11) else "UPGRADE REQUIRED")
for tool in ("git", "node", "npm"):
    path = shutil.which(tool)
    if not path:
        print(f"{tool}: missing" + (" (needed later for the web UI)" if tool != "git" else ""))
        continue
    # cmd wrappers need cmd.exe on Windows. Only fixed, trusted version commands run.
    command = [path, "--version"]
    if sys.platform == "win32" and path.lower().endswith((".cmd", ".bat")):
        command = ["cmd.exe", "/d", "/c", path, "--version"]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        print(f"{tool}: {(result.stdout or result.stderr).strip()}")
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"{tool}: could not check ({type(exc).__name__})")
print("Open Bob IDE separately and verify your hackathon account, version and coin balance.")
