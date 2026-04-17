#!/usr/bin/env python3
"""Patch langchain_chain.py to inject waste_signals into the combined prompt."""
import sys, os

path = '/home/finops/finops-ai-system/src/llm/langchain_chain.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Find the generate section via a reliable anchor
ANCHOR = 'GENERATE RECOMMENDATIONS'
idx = content.find(ANCHOR)
if idx == -1:
    print("ERROR: anchor not found")
    sys.exit(1)

# Walk back to find the \u2501\u2501\u2501 that precedes it
start = content.rfind('\\u2501\\u2501\\u2501', 0, idx)
if start == -1:
    print("ERROR: section header not found before anchor")
    sys.exit(1)

# Find the closing triple-quote after the block
end = content.find('"""', idx)
if end == -1:
    print("ERROR: closing triple-quote not found")
    sys.exit(1)
end += 3  # include the """

old_block = content[start:end]

new_block = (
    '\\u2501\\u2501\\u2501 SECTION 6: PRE-COMPUTED WASTE SIGNALS (mandatory action hints) \\u2501\\u2501\\u2501\n'
    '{context_parts.get("waste_signals", "(no pre-computed signals)")}\n\n'
    '\\u2501\\u2501\\u2501 GENERATE RECOMMENDATIONS \\u2501\\u2501\\u2501\n'
    'For EVERY resource in Section 1:\n'
    '  1. If Section 6 has a waste signal for this resource, USE its ACTION and savings directly.\n'
    '  2. Otherwise find the best KB strategy from Sections 3-4.\n'
    '  3. Look up the exact monthly cost from Section 2.\n'
    '  4. Write a DETAILED finding: type, config, strategy, cost, savings math ($X x Y% = $Z/mo).\n'
    '  5. Write why_it_matters: annual savings (x12), affected services, risk level.\n'
    '  6. Provide a real AWS CLI remediation command.\n\n'
    'STRICT RULES:\n'
    '- /aws/* log groups: ALWAYS SET_LOG_RETENTION (50% savings). NEVER REVIEW_ARCHITECTURE.\n'
    '- ECR/registry: ALWAYS ADD_LIFECYCLE (40% savings). NEVER REVIEW_ARCHITECTURE.\n'
    '- ECS/fargate/container: ALWAYS MOVE_TO_GRAVITON (20% savings). NEVER REVIEW_ARCHITECTURE.\n'
    '- Any Section 6 signal resource: use its ACTION. NEVER REVIEW_ARCHITECTURE.\n'
    '- REVIEW_ARCHITECTURE ONLY if truly no other action is possible.\n\n'
    'Sort by estimated_savings_monthly descending.\n'
    'Return ONLY a valid JSON array - no markdown, no wrapping.\n'
    '"""'
)

content = content[:start] + new_block + content[end:]
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
print(f"SUCCESS: replaced {len(old_block)} chars with {len(new_block)} chars")
print(f"Old block preview: {repr(old_block[:80])}")
