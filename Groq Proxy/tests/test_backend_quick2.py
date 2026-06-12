from backend import invoke_grok_cli_llm, invoke_grok_llm

prompt = (
    "USER: работаешь?\n\n"
    'Reply ONLY JSON: {"content": "да, работаю", "tool_calls": []}'
)
r = invoke_grok_cli_llm(prompt, timeout=60)
print("grok-cli rc", r.returncode, "elapsed", r.elapsed_s)
print("stdout:", repr(r.stdout[:500]))
print("stderr:", repr(r.stderr[:200]))

r2 = invoke_grok_llm(prompt, timeout=60)
print("invoke_grok_llm backend:", r2.backend)
print("stdout:", repr(r2.stdout[:500]))
