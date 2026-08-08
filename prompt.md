請幫我建立一個 FastMCP 泛用型 template repo,目標是讓任何基於 FastMCP 開發的 MCP server(不限於 RAG,也包含 DB 查詢、檔案操作等工具)都能套用同一套結構與測試骨架。Client 端主要是 CLI coding agent(如 Claude Code),不是一般聊天介面,所以工具描述品質、錯誤訊息可讀性、容器化部署是重點。

不使用 cookiecutter,repo 本身就是可直接 fork / 用 GitHub「Use this template」的具體專案,不含樣板變數。新專案改名時用一般 find-replace(套件名 `src.main.python` 這種路徑字串)。

## 技術棧
- Python 專案管理用 uv
- 框架:fastmcp(最新版)
- Transport:streamable HTTP,**stateless**(`stateless_http=True`,不保留 session 狀態)。部署現階段就是**單一 instance,docker compose 是唯一部署方式**,不寫 k8s manifest;stateless 純粹是「以後真要多副本不用改 auth/session 邏輯」的保險,不是現在的需求
- 容器:Docker(python:3.13-slim 為基底)+ docker compose,設定從 `.env` 讀取
- 測試:pytest + pytest-asyncio(asyncio_mode = auto)+ inline-snapshot
- lint/format:ruff
- 設定管理:pydantic-settings
- log:structlog(container 內固定輸出 JSON 到 stdout,不寫檔),欄位用 structlog 預設命名(`timestamp`/`level`/`event`/`logger`),不遷就特定 log aggregator(Datadog/ELK/ECS)的 schema,通用優先
- 外部呼叫重試:tenacity
- 檢索/生成評測(可選層,faithfulness 層用):**deepeval**(不用 ragas)。理由:template 定位不限 RAG,ragas 的 metric 設計綁死 question/context/answer 三元組,非 RAG tool 用不上;deepeval 有一樣的 faithfulness metric,還多 tool correctness/自訂 G-Eval,跟現有 pytest + pytest-asyncio 骨架原生整合,不用寫 glue code
- LLM judge(golden case 的 `llm_judge` assert_type 用):**openai SDK**(不是 anthropic SDK),指到可設定的 `LLM_JUDGE_BASE_URL`,支援任何 OpenAI-compatible provider(OpenAI/NVIDIA NIM/DeepSeek/Together/本地 vLLM 皆可,實測過 NVIDIA NIM + deepseek-v4-flash 可行)。理由:機械式語意等價判斷不需要 Anthropic 專屬功能,做成 BYO provider 比綁死單一 vendor 泛用。沒有通用預設 model/base_url,未設定時該 case 用 pytest.skip 帶清楚原因跳過,不是 fail。temperature=0,不做多數決重跑。test_agent_e2e.py 維持綁死 anthropic SDK + Sonnet,不動——那層測的是「Claude Code 用的模型選不選得對 tool」,泛用化會失去意義

## 目錄結構
建立以下結構:

