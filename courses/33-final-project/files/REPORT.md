# Project report — (fill in: your title, as in project.json)

Write this report for an IRIS reviewer who has never seen your branch: what was wrong, what you changed, how you
proved it, what the numbers say and what they do NOT say. Replace every "(fill in …)" paragraph and every "…" cell.
The numbers come from `python3 project.py evaluate` (copy them, correctly rounded). The check reads the sections by
their titles: keep the "## …" lines as they are.

## 1. The problem

(fill in: what goes wrong in NAVERA Lite, in which situation, how you saw it — a run, a number, a lesson; and the
NAVERA problem it is related to, in words, if there is one)

## 2. Pre-registration

(fill in: your hypothesis in one sentence, then the rule of project.json in words — the metric and its window, which
direction is better, the minimum effect, the guard-rail and its limit — and the date of the commit tagged before)

## 3. The change

(fill in: what you changed, in which file(s) and function(s), why this design and not another; the commit id)

## 4. The red test

(fill in: the test file, what each test asks, how it failed at 'before' — the message — and that it passes now)

## 5. The campaign

(fill in: the scenarios, the seeds — first and last of the block —, the number of paired runs, what is simulated)

## 6. Results

| | before | after | D = after − before | 95 % interval of D |
|---|---|---|---|---|
| metric: … | … | … | … | … |
| guard-rail: … | … | … | … | … |

(fill in: where each interval lies — does it contain 0, does it pass the minimum effect, the guard-rail's limit?)

## 7. Decision

(fill in: start with the decision of your rule — accept, reject or inconclusive — then why, in one or two sentences)

## 8. Limits

(fill in: what this campaign does not show — a simulation, which models, which conditions were never flown, what a
field test would need — and what you would measure next)
