import subprocess
import shutil
import tempfile
import os

grok = shutil.which("grok") or "grok"

with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
    f.write('Say exactly: OK-BACKEND')
    path = f.name

try:
    for label, cmd in [
        ("prompt_file", [grok, "-p", "--prompt-file", path, "--max-turns", "1"]),
        ("inline", [grok, "-p", "Say exactly: OK-INLINE", "--max-turns", "1"]),
        ("disallow", [grok, "-p", "--prompt-file", path, "--max-turns", "1", "--disallowed-tools", "Read,Write,Bash"]),
    ]:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        print(label, "rc=", p.returncode, "out=", repr((p.stdout or "")[:100]), "err=", repr((p.stderr or "")[:150]))
finally:
    os.unlink(path)
