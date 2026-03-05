# Agent 間互相呼叫授權協議 v1.0
**建立日期**: 2026-03-05  
**狀態**: ACTIVE  
**適用範圍**: 全系統 41 個 Agent  
**矩陣參考**: `data/agent_authorization_matrix.json`  
**稽核日誌**: `data/authorization_audit.json`  
**安全事件**: `data/security_incidents.json`

---

## 核心原則

> **「接收端守門」優於「發送端自律」**  
> 高風險 Agent 在執行前主動驗證呼叫者身份與授權等級，不依賴呼叫方自我約束。任何缺少有效令牌的高風險操作請求，接收端必須無條件拒絕。

---

## 第一節：Delegation Token（委派令牌）規格

每次 Agent A 委派 Agent B 時，任務描述中必須附帶以下結構化令牌區塊：

```
[DELEGATION_TOKEN]
caller_id: <呼叫方 agent slug>
caller_tier: <TIER-0 | TIER-1 | TIER-2 | TIER-3 | TIER-4 | TIER-5>
operation_type: <操作類型代碼，見第二節>
authorization_level: <AUTO_APPROVED | SINGLE_AUTH | DUAL_AUTH>
request_id: <YYYYMMDD-HHMMSS-{caller_slug}>
timestamp: <ISO 8601，Asia/Taipei>
[/DELEGATION_TOKEN]
```

### 令牌欄位說明

| 欄位 | 說明 | 範例 |
|------|------|------|
| `caller_id` | 呼叫方的 agent slug | `portfolio-strategy-commander` |
| `caller_tier` | 呼叫方的授權等級 | `TIER-2` |
| `operation_type` | 本次委派的操作分類 | `POSITION_REQUEST` |
| `authorization_level` | 此操作需要的授權等級 | `SINGLE_AUTH` |
| `request_id` | 唯一請求 ID，用於稽核追蹤 | `20260305-093000-portfolio-strategy-commander` |
| `timestamp` | 令牌生成時間 | `2026-03-05T09:30:00+08:00` |

---

## 第二節：操作類型分類與授權等級

### A. AUTO_APPROVED — 自動核准（無需額外授權）

以下操作風險低，附帶有效 Delegation Token 即自動執行：

| operation_type | 說明 | 最低呼叫 TIER |
|----------------|------|--------------|
| `MARKET_DATA_READ` | 讀取市場數據快照 | TIER-5 |
| `FACTOR_DATA_READ` | 讀取因子計算結果 | TIER-5 |
| `REPORT_GENERATE` | 生成分析報告 | TIER-4 |
| `TELEGRAM_NOTIFY` | 推送 Telegram 通知 | TIER-4 |
| `HYPOTHESIS_READ` | 讀取假說追蹤狀態 | TIER-4 |
| `SIMULATION_TRADE` | 模擬交易（use_simulation=true） | TIER-2 |
| `POSITION_QUERY` | 查詢部位資訊（只讀） | TIER-3 |
| `SIGNAL_QUERY` | 查詢交易訊號 | TIER-3 |
| `RISK_ASSESSMENT` | 請求風控評估 | TIER-2 |
| `DAILY_REPORT` | 發送每日報告 | TIER-2 |

### B. SINGLE_AUTH — 單一授權（需 TIER-0 或 TIER-1 明確授權）

以下操作具中高風險，需風控層或主人授權：

| operation_type | 說明 | 最低呼叫 TIER |
|----------------|------|--------------|
| `POSITION_REQUEST` | 開倉/加倉/減倉申請 | TIER-1（決策）；TIER-2（提交申請） |
| `HYPOTHESIS_WRITE` | 寫入假說追蹤（晉升/退休） | TIER-1 |
| `STOP_LOSS_EXECUTE` | 執行停損（模擬） | TIER-2 |
| `PARAMETER_UPDATE` | 更新策略參數 | TIER-1 |
| `AGENT_SUSPEND` | 暫停 Agent 運行 | TIER-1 |
| `AGENT_RESTORE` | 恢復 Agent 運行 | TIER-1 |
| `WHITELIST_UPDATE` | 更新外部 URL 白名單 | TIER-1 |

