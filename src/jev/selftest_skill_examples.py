import json, subprocess
K = open('.key').read().strip()

def post(state, questions):
    body = json.dumps({"model": "jev", "state": state, "questions": questions}, ensure_ascii=False)
    p = subprocess.run(['curl', '-s', '-w', '|%{http_code}', '-X', 'POST',
        'https://router.bynara.id/v1/systemone',
        '-H', f'Authorization: Bearer {K}', '-H', 'Content-Type: application/json',
        '-d', body], capture_output=True, text=True)
    out, code = p.stdout.rsplit('|', 1)
    try: return code, json.loads(out)
    except Exception: return code, {'raw': out[:200]}

# 1) SKILL.md 里的入排模板（原样照抄）
st = {"age": 68, "egfr": 42, "bp": "128/78",
      "exclusion": ["eGFR<45", "未控制的高血压", "5年内恶性肿瘤史"],
      "malignancy_history": "无"}
qs = {"screen": {"type": "choice", "criteria": {
        "yes": "该患者符合排除标准，应当筛除",
        "no": "逐条核对后所有排除标准均为阴性，可以入组"}}}
c, r = post(st, qs)
a = r.get('answers', {}).get('screen', {})
print(f'[模板1 入排 choice]  HTTP {c} -> {a.get("choice")} conf={a.get("confidence")}')

# 2) 外层信封字段是否真是 {ok, model, answers, usage, request}
print('   envelope keys:', sorted(r.keys()))

# 3) SKILL.md 里的 score 模板（原样照抄）
qs2 = {"triage": {"type": "score", "criteria": [
        "这份 EDC 数据缺口应该优先补录吗？",
        "紧急-阻塞统计分析", "高-影响主要终点", "中-仅影响可读性", "低-可忽略"]}}
c2, r2 = post({"field": "AE 结束日期", "issue": "缺失",
      "has_serious_ae": True, "on_primary_endpoint": False}, qs2)
a2 = r2.get('answers', {}).get('triage', {})
print(f'[模板2 score 档位]  HTTP {c2} -> score={a2.get("score")} '
      f'legend_keys={sorted(a2.get("legend", {}).keys())} prob_keys={sorted(a2.get("probabilities", {}).keys())}')
