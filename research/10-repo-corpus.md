# Repo Corpus

Screen date **2026-09-28**. Gates and scoring per [`00-signal-rubric.md`](00-signal-rubric.md) (as revised through v4).

## Screening funnel

| stage | in | out | remaining |
|---|---|---|---|
| GitHub search: >=20k stars, pushed <=90d, 14 languages, not fork/archived | — | — | 1431 |
| B1 noise-pattern + license rejection | 1431 | 307 | 1124 |
| A/B/C gate evaluation (GraphQL enrichment) | 1124 | 723 | 401 |
| Part F cluster allocation | 401 | 178 | **223** |

## Gate failure attribution

Why the 723 rejected repos were rejected. A repo can fail several gates.

| gate | meaning | rejected |
|---|---|---|
| A3 | <250 commits in 12 months | 382 |
| A4 | <10 recent authors and <2000 commits/yr | 284 |
| C | <2 of 5 production-reality proxies | 197 |
| A10 | younger than 24mo (12mo for agentic-dev) | 179 |
| A8 | no build manifest | 124 |
| A9 | no test signal | 97 |
| A11 | star velocity >15000/mo — unvalidatable adoption signal | 12 |

## Corpus by cluster

| cluster | selected | eligible | target | note |
|---|---|---|---|---|
| js-infra | 37 | 37 | 55 | **SHORTFALL — supply-limited, not padded** |
| js-app | 35 | 69 | 35 | at target |
| python | 50 | 56 | 50 | at target |
| go | 40 | 63 | 40 | at target |
| mobile | 11 | 11 | 30 | **SHORTFALL — supply-limited, not padded** |
| agentic-dev | 25 | 44 | 25 | at target |
| reliability-exemplar | 25 | 121 | 25 | at target |
| **total** | **223** | 401 | 260 | |

## Headline finding: AI-agent instruction-file adoption

Measured across all **1124** enriched repos (>=20k stars, active within 90 days) by probing for the file on the default branch. This is the adoption rate among serious production repositories, not a curated sample.

| artifact | repos | share |
|---|---|---|
| `AGENTS.md` | 412 | 36.7% |
| `CLAUDE.md` | 290 | 25.8% |
| `.claude/ skills|agents|commands|hooks` | 135 | 12.0% |
| `.agents/ directory` | 144 | 12.8% |
| `.github/copilot-instructions.md` | 117 | 10.4% |
| `.cursor/rules or .cursorrules` | 37 | 3.3% |
| `other (windsurf/gemini/cline/aider/junie)` | 22 | 2.0% |
| `.mcp.json` | 27 | 2.4% |
| **any of the above** | **539** | **48.0%** |

## The corpus

`sc` = total signal score (max 21). `D1`-`D7` = per-dimension score 0-3 (0 absent, 1 present, 2 CI-enforced, 3 exemplary). `T` = tier. `agent` = agent instruction files present.

