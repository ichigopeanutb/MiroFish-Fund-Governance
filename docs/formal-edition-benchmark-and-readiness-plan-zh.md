# MiroFish Fund Governance Edition 正式版前置研究與就緒計畫

研究日期：2026-07-11  
狀態：正式版分叉前的決策基準，不是已核准的法律、會計或投資規則

## 1. 結論先行

目前不應把 MVP 資料夾直接複製一份，然後在副本上繼續加功能。

正確做法是：

1. 將目前可運行的 alpha 凍結成一個可重現的 MVP 基線。
2. 保留原 Git 歷史，從該基線建立正式版開發分支。
3. 先定義正式版的資料契約、權限邊界、事件重播、財務精度與遷移策略。
4. 只有通過正式版基礎門檻後，才把 LP workspace、多輪基金生命週期及更複雜投資邏輯搬入正式版。

「複製資料夾」會同時複製 alpha 的單一 LP 假設、檔案式狀態、浮點數金額、beta 密碼機制與大檔案 API 結構，卻失去清楚的版本血緣。正式版需要的是受控升級，不是視覺上看起來像新產品的副本。

建議版本線：

```text
MiroFish upstream
  -> Fund Governance MVP / alpha baseline (freeze + tag)
      -> Fund Governance formal-v1 development branch
          -> private pilot release
              -> production candidate
```

建議未來建立的 tag 與分支名稱：

- MVP tag：`fund-governance-mvp-v0.1.0`
- 正式版開發分支：`fund-governance-formal-v1`
- 第一個正式私測版本：`v1.0.0-rc.1`

在完成本文件的 Phase 0 驗證前，不建立正式版 tag 或 branch。

## 2. 第一性原理：我們真正要解決什麼

基金運作不是「一群 agent 在對話」。它是多個當事人在合約、權限、時間與資金限制下，持續做出會改變權利義務與經濟結果的決策。

一個可被信任的基金治理模擬世界，最小真實單位是：

```text
對象 + 權利/義務 + 事件 + 權限依據 + 經核准的狀態變更 + 金流/帳務 + 證據 + 時間
```

因此正式版必須永久分開三種真相：

- `Facts`：文件、使用者輸入、已發生事件與外部系統匯入的事實。
- `Proposals`：LLM、情境分支或人員提出的建議、假設與候選決策。
- `Committed simulation state`：通過規則、權限與人工審批後，在特定情境分支中生效的模擬狀態。

LLM 可以解釋、提出選項與發現風險，但不得直接更改 ledger、承諾額、投票結果或正式審批紀錄。這條規則應從 alpha 的設計原則提升為正式版不可繞過的架構限制。

## 3. 產品定位：三種系統，不要混為一談

| 類型 | 真實世界用途 | 代表 benchmark | 我們的關係 |
|---|---|---|---|
| System of Record | 實際記帳、投資人帳戶、capital call、distribution、報表與文件交付 | Carta、Allvue、Juniper Square | 不在 v1 取代；以匯入、匯出與 reconciliation 對接 |
| System of Control | 實際流程、權限、審批、決議、稽核與例外處理 | Camunda、Diligent、policy engine | 借用其狀態、角色、審批與 audit 思維 |
| System of Rehearsal | 在真實決議與資金移動前，比較情境、驗證規則、觀察後果 | AnyLogic、數位分身、MiroFish | 這是 Fund Governance Edition 的核心產品位置 |

正式版的差異化不是「另一套基金會計軟體」，而是：

> 在資金真的進出、條款真的生效、IC / LPAC 真的表決以前，先把可能的路徑、治理風險、資金缺口與證據完整演練一遍。

這個定位也讓我們可以服務非技術基金經理人：使用者提供匿名化條款與商務假設，系統生成可審核的情境、決策包與資金路徑，而不是要求對方操作 GitHub 或成為系統工程師。

## 4. 真實基金商務生命週期

