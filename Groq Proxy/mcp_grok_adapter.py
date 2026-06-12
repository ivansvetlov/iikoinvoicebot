#!/usr/bin/env python3
import subprocess
import sys
import json
import re
import platform

if platform.system() == "Windows":
    import ctypes
    ctypes.windll.user32.ShowWindow(ctypes.windll.kernel32.GetConsoleWindow(), 0)

def _get_acpx_path():
    import shutil, os
    candidates = [
        r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd",
        "acpx.cmd",
        "acpx",
    ]
    for c in candidates:
        if os.path.exists(c) or shutil.which(c):
            return shutil.which(c) or c
    return "acpx.cmd"

ACPX_PATH = _get_acpx_path()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            method = req.get('method')
            req_id = req.get('id')
            
            if method == 'initialize':
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {"prompts": {"listChanged": False}},
                        "serverInfo": {"name": "grok-mcp-server", "version": "1.0.0"}
                    }
                }
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
                
            elif method == 'notifications/initialized':
                pass
                
            elif method == 'prompts/list':
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {"prompts": []}
                }
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
                
            elif method == 'prompts/get':
                params = req.get('params', {})
                prompt = params.get('prompt', '')
                system_prompt = params.get('system')  # NEW: grok SYSTEM support via ACP flag
                
                startupinfo = None
                creationflags = 0
                if platform.system() == "Windows":
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    creationflags = subprocess.CREATE_NO_WINDOW
                
                # Правильное размещение флагов: --append-system-prompt глобально (перед exec)
                cmd = [ACPX_PATH]
                if system_prompt:
                    cmd.extend(['--append-system-prompt', system_prompt])
                cmd.extend(['exec', 'grok'])
                if prompt:
                    cmd.append(prompt)
                else:
                    cmd.append("(System instructions above. Respond to any prior context or wait for the next user turn.)")
                
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding='utf-8',
                    startupinfo=startupinfo,
                    creationflags=creationflags
                )
                
                stdout, stderr = proc.communicate()
                
                # Используем улучшенную очистку (полный текст вместо lines[-1])
                output = stdout or ""
                # Простая версия очистки (чтобы не дублировать сложную функцию)
                output = re.sub(r'Error handling notification \{[\s\S]*?\}\s*\{[\s\S]*?\}', '', output)
                output = re.sub(r'\[client\][\s\S]*?(?=\n\[|\Z)', '', output, flags=re.DOTALL)
                output = re.sub(r'\[thinking\][\s\S]*?(?=\n\n|\[client\]|\Z)', '', output, flags=re.DOTALL)
                output = re.sub(r'\[done\].*', '', output)
                output = re.sub(r'\bend_turn\b', '', output)
                lines = [l.strip() for l in output.splitlines() if l.strip()]
                output = "\n".join(lines).strip()   # ВЕСЬ текст, не только [-1]
                
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "messages": [{
                            "role": "assistant",
                            "content": {"type": "text", "text": output}
                        }]
                    }
                }
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
                
            else:
                response = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"}
                }
                print(json.dumps(response, ensure_ascii=False))
                sys.stdout.flush()
                
        except Exception as e:
            error_response = {
                "jsonrpc": "2.0",
                "id": req.get('id') if 'req' in locals() else None,
                "error": {"code": -32000, "message": str(e)}
            }
            print(json.dumps(error_response, ensure_ascii=False))
            sys.stdout.flush()

if __name__ == "__main__":
    main()