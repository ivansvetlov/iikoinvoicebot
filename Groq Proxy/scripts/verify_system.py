#!/usr/bin/env python3
"""Standalone verifier for the grok SYSTEM extraction feature.
Run with: python verify_system.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

with open(os.path.join(ROOT, "openai_proxy.py"), "r", encoding="utf-8") as f:
    proxy_src = f.read()

namespace = {}
exec(compile(proxy_src.split("class OpenAIProxyHandler")[0], "openai_proxy.py", "exec"), namespace)

extract_system_prompt = namespace.get("extract_system_prompt")
build_prompt_for_backend = namespace.get("build_prompt_for_backend")
build_full_prompt = namespace.get("build_full_prompt")

def main():
    errors = []

    # 1. Basic extraction
    messages = [
        {"role": "system", "content": "You are Grok, a precise coding agent. Always be concise."},
        {"role": "user", "content": "Create a hello world in Python."},
    ]
    tools = [{"type": "function", "function": {"name": "write_file", "description": "write", "parameters": {"type": "object"}}}]

    sys_part = extract_system_prompt(messages)
    if not (sys_part and "precise coding agent" in sys_part):
        errors.append("extract_system_prompt failed")

    conv, system_append = build_prompt_for_backend(messages, tools=tools)

    if "USER:" not in conv:
        errors.append("conv missing USER:")
    if "SYSTEM:" in conv:
        errors.append("conv should not contain SYSTEM:")
    if "Create a hello world" not in conv:
        errors.append("conv missing user request text")

    if "precise coding agent" not in system_append:
        errors.append("system_append missing original system text")
    if "AVAILABLE TOOLS" not in system_append:
        errors.append("system_append missing AVAILABLE TOOLS")
    if "write_file" not in system_append:
        errors.append("system_append missing tool name")

    # 2. Legacy full prompt still works (mixed SYSTEM inside)
    p = build_full_prompt(messages, tools=tools)
    if "SYSTEM:" not in p or "USER:" not in p:
        errors.append("build_full_prompt did not include SYSTEM + USER markers")

    # 3. Multiple system messages
    multi_sys = [
        {"role": "system", "content": "Rule one."},
        {"role": "system", "content": "Rule two."},
        {"role": "user", "content": "hi"},
    ]
    s = extract_system_prompt(multi_sys)
    if "Rule one." not in s or "Rule two." not in s:
        errors.append("multi system concat failed")

    if errors:
        print("FAIL:")
        for e in errors:
            print(" -", e)
        sys.exit(1)
    else:
        print("✓ extract_system_prompt works")
        print("✓ build_prompt_for_backend cleanly splits (conv has no SYSTEM, system_append has it + tools)")
        print("✓ build_full_prompt legacy path still produces SYSTEM: ... USER: ...")
        print("✓ multi-system messages handled")
        print("\nAll grok SYSTEM support checks PASSED.")
        sys.exit(0)

if __name__ == "__main__":
    main()