正式版的 world model 至少要能表達以下生命週期，而不是只跑一段固定 12 個月劇本：

```text
LP relationship / fundraising pipeline
-> diligence and terms negotiation
-> subscription / onboarding readiness
-> closing and commitment
-> capital call and collection
-> IC authorization and investment execution
-> portfolio monitoring / NAV / reserve planning
-> LPAC / conflict / waiver / exception governance
-> follow-on / bridge / down round / write-off
-> exit / partial exit / distribution / waterfall
-> quarterly reporting / audit / clawback / wind-down
```

其中 MiroFish v1 應直接擁有：

- 情境與條款 workspace。
- LP 接觸、承諾與資金準備狀態的模擬。
- IC / LPAC governance workflow 的演練與人工核准。
- 多輪 capital call、reserve、NAV、exit、distribution 的模擬。
- 每個結果回到來源條款、輸入與決策紀錄的 evidence graph。
- 對實際基金管理、會計與投資人系統的標準化匯出及對帳。

v1 不應直接擁有：

- 真實銀行付款與保管。
- 正式總帳或法定會計帳冊。
- KYC / AML 最終判定。
- 電子簽章的法律效力。
- 自動法律、稅務或投資建議。

這些能力應由具備相應責任與控制的外部服務完成；正式版只保存必要的狀態、引用與 reconciliation 結果。

## 5. Benchmark 調查結果

### 5.1 基金營運與 LP 體驗

