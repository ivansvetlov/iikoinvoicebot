#!/usr/bin/env python3
import subprocess
import time
import os
import sys
import socket
import urllib.request
import json
from datetime import datetime

LOG_FILE = "grok_diagnose.log"

def log(msg):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def check_port(port=8080):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(('127.0.0.1', port))
        sock.close()
        return result == 0
    except:
        return False

def test_curl():
    try:
        req = urllib.request.Request("http://localhost:8080/v1/models")
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode('utf-8')
            log(f"/v1/models OK: {data[:100]}")
            return True
    except Exception as e:
        log(f"/v1/models FAIL: {e}")
        return False

def test_acpx():
    result = subprocess.run(
        ["acpx", "exec", "grok", "hi"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        log(f"acpx OK: {result.stdout[:100]}")
        return True
    else:
        log(f"acpx FAIL: {result.stderr[:100]}")
        return False

def main():
    log("=== DIAGNOSTIC START ===")
    log(f"CWD: {os.getcwd()}")
    
    port_ok = check_port(8080)
    log(f"Port 8080: {'OPEN' if port_ok else 'CLOSED'}")
    
    if port_ok:
        test_curl()
    
    test_acpx()
    
    log("=== DIAGNOSTIC END ===")
    print(f"\nLog saved to: {LOG_FILE}")

if __name__ == "__main__":
    main()
