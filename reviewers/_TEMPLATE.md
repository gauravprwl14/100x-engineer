# <Stack> reviewer

Contract: every rule below is either a runnable check or a precise review question a
human can answer yes/no. No adjectives. No "follow best practices".

## Applies when
<!-- concrete file/dependency signals that mean this reviewer is in scope -->

## Blocking rules
| # | rule | how it is checked | failure it prevents |
|---|------|-------------------|---------------------|

## Common AI failure modes in this stack
<!-- THE most valuable section: what LLMs specifically get wrong here, and the
     symptom you can grep for or see in a diff. Each needs a detection method. -->
| # | what the model does | why it looks right | detection | correct move |
|---|---------------------|--------------------|-----------|--------------|

## Edge cases routinely missed
| # | edge case | why it is missed | test that would catch it |
|---|-----------|------------------|--------------------------|

## Approach selection
<!-- For the 3-5 decisions in this stack that have several defensible answers:
     the options, the deciding factor, and a DEFAULT recommendation. -->
| decision | options | deciding factor | default recommendation |
|----------|---------|-----------------|------------------------|

## Verify
```bash
# runnable, diff-scoped where possible
```

## Sources
<!-- owner/repo:path, or SOURCE: original -->