Carta 將 capital call 描述為從金額與參與人計算、通知 LP、追蹤付款，到 funded call 自動入帳的端到端流程，並強調需符合 LPA 條款。這表示正式版的 capital call 模擬不能只是一筆數字，而要有 notice、due date、participant allocation、payment status、LPA check 與 posting boundary。  
來源：[Carta Capital Calls](https://carta.com/explore-erp/private-equity/capital-calls/)

Allvue 將 fundraising、deal management、portfolio monitoring、investor relations 與 accounting 放在共用資料模型中，避免重複輸入與 reconciliation 斷裂。這支持我們在正式版建立單一 object model，但也提醒我們不要在 v1 重做完整 back office。  
來源：[Allvue Private Equity Platform](https://www.allvuesystems.com/industries/private-equity/)

Juniper Square 的公開材料把 CRM、data room、onboarding、investor portal 與 fund administration 視為連續的 GP-LP 運作。對本產品而言，LP relationship 與 commitment readiness 應是模擬的前段輸入，不應直到 capital call 才第一次出現 LP。  
來源：[Juniper Square private-markets operating stack](https://assets.junipersquare.com/files/Building-the-tech-stack-for-the-now-generation-of-LPs-infographic.pdf?v=1768242123)

### 5.2 產業標準與治理

ILPA 2025 Capital Call & Distribution Template 將資料分成 fund-level、LP-level、transactions 與 supplemental calculations，並包含 unfunded commitment reconciliation、management fee、waterfall/carry 與 clawback 問題。正式版資料模型與報告 schema 應可映射這些欄位，但不能把 ILPA template 當作法律正確性的證明。  
來源：[ILPA Capital Call & Distribution Template](https://ilpa.org/industry-guidance/templates-standards-model-documents/ilpa-templates-hub/ilpa-capital-call-distribution-template/)

ILPA Principles 3.0 與 Model LPA 顯示 LPAC 的核心不是一個 `approved=true` 欄位，而是 authority、conflict、meeting materials、voting、waiver、adviser access 與 audit access 的組合。正式版 governance workflow 必須保存「誰以什麼身分、依據哪一版本條款、對哪一版本 packet 做了什麼決定」。  
來源：[ILPA Principles](https://ilpa.org/industry-guidance/principles-best-practices/ilpa-principles/)、[ILPA Model LPA](https://ilpa.org/industry-guidance/templates-standards-model-documents/model-limited-partnership-agreement/)

台灣《有限合夥法》區分普通合夥人與有限合夥人的責任及經營角色，且特定業務仍可能受目的事業主管機關規範。正式版不應把 Delaware 或任何單一 LPA 模型寫死；應採 `jurisdiction profile + fund-specific governing documents`。  
來源：[經濟部有限合夥法](https://law.moea.gov.tw/LawContent.aspx?id=FL077268)

### 5.3 流程、規則與耐久執行

Camunda 的 BPMN / DMN 思路將可預期的流程與決策規則明確化，並把 AI 放在有狀態、可稽核、可升級與可人工接管的流程內。正式版可以先保留 Python domain rules，但需要版本化的 workflow / decision contract；之後再評估是否匯出 BPMN / DMN，而不是立即導入完整平台。  
來源：[Camunda agentic orchestration guardrails](https://camunda.com/blog/2026/01/guardrails-and-best-practices-for-agentic-orchestration/)

Temporal 的 durable execution 可讓長時間流程在服務中斷後從既有狀態恢復。這是 hosted 正式版的重要 benchmark，但不是 Phase 0 就必須加入的 dependency；應先把 event replay、idempotency 與 transaction boundary 做正確，再決定使用 Temporal 或較輕的 job runtime。  
來源：[Temporal documentation](https://docs.temporal.io/)

Open Policy Agent 展示了 policy decision 與 enforcement 分離、policy bundle 版本及 decision log 的做法。正式版的 LPA / governance rule 也應有 `rule_version`、`decision_id`、input、result 與 masked audit payload；v1 可先做內部 domain policy interface，不必立刻採用 Rego。  
來源：[Open Policy Agent](https://www.openpolicyagent.org/docs)、[OPA Decision Logs](https://www.openpolicyagent.org/docs/management-decision-logs)

### 5.4 物件中心與模擬

Celonis 的 object-centric model 以 objects、events、relationships 與 perspectives 表達一個事件同時影響多個商務物件。基金世界中的 capital call 同時牽涉 fund、LP、notice、commitment、bank status 與 ledger projection，因此正式版應延續 OCEL-style 核心，而不是回到單一 case id。  
來源：[Celonis Objects and Events](https://docs.celonis.com/en/object-centric-process-mining.html)

AnyLogic 的金融後台案例同時使用 discrete-event 與 agent-based simulation 比較流程、資源與異常量。這支持 MiroFish 採 hybrid model：確定性事件引擎負責財務與治理狀態，agent behavior 只產生行為意圖與不確定性分布。  
來源：[AnyLogic Banca d'Italia case study](https://www.anylogic.com/resources/case-studies/modeling-of-banca-d-italia-back-office-system/)

### 5.5 AI 風險

NIST AI RMF 與 Generative AI Profile 強調治理、測量、測試、驗證與全生命週期風險管理。正式版每次生成的條款解讀、scenario proposal 與 report narrative 都應保存 model / prompt version、輸入 evidence、結構化輸出、validator 結果與人工覆核狀態。  
來源：[NIST AI RMF](https://www.nist.gov/itl/ai-risk-management-framework)

## 6. Build / Borrow / Integrate 決策

### 自己建立，因為這是產品差異化

- Object-centric fund world compiler。
- Scenario branch、counterfactual comparison 與 deterministic replay。
- Fund terms / side letter / governance rule versioning。
- Capital strategy、reserve、waterfall 與 governance consequence simulator。
- Facts / proposals / committed simulation state 的不可混用邊界。
- Evidence graph、decision packet、LP / IC / LPAC meeting pack。
- Simulation-to-record reconciliation contract。

### 採用成熟基礎設施，不自行發明

- PostgreSQL transaction、index、row-level access 與 migration framework。
- 正式 authentication、MFA、session、organization / workspace membership。
- Object storage、encryption、backup、secret management、observability。
- Durable jobs / workflow runtime；在 replay contract 穩定後評估 Temporal。
- PDF / DOCX parsing、virus scan、OCR 與電子簽章 provider。

### 以 adapter 整合，不納入正式版核心責任

- Fund administrator / accounting system。
- Bank / payment / custody。
- KYC / AML / sanctions screening。
- CRM、email、data room 與 e-signature。
- Tax、legal opinion 與 statutory filing。

## 7. 目前 MVP 的就緒稽核

### 已證明，應保留

- 已從 OASIS social simulation route 分離出 business simulation API 與 engine。
- 已有 object/event、decision record、rule execution、ledger 與 report context 的基本形狀。
- 已有 terms、waterfall、capital call、governance review、meeting pack、scenario patch 與 evidence binding。
- LLM / extracted hints 採 proposal-only，不能直接改 ledger。
- 現有 business simulation 測試在正確 backend virtualenv 中為 `7 passed`。
- 已建立獨立 Fund Governance Edition repo 身分與非技術 LP-facing workflow。

### 正式版 P0 阻塞項目

1. **金額精度**：目前大量使用 Python `float` 與 `round`。正式版必須改成 `Decimal` 或最小貨幣單位整數，並明確保存 currency、rounding policy 與 FX source。
2. **多當事人模型**：engine 多處固定取 `gps[0]`、`lps[0]`、`portfolio_companies[0]`。正式版必須支援多 LP、多 share class、多 vehicle、SPV、co-invest 與多 portfolio position。
3. **耐久與交易一致性**：目前 JSON / JSONL 檔案沒有資料庫 transaction、concurrency control 或 crash recovery；`JsonlWriter` 初始化時還會清空既有檔案。正式版不得把它當 authoritative event store。
4. **事件重播與 idempotency**：MVP spec 原本要求 event log 可重建 final state，但現有測試未證明完整 replay、重複 command 防護與 deterministic migration。
5. **Schema 與 migration**：多個輸出仍固定 `schema_version: 0.1`，缺少中央 schema registry、向前/向後相容規則及 migration tests。
6. **權限與職責分離**：現有 access code 是 beta gate，不是 organization、role、fund scope、maker-checker、IC / LPAC membership 或 MFA。
7. **模組邊界**：`business_simulation.py` 約 3,500 行、`engine.py` 約 1,800 行、主要 Vue view 約 1,900 行。正式版需要 domain、application、persistence、API、export 與 UI workflow 分層。
8. **財務 test oracle**：現有 ledger balance 測試不足以證明 waterfall、fee、clawback、default、multi-currency 與 side-letter allocation 正確；需要由可人工核對的 spreadsheet / golden cases 驗證。
9. **資料治理**：尚未定義 tenant isolation、retention、deletion、backup/restore、document classification、PII masking、audit export 與 incident response。
10. **正式部署可靠性**：需要 health checks、job recovery、rate limits、structured telemetry、error taxonomy、backup restore drill 與 release rollback。

因此目前的準確狀態是：

> MVP 已證明產品概念與一條完整 happy path；尚未證明它可以承擔正式基金資料或真實操作責任。

## 8. 正式版前置 Phase 0：Freeze and Characterize

這是下一個應執行的 milestone。它不是重做產品，而是把已經完成的 MVP 變成可安全升級的基線。

### 工作項目

1. 建立 feature inventory 與 route / output contract 清單。
2. 跑完整 backend、frontend build、public-alpha smoke 與 stable launcher smoke。
3. 對 demo seed 建立 golden outputs 與 checksum，證明未來重構沒有偷偷改變結果。
4. 新增缺少的 replay characterization test；先記錄現有行為，再設計 v1 event store。
5. 建立 architecture decision records：Money、Event Store、Workflow、Policy、Auth、Tenant、Document Security。
6. 建立威脅模型與資料分類；確認 synthetic demo 與 real confidential workspace 完全隔離。
7. 標記 MVP 已知限制，凍結 alpha schema，不在 alpha 分支繼續加入正式功能。
8. Phase 0 全部通過後，才建立 `fund-governance-mvp-v0.1.0` tag 與 `fund-governance-formal-v1` branch。

### Phase 0 驗收門檻

- 同一 seed、terms 與 scenario 可重現相同 normalized business result。
- 所有現有 route、輸入與輸出已有 contract inventory。
- 所有金流相關輸出都有 golden test 或清楚列為未驗證。
- crash / rerun / duplicate command 的現況已被測試鎖定。
- real-data boundary、權限責任與 non-advice boundary 已形成文件。
- 正式版 branch 從可驗證 commit 分叉，而不是從帶有不明 working-tree 修改的狀態分叉。

## 9. Phase 0 之後的正式版 Roadmap

每個 milestone 開始前仍需重新做 roadmap fit check；下列順序是目前基於 LP 接觸、資金進入與真實商務運作的建議，而不是不可更動的承諾。

### Formal Milestone 1：Domain Core and Replay v1

- Money / Currency / FX precision。
- Multi-party fund objects。
- PostgreSQL event store、snapshot、idempotent command。
- Schema registry、migration、deterministic replay。
- Versioned rule evaluation 與 immutable decision references。

### Formal Milestone 2：LP Capital Readiness Workspace v1

- LP relationship stage、diligence request、commitment probability 與 readiness checklist。
- Allocation、first close / subsequent close、commitment、unfunded 與 capital-call schedule。
- Resource readiness：legal、admin、finance、banking、reporting、follow-on reserve。
- 匿名 / synthetic intake 到 scenario 的非技術操作流程。

這個 milestone 被提前，是因為目前的真實商務需求是與 LP 接觸、安排資金進入與準備策略資源。

### Formal Milestone 3：Governance Workflow and Segregation of Duties v1

- Organization、fund、workspace、role 與 permission。
- Maker-checker、IC / LPAC quorum、conflict、recusal、approve / reject / waive / rerun。
- Packet revision lock、decision audit、rule version pinning。
- 審批只改 simulation governance state，不會自動觸發真實付款或帳務。

### Formal Milestone 4：Multi-Round Lifecycle and Portfolio Scenarios v1

- 多輪 capital call、quarterly NAV、follow-on、bridge、down round、write-off。
- Partial / delayed exit、regulatory block、LP default cure / waiver。
- Whole-of-fund 與 deal-by-deal waterfall profile。
- Clawback、recycling、fee offset、side-letter scenario。

### Formal Milestone 5：Evidence and Reporting Interoperability v1

- 條款與決策回到文件段落、版本與 confidence。
- ILPA-aligned capital call / distribution / quarterly reporting export。
- LP / IC / LPAC meeting pack、change log、assumption register。
- Fund-admin / accounting adapter 與 reconciliation report。

### Formal Milestone 6：Hosted Private Pilot v1

- 正式 auth、MFA、tenant isolation、encrypted storage。
- Background job recovery、rate limits、monitoring、backup / restore。
- Private invitation、workspace provisioning、trial lifecycle 與 deletion。
- 只允許通過 data-readiness gate 的受控真實資料試點。

### Formal Milestone 7：Production Candidate and Public Packaging

- Security review、dependency / license review、threat-model closure。
- Load、recovery、migration、rollback 與 audit-export drills。
- Operator runbook、support boundary、incident response、release notes。
- Public repo 與 hosted product的邊界重新決策；不因為程式公開就公開客戶資料或正式服務。

## 10. 下一個明確決策

下一步不是複製 MVP，也不是立刻導入 Temporal、Camunda 或 Allvue 類完整平台。

下一步是執行 **Formal Phase 0：Freeze and Characterize**。完成後，我們才有資格把目前 MVP 凍結、建立正式版分支，並開始 `Domain Core and Replay v1`。

這個順序同時保留兩件重要的事：

- 不破壞已經能展示、能給 LP / 基金經理人看的 MVP。
- 正式版從第一天就以真實資金、真實權限與真實商務責任的標準設計，而不是把 demo 慢慢堆成 production。
