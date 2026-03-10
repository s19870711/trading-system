---
slug: v30-code-agent-github-agent
title: 每日備份與版本管理 v3.0 — code-agent 讀取 + github-agent 上傳
steps:
- description: "【nebula】使用工作區檔案瀏覽工具，依序讀取以下12個目標路徑的檔案內容（檔案不存在則記入 skipped_files，不報錯繼續）：\n\
    \n目標路徑：\n1. data/hypothesis_tracker.json\n2. data/trade_log.json\n3. data/system_health_daily.json\n\
    4. data/daily_watchlist.json\n5. data/m13_regime_state.json\n6. data/m17_latest.json\n\
    7. data/okx_funding_snapshot.json\n8. data/glint_latest.json\n9. data/var_latest.json\n\
    10. data/data_snapshot_latest.json\n11. data/learning_journal_*.json（用 browse_files\
    \ 找最新一份，按 updated_at 排序）\n12. tasks/v20/TASK.md\n\n讀取方法：用 text_editor view 逐一讀取每個路徑，成功則加入\
    \ files 陣列，失敗/不存在則加入 skipped_files。\n\n【強化清理步驟 v2.0】同步清理舊快照與臨時檔案：\n- data/glint_report_*.json\
    \ → 保留最新5個（按 created_at 排序，刪除第6個以後）\n- data/quality_check_*.json → 保留最新3個\n- data/m13_report_*.json\
    \ → 保留最新5個\n- data/data_snapshot_202*.json → 保留最新3個（data_snapshot_latest.json\
    \ 不刪）\n- data/p0_*_ex*.json → 全部刪除（執行期臨時檔，不需保留）\n- data/geopolitical_gate_ex*.json\
    \ → 全部刪除\n- data/var_pnl_attribution/staging/unverified/var_*_ex*_staging.json\
    \ → 全部刪除\n- data/m17_report_*.json → 保留最新5個，刪除舊版\n- tmp/ 目錄下超過3天的檔案 → 全部刪除\n\n\
    從 data/trade_log.json 讀取 total_trades 數量（不存在則為0）。\n\n輸出 JSON 格式：\n{\n  \"files\"\
    : [{\"path\": \"data/m13_regime_state.json\", \"content\": \"...完整UTF-8字串...\"\
    , \"size_bytes\": N}, ...],\n  \"skipped_files\": [\"data/hypothesis_tracker.json\"\
    , ...],\n  \"cleanup_summary\": {\"deleted_files\": [], \"deleted_count\": N,\
    \ \"freed_bytes\": N},\n  \"total_trades\": N,\n  \"scan_timestamp_cst\": \"2026-MM-DD\
    \ HH:MM CST\"\n}"
  agent_slug: nebula
  format_guide: '輸出 JSON：{files: [{path, content(UTF-8字串), size_bytes}], skipped_files:
    [], cleanup_summary: {deleted_files: [], deleted_count: N, freed_bytes: N}, total_trades:
    N, scan_timestamp_cst: str}'
- description: "【github-agent】接收 Step 1 nebula 輸出的 {files, skipped_files, total_trades,\
    \ scan_timestamp_cst}，透過 GitHub API 將所有 files 陣列中的檔案 upsert 至 repo main branch。\n\
    \n- 目標 repo：從 GitHub 已連接帳號取得，優先使用 s19870711 帳號下含 'nebula' 或 'trading' 或 'backup'\
    \ 的 repo\n- 對每個 file（files[] 陣列），content 欄位為 UTF-8 字串，呼叫 GitHub Contents API PUT\
    \ /repos/{owner}/{repo}/contents/{path} 時先將 content base64 encode 後上傳\n- Commit\
    \ message 格式：auto-backup: {scan_timestamp_cst} | trades={total_trades}筆 | files={N}\n\
    - 若文件已存在需先取得 sha 再 upsert（避免 409 衝突）\n- skipped_files 中的項目不需上傳\n\n輸出格式：\n{\n \
    \ \"committed_files\": [\"path1\", \"path2\", ...],\n  \"failed_files\": [],\n\
    \  \"commit_sha\": \"abc123...\",\n  \"backup_status\": \"COMPLETE/PARTIAL/FAILED\"\
    ,\n  \"integrity_score\": N\n}"
  agent_id: agt_06991c9c77d879178000e8fdb2812a53
  agent_slug: github-agent
  format_guide: '輸出 JSON：{committed_files: [], failed_files: [], commit_sha: str,
    backup_status: COMPLETE/PARTIAL/FAILED, integrity_score: N (committed/total*100)}'
- description: '【notion-agent】在父頁面 3166b075-aa9e-8085-9881-cda3d9f74bc8 下建立當日備份快照子頁面，並在系統日誌資料庫新增備份記錄。


    【操作1】建立當日快照頁面，標題：「機構指揮中心 {今日CST日期} 狀態快照」

    頁面內容（markdown）：

    - 備份時間 / Commit SHA / 備份文件數 / 交易筆數

    - 市場狀態：讀取 data/glint_latest.json 的 gts.current + severity_code、m13_regime_state.json
    的 market_regime、data/okx_funding_snapshot.json 的 arbitrage_signal

    - 今日倉位指引（GTS>=80 防禦模式 / GTS<60 解鎖模式）

    - 底部戳記：「由Nebula {CST時間} 自動生成 | v3.0 | code-agent+github-agent 雙引擎架構」


    【操作2】在系統日誌資料庫新增記錄：日期、備份文件數、commit_sha前8碼、交易筆數、備份狀態。'
  agent_id: agt_06991c9c769d7dee8000a464e7c68d20
  agent_slug: notion-agent
  format_guide: '輸出：{notion_page_created: true/false, page_id: str, log_entry_created:
    true/false}'
- description: "【nebula】依備份完整性分數決定通知級別並推送 Telegram（chat_id: 6904817875）：\n\n- integrity_score\
    \ = 100 且 backup_status = COMPLETE → 靜默（SILENT），只寫 data/backup_log.json\n- integrity_score\
    \ 80-99 → Telegram ALERT：列出 failed_files，說明哪些未備份成功\n- integrity_score < 80 或 backup_status\
    \ = FAILED → Telegram ESCALATE：\n  ❗每日備份失敗 — {CST時間}\n  \U0001F50D根因：{具體 failed_files\
    \ 與錯誤}\n  \U0001F4CB建議操作：\n  A. 立即重新執行備份\n  B. 手動確認 GitHub 倉庫狀態\n  C. 忽略並在下次排程重試\n\
    \n無論哪種情況，都寫入 data/backup_log.json：{timestamp_cst, integrity_score, backup_status,\
    \ committed_files, failed_files, commit_sha}"
  agent_slug: nebula
  format_guide: 靜默條件：integrity_score=100 → 只寫 backup_log.json。否則按分級推送 Telegram。
---