### C. DUAL_AUTH — 雙重授權（需 Nebula 對話框 + Telegram 雙確認）

以下操作涉及真實資金或系統根本架構，必須雙重確認：

| operation_type | 說明 | 最低呼叫 TIER |
|----------------|------|--------------|
| `REAL_ORDER` | 真實下單（use_simulation=false） | **TIER-0 或 TIER-1 only** |
| `DISABLE_SIMULATION` | 關閉模擬模式 | **TIER-0 only** |
| `FORCE_CLOSE` | 強制平倉所有部位 | **TIER-0 或 TIER-1 only** |
| `POSITION_OVERRIDE` | 強制覆蓋部位狀態 | **TIER-0 或 TIER-1 only** |
| `HYPOTHESIS_FORCE_PROMOTE` | 強制晉升假說（繞過統計門檻） | **TIER-0 only** |
| `AUTH_MATRIX_MODIFY` | 修改授權矩陣本身 | **TIER-0 only** |
| `AGENT_PERMANENTLY_DISABLE` | 永久停用 Agent | **TIER-0 only** |
| `LARGE_CAPITAL_OP` | 單筆超過 100,000 NTD | **TIER-0 或 TIER-1 only** |

---

## 第三節：接收端驗證流程（所有 TIER-1/TIER-2 受保護 Agent 必須執行）

```
收到 delegate_task 時：

STEP 1: 解析令牌
  - 從任務描述中提取 [DELEGATION_TOKEN] ... [/DELEGATION_TOKEN] 區塊
  - 若無令牌區塊：
      → 記錄至 data/security_incidents.json（incident_type: MISSING_TOKEN）
      → 推送 Telegram 告警
      → STOP，不執行任何操作

STEP 2: 驗證 caller_id
  - 讀取 data/agent_authorization_matrix.json
  - 確認 caller_id 存在於矩陣的 agents 清單中
  - 若 caller_id 不在矩陣中：
      → UNKNOWN_CALLER 事件，寫入 security_incidents.json
      → STOP

STEP 3: 驗證 caller_tier 與操作權限
  - 對照矩陣中本 Agent 的 allowed_callers 規則
  - 確認 caller_tier 在允許清單中
  - 若 operation_type 屬於 DUAL_AUTH 類別：
      → 額外確認 caller_tier <= TIER-1
      → 確認 authorization_audit.json 中存在對應的人工授權記錄
      → 若無：STOP + 安全事件

STEP 4: 執行前寫入稽核
  - 寫入 data/authorization_audit.json：
    {
      "audit_id": "<request_id>",
      "timestamp": "<ISO 8601>",
      "caller_id": "<caller_id>",
      "callee_id": "<本 Agent slug>",
      "operation_type": "<operation_type>",
      "authorization_level": "<level>",
      "decision": "APPROVED | REJECTED",
      "reason": "<原因說明>"
    }

STEP 5: 執行操作（僅在 STEP 1-4 全部通過後）
```

---

## 第四節：發送端令牌注入規範（TIER-1/TIER-2 Agent 必須遵守）

每次呼叫 `delegate_task` 時，任務描述開頭必須附帶令牌：

```python
# 範例：portfolio-strategy-commander 呼叫 hedge-fund-risk-controller
task = """
[DELEGATION_TOKEN]
caller_id: portfolio-strategy-commander
caller_tier: TIER-2
operation_type: POSITION_REQUEST
authorization_level: SINGLE_AUTH
request_id: 20260305-093000-portfolio-strategy-commander
timestamp: 2026-03-05T09:30:00+08:00
[/DELEGATION_TOKEN]

請評估以下開倉申請：
symbol: 2330, quantity: 1000, rationale: 突破月線
"""
```

### 操作類型快速判斷表

| 我要做什麼 | operation_type | authorization_level |
|-----------|----------------|---------------------|
| 查詢市場數據 | MARKET_DATA_READ | AUTO_APPROVED |
| 請求風控評估 | RISK_ASSESSMENT | AUTO_APPROVED |
| 開倉申請 | POSITION_REQUEST | SINGLE_AUTH |
| 模擬交易執行 | SIMULATION_TRADE | AUTO_APPROVED |
| 真實下單 | REAL_ORDER | DUAL_AUTH |
| 強制平倉 | FORCE_CLOSE | DUAL_AUTH |
| 更新假說 | HYPOTHESIS_WRITE | SINGLE_AUTH |
| 推送通知 | TELEGRAM_NOTIFY | AUTO_APPROVED |

