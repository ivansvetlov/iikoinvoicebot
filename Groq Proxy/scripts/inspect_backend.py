#!/usr/bin/env python3
"""Inspect the grok / acpx CLI for help, options, and tool support."""
import subprocess
import sys
import os
import shutil

def main():
    print("Python:", sys.version)
    print("CWD:", os.getcwd())
    print("acpx in PATH?", shutil.which("acpx") or shutil.which("acpx.cmd"))
    print("grok in PATH?", shutil.which("grok"))

    results = []

    def log_and_run(args, timeout=8):
        cmd_str = ' '.join(args)
        print(f"\n=== Running: {cmd_str} ===")
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
            out = proc.stdout or "<empty>"
            err = proc.stderr or ""
            block = f"\n=== CMD: {cmd_str} ===\nRC={proc.returncode}\nSTDOUT:\n{out}\n"
            if err:
                block += f"STDERR:\n{err}\n"
            print(block)
            results.append(block)
            return proc
        except FileNotFoundError as e:
            msg = f"FileNotFound: {e}"
            print(msg)
            results.append(msg)
        except subprocess.TimeoutExpired:
            msg = "TIMEOUT"
            print(msg)
            results.append(msg)
        except Exception as e:
            msg = f"Error: {e}"
            print(msg)
            results.append(msg)
        return None

    # Capture all
    log_and_run([r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd", "--help"])
    log_and_run([r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd", "exec", "--help"])
    log_and_run([r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd", "exec", "grok", "--help"])

    log_and_run(["grok", "--help"])
    log_and_run(["grok", "agent", "--help"])
    log_and_run(["grok", "agent", "stdio", "--help"])

    print("\n=== Attempting a tiny exec grok 'hi' (may fail if no auth) ===")
    log_and_run([r"C:\Users\MiBookPro\AppData\Roaming\npm\acpx.cmd", "exec", "grok", "Reply with exactly: PONG"], timeout=15)

    # Write full results to file for retrieval
    with open("cli_inspect.log", "w", encoding="utf-8") as f:
        f.write("".join(results))
    print("\n\nFull output also written to cli_inspect.log")

if __name__ == "__main__":
    main()