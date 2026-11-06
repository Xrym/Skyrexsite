import sys, os
sys.path.insert(0, os.path.abspath('.'))

from db.database import reset_ai_rules, reset_prompt_template, get_ai_rules, get_prompt_template

count = reset_ai_rules()
print(f"Reset {count} AI rules to updated defaults.")

p_cnt = reset_prompt_template("assistant_system")
print(f"Reset assistant_system prompt template ({p_cnt} updated).")

for r in get_ai_rules():
    if r['id'] in (4, 12, 17):
        print(f"Rule #{r['id']} [{r['title']}]:\n  {r['rule_text'][:130]}...\n")

print("Assistant system prompt:\n", get_prompt_template("assistant_system"))
