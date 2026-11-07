import json
from collections import Counter
from itertools import combinations

DATA_FILE = "data/python_vacancies.jsonl"


def read_vacancies(path=DATA_FILE):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def process(vacancy, skill_counter, pair_counter, triple_counter):
    skills = list(set(s.strip().lower() for s in vacancy.get("key_skills", []) if s.strip()))
    skills.sort()
    for skill in skills:
        skill_counter[skill] += 1
    for pair in combinations(skills, 2):
        pair_counter[pair] += 1
    if len(skills) >= 3:
        for triple in combinations(skills, 3):
            triple_counter[triple] += 1


def control_line(n, skill_counter, pair_counter, triple_counter):
    top_pair, top_cnt = pair_counter.most_common(1)[0]
    return (f"КОНТРОЛЬ: вакансий={n} навыков={len(skill_counter)} пар={len(pair_counter)} "
            f"троек={len(triple_counter)} сумма_пар={sum(pair_counter.values())} "
            f"топ_пара={'+'.join(top_pair)}:{top_cnt}")


def top(counter, k=10):
    return [{"skills": list(key) if isinstance(key, tuple) else key, "count": v}
            for key, v in counter.most_common(k)]