---

## 第五節：安全事件分類與處理

### 事件等級

| 等級 | 代碼 | 觸發條件 | 處理方式 |
|------|------|---------|---------|
| CRITICAL | `UNAUTHORIZED_REAL_ORDER` | TIER-2+ 嘗試真實下單 | 立即 STOP + Telegram 緊急告警 + 寫入事件日誌 |
| CRITICAL | `FORCE_OVERRIDE_VIOLATION` | TIER-2+ 嘗試強制覆蓋部位 | 立即 STOP + Telegram 緊急告警 |
| HIGH | `MISSING_TOKEN` | 高風險操作無令牌 | STOP + 告警 + 事件日誌 |
| HIGH | `UNKNOWN_CALLER` | caller_id 不在授權矩陣 | STOP + 告警 + 事件日誌 |
| HIGH | `TIER_VIOLATION` | caller_tier 超出允許範圍 | STOP + 告警 + 事件日誌 |
| MEDIUM | `EXPIRED_TOKEN` | 令牌時間戳超過 15 分鐘 | 要求重新委派 |
| LOW | `AUDIT_WRITE_FAIL` | 無法寫入稽核日誌 | 告警但允許繼續（不阻斷業務） |

### 安全事件 JSON 格式

```json
{
  "incident_id": "INC-20260305-001",
  "timestamp": "2026-03-05T09:30:00+08:00",
  "incident_type": "TIER_VIOLATION",
  "severity": "HIGH",
  "caller_id": "taiwan-stock-day-trading-commander",
  "caller_tier": "TIER-3",
  "callee_id": "order-execution-engine",
  "attempted_operation": "REAL_ORDER",
  "token_provided": true,
  "token_valid": false,
  "violation_reason": "TIER-3 不允許呼叫 REAL_ORDER，最低需 TIER-1",
  "action_taken": "BLOCKED",
  "telegram_alerted": true,
  "resolved": false
}
```

---

## 第六節：特殊規則

### 6.1 緊急停損例外
`EMERGENCY_STOP`（帳戶單日虧損達硬性上限）由 `multi-market-position-manager` 自動觸發，不需等待風控批准。但仍須：
- 附帶 `DUAL_AUTH` 令牌
- `caller_id` 為 `multi-market-position-manager`（TIER-2，擁有緊急停損例外權限）
- 事後立即通知 `hedge-fund-risk-controller` 與 Telegram

### 6.2 Citadel BLACK 狀態
當 `citadel-circuit-breaker-guardian` 發出 BLACK 狀態時：
- 所有 TIER-2+ Agent 的委派請求自動被系統攔截
- 僅 TIER-0 與 TIER-1 可繼續操作
- Override Code 格式：`CB-{YYYYMMDD}-{4-digit-hash}`

### 6.3 Nebula 主人直接指令
透過 Nebula 對話框或 Telegram chat_id `6904817875` 的指令視為 TIER-0，不需要 Delegation Token（由 Nebula 平台本身保障身份真實性）。

### 6.4 排程觸發器（Cron/Webhook）
由 Nebula 排程觸發器啟動的任務，authorization_level 自動標注為 `AUTO_APPROVED_SCHEDULED`，視為 TIER-0 下令的排程授權，可執行 SINGLE_AUTH 以下操作。DUAL_AUTH 操作仍需人工授權。

---

## 第七節：授權矩陣維護規則

1. 矩陣更新（`AUTH_MATRIX_MODIFY`）僅 TIER-0 可執行
2. 每次更新須記錄：更新者、更新原因、更新前/後差異
3. 矩陣版本號格式：`v{major}.{minor}`，重大結構變更升 major，新增/修改 Agent 升 minor
4. 每月第一個週日自動稽核矩陣完整性（對比系統實際 Agent 清單）

---

## 版本歷史

| 版本 | 日期 | 說明 |
|------|------|------|
| v1.0 | 2026-03-05 | 初始建立，覆蓋 41 個 Agent |
