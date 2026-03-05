---
slug: 0915-s1
title: 每日當沖監控 09:15 — S1進場條件全檢
steps:
- description: 【熔斷前置檢查】讀取 data/daily_pnl_realtime.json 取得今日已實現損益，若 realized_loss_twd
    <= -15000 則熔斷鎖倉
  action_key: scrape-page
  action_props:
    url: file://data/daily_pnl_realtime.json
- description: 【熔斷守門員】若今日虧損已達熔斷閾值，推送 Telegram 熔斷通知並停止後續步驟
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: 若需推送熔斷通知：發送至 Telegram chat_id 6904817875，格式：🚨 **今日熔斷觸發 — 禁止新倉**\n今日已實現虧損：{realized_loss_twd}
    TWD\n已達 -15,000 熔斷線。即刻起禁止開任何新倉。
  filtering_prompt: 讀取 $prev 中的 realized_loss_twd 欄位。若該值 <= -15000，推送 Telegram chat_id
    6904817875 訊息：🚨 **今日熔斷觸發 — 禁止新倉** 今日已實現虧損：{realized_loss_twd} TWD，已達 -15,000 熔斷線。**即刻起禁止開任何新倉，靜待
    13:00 清倉。** 系統已鎖倉，不再執行 09:15 進場評估。 然後 stop。若 realized_loss_twd > -15000（或檔案不存在），continue。
- description: 讀取 data/daily_watchlist.json 取得今日 rank1/rank2 的 entry_condition（S1條件）、entry_zone_low/high、t1_target、t2_target、stop_loss_price、recommended_lots、recommended_lots_aggressive
  action_key: scrape-page
  action_props:
    url: file://data/daily_watchlist.json
- description: market-data-validation-gatekeeper 執行 09:15 S1條件驗證（四層確認）：抓取 rank1/rank2 即時報價、VWAP、量比、OBV趨勢、15分鐘K棒方向，ADX Regime Filter 前置判斷，與 entry_condition 逐條比對
  agent_id: agt_069a58fa85e17d738000972f26787f7a
  agent_slug: market-data-validation-gatekeeper
  format_guide: '從 $prev 讀取 rank1/rank2 代號與 entry_condition。執行四層確認框架：

    【前置 Regime Filter】查詢大盤加權指數 ADX(14)：若 ADX < 20（盤整市），所有標的強制進入「均值回歸模式」，禁止輸出趨勢追漲型
    ENTER 訊號，overall_signal 最高只能 WAIT，附加說明 regime=RANGING。

    【第一層：價格位置確認】price_realtime 是否在 entry_zone_low ~ entry_zone_high 之內。

    【第二層：量比確認】volume_ratio 是否達到 entry_condition 中指定的量比門檻（通常 >= 1.5x）。

    【第三層：VWAP 位置確認】計算 vwap_deviation_pct = (price_realtime - VWAP) / VWAP * 100。LONG 方向：price > VWAP 且
    vwap_deviation_pct <= 1.5% 為 PASS；偏離 > 1.5% 標記 VWAP_EXTENDED，建議等待回踩。

    【第四層：OBV 趨勢確認】計算當日累計 OBV 方向（對比 5 日均線斜率）：OBV 趨勢向上且當前成交量方向與價格方向一致 = OBV_CONFIRM=true；K棒收紅但
    OBV 斜率轉負（主力出貨特徵）= OBV_CONFIRM=false，此時強制 WAIT，不得輸出 ENTER。

    四層全部 PASS 且 ADX >= 20 → overall_signal=ENTER。
    任一層 FAIL 且非 Regime 問題 → WAIT + 說明缺少哪層。
    技術形態完全不符 → ABORT。

    回傳：{ticker, price_realtime, volume_ratio, vwap_position, vwap_deviation_pct,
    obv_trend_direction, obv_confirm, regime_adx, regime_mode,
    s1_conditions_met: {layer1_price: bool, layer2_volume: bool, layer3_vwap: bool, layer4_obv: bool},
    overall_signal: ''ENTER''/''WAIT''/''ABORT'', suggested_limit_price, validation_status}'
