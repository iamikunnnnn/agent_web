import os

# Find agent.py file
agent_py_path = ".venv/Lib/site-packages/agno/agent/agent.py"
if os.path.exists(agent_py_path):
    with open(agent_py_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    # Find lines containing 'reasoning'
    for i, line in enumerate(lines):
        if 'reasoning' in line.lower():
            print(f"{i+1}: {line.rstrip()}")
else:
    print("File not found")