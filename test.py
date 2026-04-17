import sys
import os
import json
import logging

logging.basicConfig(level=logging.INFO)

sys.path.insert(0, '/app')

from src.llm.client import call_llm, _assemble_finops_context
from src.llm.prompts import FINOPS_COST_SYSTEM_PROMPT, FINOPS_COST_USER_PROMPT

try:
    with open('/app/data/synthetic/ecommerce_medium.json', 'r') as f:
        graph_data = json.load(f)

    ctx = _assemble_finops_context({}, graph_data, {}, {}, graph_data.get('services', []), graph_data.get('edges', []))
    print("Context generated.")
    user = FINOPS_COST_USER_PROMPT.format(**ctx)
    resp = call_llm(system_prompt=FINOPS_COST_SYSTEM_PROMPT, user_prompt=user, max_tokens=3000)
    print("LLM RESPONSE:")
    print(resp)
except Exception as e:
    import traceback
    traceback.print_exc()
