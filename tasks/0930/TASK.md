---
slug: 0930
title: 每日當沖監控 09:30 — 持倉確認+加碼評估
steps:
- description: 【熔斷前置檢查】讀取 data/daily_pnl_realtime.json 取得今日已實現損益
  action_key: scrape-page
  action_props:
    url: file://data/daily_pnl_realtime.json
- description: 【熔斷守門員】若今日虧損已達 -15000 推送熔斷通知並停止後續步驟
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: 推送熔斷 Telegram 訊息至 chat_id 6904817875，格式：🚨 **今日熔斷觸發 — 禁止新倉**\n今日已實現虧損：{realized_loss_twd}
    TWD\n已達 -15,000 熔斷線。即刻起禁止開任何新倉，靜待 13:00 清倉。
  filtering_prompt: 讀取 $prev 中的 realized_loss_twd。若 <= -15000，推送 Telegram chat_id
    6904817875：🚨 **今日熔斷觸發 — 禁止新倉** 今日已實現虧損 {realized_loss_twd} TWD 已達 -15,000 熔斷線。即刻起禁止開任何新倉，靜待
    13:00 清倉。然後 stop。若 > -15000（或檔案不存在）則 continue。
- description: 讀取 data/daily_watchlist.json 取得今日 rank1/rank2 的 entry_zone、t1_target、t2_target、stop_loss_price、recommended_lots、recommended_lots_aggressive
  action_key: scrape-page
  action_props:
    url: file://data/daily_watchlist.json
- description: market-data-validation-gatekeeper 抓取 rank1/rank2 09:30 即時報價，計算浮盈浮虧與停損觸發判斷
  agent_id: agt_069a58fa85e17d738000972f26787f7a
  agent_slug: market-data-validation-gatekeeper
  format_guide: 從 $prev 讀取 rank1/rank2 代號及 entry_zone_low/high、t1_target、t2_target、stop_loss_price。查詢即時報價（price_realtime）。計算：entry_mid=(low+high)/2，unrealized_pnl_pct=(price_realtime-entry_mid)/entry_mid*100，t1_distance_pct=(t1_target-price_realtime)/price_realtime*100。判斷：is_above_entry、is_t1_hit、is_stop_hit（price_realtime<=stop_loss_price）。回傳完整結構含
    stop_loss_price。
- description: taiwan-stock-day-trading-commander 綜合浮盈浮虧數據，提供加碼/持倉/停損決策建議
  agent_id: agt_0699bd923f75732f8000d98d97fdcc21
  agent_slug: taiwan-stock-day-trading-commander
  format_guide: 從 $step.4 讀取每個標的的 unrealized_pnl_pct、is_t1_hit、is_stop_hit、t1_distance_pct
    和 recommended_lots_aggressive。輸出決策建議：(1) 若 is_t1_hit=true：建議移動止損至成本，評估是否繼續持有等待T2；(2)
    若 is_above_entry 且未到T1：建議繼續持有；(3) 若 is_stop_hit=true：強制建議立即出場，標記 STOP_TRIGGERED；(4)
    若尚未進場（價格在進場區以下）：重新評估進場時機。
- description: telegram-bot-communication-agent 推送 09:30 持倉確認報告 + 停損點強制標示 + 停損觸及60秒警告至
    Telegram
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '整合 $step.4 和 $step.5，推送至 Telegram chat_id 6904817875。


    若任一標的 is_stop_hit=true，優先推送緊急警告：

    🚨🚨🚨 **停損觸及 — 60秒倒數** 🚨🚨🚨

    {ticker} {名稱} 現價 {price_realtime} 已跌破停損點 {stop_loss_price}

    ⏱ **請在60秒內執行出場，不等反彈，不扛單**

    若60秒內未回應，系統視為確認出場意願。


    一般格式：

    📊 **09:30 持倉確認點**


    🥇 {rank1代號} {名稱}

    現價：{price_realtime} | 浮盈：{unrealized_pnl_pct:+.1f}%

    T1 距離：{t1_distance_pct:.1f}% | T1達成：{是/否}

    🛑 停損點：{stop_loss_price} — 請確認停損單已掛出

    → 決策：**{加碼/持倉/停損/等待進場}**

    {詳細說明}


    🥈 {rank2代號} {名稱}

    （同上格式）


    ⚠️ **紀律提醒：停損點是底線，不甘心不是理由。**

    下一停損提醒：10:00 | 下一檢查點：10:00 盤中評估'
---

每個交易日 09:30 CST 執行。進場後 15 分鐘確認點。計算浮盈浮虧、判斷是否觸及 T1、評估加碼或停損決策。永久版 v1.0。