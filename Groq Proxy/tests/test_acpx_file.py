import subprocess
import sys
import tempfile
import os

acpx = r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd"
full = (
    "SYSTEM: You are a coding agent. Use tools when needed.\n\n"
    "AVAILABLE TOOLS:\n- read_file: Read file\n\n"
    "INSTRUCTIONS: respond with tool call NAME with\n\n"
    "USER: Read README.md using read_file tool."
)

with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
    f.write(full)
    path = f.name

try:
    cmd = [acpx, "exec", "grok", "-f", path]
    kwargs = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    p = subprocess.run(cmd, **kwargs)
    print("rc=", p.returncode)
    print("stderr:", (p.stderr or "")[:120])
    print("stdout tail:", (p.stdout or "")[-300:])
finally:
    os.unlink(path)
