---
slug: github-notion
title: 每日自動備份 — GitHub + Notion雙備份
steps:
- description: 讀取所有核心數據文件並驗證完整性
  agent_slug: nebula
  format_guide: |
    使用 browse_files 掃描工作區，列出 data/、tasks/、docs/ 下的文件數量與核心文件清單。
    輸出格式：
    {
      "data_files": <data/ 文件數>,
      "tasks_files": <tasks/ TASK.md 數>,
      "docs_files": <docs/ 文件數>,
      "core_json_list": ["data/trade_log.json", "data/hypothesis_tracker.json", ...],
      "verified": true,
      "timestamp_cst": "<當前 CST 時間>"
    }
    若 data/trade_log.json 存在，從中讀取 _record_count 欄位一併回傳。
    此步驟為驗證用途，不做任何修改。
- description: 備份核心JSON文件至GitHub倉庫（使用github-agent）— C1 強化版：含學習知識庫完整備份
  agent_id: agt_06991c9c77d879178000e8fdb2812a53
  agent_slug: github-agent
  format_guide: |
    使用 GitHub API 將以下文件 upsert 至 repo 的 main branch。

    備份目標（每個文件讀取後 commit）：

    【核心交易數據】
    - data/trade_log.json
    - data/stock_tracker.json
    - data/model_version_log.json
    - data/hypothesis_tracker.json
    - data/daily_watchlist.json
    - data/alpha_decay_state.json
    - data/m11_vulnerability_cache.json
    - data/m13_regime_state.json
    - data/m17_arb_opportunities.json
    - data/m18_factor_decomposition.json

    【知識庫 — 學習日誌（當日 + 過去7天）】
    - data/learning_journal_$today|date.json
    - data/learning_journal_$24h_ago|date.json

    【快照備份 — 當日所有時間戳版本】
    - data/data_snapshot_latest.json
    列出 data/ 目錄下所有 data_snapshot_{today}*.json 時間戳檔案並一併備份

    【Recipe 文件】
    - tasks/09001330-cst/TASK.md
    - tasks/0820-cst/TASK.md
    - tasks/1400-cst/TASK.md
    - tasks/2230-cst/TASK.md
    - tasks/1500-cst0500-cst/TASK.md
    - tasks/ai-0815-cst/TASK.md
    - tasks/alpha-decay-2005-cst/TASK.md
    - tasks/nebula-tw-moltbook/TASK.md
    - tasks/nebula-tw-2300-cst/TASK.md
    - tasks/github-notion/TASK.md

    【文檔】
    - docs/TRAINING_ROADMAP.md
    - docs/daytrade_capital_analysis.md

    Commit message 格式：
    "auto-backup: {YYYY-MM-DD} | trades={record_count}筆 | concepts={learning_concepts_count}個 | snapshots={snapshot_backup_count}份"

    若文件不存在則跳過（不中斷流程）。
    完成後輸出：{committed_files: [...], skipped_files: [...], commit_sha: "...", learning_journals_backed_up: N, snapshot_backups_backed_up: N}
- description: 同步備份摘要至Notion統一帳薄
  agent_id: agt_06991c9c769d7dee8000a464e7c68d20
  agent_slug: notion-agent
  format_guide: '在 Notion 的「系統日誌」資料庫中新增一筆備份記錄，包含以下欄位：


    - 日期：今日CST日期

    - 備份類型：GitHub自動備份

    - 備份文件數：從 $prev 的 committed_files 數量

    - 跳過文件數：skipped_files 數量

    - Commit SHA：來自 $prev 的 commit_sha（前8碼即可）

    - 交易筆數快照：從 $step.1 的 _record_count

    - 備份狀態：SUCCESS 或 PARTIAL（若有skipped）

    - 備份時間：當前CST時間


    若Notion中無「系統日誌」資料庫，則建立一個。'
- description: 推送備份完成通知至Telegram
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '推送備份完成通知至 Telegram chat_id: 6904817875。


    格式：

    == [系統自動備份完成] ==

    日期：{今日CST日期}

    備份文件：{committed_files數}個

    Commit：{commit_sha前8碼}

    交易記錄：{record_count}筆

    Notion同步：✅

    下次備份：明日 23:30 CST


    若有跳過文件，在最後加上：

    ⚠️ 跳過文件：{skipped_files列表}


    備份正常則整條訊息靜默（不推送），僅在以下情況推送：

    1. commit_sha存在（備份成功有新變更）

    2. 有skipped_files（部分失敗需關注）

    3. 出現任何錯誤'
---

每日 23:30 CST 自動備份所有核心數據文件至 GitHub（版本控制）和 Notion（可視化查閱）。備份範圍：data/ 下所有 JSON + tasks/ + docs/。無需VM，純Nebula執行。