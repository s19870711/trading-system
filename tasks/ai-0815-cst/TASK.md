---
slug: ai-0815-cstv30
title: 每日 AI 動態選股 — 當沖標的掃描（08:15 CST）v3.0 機構級作戰卡
steps:
- description: 【B1 學習快速通道 T+1】讀取昨日 learning_journal，提取 actionability_score >= 8 的概念作為今日選股補充過濾條件
  agent_slug: nebula
  format_guide: "讀取 data/learning_journal_$24h_ago|date.json（昨日學習日誌）。\n若檔案不存在，輸出 {\"\
    learning_filters\": [], \"source\": \"no_journal_found\"} 並繼續。\n\n若存在，從所有 scan_sessions[].new_concepts[]\
    \ 中篩選：\n- actionability_score >= 8\n- 且 applicability 包含 \"tw_stocks\" 或 \"universal\"\
    \n\n對每個符合概念，轉換為可執行的選股過濾規則，例如：\n- \"ATR 開盤排除 08:45-09:00\" → filter: \"exclude_entry_window_0845_0905\"\
    \n- \"Regime Confidence Scoring\" → filter: \"apply_confidence_multiplier_to_position\"\
    \n- \"Kill Switch 首次來回\" → filter: \"enable_first_rt_kill_switch\"\n- \"分層約束層級\"\
    \ → filter: \"enforce_tier1_market_regime_first\"\n\n輸出 JSON：\n{\n  \"learning_filters\"\
    : [\n    {\n      \"concept_title\": \"...\",\n      \"filter_rule\": \"...\"\
    ,\n      \"filter_description\": \"...\",\n      \"actionability_score\": N,\n\
    \      \"apply_to\": \"entry_screening | position_sizing | exit_rules\"\n    }\n\
    \  ],\n  \"filter_count\": N,\n  \"source\": \"learning_journal_YYYYMMDD\",\n\
    \  \"note\": \"These filters supplement (not replace) the core scoring system\"\
    \n}"
- description: 全市場掃描 + 機構級評分（五維）+ ATR動態停損 + OBV動能偵測 + 完整作戰卡產出，寫入 data/daily_watchlist.json
  agent_id: agt_0699bd923f75732f8000d98d97fdcc21
  agent_slug: taiwan-stock-day-trading-commander
  format_guide: "執行以下完整選股流程（v4.0 五維評分 + ATR動態停損版）：\n\n【第一步：全市場篩選】\n呼叫 Yahoo Finance\
    \ 或 mis.twse.com.tw 取得前一交易日全市場成交值排行，取前100名。\n排除永久黑名單：金融股(2882/2886/2891/2884/5880等)、電信股(2412)、ETF(00xx)、人壽保險類。\n\
    \n【第二步：五維當沖適性評分】\n1. 流動性（25分）：昨日成交值 >20億=25分，10-20億=20分，5-10億=15分，<5億=5分\n2. 波動度（25分）：昨日振幅\
    \ 2-5%=25分，1.5-2%=20分，5-8%=15分，<1.5%或>8%=5分\n3. 法人動向（25分）：外資+投信合計買超張數，買超>500張=25分，買超100-500=20分，中性=15分，賣超=5分\n\
    4. 技術突破（25分）：突破20日均線+MACD金叉=25分，突破10日均線=20分，突破5日均線=15分，跌破=5分\n5. OBV動能（20分，附加維度）：OBV趨勢向上且成交量遞增=20分；OBV平穩（斜率接近零）=10分；OBV背離（K棒收紅但OBV下滑，主力出貨特徵）=0分，同時標記\
    \ momentum_risk=HIGH\n\n評分說明：前四維滿分100分，第五維OBV動能為附加評分（+20分），總分上限120分，對外排名用正規化後100分制。OBV_DIVERGENCE標的即使前四維高分，position_suggestion_twd自動減半（風控保護）。\n\
    \n同時套用 $prev 的 learning_filters 作為附加篩選條件（不取代核心評分，僅作補充過濾）。\n\n【第三步：對每檔精選標的計算作戰參數】\n\
    必須計算以下數值（不可用假數據）：\n- direction：LONG 或 SHORT（根據技術+籌碼綜合判斷）\n- entry_low / entry_high：建議進場價區間（根據昨收±技術支撐，精確到小數點後1位）\n\
    - target_price：止盈目標（entry_mid × (1 + 預期波動%)，精確到整數）\n- stop_loss：ATR動態停損（必須計算 ATR(14)\
    \ × 1.5，以前一交易日ATR值為基礎，精確到小數點後1位；禁止用固定百分比替代）\n- atr_value：ATR(14)當日值（明確列出，不可省略）\n\
    - risk_reward：風險報酬比（(target-entry)/(entry-stop)，需≥1.5才列入）\n- expected_pnl_per_lot：每張預期盈虧（TWD，扣除來回成本0.321%）\n\
    - best_entry_window：最佳進場時間窗口（如 09:00-09:15 開盤衝刺 / 09:30-10:00 回測確認）\n- operation_guide：3行以內的具體操作指引（「開盤衝量突破XXX買進，目標YYY，ATR停損ZZZ出場」）\n\
    - signal_reason：選入理由（法人動向+技術面+量能+OBV狀態，50字以內）\n- obv_status：OBV_BULLISH（趨勢向上）/\
    \ OBV_NEUTRAL（平穩）/ OBV_DIVERGENCE（背離，主力出貨警示）\n- momentum_risk：LOW / MEDIUM / HIGH（OBV_DIVERGENCE強制HIGH）\n\
    \n成本模型（富邦6折）：買0.0855% + 賣0.0855% + 稅0.15% = 來回0.321%\n風險報酬比 < 1.5 的標的自動淘汰，不論評分高低。OBV_DIVERGENCE標的倉位自動減半。\n\
    \n【第四步：寫入 data/daily_watchlist.json】\n{\n  \"date\": \"YYYY-MM-DD\",\n  \"generated_at\"\
    : \"08:15 CST\",\n  \"version\": \"v4.0\",\n  \"quota_reminder\": \"當沖持倉上限100萬（單一時點最大持倉），買賣合計沖銷上限200萬/日\"\
    ,\n  \"stocks\": [\n    {\n      \"rank\": 1,\n      \"code\": \"2330\",\n   \
    \   \"name\": \"台積電\",\n      \"score\": 88,\n      \"direction\": \"LONG\",\n\
    \      \"entry_low\": 950.0,\n      \"entry_high\": 955.0,\n      \"target_price\"\
    : 968,\n      \"stop_loss\": 944.5,\n      \"atr_value\": 7.0,\n      \"risk_reward\"\
    : 2.1,\n      \"position_suggestion_twd\": 500000,\n      \"expected_pnl_per_lot\"\
    : 2800,\n      \"best_entry_window\": \"09:00-09:15\",\n      \"operation_guide\"\
    : \"開盤突破955量縮確認買進，目標968，ATR停損944.5，不追高\",\n      \"signal_reason\": \"外資昨日買超2800張，突破20日均線，振幅4.2%，OBV向上，籌碼集中\"\
    ,\n      \"obv_status\": \"OBV_BULLISH\",\n      \"momentum_risk\": \"LOW\"\n\
    \    }\n  ],\n  \"blacklist_applied\": [\"金融股\", \"ETF\", \"電信股\", \"人壽股\"],\n\
    \  \"scan_universe\": 100,\n  \"qualified_rr_ratio\": \"風險報酬比≥1.5才入選\"\n}\n\n\
    輸出完整 daily_watchlist.json 內容。"