### js-infra (37)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [prisma/orm](https://github.com/prisma/orm) | 47,677 | TypeScript | 87mo | 8,314 | **17** | 1 | 3 | 2 | 2 | 2 | 3 | 2 | 3 | ACD |
| [nrwl/nx](https://github.com/nrwl/nx) | 29,380 | TypeScript | 110mo | 2,567 | **16** | 1 | 3 | 2 | 3 | 2 | 3 | 1 | 2 | ACSD |
| [QwikDev/qwik](https://github.com/QwikDev/qwik) | 22,067 | TypeScript | 64mo | 3,970 | **16** | 1 | 3 | 2 | 2 | 2 | 2 | 2 | 3 | AC |
| [ant-design/ant-design](https://github.com/ant-design/ant-design) | 99,633 | TypeScript | 137mo | 2,569 | **15** | 1 | 3 | 1 | 3 | 3 | 2 | 1 | 2 | ACDP |
| [nuxt/nuxt](https://github.com/nuxt/nuxt) | 60,905 | TypeScript | 119mo | 1,580 | **15** | 1 | 3 | 2 | 2 | 3 | 2 | 1 | 2 | AC |
| [ToolJet/ToolJet](https://github.com/ToolJet/ToolJet) | 41,010 | JavaScript | 66mo | 5,758 | **15** | 1 | 3 | 0 | 3 | 2 | 3 | 2 | 2 | ACSDP |
| [axios/axios](https://github.com/axios/axios) | 109,241 | JavaScript | 145mo | 469 | **14** | 2 | 3 | 1 | 2 | 2 | 2 | 1 | 3 | AP |
| [cypress-io/cypress](https://github.com/cypress-io/cypress) | 51,031 | TypeScript | 139mo | 1,724 | **14** | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 3 | ACS |
| [react/react](https://github.com/react/react) | 250,796 | JavaScript | 160mo | 769 | **13** | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 2 | CS |
| [cline/cline](https://github.com/cline/cline) | 69,476 | TypeScript | 27mo | 3,886 | **13** | 2 | 3 | 0 | 3 | 1 | 2 | 1 | 3 | ASDP |
| [jestjs/jest](https://github.com/jestjs/jest) | 45,464 | TypeScript | 154mo | 285 | **13** | 2 | 3 | 2 | 2 | 2 | 1 | 0 | 3 | CP |
| [babel/babel](https://github.com/babel/babel) | 44,043 | TypeScript | 144mo | 459 | **13** | 2 | 3 | 2 | 1 | 2 | 2 | 1 | 2 | A |
| [eslint/eslint](https://github.com/eslint/eslint) | 27,521 | JavaScript | 159mo | 657 | **13** | 2 | 3 | 2 | 1 | 2 | 2 | 0 | 3 | A |
| [marmelab/react-admin](https://github.com/marmelab/react-admin) | 26,944 | TypeScript | 122mo | 1,061 | **13** | 2 | 3 | 2 | 2 | 2 | 1 | 1 | 2 | ACD |
| [mochajs/mocha](https://github.com/mochajs/mocha) | 22,894 | JavaScript | 187mo | 405 | **13** | 2 | 2 | 1 | 2 | 2 | 2 | 1 | 3 | AP |
| [vercel/next.js](https://github.com/vercel/next.js) | 142,827 | JavaScript | 120mo | 4,941 | **12** | 2 | 3 | 2 | 2 | 2 | 0 | 1 | 2 | AD |
| [vitejs/vite](https://github.com/vitejs/vite) | 83,061 | TypeScript | 77mo | 1,233 | **12** | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 2 | P |
| [hoppscotch/hoppscotch](https://github.com/hoppscotch/hoppscotch) | 80,535 | TypeScript | 85mo | 330 | **12** | 2 | 2 | 2 | 0 | 1 | 2 | 2 | 3 | — |
| [usebruno/bruno](https://github.com/usebruno/bruno) | 47,240 | JavaScript | 48mo | 1,659 | **12** | 2 | 3 | 1 | 1 | 2 | 2 | 0 | 3 | S |
| [reactive-resume/reactive-resume](https://github.com/reactive-resume/reactive-resume) | 43,501 | TypeScript | 78mo | 1,297 | **12** | 2 | 3 | 2 | 2 | 3 | 1 | 1 | 0 | ACP |
| [chakra-ui/chakra-ui](https://github.com/chakra-ui/chakra-ui) | 40,672 | TypeScript | 85mo | 441 | **12** | 2 | 1 | 2 | 2 | 2 | 2 | 1 | 2 | CS |
| [element-plus/element-plus](https://github.com/element-plus/element-plus) | 27,792 | TypeScript | 74mo | 1,058 | **12** | 2 | 3 | 2 | 1 | 3 | 0 | 1 | 2 | A |
| [monkeytypegame/monkeytype](https://github.com/monkeytypegame/monkeytype) | 20,775 | TypeScript | 76mo | 1,253 | **12** | 2 | 2 | 2 | 3 | 2 | 1 | 1 | 1 | ACSP |
| [angular/angular](https://github.com/angular/angular) | 101,032 | TypeScript | 144mo | 3,911 | **11** | 2 | 2 | 2 | 1 | 1 | 2 | 1 | 2 | A |
| [microsoft/playwright](https://github.com/microsoft/playwright) | 96,804 | TypeScript | 82mo | 2,608 | **11** | 2 | 2 | 1 | 2 | 2 | 2 | 1 | 1 | CSP |
| [puppeteer/puppeteer](https://github.com/puppeteer/puppeteer) | 95,630 | TypeScript | 113mo | 789 | **11** | 2 | 2 | 1 | 1 | 2 | 2 | 1 | 2 | D |
| [sveltejs/svelte](https://github.com/sveltejs/svelte) | 88,218 | JavaScript | 118mo | 825 | **11** | 2 | 2 | 2 | 2 | 2 | 0 | 1 | 2 | AD |
| [react-hook-form/react-hook-form](https://github.com/react-hook-form/react-hook-form) | 44,864 | TypeScript | 91mo | 392 | **11** | 2 | 3 | 2 | 0 | 2 | 2 | 0 | 2 | — |
| [refinedev/refine](https://github.com/refinedev/refine) | 35,734 | TypeScript | 68mo | 376 | **11** | 2 | 2 | 2 | 0 | 2 | 1 | 1 | 3 | — |
| [eclipse-theia/theia](https://github.com/eclipse-theia/theia) | 21,703 | TypeScript | 115mo | 922 | **11** | 2 | 2 | 2 | 1 | 1 | 2 | 1 | 2 | C |
| [nestjs/nest](https://github.com/nestjs/nest) | 76,747 | TypeScript | 116mo | 2,931 | **10** | 2 | 2 | 2 | 0 | 1 | 3 | 0 | 2 | — |
| [Kong/insomnia](https://github.com/Kong/insomnia) | 40,038 | TypeScript | 125mo | 797 | **10** | 2 | 2 | 1 | 2 | 1 | 1 | 1 | 2 | ACS |
| [heroui-inc/heroui](https://github.com/heroui-inc/heroui) | 30,843 | TypeScript | 65mo | 781 | **10** | 2 | 1 | 2 | 2 | 2 | 0 | 1 | 2 | ACS |
| [quasarframework/quasar](https://github.com/quasarframework/quasar) | 27,215 | JavaScript | 132mo | 2,147 | **10** | 2 | 2 | 1 | 2 | 1 | 1 | 1 | 2 | ACS |
| [tailwindlabs/tailwindcss](https://github.com/tailwindlabs/tailwindcss) | 97,723 | TypeScript | 108mo | 420 | **8** | 3 | 2 | 2 | 0 | 0 | 0 | 1 | 3 | — |
| [fastify/fastify](https://github.com/fastify/fastify) | 37,206 | JavaScript | 120mo | 346 | **8** | 3 | 2 | 0 | 0 | 2 | 2 | 0 | 2 | — |
| [honojs/hono](https://github.com/honojs/hono) | 32,369 | TypeScript | 58mo | 441 | **8** | 3 | 3 | 1 | 0 | 2 | 0 | 1 | 1 | — |

### js-app (35)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [grafana/grafana](https://github.com/grafana/grafana) | 76,963 | TypeScript | 154mo | 11,244 | **18** | 1 | 3 | 3 | 2 | 3 | 2 | 2 | 3 | ACS |
| [backstage/backstage](https://github.com/backstage/backstage) | 34,516 | TypeScript | 80mo | 8,458 | **18** | 1 | 3 | 1 | 3 | 3 | 3 | 2 | 3 | ASPR |
| [TryGhost/Ghost](https://github.com/TryGhost/Ghost) | 55,453 | TypeScript | 161mo | 5,848 | **16** | 1 | 3 | 2 | 3 | 2 | 1 | 2 | 3 | ACSD |
| [calcom/cal.diy](https://github.com/calcom/cal.diy) | 48,710 | TypeScript | 66mo | 2,202 | **16** | 1 | 3 | 2 | 2 | 2 | 2 | 2 | 3 | AC |
| [actualbudget/actual](https://github.com/actualbudget/actual) | 29,193 | TypeScript | 53mo | 1,479 | **16** | 1 | 3 | 2 | 3 | 2 | 2 | 2 | 2 | ACSDR |
| [supabase/supabase](https://github.com/supabase/supabase) | 110,852 | TypeScript | 84mo | 6,040 | **15** | 1 | 3 | 3 | 3 | 2 | 1 | 1 | 2 | ACDPM |
| [mui/material-ui](https://github.com/mui/material-ui) | 99,107 | JavaScript | 145mo | 1,391 | **15** | 1 | 2 | 2 | 3 | 2 | 3 | 1 | 2 | ACSD |
| [mermaid-js/mermaid](https://github.com/mermaid-js/mermaid) | 90,457 | TypeScript | 143mo | 2,423 | **15** | 1 | 3 | 2 | 0 | 3 | 2 | 2 | 3 | — |
| [facebook/docusaurus](https://github.com/facebook/docusaurus) | 66,353 | TypeScript | 111mo | 439 | **15** | 1 | 3 | 2 | 1 | 3 | 2 | 1 | 3 | A |
| [payloadcms/payload](https://github.com/payloadcms/payload) | 45,002 | TypeScript | 69mo | 1,800 | **15** | 1 | 3 | 2 | 3 | 2 | 2 | 1 | 2 | ASDM |
| [TriliumNext/Trilium](https://github.com/TriliumNext/Trilium) | 38,052 | TypeScript | 112mo | 18,402 | **15** | 1 | 3 | 2 | 2 | 2 | 3 | 2 | 1 | CSM |
| [better-auth/better-auth](https://github.com/better-auth/better-auth) | 30,106 | TypeScript | 28mo | 3,050 | **15** | 1 | 3 | 2 | 2 | 2 | 2 | 2 | 2 | AC |
| [DIYgod/RSSHub](https://github.com/DIYgod/RSSHub) | 46,347 | TypeScript | 102mo | 2,640 | **14** | 2 | 3 | 0 | 1 | 3 | 3 | 2 | 2 | A |
| [LibreChat-AI/LibreChat](https://github.com/LibreChat-AI/LibreChat) | 45,026 | TypeScript | 44mo | 2,610 | **14** | 2 | 3 | 2 | 2 | 2 | 1 | 2 | 2 | ACS |
| [ueberdosis/tiptap](https://github.com/ueberdosis/tiptap) | 38,567 | TypeScript | 97mo | 928 | **14** | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 3 | AC |
| [facebook/lexical](https://github.com/facebook/lexical) | 23,902 | TypeScript | 70mo | 815 | **14** | 2 | 3 | 2 | 2 | 2 | 1 | 1 | 3 | AC |
| [renovatebot/renovate](https://github.com/renovatebot/renovate) | 22,613 | TypeScript | 117mo | 4,980 | **14** | 2 | 3 | 2 | 2 | 2 | 3 | 0 | 2 | AC |
| [super-productivity/super-productivity](https://github.com/super-productivity/super-productivity) | 22,317 | TypeScript | 117mo | 6,910 | **14** | 2 | 3 | 1 | 2 | 2 | 2 | 2 | 2 | ACD |
| [sveltejs/kit](https://github.com/sveltejs/kit) | 20,828 | JavaScript | 71mo | 1,561 | **14** | 2 | 2 | 2 | 2 | 3 | 2 | 1 | 2 | ACP |
| [microsoft/vscode](https://github.com/microsoft/vscode) | 193,208 | TypeScript | 133mo | 27,009 | **13** | 2 | 3 | 0 | 3 | 2 | 3 | 0 | 2 | ADPM |
| [makeplane/plane](https://github.com/makeplane/plane) | 59,983 | TypeScript | 46mo | 808 | **13** | 2 | 2 | 2 | 2 | 1 | 2 | 2 | 2 | AS |
| [remix-run/react-router](https://github.com/remix-run/react-router) | 56,589 | TypeScript | 148mo | 888 | **13** | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 2 | ACD |
| [mozilla/pdf.js](https://github.com/mozilla/pdf.js) | 53,952 | JavaScript | 185mo | 2,586 | **13** | 2 | 3 | 0 | 2 | 3 | 2 | 1 | 2 | AM |
| [typeorm/typeorm](https://github.com/typeorm/typeorm) | 36,658 | TypeScript | 127mo | 474 | **13** | 2 | 2 | 2 | 1 | 1 | 3 | 2 | 2 | P |
| [wekan/wekan](https://github.com/wekan/wekan) | 21,098 | JavaScript | 152mo | 16,379 | **13** | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | ACD |
| [excalidraw/excalidraw](https://github.com/excalidraw/excalidraw) | 133,140 | TypeScript | 81mo | 272 | **12** | 2 | 2 | 2 | 2 | 3 | 0 | 2 | 1 | ACP |
| [shadcn-ui/ui](https://github.com/shadcn-ui/ui) | 124,751 | TypeScript | 45mo | 1,523 | **12** | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 2 | R |
| [louislam/uptime-kuma](https://github.com/louislam/uptime-kuma) | 91,903 | JavaScript | 63mo | 1,348 | **12** | 2 | 3 | 0 | 2 | 2 | 2 | 1 | 2 | ACP |
| [prettier/prettier](https://github.com/prettier/prettier) | 52,317 | JavaScript | 118mo | 1,503 | **12** | 2 | 3 | 2 | 0 | 3 | 1 | 1 | 2 | — |
| [HeyPuter/puter](https://github.com/HeyPuter/puter) | 43,607 | TypeScript | 31mo | 2,540 | **12** | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | AC |
| [trpc/trpc](https://github.com/trpc/trpc) | 40,669 | TypeScript | 74mo | 256 | **12** | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 2 | R |
| [TanStack/table](https://github.com/TanStack/table) | 28,463 | TypeScript | 119mo | 447 | **12** | 2 | 3 | 2 | 1 | 2 | 0 | 1 | 3 | A |
| [badges/shields](https://github.com/badges/shields) | 27,221 | JavaScript | 164mo | 605 | **12** | 2 | 3 | 0 | 0 | 3 | 2 | 2 | 2 | — |
| [jhipster/generator-jhipster](https://github.com/jhipster/generator-jhipster) | 22,459 | TypeScript | 155mo | 3,869 | **12** | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | ACP |
| [immich-app/immich](https://github.com/immich-app/immich) | 115,201 | TypeScript | 56mo | 2,831 | **11** | 2 | 2 | 2 | 0 | 2 | 2 | 1 | 2 | — |

### python (50)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [apache/superset](https://github.com/apache/superset) | 74,946 | Python | 134mo | 5,523 | **16** | 1 | 3 | 1 | 3 | 2 | 2 | 2 | 3 | ACSPR |
| [apache/airflow](https://github.com/apache/airflow) | 46,999 | Python | 138mo | 8,291 | **14** | 2 | 3 | 0 | 3 | 1 | 3 | 2 | 2 | ACSD |
| [streamlit/streamlit](https://github.com/streamlit/streamlit) | 45,847 | Python | 85mo | 2,382 | **14** | 2 | 3 | 0 | 3 | 2 | 3 | 1 | 2 | ACSPR |
| [marimo-team/marimo](https://github.com/marimo-team/marimo) | 22,921 | Python | 38mo | 2,505 | **14** | 2 | 3 | 2 | 2 | 1 | 2 | 1 | 3 | ACP |
| [onnx/onnx](https://github.com/onnx/onnx) | 21,539 | Python | 109mo | 730 | **14** | 2 | 3 | 0 | 3 | 2 | 3 | 1 | 2 | ACDP |
| [zulip/zulip](https://github.com/zulip/zulip) | 25,964 | Python | 132mo | 5,019 | **13** | 2 | 2 | 1 | 2 | 2 | 2 | 2 | 2 | AS |
| [docling-project/docling](https://github.com/docling-project/docling) | 68,115 | Python | 27mo | 836 | **12** | 2 | 2 | 1 | 3 | 0 | 1 | 2 | 3 | ACSD |
| [topoteretes/cognee](https://github.com/topoteretes/cognee) | 31,110 | Python | 37mo | 7,360 | **12** | 2 | 3 | 0 | 2 | 1 | 2 | 2 | 2 | ACS |
| [reflex-dev/reflex](https://github.com/reflex-dev/reflex) | 28,920 | Python | 47mo | 799 | **12** | 2 | 3 | 1 | 2 | 0 | 2 | 1 | 3 | ACS |
| [Skyvern-AI/skyvern](https://github.com/Skyvern-AI/skyvern) | 23,090 | Python | 31mo | 3,913 | **12** | 2 | 3 | 1 | 2 | 1 | 1 | 2 | 2 | ACS |
| [huggingface/transformers](https://github.com/huggingface/transformers) | 166,755 | Python | 95mo | 3,527 | **11** | 2 | 3 | 0 | 2 | 0 | 3 | 1 | 2 | ACP |
| [home-assistant/core](https://github.com/home-assistant/core) | 91,193 | Python | 156mo | 18,413 | **11** | 2 | 3 | 0 | 3 | 1 | 1 | 1 | 2 | ACSP |
| [ccxt/ccxt](https://github.com/ccxt/ccxt) | 44,192 | Python | 112mo | 10,099 | **11** | 2 | 1 | 0 | 3 | 2 | 1 | 2 | 2 | ACSD |
| [huggingface/diffusers](https://github.com/huggingface/diffusers) | 34,624 | Python | 52mo | 1,065 | **11** | 2 | 3 | 0 | 2 | 1 | 2 | 1 | 2 | AC |
| [PrefectHQ/prefect](https://github.com/PrefectHQ/prefect) | 23,942 | Python | 99mo | 2,545 | **11** | 2 | 3 | 0 | 2 | 0 | 2 | 2 | 2 | AS |
| [wagtail/wagtail](https://github.com/wagtail/wagtail) | 20,509 | Python | 152mo | 1,384 | **11** | 2 | 3 | 0 | 1 | 3 | 2 | 0 | 2 | A |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | 67,407 | Python | 193mo | 1,141 | **10** | 2 | 3 | 0 | 1 | 1 | 2 | 1 | 2 | A |
| [deepspeedai/DeepSpeed](https://github.com/deepspeedai/DeepSpeed) | 43,162 | Python | 80mo | 562 | **10** | 2 | 3 | 0 | 2 | 1 | 1 | 1 | 2 | AC |
| [psf/black](https://github.com/psf/black) | 41,859 | Python | 102mo | 313 | **10** | 2 | 3 | 0 | 0 | 1 | 2 | 2 | 2 | — |
| [jax-ml/jax](https://github.com/jax-ml/jax) | 36,358 | Python | 95mo | 7,819 | **10** | 2 | 3 | 0 | 0 | 2 | 2 | 1 | 2 | — |
| [openai/openai-python](https://github.com/openai/openai-python) | 31,711 | Python | 71mo | 540 | **10** | 2 | 2 | 1 | 1 | 0 | 2 | 1 | 3 | A |
| [ArchiveBox/ArchiveBox](https://github.com/ArchiveBox/ArchiveBox) | 28,638 | Python | 113mo | 3,066 | **10** | 2 | 2 | 0 | 1 | 1 | 2 | 2 | 2 | A |
| [huggingface/lerobot](https://github.com/huggingface/lerobot) | 27,824 | Python | 32mo | 792 | **10** | 2 | 3 | 0 | 2 | 0 | 2 | 1 | 2 | AC |
| [huggingface/peft](https://github.com/huggingface/peft) | 21,731 | Python | 46mo | 495 | **10** | 2 | 3 | 0 | 2 | 0 | 2 | 1 | 2 | AC |
| [vllm-project/vllm](https://github.com/vllm-project/vllm) | 92,858 | Python | 44mo | 12,099 | **9** | 3 | 3 | 0 | 2 | 0 | 2 | 0 | 2 | ASD |
| [keras-team/keras](https://github.com/keras-team/keras) | 64,346 | Python | 138mo | 1,053 | **9** | 3 | 3 | 0 | 0 | 0 | 3 | 1 | 2 | — |
| [roboflow/supervision](https://github.com/roboflow/supervision) | 51,068 | Python | 46mo | 673 | **9** | 3 | 3 | 0 | 2 | 0 | 1 | 1 | 2 | ACP |
| [ray-project/ray](https://github.com/ray-project/ray) | 43,939 | Python | 119mo | 4,650 | **9** | 3 | 2 | 0 | 2 | 1 | 2 | 0 | 2 | AS |
| [locustio/locust](https://github.com/locustio/locust) | 28,184 | Python | 187mo | 568 | **9** | 3 | 3 | 0 | 1 | 0 | 2 | 1 | 2 | A |
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 194,068 | Python | 71mo | 502 | **8** | 3 | 2 | 0 | 0 | 1 | 1 | 1 | 3 | — |
| [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | 135,310 | Python | 44mo | 2,052 | **8** | 3 | 2 | 0 | 1 | 1 | 1 | 1 | 2 | A |
| [django/django](https://github.com/django/django) | 91,226 | Python | 173mo | 1,046 | **8** | 3 | 3 | 0 | 1 | 2 | 1 | 0 | 1 | P |
| [ultralytics/ultralytics](https://github.com/ultralytics/ultralytics) | 62,063 | Python | 49mo | 2,116 | **8** | 3 | 2 | 0 | 2 | 1 | 1 | 1 | 1 | AC |
| [freqtrade/freqtrade](https://github.com/freqtrade/freqtrade) | 54,867 | Python | 112mo | 3,295 | **8** | 3 | 3 | 0 | 0 | 0 | 1 | 2 | 2 | — |
| [pandas-dev/pandas](https://github.com/pandas-dev/pandas) | 49,856 | Python | 193mo | 2,668 | **8** | 3 | 2 | 0 | 1 | 0 | 3 | 0 | 2 | A |
| [frappe/erpnext](https://github.com/frappe/erpnext) | 39,617 | Python | 184mo | 7,041 | **8** | 3 | 2 | 0 | 0 | 2 | 1 | 1 | 2 | — |
| [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 38,392 | Python | 45mo | 501 | **8** | 3 | 2 | 0 | 1 | 0 | 2 | 1 | 2 | D |
| [soxoj/maigret](https://github.com/soxoj/maigret) | 38,031 | Python | 75mo | 554 | **8** | 3 | 2 | 0 | 0 | 0 | 2 | 2 | 2 | — |
| [dgtlmoon/changedetection.io](https://github.com/dgtlmoon/changedetection.io) | 34,628 | Python | 68mo | 660 | **8** | 3 | 2 | 0 | 0 | 1 | 2 | 2 | 1 | — |
| [Lightning-AI/pytorch-lightning](https://github.com/Lightning-AI/pytorch-lightning) | 31,367 | Python | 90mo | 273 | **8** | 3 | 3 | 0 | 0 | 0 | 2 | 1 | 2 | — |
| [pydantic/pydantic](https://github.com/pydantic/pydantic) | 28,892 | Python | 113mo | 664 | **8** | 3 | 3 | 0 | 1 | 0 | 2 | 0 | 2 | D |
| [searxng/searxng](https://github.com/searxng/searxng) | 37,715 | Python | 66mo | 845 | **7** | 3 | 2 | 0 | 0 | 2 | 2 | 0 | 1 | — |
| [kovidgoyal/kitty](https://github.com/kovidgoyal/kitty) | 35,104 | Python | 119mo | 2,898 | **7** | 3 | 1 | 0 | 1 | 1 | 3 | 0 | 1 | P |
| [invoke-ai/InvokeAI](https://github.com/invoke-ai/InvokeAI) | 28,309 | Python | 49mo | 712 | **7** | 3 | 2 | 0 | 0 | 1 | 1 | 1 | 2 | — |
| [ranaroussi/yfinance](https://github.com/ranaroussi/yfinance) | 25,386 | Python | 112mo | 320 | **7** | 3 | 2 | 0 | 0 | 1 | 1 | 1 | 2 | — |
| [modelscope/FunASR](https://github.com/modelscope/FunASR) | 20,532 | Python | 46mo | 1,138 | **7** | 3 | 3 | 0 | 0 | 0 | 1 | 1 | 2 | — |
| [sherlock-project/sherlock](https://github.com/sherlock-project/sherlock) | 92,954 | Python | 93mo | 258 | **6** | 3 | 2 | 0 | 0 | 1 | 1 | 1 | 1 | — |
| [exo-explore/exo](https://github.com/exo-explore/exo) | 47,668 | Python | 27mo | 629 | **6** | 3 | 2 | 0 | 2 | 0 | 0 | 0 | 2 | ACR |
| [huggingface/pytorch-image-models](https://github.com/huggingface/pytorch-image-models) | 37,173 | Python | 92mo | 313 | **6** | 3 | 2 | 0 | 2 | 0 | 1 | 0 | 1 | AC |
| [jumpserver/jumpserver](https://github.com/jumpserver/jumpserver) | 31,625 | Python | 147mo | 1,185 | **6** | 3 | 1 | 0 | 0 | 0 | 1 | 2 | 2 | — |

### go (40)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [vitessio/vitess](https://github.com/vitessio/vitess) | 21,358 | Go | 159mo | 885 | **16** | 1 | 3 | 0 | 3 | 2 | 3 | 2 | 3 | ACDP |
| [gravitational/teleport](https://github.com/gravitational/teleport) | 20,950 | Go | 139mo | 3,854 | **16** | 1 | 3 | 2 | 2 | 3 | 2 | 1 | 3 | ASD |
| [prometheus/prometheus](https://github.com/prometheus/prometheus) | 66,290 | Go | 166mo | 2,559 | **14** | 2 | 2 | 0 | 2 | 2 | 3 | 2 | 3 | AC |
| [go-gitea/gitea](https://github.com/go-gitea/gitea) | 58,204 | Go | 119mo | 1,750 | **14** | 2 | 3 | 1 | 1 | 3 | 2 | 2 | 2 | A |
| [mudler/LocalAI](https://github.com/mudler/LocalAI) | 49,305 | Go | 42mo | 3,539 | **14** | 2 | 3 | 0 | 2 | 2 | 3 | 2 | 2 | ACD |
| [k3s-io/k3s](https://github.com/k3s-io/k3s) | 34,051 | Go | 100mo | 527 | **14** | 2 | 3 | 0 | 1 | 2 | 3 | 2 | 3 | D |
| [jaegertracing/jaeger](https://github.com/jaegertracing/jaeger) | 23,248 | Go | 125mo | 1,019 | **14** | 2 | 2 | 0 | 2 | 2 | 3 | 2 | 3 | ACP |
| [pulumi/pulumi](https://github.com/pulumi/pulumi) | 25,737 | Go | 119mo | 2,418 | **13** | 2 | 3 | 0 | 2 | 2 | 2 | 1 | 3 | ACS |
| [argoproj/argo-cd](https://github.com/argoproj/argo-cd) | 24,262 | Go | 104mo | 2,198 | **13** | 2 | 2 | 0 | 2 | 1 | 3 | 2 | 3 | AC |
| [netdata/netdata](https://github.com/netdata/netdata) | 80,676 | Go | 159mo | 2,575 | **12** | 2 | 2 | 1 | 3 | 0 | 2 | 2 | 2 | ACD |
| [traefik/traefik](https://github.com/traefik/traefik) | 64,987 | Go | 132mo | 913 | **12** | 2 | 2 | 0 | 2 | 1 | 2 | 2 | 3 | ACS |
| [gofiber/fiber](https://github.com/gofiber/fiber) | 40,187 | Go | 80mo | 2,745 | **12** | 2 | 2 | 1 | 2 | 2 | 2 | 1 | 2 | AP |
| [grafana/k6](https://github.com/grafana/k6) | 31,684 | Go | 126mo | 834 | **12** | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | AC |
| [grafana/loki](https://github.com/grafana/loki) | 28,963 | Go | 101mo | 2,959 | **12** | 2 | 2 | 1 | 1 | 2 | 2 | 1 | 3 | A |
| [trufflesecurity/trufflehog](https://github.com/trufflesecurity/trufflehog) | 28,159 | Go | 117mo | 400 | **12** | 2 | 2 | 0 | 1 | 2 | 2 | 2 | 3 | S |
| [redis/go-redis](https://github.com/redis/go-redis) | 22,255 | Go | 170mo | 285 | **12** | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | ACS |
| [microsoft/TypeScript](https://github.com/microsoft/TypeScript) | 111,253 | Go | 147mo | 1,800 | **11** | 2 | 1 | 1 | 1 | 2 | 3 | 1 | 2 | P |
| [moby/moby](https://github.com/moby/moby) | 72,146 | Go | 164mo | 3,849 | **11** | 2 | 2 | 0 | 2 | 2 | 2 | 1 | 2 | ACP |
| [etcd-io/etcd](https://github.com/etcd-io/etcd) | 52,314 | Go | 159mo | 1,409 | **11** | 2 | 3 | 0 | 0 | 1 | 3 | 2 | 2 | — |
| [tailscale/tailscale](https://github.com/tailscale/tailscale) | 36,960 | Go | 80mo | 1,765 | **11** | 2 | 2 | 1 | 0 | 2 | 2 | 2 | 2 | — |
| [dapr/dapr](https://github.com/dapr/dapr) | 26,118 | Go | 87mo | 577 | **11** | 2 | 3 | 0 | 1 | 1 | 2 | 1 | 3 | P |
| [cilium/cilium](https://github.com/cilium/cilium) | 25,568 | Go | 129mo | 5,478 | **11** | 2 | 3 | 0 | 0 | 2 | 2 | 1 | 3 | — |
| [temporalio/temporal](https://github.com/temporalio/temporal) | 23,334 | Go | 83mo | 1,995 | **11** | 2 | 2 | 0 | 3 | 2 | 0 | 1 | 3 | ASPR |
| [wavetermdev/waveterm](https://github.com/wavetermdev/waveterm) | 22,378 | Go | 52mo | 582 | **11** | 2 | 2 | 0 | 2 | 3 | 2 | 1 | 1 | CP |
| [containerd/containerd](https://github.com/containerd/containerd) | 21,347 | Go | 130mo | 1,790 | **11** | 2 | 3 | 0 | 2 | 2 | 2 | 1 | 1 | AC |
| [infiniflow/ragflow](https://github.com/infiniflow/ragflow) | 91,423 | Go | 34mo | 5,741 | **10** | 2 | 3 | 0 | 2 | 1 | 1 | 2 | 1 | ADP |
| [caddyserver/caddy](https://github.com/caddyserver/caddy) | 76,138 | Go | 140mo | 344 | **10** | 2 | 2 | 0 | 1 | 2 | 2 | 1 | 2 | A |
| [rclone/rclone](https://github.com/rclone/rclone) | 59,985 | Go | 150mo | 1,294 | **10** | 2 | 1 | 0 | 2 | 1 | 1 | 2 | 3 | AC |
| [milvus-io/milvus](https://github.com/milvus-io/milvus) | 46,270 | Go | 84mo | 2,490 | **10** | 2 | 3 | 0 | 2 | 2 | 0 | 2 | 1 | AC |
| [aquasecurity/trivy](https://github.com/aquasecurity/trivy) | 38,105 | Go | 90mo | 517 | **10** | 2 | 2 | 0 | 0 | 1 | 2 | 2 | 3 | — |
| [podman-container-tools/podman](https://github.com/podman-container-tools/podman) | 32,960 | Go | 107mo | 2,491 | **10** | 2 | 2 | 0 | 1 | 2 | 2 | 1 | 2 | A |
| [opentofu/opentofu](https://github.com/opentofu/opentofu) | 30,312 | Go | 37mo | 910 | **10** | 2 | 2 | 0 | 1 | 1 | 1 | 2 | 3 | A |
| [helm/helm](https://github.com/helm/helm) | 30,288 | Go | 132mo | 1,101 | **10** | 2 | 1 | 0 | 1 | 2 | 3 | 1 | 2 | A |
| [goharbor/harbor](https://github.com/goharbor/harbor) | 29,467 | Go | 128mo | 365 | **10** | 2 | 2 | 0 | 0 | 1 | 3 | 1 | 3 | — |
| [MHSanaei/3x-ui](https://github.com/MHSanaei/3x-ui) | 47,093 | Go | 44mo | 1,649 | **9** | 3 | 1 | 0 | 1 | 1 | 2 | 2 | 2 | C |
| [dokku/dokku](https://github.com/dokku/dokku) | 32,162 | Go | 160mo | 2,074 | **9** | 3 | 2 | 0 | 0 | 2 | 2 | 2 | 1 | — |
| [kubernetes/minikube](https://github.com/kubernetes/minikube) | 32,161 | Go | 125mo | 2,096 | **9** | 3 | 3 | 0 | 0 | 2 | 2 | 0 | 2 | — |
| [authelia/authelia](https://github.com/authelia/authelia) | 29,117 | Go | 118mo | 2,468 | **9** | 3 | 1 | 0 | 0 | 2 | 3 | 1 | 2 | — |
| [lima-vm/lima](https://github.com/lima-vm/lima) | 21,985 | Go | 64mo | 1,742 | **9** | 3 | 1 | 0 | 2 | 2 | 2 | 1 | 1 | AC |
| [QuantumNous/new-api](https://github.com/QuantumNous/new-api) | 49,007 | Go | 35mo | 2,228 | **8** | 3 | 2 | 0 | 2 | 0 | 1 | 2 | 1 | ACD |

### mobile (11)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [expo/expo](https://github.com/expo/expo) | 52,475 | TypeScript | 121mo | 6,462 | **12** | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 2 | S |
| [NativeScript/NativeScript](https://github.com/NativeScript/NativeScript) | 25,653 | TypeScript | 139mo | 439 | **11** | 2 | 2 | 2 | 1 | 2 | 2 | 1 | 1 | A |
| [react/react-native](https://github.com/react/react-native) | 126,753 | C++ | 141mo | 3,172 | **9** | 3 | 2 | 1 | 1 | 2 | 0 | 1 | 2 | A |
| [localsend/localsend](https://github.com/localsend/localsend) | 92,882 | Dart | 45mo | 351 | **9** | 3 | 1 | 1 | 2 | 0 | 2 | 1 | 2 | AC |
| [ionic-team/ionic-framework](https://github.com/ionic-team/ionic-framework) | 52,686 | TypeScript | 157mo | 462 | **9** | 3 | 1 | 2 | 0 | 1 | 2 | 1 | 2 | — |
| [flutter/flutter](https://github.com/flutter/flutter) | 179,133 | Dart | 139mo | 5,587 | **8** | 3 | 1 | 1 | 1 | 0 | 1 | 1 | 3 | D |
| [onevcat/Kingfisher](https://github.com/onevcat/Kingfisher) | 24,404 | Swift | 138mo | 329 | **6** | 3 | 2 | 0 | 2 | 0 | 0 | 0 | 2 | AC |
| [lysine-dev/okhttp](https://github.com/lysine-dev/okhttp) | 47,077 | Kotlin | 170mo | 395 | **5** | 3 | 1 | 0 | 0 | 1 | 0 | 1 | 2 | — |
| [signalapp/Signal-Android](https://github.com/signalapp/Signal-Android) | 29,400 | Kotlin | 177mo | 3,186 | **5** | 3 | 2 | 0 | 0 | 1 | 0 | 0 | 2 | — |
| [swiftlang/swift](https://github.com/swiftlang/swift) | 70,434 | Swift | 131mo | 12,416 | **4** | 3 | 1 | 0 | 0 | 1 | 0 | 0 | 2 | — |
| [ReVanced/revanced-manager](https://github.com/ReVanced/revanced-manager) | 29,659 | Kotlin | 54mo | 705 | **4** | 3 | 1 | 0 | 0 | 1 | 0 | 1 | 1 | — |

### agentic-dev (25)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [CherryHQ/cherry-studio](https://github.com/CherryHQ/cherry-studio) | 52,208 | TypeScript | 28mo | 4,496 | **17** | 1 | 3 | 2 | 3 | 3 | 2 | 1 | 3 | ACSD |
| [QwenLM/qwen-code](https://github.com/QwenLM/qwen-code) | 28,192 | TypeScript | 15mo | 7,806 | **17** | 1 | 3 | 2 | 2 | 2 | 3 | 2 | 3 | AC |
| [ComposioHQ/composio](https://github.com/ComposioHQ/composio) | 30,348 | TypeScript | 31mo | 4,477 | **16** | 1 | 3 | 2 | 3 | 2 | 2 | 1 | 3 | ACSD |
| [promptfoo/promptfoo](https://github.com/promptfoo/promptfoo) | 25,526 | TypeScript | 41mo | 4,218 | **16** | 1 | 3 | 2 | 2 | 3 | 2 | 2 | 2 | ASD |
| [mlflow/mlflow](https://github.com/mlflow/mlflow) | 28,160 | Python | 100mo | 4,760 | **15** | 1 | 3 | 1 | 3 | 1 | 3 | 2 | 2 | ACSD |
| [langflow-ai/langflow](https://github.com/langflow-ai/langflow) | 155,326 | Python | 44mo | 2,497 | **14** | 2 | 3 | 1 | 3 | 2 | 3 | 1 | 1 | ACDR |
| [CopilotKit/CopilotKit](https://github.com/CopilotKit/CopilotKit) | 37,580 | TypeScript | 39mo | 13,587 | **14** | 2 | 2 | 2 | 3 | 1 | 2 | 1 | 3 | ACRM |
| [simstudioai/sim](https://github.com/simstudioai/sim) | 29,746 | TypeScript | 21mo | 5,540 | **14** | 2 | 2 | 2 | 3 | 1 | 2 | 2 | 2 | ACSDR |
| [yamadashy/repomix](https://github.com/yamadashy/repomix) | 28,517 | TypeScript | 26mo | 2,390 | **14** | 2 | 3 | 0 | 3 | 2 | 2 | 2 | 2 | ACSDPR |
| [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode) | 27,429 | TypeScript | 19mo | 29,654 | **14** | 2 | 2 | 2 | 1 | 2 | 3 | 1 | 3 | A |
| [vectordotdev/vector](https://github.com/vectordotdev/vector) | 22,631 | Rust | 97mo | 1,357 | **14** | 2 | 3 | 0 | 2 | 2 | 2 | 2 | 3 | AC |
| [github/spec-kit](https://github.com/github/spec-kit) | 139,218 | Python | 13mo | 1,803 | **13** | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 3 | A |
| [pingcap/tidb](https://github.com/pingcap/tidb) | 40,597 | Go | 133mo | 1,760 | **13** | 2 | 3 | 0 | 3 | 2 | 2 | 1 | 2 | ACSD |
| [ruvnet/ruflo](https://github.com/ruvnet/ruflo) | 73,421 | TypeScript | 16mo | 4,778 | **12** | 2 | 2 | 0 | 3 | 1 | 3 | 1 | 2 | ACSD |
| [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 59,132 | Python | 35mo | 1,178 | **12** | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 2 | A |
| [AstrBotDevs/AstrBot](https://github.com/AstrBotDevs/AstrBot) | 41,145 | Python | 46mo | 2,194 | **12** | 2 | 2 | 0 | 2 | 2 | 2 | 2 | 2 | AP |
| [HKUDS/LightRAG](https://github.com/HKUDS/LightRAG) | 39,898 | Python | 24mo | 5,699 | **12** | 2 | 2 | 0 | 3 | 1 | 2 | 2 | 2 | ACS |
| [continuedev/continue](https://github.com/continuedev/continue) | 36,052 | TypeScript | 40mo | 2,266 | **12** | 2 | 2 | 1 | 1 | 2 | 3 | 1 | 2 | S |
| [iOfficeAI/AionUi](https://github.com/iOfficeAI/AionUi) | 33,182 | TypeScript | 14mo | 5,297 | **12** | 2 | 3 | 1 | 2 | 1 | 0 | 2 | 3 | ACS |
| [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | 26,623 | Python | 82mo | 2,066 | **12** | 2 | 3 | 0 | 2 | 1 | 3 | 1 | 2 | AC |
| [comet-ml/opik](https://github.com/comet-ml/opik) | 22,271 | Python | 41mo | 4,287 | **12** | 2 | 2 | 0 | 2 | 2 | 3 | 1 | 2 | ADP |
| [OpenHands/OpenHands](https://github.com/OpenHands/OpenHands) | 89,363 | TypeScript | 30mo | 3,086 | **11** | 2 | 3 | 0 | 2 | 2 | 1 | 1 | 2 | AD |
| [openinterpreter/openinterpreter](https://github.com/openinterpreter/openinterpreter) | 68,462 | Rust | 38mo | 9,394 | **11** | 2 | 1 | 2 | 1 | 2 | 2 | 1 | 2 | A |
| [getzep/graphiti](https://github.com/getzep/graphiti) | 31,250 | Python | 26mo | 384 | **11** | 2 | 2 | 0 | 2 | 1 | 2 | 2 | 2 | AC |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | 20,233 | Python | 27mo | 2,379 | **11** | 2 | 3 | 0 | 3 | 0 | 2 | 1 | 2 | ACSD |

### reliability-exemplar (25)

| repo | stars | lang | age | c/12mo | sc | T | D1 | D2 | D3 | D4 | D5 | D6 | D7 | agent |
|---|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|
| [discourse/discourse](https://github.com/discourse/discourse) | 47,918 | Ruby | 164mo | 7,391 | **15** | 1 | 3 | 2 | 3 | 3 | 1 | 1 | 2 | ACDR |
| [nextcloud/server](https://github.com/nextcloud/server) | 36,945 | PHP | 124mo | 7,780 | **15** | 1 | 3 | 1 | 2 | 3 | 3 | 0 | 3 | AC |
| [pnpm/pnpm](https://github.com/pnpm/pnpm) | 36,686 | Rust | 128mo | 3,803 | **15** | 1 | 3 | 1 | 2 | 2 | 3 | 1 | 3 | ACD |
| [clash-verge-rev/clash-verge-rev](https://github.com/clash-verge-rev/clash-verge-rev) | 147,964 | Rust | 34mo | 1,679 | **14** | 2 | 2 | 2 | 2 | 3 | 2 | 1 | 2 | AC |
| [swc-project/swc](https://github.com/swc-project/swc) | 34,209 | Rust | 105mo | 1,046 | **14** | 2 | 2 | 2 | 3 | 0 | 2 | 2 | 3 | ACDM |
| [envoyproxy/envoy](https://github.com/envoyproxy/envoy) | 29,009 | C++ | 122mo | 3,612 | **14** | 2 | 3 | 0 | 2 | 2 | 3 | 1 | 3 | ADP |
| [mastodon/mastodon](https://github.com/mastodon/mastodon) | 50,336 | Ruby | 127mo | 2,842 | **13** | 2 | 3 | 1 | 0 | 3 | 2 | 2 | 2 | — |
| [jdx/mise](https://github.com/jdx/mise) | 34,365 | Rust | 45mo | 4,688 | **13** | 2 | 3 | 0 | 3 | 2 | 1 | 2 | 2 | ACSDR |
| [kestra-io/kestra](https://github.com/kestra-io/kestra) | 28,399 | Java | 85mo | 4,718 | **13** | 2 | 3 | 0 | 2 | 1 | 3 | 2 | 2 | AC |
| [oxc-project/oxc](https://github.com/oxc-project/oxc) | 22,904 | Rust | 44mo | 8,638 | **13** | 2 | 2 | 2 | 2 | 2 | 2 | 1 | 2 | ADP |
| [forem/forem](https://github.com/forem/forem) | 22,784 | Ruby | 118mo | 903 | **13** | 2 | 3 | 0 | 3 | 2 | 2 | 1 | 2 | ACPR |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp) | 129,757 | C++ | 43mo | 4,618 | **12** | 2 | 3 | 0 | 2 | 3 | 1 | 1 | 2 | AC |
| [tauri-apps/tauri](https://github.com/tauri-apps/tauri) | 111,451 | Rust | 86mo | 571 | **12** | 2 | 3 | 2 | 0 | 2 | 2 | 1 | 2 | — |
| [astral-sh/uv](https://github.com/astral-sh/uv) | 90,243 | Rust | 36mo | 3,085 | **12** | 2 | 3 | 0 | 1 | 2 | 2 | 2 | 2 | A |
| [appwrite/appwrite](https://github.com/appwrite/appwrite) | 57,497 | PHP | 90mo | 12,103 | **12** | 2 | 3 | 1 | 2 | 0 | 2 | 2 | 2 | AC |
| [ClickHouse/ClickHouse](https://github.com/ClickHouse/ClickHouse) | 50,123 | C++ | 124mo | 98,741 | **12** | 2 | 2 | 1 | 3 | 1 | 2 | 1 | 2 | ASDP |
| [astral-sh/ruff](https://github.com/astral-sh/ruff) | 49,820 | Rust | 50mo | 5,105 | **12** | 2 | 2 | 0 | 3 | 1 | 1 | 2 | 3 | ACSD |
| [valkey-io/valkey](https://github.com/valkey-io/valkey) | 27,318 | C | 30mo | 780 | **12** | 2 | 3 | 0 | 2 | 1 | 3 | 1 | 2 | AP |
| [biomejs/biome](https://github.com/biomejs/biome) | 25,871 | Rust | 38mo | 2,400 | **12** | 2 | 2 | 2 | 2 | 2 | 0 | 1 | 3 | ACS |
| [tursodatabase/turso](https://github.com/tursodatabase/turso) | 24,417 | Rust | 37mo | 11,014 | **12** | 2 | 3 | 2 | 3 | 0 | 0 | 2 | 2 | ACSD |
| [electron/electron](https://github.com/electron/electron) | 123,293 | C++ | 162mo | 1,612 | **11** | 2 | 2 | 0 | 2 | 2 | 2 | 1 | 2 | CSP |
| [coollabsio/coolify](https://github.com/coollabsio/coolify) | 62,339 | PHP | 68mo | 4,828 | **11** | 2 | 2 | 0 | 3 | 1 | 1 | 2 | 2 | ASDRM |
| [aaif-goose/goose](https://github.com/aaif-goose/goose) | 54,729 | Rust | 25mo | 3,412 | **11** | 2 | 1 | 1 | 2 | 0 | 2 | 2 | 3 | ACP |
| [grpc/grpc](https://github.com/grpc/grpc) | 45,348 | C++ | 142mo | 1,518 | **11** | 2 | 2 | 0 | 1 | 2 | 2 | 1 | 3 | A |
| [SeleniumHQ/selenium](https://github.com/SeleniumHQ/selenium) | 34,514 | Java | 164mo | 1,563 | **11** | 2 | 2 | 1 | 2 | 2 | 1 | 1 | 2 | ACP |

Agent-file legend: `A`=AGENTS.md `C`=CLAUDE.md `S`=.claude/skills|agents|commands|hooks `D`=.agents/ `P`=copilot-instructions `R`=cursor rules `M`=.mcp.json

## Known limitations of this screen

- **Directory probe, not full tree.** Enrichment reads ~20 targeted directories per repo via GraphQL, not the recursive tree. A signal file in an unprobed path is invisible. Absence in this table means *not found at the probed paths*, never *does not exist*.

- **A4 is a proxy.** Distinct authors among the last 100 commits, with a 2000-commits/yr escape hatch. Squash-merge and bot-heavy repos can still be undercounted.

- **CI detection is GitHub-Actions-biased.** Projects on other CI systems score lower on D1 than they deserve. This is why v3 removed CI from the hard gate.

- **Production adoption is inferred, never observed.** Part C uses 5 proxies. No repo in this corpus was verified to have real users; we verified it has the *artifacts* of a project that does.

- **Mobile is under-represented (11 of 30).** Mobile repos at 20k+ stars sustaining 250+ commits/year are scarce. Mobile findings draw on a correspondingly thinner base, and are supplemented by named below-gate repos recorded in the mobile findings document.

- **Scores measure presence of machinery, not quality of use.** A repo scoring 3 on D1 has many test signals; it does not follow that its tests are good. Tier-1 status licenses a deep read, it does not certify the practice.

