# 專案現況記錄

記錄時間:2026-08-09。這份文件是給人看的專案快照,不是自動產生的,之後有大改動記得回來更新或直接砍掉重寫,不要放到跟實際程式碼脫節。

## 已完成,而且真的驗證過(不是只有寫,有實際跑過確認)

### 核心 server
- FastMCP + streamable HTTP(stateless)+ python:3.13-slim + uv,單一 instance / docker compose 部署(不含 k8s manifest,見下方「刻意不做」)
- 兩個範例 tool:
  - `word_count`——純邏輯,不碰 I/O,示範 `errors.py` 統一錯誤格式
  - `fetch_json`——外部 HTTP 呼叫類 tool,示範 tenacity 重試(連線錯誤/5xx 重試、4xx 不重試),用本地 scripted HTTP server 真的測過「重試後成功」「重試耗盡回 recoverable=true」「4xx 不重試立即失敗」三種情境
- 統一錯誤格式(`errors.py`):`code`/`message`/`recoverable`/`details`,`test_contract.py` 強制每個 tool 都要示範一個會觸發它的案例
- 兩個範例 tool 都補上 MCP tool annotations(`readOnlyHint`/`destructiveHint`/`idempotentHint`/`openWorldHint`),對照 `mcp-builder` skill 的 best practices 抓出的落差。`docs/TOOL_GUIDELINES.md` 新增對應規範段落 + service 命名慣例、data-heavy tool 的 response format/pagination 指引、之後有真實資料時怎麼用 mcp-builder 的 Q&A 評估法——都是給未來加 tool 的人看的指引,不是現在就要做

### 容器化
- multi-stage Dockerfile、非 root user、`/health` + `/metrics` custom route
- 真的 `docker build` + `docker compose up`,在本機跟 GitHub Actions runner 上都各自重跑驗證過(auth 移除後不再需要 mock JWKS + `host.docker.internal` 那段)
- 過程中抓到一個真 bug:`ALLOWED_ORIGINS` 用 `list[str]` 型別會被 pydantic-settings 當 JSON 解析,空值直接讓 container 啟動失敗——已改成純字串 + `allowed_origins_list` property

### 測試分層
- `tests/server/`(MCP 本身正不正常):test_contract、test_functional(6 種 assert_type:exact_match/contains/regex_match/numeric_tolerance/llm_judge/custom)、test_fetch_json_tool、test_observability、test_container_smoke
- `test_contract.py` 的四項通用檢查(schema 合法性/description 長度/param description/CONTRACT_INVALID_CASE 宣告)抽出共用邏輯到 `contract_checks.py`,`test_contract_self_check.py` 故意弄壞 4 種情境,真的確認這些檢查抓得到違規(mutation-testing 精神,不是只驗證過「正常情況會過」)
- `tests/agent/`(agent 能不能正常用),三支檔案對應 `docs/TESTING.md` 的 layer 1/2/3,**全部真的跑過驗證,不是只有寫**:
  - `test_tool_selection.py`(**改名自 `test_agent_e2e.py`**——它測的是單發 function-calling 選 tool,不是真的多輪 e2e)。**已改成 provider-agnostic**,吃 `LLM_JUDGE_*`(不再寫死 Anthropic,`anthropic` 套件也整個移除),用 deepeval `ToolCorrectnessMetric`(不傳 `available_tools=`,決定性 set 比對)打分。真的用本地 scripted OpenAI-compatible server + 真的 NVIDIA NIM(`meta/llama-3.1-8b-instruct`)key 跑過 `pytest -m slow`,兩個 scenario 全過
  - `test_tool_selection_quality.py`(新增,layer 2)——同一個 metric,**傳 `available_tools=`**,這才真的觸發 LLM judge 打分(「這是不是所有可選項裡最好的選擇」,不只是「有沒有出現」)。**真的用 NIM key 跑過一次 `pytest -m slow`,PASSED**——deepeval 的 judge 真的被呼叫,不是掛著沒用的裝飾。目前是 template:這 repo 兩個 tool 語意差太多,judge 的額外判斷力還用不上,等加了功能重疊的 tool 才有意義
  - `test_agent_e2e_multiturn.py`(新增,layer 3,**真正的多輪 e2e**)——`claude-agent-sdk`(新依賴群組 `agent-sdk`)驅動這個 repo 真正的 MCP server,走真的 HTTP(不是其他測試用的 in-memory `fastmcp.Client`,因為 `claude` CLI 是真的 OS subprocess,要連真的 TCP port)。**真的裝了 `claude-agent-sdk` + 用這台機器上已登入的 Claude Code CLI 跑過 `pytest -m slow`,PASSED**:兩輪對話,第二輪的正確性依賴第一輪的 context 有沒有留住,兩輪都正確呼叫 `mcp__my-mcp-template__word_count`、兩輪答案都對。過程中抓到一個真的命名 bug——MCP tool 在 Claude Agent SDK 裡的實際名稱是 `mcp__<server>__<tool>` 前綴過的,不是裸名稱,一開始斷言寫錯,靠實測抓到修正
  - CI 的 `--all-groups` 改成 `--all-groups --no-group agent-sdk`——CI runner 沒裝 `claude` CLI,這條測試在 CI 永遠只會 skip,裝那個 ~80MB 套件純浪費頻寬
- fast/slow marker 分兩個 CI job,fast 完全不碰網路/docker,slow 才跑