```
my-mcp-template/
├── src/main/python/
│   ├── __init__.py
│   ├── main.py              # FastMCP() 實例(stateless_http=True)、lifespan management、streamable-http 啟動
│   ├── tools/
│   │   ├── __init__.py      # 自動掃描/註冊本目錄下所有 tool
│   │   └── example_tool.py  # 範例 tool,純邏輯/不碰 I/O(不示範檔案讀寫),含完整 docstring + 錯誤處理示範(用參數驗證失敗觸發 ToolError)+ 示範一次 get_current_identity() 用法
│   ├── config.py            # pydantic-settings:HOST/PORT/ENV(dev|prod)/LOG_LEVEL/AUTH_ENABLED/OIDC_ISSUER/JWKS_URL/AUDIENCE/TENANT_CLAIM_NAME/ALLOWED_ORIGINS 等,集中管理環境變數
│   ├── auth.py               # 認證邏輯:FastMCP JWTVerifier(jwks_uri/issuer/audience)設定、AUTH_ENABLED=false 時 no-op passthrough;提供 helper 從 get_access_token() 的 token_claims 抽 tenant/user id
│   └── errors.py            # 統一錯誤格式,包含 recoverable: bool 欄位,讓 agent 判斷該不該重試
├── tests/
│   ├── conftest.py          # FastMCP in-memory Client fixture(直接對 mcp 實例連線,不經 HTTP/容器,transport 對測試透明)
│   ├── golden/
│   │   ├── schema.py        # pydantic model 定義 GoldenCase(tool_name, input, assert_type: exact_match|contains|regex_match|numeric_tolerance|llm_judge|custom, expected, tolerance(numeric_tolerance 用), custom_assertion path)
│   │   └── example.yaml     # 範例 golden case
│   ├── server/               # 分組一:MCP 本身是否運作正常(誰呼叫都一樣要對,跟是不是 agent 呼叫無關)
│   │   ├── test_contract.py     # schema 合法性、description 長度/非空、每個參數有 description、非法輸入回統一錯誤格式(偏 unit)——
│   │   │                         #   (a) schema 合法性
│   │   │                         #   (b) description 長度 >= 20 字元且非空
│   │   │                         #   (c) 每個參數都有 description
│   │   │                         #   (d) 非法輸入時回傳統一錯誤格式,不是 unhandled traceback
│   │   ├── test_functional.py   # 讀 golden/*.yaml,依 assert_type 分派驗證邏輯(exact_match/contains/regex_match/numeric_tolerance 用一般 assert,偏 unit;llm_judge 用 openai SDK(BYO base_url)呼叫 judge prompt,未設定 LLM_JUDGE_BASE_URL/MODEL 時 pytest.skip,偏 integration,標 slow;custom 用 importlib 動態載入使用者提供的驗證函式)
│   │   ├── auth/
│   │   │   └── mock_jwks.py     # 測試用:動態生 RSA keypair、起輕量 HTTP server 吐 JWKS、簽帶自訂 claims 的測試 JWT。給 test_auth.py 與 test_container_smoke.py 共用,不依賴真的外部 IdP
│   │   ├── test_auth.py         # unit test auth.py 的 JWTVerifier 設定與 claim 抽取邏輯,用 mock_jwks 簽的 token 直接測,不牽 docker
│   │   └── test_container_smoke.py  # marker: slow。實際 docker compose up 後,用 fastmcp Client 以 streamable-http 連線打進容器,確認 list_tools / 呼叫一次 example_tool 都正常;AUTH_ENABLED=true 情境下不帶 token 要回 401(統一錯誤格式),帶 mock_jwks 簽的合法 token 要能通過。真正的 integration/system test(真 docker、真 HTTP、真 auth),只驗整合面,不重複測 auth 邏輯細節
│   └── agent/                # 分組二:agent 能否正常使用(測 tool description 品質,對應「工具描述品質是重點」這個定位)
│       └── test_agent_e2e.py    # marker: slow。定義 AGENT_SCENARIOS 清單(prompt, expect_tool_called, expect_not_called),用 anthropic SDK(模型:Sonnet,跟實際 Claude Code 用戶端代表性一致)把 tool list 轉成 tool_use 格式丟給 Claude,檢查是否選對工具、沒有誤觸不該用的工具;temperature=0,不做多數決重跑
├── docs/
│   ├── TOOL_GUIDELINES.md   # 寫清楚:tool description 怎麼寫才利於 agent 自動發現與正確呼叫、錯誤訊息要包含哪些資訊讓 agent 能自我修正重試、參數命名慣例
│   └── DEPLOYMENT.md         # production 部署指南:怎麼接公司既有 SSO/OIDC provider(OIDC_ISSUER/JWKS_URL/AUDIENCE/TENANT_CLAIM_NAME 怎麼填)、client 端 token 怎麼取得與帶入、CORS 何時該開、reverse proxy(TLS/rate limit)建議
├── Dockerfile                # multi-stage:builder(uv sync 產生 .venv)+ runtime(python:3.13-slim,非 root user,只複製 .venv 與 src)
├── entrypoint.sh              # exec python -m src.main.python.main,確保 PID 1 正確接收 SIGTERM
├── docker-compose.yml         # 單一 service,env_file: .env,port mapping 用 ${MCP_PORT:-8000},healthcheck 打 FastMCP custom_route("/health")
├── .env.example                # HOST/PORT/ENV/ANTHROPIC_API_KEY/OIDC_ISSUER/JWKS_URL/AUDIENCE/TENANT_CLAIM_NAME/LLM_JUDGE_BASE_URL/LLM_JUDGE_API_KEY/LLM_JUDGE_MODEL 等變數範例,真正 .env 不進版控
├── .dockerignore               # 排除 .venv/.git/tests/__pycache__,避免污染 build context
├── .github/workflows/ci.yml   # 用 pytest marker 分兩個 job,跟 tests/server 與 tests/agent 這個分組垂直、互不干擾:
│                              #   fast job(每個 PR):pytest -m "not slow" → tests/server 裡不用呼叫外部 LLM/docker 的部分(test_contract.py、test_functional.py 的 exact_match/contains/regex_match/numeric_tolerance/custom 案例、test_auth.py)+ docker build 驗證(build 成功即可,不跑 container)
│                              #   slow job(merge 到 main 才跑):pytest -m slow → test_functional.py 的 llm_judge 案例、tests/server/test_container_smoke.py(docker compose up 跑)、tests/agent/test_agent_e2e.py(呼叫 LLM API)
└── pyproject.toml
```

