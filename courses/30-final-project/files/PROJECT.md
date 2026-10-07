# My NAVERA project: (your title here)

Name: (your name)          Branch: (e.g. project/min-satellites)          Date: (today)

Replace every text in parentheses with your own text. Keep the six `##` headings and the four
**bold** labels of the Proposal. Write the Proposal BEFORE you measure the "after" result.

## Proposal

**Problem:** (What goes wrong today, for whom — operator, autopilot, engineer — and how often?
Name the NAVERA files and functions involved.)

**Hypothesis:** (One sentence that the measurement can prove false, e.g. "Refusing fixes from
fewer than 4 satellites lowers the p95 error of accepted fixes".)

**Metric:** (The primary metric, its unit, which direction is better, the data set and the number of
samples; the guard-rail metric(s) that must not get much worse.)

**Acceptance criterion:** (Decided now, before the "after" measurement: e.g. "accept if the 95 %
CI of the difference is entirely below 0 and the CI of the availability loss stays above -10 points".)

## Change

(What exactly did you change, in which files and functions? One concern only. Your commits:
`git log --oneline base..HEAD`.)

## Test

(Which test did you add, which cases (normal, boundary, old behaviour kept), the command that runs it,
the result line ("5 passed in 0.4 s"). Did it FAIL on the code before your change? Did the package's
existing tests still pass?)

## Measurement

(Before / after with numbers and 95 % confidence intervals: a table. The command, the data, the number
of samples, the bootstrap method — iid or block, block length, number of resamples, seed.)

## Result

(The decision from your acceptance criterion: accept, reject or inconclusive — and why. What got better,
what got worse, by how much. Do not round a CI into a certainty.)

## Limits

(What your measurement does NOT prove: simulated or synthetic data, few independent episodes, cases
you did not test, what would be needed before this change goes into the product.)
