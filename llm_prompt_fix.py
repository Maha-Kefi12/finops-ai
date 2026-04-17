import re

print("Testing regex.")
match = re.search(r'\[.*\]', '```\n[{"foo": "bar"}]\n```', re.DOTALL)
if match:
    print(match.group())