## 容器化細節(補充規格)
- `main.py` 內:`FastMCP(name=..., stateless_http=True)`,啟動用 `mcp.run(transport="streamable-http", host=settings.host, port=settings.port)`
- `config.py` 新增:`HOST`(預設 `0.0.0.0`)、`PORT`(預設 `8000`)、`ENV`(`dev`/`prod`,控制 structlog 用 console renderer 還是 JSON renderer)
- Dockerfile 用 multi-stage:builder stage 裝 uv、`uv sync --frozen` 產生 `.venv`;runtime stage 只複製 `.venv` 與 `src`,建立非 root user 執行,`EXPOSE 8000`
- healthcheck 不要打 MCP protocol endpoint 本身(POST-only、需特定 header),額外用 FastMCP 的 `@mcp.custom_route("/health")` 開一個純 GET 200 的 route 給 docker/compose healthcheck 用。單一 instance 部署,只需要這一支,不拆 liveness/readiness(那是 k8s 概念,現在不用)
- example_tool.py 本身不碰檔案(純邏輯範例),docker-compose.yml 沒有預設 volume mount。若日後使用者自己加了真的檔案操作 tool,才需要在 docker-compose.yml 補 `volumes:` 對應 host 路徑——這段先留一行註解說明,不是現在的阻塞項
- README 裡 client 連線範例要改成 streamable-http 的寫法(URL,不是 `command` + spawn 子行程),包含 Claude Code mcp config 範例

## 認證與多租戶策略(production)

streamable HTTP 是網路可及的服務,不像 stdio 天生受 process 邊界保護,預設就要假設它會被暴露在網路上,因此認證不是選配項,是預設行為。部署情境確定是 **multi-tenant:單一組織、多個使用者、共用一個企業 SSO/IdP**,整套認證設計以此為準。

### 認證(Auth)— SSO / OIDC resource server
- 用 FastMCP 的 `JWTVerifier`(`fastmcp.server.auth.providers.jwt`),吃 `jwks_uri`/`issuer`/`audience` 三參數,對接使用者自己組織既有的 OIDC-compliant IdP(Okta/Azure AD/Google Workspace 皆可)。不手刻 middleware,不用 static token。
- **template 只做 resource server**:只驗「拿到的 token 合不合法」,不處理「使用者怎麼登入拿到 token」這段。這段假設由企業既有的 SSO CLI 工具(或其他機制)完成,產出的 token 讓 client 當 Bearer token 帶進來就好。不做 MCP OAuth metadata endpoint / `OAuthProxy` 那套互動登入導向流程——那是完整 OAuth client 等級的複雜度,對泛用 template 負擔太重,且 client 端(Claude Code)對任意企業 IdP 的支援程度是外部變數,控制不了。這點在 DEPLOYMENT.md 要明講是刻意的範圍界線,不是漏做。
- `config.py` 新增:`AUTH_ENABLED: bool`、`OIDC_ISSUER`、`JWKS_URL`、`AUDIENCE`、`TENANT_CLAIM_NAME`(告訴 auth.py 去 JWT 的哪個 claim 讀 tenant/user id,不同 IdP 命名不同,例如 Azure AD 用 `tid`,沒有通用預設值,必須讓使用者填)。`ENV=dev` 時 `AUTH_ENABLED=False`(本機/MCP Inspector 開發不擋),`ENV=prod` 時**強制**`AUTH_ENABLED=True`,若 `OIDC_ISSUER`/`JWKS_URL`/`AUDIENCE` 任一未設就要在啟動時直接 fail fast(不要靜默放行)。
- 未帶或帶錯 token 時回 401,包成 errors.py 的統一錯誤格式,`recoverable=False`。
- auth.py 提供一個 helper(例如 `get_current_identity()`),包裝 FastMCP 的 `get_access_token()`,從回傳的 `token_claims` 依 `TENANT_CLAIM_NAME` 抽出身份,回傳給 tool function 用。
- `.env.example` 的 `OIDC_ISSUER`/`JWKS_URL`/`AUDIENCE` 留空值,註解寫明:這三個要填你組織實際 IdP 的值,沒有通用預設。

### 資料隔離 — template 不管,tool 自己決定
- 同組織不同使用者之間,資料(檔案、DB 查詢範圍)要不要互相隔離,**template 不強制**。template 的責任只到「把驗證過的身份透過 `get_current_identity()` 傳給 tool」,要不要用這個身份做 scope 限制是每個 tool 的業務邏輯,template 裡的 example_tool 只示範「怎麼拿到身份」,不示範隔離規則。
- example_tool.py 裡示範一次 `get_current_identity()` 的用法,並在 docstring/comment 註明「這是拿身份的方式,實際要不要拿來做資料隔離看你的 tool 需求」。