- description: taiwan-stock-day-trading-commander 綜合 S1 訊號研判，補充盤口分析與進場時機建議
  agent_id: agt_0699bd923f75732f8000d98d97fdcc21
  agent_slug: taiwan-stock-day-trading-commander
  format_guide: 從 $step.4 讀取 rank1/rank2 的 overall_signal 和即時報價，補充：(1) 盤口買賣力道判斷（bid/ask掛單比）；(2)
    若 ENTER：建議限價掛單價位（精確到分）；(3) 若 WAIT：說明缺少哪個條件；(4) 若 ABORT：說明原因。回傳補充分析。
- description: telegram-bot-communication-agent 推送 S1 進場判定 + 停損點強制標示至 Telegram chat_id
    6904817875
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: '整合 $step.4 和 $step.5，推送至 Telegram chat_id 6904817875。訊息格式：


    🎯 **09:15 S1 進場條件全檢**

    保護區結束 — 正式評估


    🥇 {rank1代號} {名稱} → **{ENTER🟢/WAIT🟡/ABORT🔴}**

    現價：{price_realtime} | 量比：{volume_ratio}x

    條件逐項：{逐條 PASS/FAIL}

    {若ENTER：建議限價：XXX，口數：N張}

    {若WAIT：缺：XXX條件}

    🛑 停損點：{stop_loss_price}（進場後請立即掛停損單）


    🥈 {rank2代號} {名稱} → **{ENTER🟢/WAIT🟡/ABORT🔴}**

    （同上格式）


    ⚠️ **追高警告規則**：現價偏離基準 >1% 禁止進場

    下一確認點：09:30 持倉確認'
- description: 追高偵測守門員 — 若進場價偏離 S1 基準超過 1% 推送 Telegram 阻止警告
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: 從 $step.4 讀取每個標的的 suggested_limit_price 和 overall_signal。從 $step.3
    讀取 entry_zone_low 和 entry_zone_high。計算 entry_mid = (entry_zone_low + entry_zone_high)
    / 2。對每個 overall_signal=ENTER 的標的計算偏離度：deviation_pct = (suggested_limit_price -
    entry_mid) / entry_mid * 100。若任一標的 deviation_pct > 1.0，推送至 Telegram chat_id 6904817875：⚠️
    **追高警告 — 非計劃進場偵測** {ticker}：S1基準 {entry_mid} | 建議進場 {suggested_limit_price} |
    偏離 +{deviation_pct:.1f}% ⚠️ 超出1%容忍範圍 ❌ 請勿追高進場，等待價格回落至基準區間。若所有標的偏離度 <= 1% 則靜默。
- description: 自動下單 — 對 overall_signal=ENTER 且追高未觸發的標的呼叫 VM API 真實委託，記錄至 data/auto_orders_log.json
  agent_id: agt_0699a31c355072008000eeeb532e0b27
  agent_slug: order-execution-engine
  format_guide: '從 $step.4 讀取每個標的的 overall_signal 和 suggested_limit_price。從 $step.3
    讀取 recommended_lots 和 direction。對每個 overall_signal=ENTER 的標的，呼叫 VM API POST http://35.185.145.204:8080/api/order/stock，body:
    {symbol, action: BUY/SELL, quantity: lots, price: suggested_limit_price, order_type:
    limit, time_in_force: ROD, user_def: S1_AUTO_{symbol}}。記錄結果至 data/auto_orders_log.json。若無
    ENTER 訊號則輸出 {orders_placed: 0}。'
---

每個交易日 09:15 CST 執行。保護區結束，全面檢核 rank1/rank2 的 S1 進場條件（VWAP位置、量比、K棒形態、跳空方向），發出明確「進場/等待/放棄」指令 + 精確限價單價位。永久版 v1.0。