---
slug: 1100-t2
title: 每日當沖監控 11:00 — 盤中中場報告+T2評估
steps:
- description: 【熔斷前置檢查】讀取 data/daily_pnl_realtime.json 取得今日已實現損益
  action_key: scrape-page
  action_props:
    url: file://data/daily_pnl_realtime.json
- description: 【熔斷守門員】若今日虧損已達 -15000 推送熔斷通知並停止後續步驟
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '推送熔斷 Telegram 訊息至 chat_id 6904817875，格式：🚨 **今日熔斷觸發 — 禁止新倉**

    今日已實現虧損：{realized_loss_twd} TWD

    禁止新倉，靜待 13:00 清倉。'
  filtering_prompt: 讀取 $prev 中的 realized_loss_twd。若 <= -15000，推送 Telegram chat_id
    6904817875：🚨 **今日熔斷觸發** 已實現虧損 {realized_loss_twd} TWD，禁止新倉，靜待 13:00 清倉。然後 stop。若
    > -15000（或檔案不存在）則 continue。
- description: 讀取 data/daily_watchlist.json 取得今日所有已選標的（rank1-rank3）的 t2_target、stop_loss_price、entry_zone_low/high
  action_key: scrape-page
  action_props:
    url: file://data/daily_watchlist.json
- description: market-data-validation-gatekeeper 抓取所有標的即時報價 + 加權指數目前狀態，計算停損觸發判斷
  agent_id: agt_069a58fa85e17d738000972f26787f7a
  agent_slug: market-data-validation-gatekeeper
  format_guide: 從 $prev 讀取所有標的代號。分別查詢即時報價。計算：t2_distance_pct=(t2_target-price)/price*100、pnl_from_entry_pct（相對
    entry_zone 中位數）、volume_ratio（評估当前動能）、is_stop_hit（price<=stop_loss_price）。同時查詢加權指數（IX0001）目前價格與早盤比較。回傳含
    stop_loss_price 的完整結構。
- description: taiwan-stock-day-trading-commander 綜合中場走勢，評估各標的動能強弱、OBV衰退偵測與 T2 達成機率
  agent_id: agt_0699bd923f75732f8000d98d97fdcc21
  agent_slug: taiwan-stock-day-trading-commander
  format_guide: '從 $step.4 讀取所有標的數據。執行以下評估：


    (1) 動能強弱評估：volume_ratio 和價格動進方向綜合判斷（強/中/弱）


    (2) OBV動能衰退偵測（新增）：

    - 若 volume_ratio 在最近連續 2 個 15 分鐘週期下滑，且 OBV 斜率轉負（當前成交量方向與價格方向不一致），標記該標的 MOMENTUM_DECAY=true

    - MOMENTUM_DECAY=true 的標的：建議提前鎖利（鎖住現有獲利），而非繼續持倉等待 T2；若 MOMENTUM_DECAY=true 且距
    T2 尚有 >1%，強烈建議部分出場（50%倉位）

    - 若 OBV 斜率持續向上且 volume_ratio > 1.0，標記 MOMENTUM_DECAY=false（動能健康）


    (3) 距T2差距與達成機率：t2_distance_pct 及剩餘時間（還有90分鐘）


    (4) 停損觸及處理：若 is_stop_hit=true，標記 STOP_TRIGGERED，建議立即出場


    (5) 操作建議矩陣：

    - MOMENTUM_DECAY=false + 距T2 < 0.5% → 持倉等T2

    - MOMENTUM_DECAY=false + 距T2 > 0.5% → 正常持倉監控

    - MOMENTUM_DECAY=true + 有浮盈 → 建議提前鎖利（部分或全部）

    - MOMENTUM_DECAY=true + 接近停損 → 建議立即出場

    - is_stop_hit=true → 立即出場，不等不扛


    最後提醒 12:45 為每日最後開倉時間。'
- description: telegram-bot-communication-agent 推送 11:00 中場報告 + OBV動能衰退警示 + 停損點強制顯示至
    Telegram
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '整合 $step.4 和 $step.5，推送至 Telegram chat_id 6904817875。


    若任一標的 is_stop_hit=true，優先推送：

    🚨🚨🚨 **11:00 停損觸及緊急警告** 🚨🚨🚨

    {ticker} 現價 {price} 已跌破停損點 {stop_loss_price}

    ❌ 立即出場，不等反彈，不扛單，這是系統強制指令。


    若任一標的 MOMENTUM_DECAY=true，推送動能衰退警示：

    ⚠️ **動能衰退偵測** — {ticker}

    volume_ratio 連續下滑 + OBV斜率轉負（主力可能撤退）

    💡 建議：提前鎖利，勿死等T2。剩餘目標距離：{t2_distance_pct:.1f}%


    標準格式：

    📊 **11:00 中場走勢報告**

    大盤：{taiex_now} ({taiex_change_pct:+.2f}%)


    🥇 {rank1代號} {名稱}

    現價：{price} | P&L：{pnl_pct:+.1f}%

    距T2差距：{t2_distance_pct:.1f}% | 動能：{強/中/弱} | OBV：{DECAY/OK}

    → **{操作建議}**


    🥈 {rank2代號} {名稱}

    （同上格式）


    🛑 **停損點（每次必看）：**

    {rank1代號} ATR停損：{stop_loss_price} | {rank2代號} ATR停損：{stop_loss_price}

    現價若低於停損點 → 立即出場，不等不扛。


    ⏰ **12:45 不再開新倉**，13:00 強制清倉。'
---

每個交易日 11:00 CST 執行。盤中中場報告，評估各標的距 T2 目標距離，動能強弱判斷，提醒 12:45 停止新倉。永久版 v1.0。