### CORS
- 預設**不掛** CORSMiddleware。MCP client 主要是 CLI coding agent(Claude Code 這類),不是瀏覽器,大部分部署根本不需要 CORS。
- 若未來要接瀏覽器端 client(例如 web 版 inspector/dashboard),才在 config.py 加 `ALLOWED_ORIGINS`(逗號分隔的白名單),明確列出允許的 origin。禁止 `allow_origins=["*"]` 與 `allow_credentials=True` 同時開(這組合等於讓任何網站都能代表使用者打你的 server,是常見誤設)。
- 這段預設關閉、白名單開放的邏輯要寫進 auth.py 或另開 `middleware.py`,不要跟 tool 邏輯混在一起。

### 部署層建議(非 template 程式碼範圍,寫進 docs/DEPLOYMENT.md 當建議)
- 正式環境建議放在 reverse proxy(nginx/Traefik/Caddy)後面做 TLS termination,container 本身只認內網 plain HTTP,不用在 app 層處理憑證。
- Rate limiting 建議放 proxy 層處理,不進 template 程式碼範圍,DEPLOYMENT.md 提一句帶過即可。
- 若之後真的需要「MCP server 自己驅動互動登入導向」(client 沒有其他方式拿 token),升級路徑是接 FastMCP 的 `OAuthProxy`,DEPLOYMENT.md 提一句作未來擴充方向,不是現在做。

## 執行要求
1. 先建立最小可跑的骨架(main.py + 一個 example_tool),確認 `uv run python -m src.main.python.main` 能本機啟動、MCP Inspector 能用 streamable-http 連上(此階段 `AUTH_ENABLED=False`)
2. 依序完成 tests/server/test_contract.py、golden case schema(六種 assert_type)、tests/server/test_functional.py,每完成一支就跑一次 pytest 確認通過——這組是「MCP 本身是否運作正常」
3. errors.py 的統一錯誤格式要在 example_tool.py 裡實際示範用法(故意寫一個會觸發 ToolError 的邊界情況並測試它)
4. 寫 auth.py(JWTVerifier + `get_current_identity()`)+ tests/server/auth/mock_jwks.py + tests/server/test_auth.py,確認 fast layer 能在不接真 IdP 的情況下測完整個驗證邏輯
5. 寫 Dockerfile + entrypoint.sh + docker-compose.yml,`docker compose up` 後跑 tests/server/test_container_smoke.py 確認容器內服務可從外部連線呼叫,且 401/合法 token 兩種情境都對——「MCP 本身是否運作正常」這組到此收尾
6. 寫 tests/agent/test_agent_e2e.py,確認「agent 能否正常使用」這組獨立跑得過,驗的是 tool description 品質,不是功能正確性
7. TOOL_GUIDELINES.md 要包含 1-2 個「好的 tool description」和「不好的 tool description」對照範例
8. README.md 說明:如何當 GitHub template 使用(找哪些字串要重新命名)、如何跑 fast/slow 測試、tests/server 與 tests/agent 這兩組分別驗什麼、如何選擇是否啟用 faithfulness 層(deepeval)、如何 `docker compose up` 本機跑、Claude Code 端怎麼設定連到這個容器(含帶 SSO token 的方式)
9. 全部寫完後,列出一份檢查清單,確認每一組測試涵蓋到我要求的內容,並把未定案項目拆成三類:
   - **阻塞項(必須我自己填,沒填就該 fail fast,不給預設)**:golden case 實際內容、正式環境 `OIDC_ISSUER`/`JWKS_URL`/`AUDIENCE`/`TENANT_CLAIM_NAME` 實際值(prod 缺任一值啟動要直接失敗並報清楚錯誤,不同 IdP 的 claim 命名不同,沒有通用值)
   - **條件項(只有你真的加了對應功能才要填)**:file-tool 的 volume mount host 路徑(只有你自己加了真的檔案操作 tool 才需要)、`LLM_JUDGE_BASE_URL`/`LLM_JUDGE_API_KEY`/`LLM_JUDGE_MODEL`(只有 golden case 真的用到 `llm_judge` assert_type 才需要,沒設定該 case 用 pytest.skip 跳過不是 fail)
   - **已有合理預設可先跑,想調再調(code 裡用 `# TODO: tune per case` 之類 comment 標記)**:LLM judge 門檻值(先給 0.7)、`ALLOWED_ORIGINS`(先留空清單 = CORS 關閉,等真有瀏覽器 client 需求才填)、要不要從純 resource-server 升級到 `OAuthProxy` 互動登入導向(先不做,架構上不擋這條路)

先跟我確認你對這個結構的理解,尤其是 test_functional.py 的可插拔 assertion 設計、errors.py 的 recoverable 欄位怎麼串接、以及 stateless streamable-http 對 test_container_smoke.py 連線方式的影響,再開始動手。
