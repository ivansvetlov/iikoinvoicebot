import subprocess
import shutil
import tempfile
import os

grok = shutil.which("grok") or "grok"
prompt = (
    'USER: работаешь?\n\n'
    'Reply ONLY JSON: {"content":"да, работаю.","tool_calls":[]}'
)

with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
    f.write(prompt)
    path = f.name

try:
    for label, extra in [
        ("max1", ["--max-turns", "1"]),
        ("tools_empty", ["--max-turns", "1", "--tools", ""]),
    ]:
        cmd = [grok, "--prompt-file", path, "--output-format", "plain"] + extra
        p = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60
        )
        out = p.stdout or ""
        print(label, "rc", p.returncode, "len", len(out))
        print("has_tool_noise", any(x in out for x in ("list_dir", "[tool]", "ListDir")))
        print("out", repr(out[:250]))
        print()
finally:
    os.unlink(path)
