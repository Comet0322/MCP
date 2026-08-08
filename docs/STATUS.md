# 專案現況記錄

記錄時間:2026-08-09。這份文件是給人看的專案快照,不是自動產生的,之後有大改動記得回來更新或直接砍掉重寫,不要放到跟實際程式碼脫節。

## 已完成,而且真的驗證過(不是只有寫,有實際跑過確認)

### 核心 server
- FastMCP + streamable HTTP(stateless)+ python:3.13-slim + uv,單一 instance / docker compose 部署(不含 k8s manifest,見下方「刻意不做」)
- 兩個範例 tool:
  - `word_count`——純邏輯,不碰 I/O,示範 `errors.py` 統一錯誤格式與 `get_current_identity()` 用法
  - `fetch_json`——外部 HTTP 呼叫類 tool,示範 tenacity 重試(連線錯誤/5xx 重試、4xx 不重試),用本地 scripted HTTP server 真的測過「重試後成功」「重試耗盡回 recoverable=true」「4xx 不重試立即失敗」三種情境
- 統一錯誤格式(`errors.py`):`code`/`message`/`recoverable`/`details`,`test_contract.py` 強制每個 tool 都要示範一個會觸發它的案例

### 認證(SSO / OIDC resource server,multi-tenant)
- `JWTVerifier` + `TENANT_CLAIM_NAME`(claim-based 多租戶),`AUTH_ENABLED`/`ENV=prod` 缺設定會 fail-fast
- 自簽 JWKS mock server(`tests/server/auth/mock_jwks.py`),真的簽過 JWT、真的過 `JWTVerifier` 驗證(不是 mock 掉驗證邏輯本身)
- 刻意不做互動登入導向(`OAuthProxy`)——見下方「刻意不做」

### 容器化
- multi-stage Dockerfile、非 root user、`/health` + `/metrics` custom route
- 真的 `docker build` + `docker compose up` + 真的透過 `host.docker.internal` 打 mock JWKS 驗證 auth,在本機跟 GitHub Actions runner 上都各自重跑驗證過
- 過程中抓到一個真 bug:`ALLOWED_ORIGINS` 用 `list[str]` 型別會被 pydantic-settings 當 JSON 解析,空值直接讓 container 啟動失敗——已改成純字串 + `allowed_origins_list` property

### 測試分層
- `tests/server/`(MCP 本身正不正常):test_contract、test_functional(6 種 assert_type:exact_match/contains/regex_match/numeric_tolerance/llm_judge/custom)、test_auth、test_fetch_json_tool、test_observability、test_container_smoke
- `tests/agent/`(agent 能不能正常用):test_agent_e2e——**寫好了、能 skip、但從沒真的打過 Anthropic API**(見下方「未充分驗證」)
- fast/slow marker 分兩個 CI job,fast 完全不碰網路/docker,slow 才跑

### CI(GitHub Actions,public repo,已跑綠 4 次以上)
- fast job:ruff(含 `S` bandit ruleset)、pip-audit、pytest fast、docker build、Trivy image scan(report-only,SARIF 傳到 Security tab)
- slow job:llm_judge(沒設 key 會 skip)、container smoke(真的 docker compose up,在 CI runner 上也驗證過)、agent e2e(沒設 key 會 skip)
- 實測發現 base image(`python:3.13-slim`)目前有 ~23 個上游未修的 CRITICAL/HIGH CVE,所以 Trivy 設計成不擋 build

### Observability
- **Langfuse tracing(經 OpenTelemetry)**:FastMCP 原生的 `fastmcp.server.telemetry` span + 我們自己的 `TenantTracingMiddleware`(補 `tenant_id`,跟 FastMCP 原生 span 並列不是巢狀,因為 middleware 摸不到 FastMCP 自己那個 span 的 context)。**用真的 Langfuse 帳號驗證過**,兩層 span 都有正確送達
- **Prometheus `/metrics`**:`mcp_tool_calls_total`(counter)+ `mcp_tool_call_duration_seconds`(histogram),永遠開著、零外部依賴,真的在本機 server 跟 docker container 裡都驗證過有正確記錄
- 兩層都設計成「掛掉不會弄壞真正的 tool call」(try/except 包住,log warning 不 raise)

### 開發流程
- pre-commit hooks(ruff、gitleaks、`uv lock --check`、基本檔案衛生),已裝 git hook 且真的在一次 commit 上跑過
- git repo 已 push 到 `github.com/Comet0322/MCP`(public),6 個 commit,CI 全綠

## 已經寫了,但沒有充分驗證

- **`tests/agent/test_agent_e2e.py`**:語法對、能正確 skip,但從沒有在有 `ANTHROPIC_API_KEY` 的情況下真的跑過一次——「Claude 選不選得對 tool」這件事目前是純設計,沒有實測數據
- **`llm_judge` golden case**:手動測過可以接 NVIDIA NIM(`meta/llama-3.1-8b-instruct` 驗證有效),但那是臨時用 shell env var 測的,`.env`/CI secrets 都沒有正式設定,CI 裡這條目前還是 skip 狀態
- **golden case 覆蓋**:只有 6 條,全部是 `word_count` 的,`fetch_json` 沒有 golden case(它的正確性是靠 test_fetch_json_tool.py 的專屬測試蓋的,不是走 golden case 機制)

## 刻意不做的範圍(設計決策,不是漏掉)

- **k8s manifest**:單一 instance + docker compose 是目前唯一部署方式,grill 過的決定
- **互動 OAuth 登入導向(`OAuthProxy`)**:template 只做 resource server,token 怎麼發是外部 SSO 機制的事
- **Rate limiting**:留給 reverse proxy 層,不進 template 程式碼
- **File-operation tool 範例**:`example_tool.py` 刻意選純邏輯,不示範真的檔案讀寫(volume mount 是條件項,只有真的加檔案 tool 才要設)

## 對一個「模板」來說,可能還缺的東西

- **LICENSE 檔案**:目前沒有,別人要 fork/引用這個 template,沒有授權條款
- **CONTRIBUTING.md**:沒有,如果預期會有其他人貢獻這個 template 本身,值得補
- **CHANGELOG / 版本號機制**:`pyproject.toml` 裡 `version = "0.1.0"` 但沒有實際的 release/tag 流程
- **Dependabot alerts**:GitHub 這個 repo 目前是關閉的(免費功能,`gh api` 查證過),沒有自動化的依賴漏洞提醒/PR
- **DB 查詢類 tool 範例**:原始需求提過「不限 RAG,也包含 DB 查詢」,但目前兩個範例 tool(純邏輯 + 外部 HTTP)都沒有實際示範 DB 查詢這個 class,連線池/交易/SQL injection 防護這些慣例完全沒被驗證過
- **`ruff-pre-commit` 版本同步**:pre-commit 用的 ruff 是獨立環境、獨立版號釘住的,跟專案 `uv.lock` 管的 ruff 不會自動同步,長期會 drift,需要人工維護或另外接 Renovate/Dependabot 幫忙開 PR
- **本地開發除錯用的 `ConsoleSpanExporter`**:討論過,還沒實作——現在沒有 Langfuse key 的情況下完全看不到任何 trace,對本機開發除錯不方便
- **反向測試(mutation-testing 精神)**:`test_contract.py` 的四項通用檢查從沒故意弄壞一個 tool 去確認測試真的抓得到違規,只驗證過「正常情況會過」
- **CD / 部署自動化**:CI 只做到 build + test + scan,沒有 push image 到任何 registry、沒有實際部署到任何環境的步驟