- description: 推送機構級作戰卡至 Telegram（08:45 CST前完成，確保09:00開盤前操作者已備戰）
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '根據 $prev 的 daily_watchlist.json，組成以下格式推送至 chat_id 6904817875。


    這是開盤前最重要的一條訊息，必須在 08:45 前送達，讓操作者在 09:00 開盤前完全知道今天該做什麼。


    格式如下（使用實際數據，絕對禁止假數據）：


    🎯 AI當沖作戰日報 {YYYY/MM/DD} | 08:15掃描 v4.0


    ━━━━━━━━━━━━━━━━━━


    📋 今日精選 {N}檔｜宇宙100檔篩選｜五維評分（含OBV動能）｜風險報酬≥1.5才入選


    ⚡ 持倉上限：100萬｜日成交沖銷上限：200萬


    ━━━━━━━━━━━━━━━━━━


    針對每一檔標的，輸出完整作戰卡（每檔一個區塊）：


    {rank}. {方向emoji} {code} {name} ｜評分：{score}/100｜OBV：{obv_status}｜動能風險：{momentum_risk}


    ├ 方向：{LONG▲/SHORT▼}


    ├ 進場區間：{entry_low} ~ {entry_high}


    ├ 🎯 止盈目標：{target_price}（+{預期獲利%}%）


    ├ 🛑 ATR動態停損：{stop_loss}（ATR={atr_value}，×1.5）


    ├ ⚖️ 風險報酬比：{risk_reward}:1


    ├ 💰 建議倉位：{position_suggestion_twd/10000}萬（預期每張盈虧{expected_pnl_per_lot}元）


    ├ ⏰ 最佳進場窗口：{best_entry_window}


    ├ 📋 操作指引：{operation_guide}


    └ 📌 選入理由：{signal_reason}


    （重複以上格式輸出每一檔）


    ━━━━━━━━━━━━━━━━━━


    ⛔ 永久黑名單已排除：金融/ETF/電信/人壽


    📊 OBV_DIVERGENCE標的倉位已自動減半（主力出貨風控）


    📝 完整數據已寫入 data/daily_watchlist.json


    ⚠️ 純模擬訓練，非真實交易建議


    ⏰ 09:00 開盤 — 準備就緒！


    使用 $prev 中的實際數據填入每一個欄位。'
---

每個交易日 08:15 CST 執行全市場掃描，動態選出當日最適當沖標的 5-8 檔。v3.0 機構級升級：每檔標的輸出完整作戰卡（方向/進場區間/止盈價/止損價/評分理由/操作指引），08:45 CST 前推送完整 Telegram 作戰報告，確保 09:00 開盤前操作者已知道該做什麼。永久黑名單：金融股/電信股/ETF/人壽股。