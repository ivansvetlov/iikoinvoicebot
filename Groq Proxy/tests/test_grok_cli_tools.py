import subprocess
import shutil
import tempfile
import os
from prompt_pipeline import prepare_kilo_prompt

grok = shutil.which("grok") or "grok"
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read",
            "parameters": {
                "type": "object",
                "properties": {"target_file": {"type": "string"}},
                "required": ["target_file"],
            },
        },
    }
]
msgs = [{"role": "user", "content": "Use read_file on openai_proxy.py"}]
p = prepare_kilo_prompt(msgs, tools)

with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
    f.write(p)
    path = f.name

try:
    for label, extra in [
        ("plain", []),
        ("max1", ["--max-turns", "1"]),
    ]:
        cmd = [grok, "--prompt-file", path, "--output-format", "plain"] + extra
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=90
        )
        print(label, "rc", proc.returncode, "len", len(proc.stdout or ""))
        print("out", repr((proc.stdout or "")[:400]))
        print("err", repr((proc.stderr or "")[:200]))
        print()
finally:
    os.unlink(path)
