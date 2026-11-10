import sys, json
sys.path.insert(0,'/REPOS_ROOT/kb-health/outcome_bench')
sys.path.insert(0,'/REPOS_ROOT/kb-health/probe_screen')
from conventions import TASKS
from run_bench import prompt_for
from run_probes import load_env, chat, usage_cost
env=load_env()
t=TASKS[0]
msgs=prompt_for(t,'c0',0)
print('prompt chars', len(msgs[0]['content']))
try:
    resp=chat(env,msgs,'deepseek-chat',0.0,1)
    u=resp.get('usage') or {}
    print('usage:',json.dumps(u))
    print('cost',usage_cost(u))
except Exception as e:
    print('ERR',repr(e))
