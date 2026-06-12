import subprocess
import sys

acpx = r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd"
system_append = (
    "You are a coding agent. Use tools when needed.\n\n"
    "AVAILABLE TOOLS:\n\n"
    "- read_file: Read file\n"
    '  Parameters: {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}\n\n'
    "INSTRUCTIONS:\n"
    "When you need to use a tool, respond with:\n"
    "tool call TOOL_NAME with\n"
    "arg1 is value1\n"
)
prompt = "USER: Read README.md using read_file tool."

def run(label, hide_window=False, use_sys=True):
    cmd = [acpx]
    if use_sys:
        cmd.extend(["--append-system-prompt", system_append])
    cmd.extend(["exec", "grok", prompt])
    kwargs = dict(capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if hide_window and sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = subprocess.SW_HIDE
        kwargs["startupinfo"] = si
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    p = subprocess.run(cmd, **kwargs)
    print(f"=== {label} rc={p.returncode} stdout={len(p.stdout or '')} stderr={(p.stderr or '')[:80]!r}")

run("visible+sys", hide_window=False, use_sys=True)
run("hidden+sys", hide_window=True, use_sys=True)
run("hidden no sys", hide_window=True, use_sys=False)