### CI(GitHub Actions,public repo,已跑綠 4 次以上)
- fast job:ruff(含 `S` bandit ruleset)、pip-audit、pytest fast、docker build、Trivy image scan(report-only,SARIF 傳到 Security tab)
- slow job:llm_judge、container smoke(真的 docker compose up,在 CI runner 上也驗證過)、tool selection——三條都吃 `LLM_JUDGE_*` secrets,**CI repo secrets 還沒設,目前仍是 skip 狀態**(本機 `.env` 已設定且真的跑過,見上)
- 實測發現 base image(`python:3.13-slim`)目前有 ~23 個上游未修的 CRITICAL/HIGH CVE,所以 Trivy 設計成不擋 build
- `.github/dependabot.yml`:pip/github-actions/docker 三個 ecosystem 週更;repo 的 vulnerability alerts 也已經開啟(`gh api -X PUT repos/.../vulnerability-alerts`確認過)。**不含** pre-commit hook rev(`ruff-pre-commit` 等)——Dependabot 沒有 pre-commit ecosystem,這塊還是要人工或另外裝 Renovate

### Observability
- **Langfuse tracing(經 OpenTelemetry)**:FastMCP 原生的 `fastmcp.server.telemetry` span,指到 Langfuse 的 OTLP endpoint。**用真的 Langfuse 帳號驗證過**有正確送達。原本還有自己的 `TenantTracingMiddleware` 補 `tenant_id`,auth 整層拿掉後這個 middleware 也跟著刪了(見下方「刻意不做」)
- **Prometheus `/metrics`**:`mcp_tool_calls_total`(counter)+ `mcp_tool_call_duration_seconds`(histogram),永遠開著、零外部依賴,真的在本機 server 跟 docker container 裡都驗證過有正確記錄
- 兩層都設計成「掛掉不會弄壞真正的 tool call」(try/except 包住,log warning 不 raise)

### 開發流程
- pre-commit hooks(ruff、gitleaks、`uv lock --check`、基本檔案衛生),已裝 git hook 且真的在一次 commit 上跑過
- git repo 已 push 到 `github.com/Comet0322/MCP`(public),6 個 commit,CI 全綠
- `LICENSE`(MIT)、`CONTRIBUTING.md` 已補

## 已經寫了,但沒有充分驗證

- **golden case 覆蓋**:只有 6 條,全部是 `word_count` 的,`fetch_json` 沒有 golden case(它的正確性是靠 test_fetch_json_tool.py 的專屬測試蓋的,不是走 golden case 機制)
- **CI 裡的 slow job**:本機用 `.env` 真的驗證過 llm_judge/container smoke/tool selection 三條都會過,但 CI repo secrets(`LLM_JUDGE_*`)還沒設,CI 自己還沒真的跑過這條路——本機驗證 ≠ CI 環境驗證

## 刻意不做的範圍(設計決策,不是漏掉)

- **Auth 整層(2026-08-09 拿掉)**:原本有 `JWTVerifier` + claim-based 多租戶(`auth.py`、`AUTH_ENABLED`/`OIDC_ISSUER`/`JWKS_URL`/`AUDIENCE`/`TENANT_CLAIM_NAME`、自簽 JWKS mock server、`test_auth.py`),**整個移除**,改成「template 完全不管 auth,使用者自己接」——理由:每個組織的 IdP/tenant claim 格式都不一樣,內建一套會變成「先拆掉再重接」而不是省事。`docs/DEPLOYMENT.md` 新增「Adding auth, if you need it」段落,指向 FastMCP 原生的 `JWTVerifier`/`OAuthProxy`,教怎麼自己接回去,不是完全沒文件。連帶影響:`get_current_identity()`/`Identity`、`TenantTracingMiddleware`(tenant_id tagging)、兩個範例 tool 的 `requested_by` 欄位、golden case 裡驗 `requested_by` 的 2 條、container smoke 的 mock JWKS + `host.docker.internal` + `test_call_without_token_is_rejected` 都一起清掉。**這是覆蓋掉之前「刻意不做互動 OAuth 登入導向」那條決定的更大範圍版本**——原本只是不做 `OAuthProxy`,現在連 resource-server-only 的 `JWTVerifier` 也不做了
- **k8s manifest**:單一 instance + docker compose 是目前唯一部署方式,grill 過的決定
- **Rate limiting**:留給 reverse proxy 層,不進 template 程式碼
- **File-operation tool 範例**:`example_tool.py` 刻意選純邏輯,不示範真的檔案讀寫(volume mount 是條件項,只有真的加檔案 tool 才要設)

## 對一個「模板」來說,可能還缺的東西

- **CHANGELOG / 版本號機制**:`pyproject.toml` 裡 `version = "0.1.0"` 但沒有實際的 release/tag 流程
- **DB 查詢類 tool 範例**:原始需求提過「不限 RAG,也包含 DB 查詢」,但目前兩個範例 tool(純邏輯 + 外部 HTTP)都沒有實際示範 DB 查詢這個 class,連線池/交易/SQL injection 防護這些慣例完全沒被驗證過
- **`ruff-pre-commit` 版本同步**:討論過,決定維持現狀(mirror repo + 釘死 `rev` 是主流做法,ruff 官方自己也推薦,不是設計缺陷)。真正缺的是讓 rev 保持新鮮的自動化——`pre-commit autoupdate` 排程 CI 或裝 Renovate——目前故意先不做
- **本地開發除錯用的 `ConsoleSpanExporter`**:討論過,決定先不做——現在沒有 Langfuse key 的情況下完全看不到任何 trace,對本機開發除錯不方便,但優先度排在後面
- **CD / 部署自動化**:CI 只做到 build + test + scan,沒有 push image 到任何 registry、沒有實際部署到任何環境的步驟
