from collections import Counter
from skills import read_vacancies, process, control_line

vacancies = read_vacancies()
s, p, t = Counter(), Counter(), Counter()
for v in vacancies:
    process(v, s, p, t)
print("ДЗ №3")
print(f"Уникальных навыков: {len(s)}")
print(f"Уникальных пар: {len(p)}")
print(f"Уникальных троек: {len(t)}")
print(control_line(len(vacancies), s, p, t))
