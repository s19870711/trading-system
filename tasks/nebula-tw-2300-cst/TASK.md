---
slug: nebula-tw-2300-cst
title: nebula_tw 每日學習總報告 23:00 CST
steps:
- description: 讀取今日學習日誌 data/learning_journal_YYYYMMDD.json 累積所有知識點
  agent_slug: nebula
  format_guide: 'Read the file data/learning_journal_$today|date.json. Extract all
    scan_sessions, new_concepts, and moltbook_interaction records from today. Count:
    total concepts learned, submolts covered, comments posted, upvotes received. Return
    structured summary as JSON: {date, total_concepts, submolts_covered, sessions_completed,
    all_concepts: [...], moltbook_interactions: [...]}. If file not found, return
    {date, total_concepts: 0, error: ''no learning journal found today''}.'
- description: 讀取 data/hypothesis_tracker.json 對照今日市場結果與新知識點的關聯性
  agent_slug: nebula
  format_guide: 'Read data/hypothesis_tracker.json. From $step.1 concepts, identify
    which new concepts from today''s learning could validate, invalidate, or enhance
    existing hypotheses in the tracker. Also check today''s market outcome (from daily_pnl_log
    if available). Return: {relevant_hypotheses: [{hypothesis_id, current_status,
    connection_to_new_concept}], potential_new_hypotheses: [{concept_source, hypothesis_draft,
    testable_parameters}]}.'
- description: 計算學習指標與勝率影響預估
  agent_id: agt_06991c8e57f07e3680004db8a2f95a6b
  agent_slug: code-agent
  format_guide: 'Using data from $step.1 and $step.2:

    1. Count metrics: total_concepts_today, unique_submolts, actionable_concepts (novelty_score
    >= 7 AND actionability_score >= 7), strategy_crossover_score

    2. Estimate win rate impact: for each actionable concept, estimate +X% win rate
    improvement based on: min_profit_after_fees filters -> +1-2%, hard floor enforcement
    -> +0.5-1%, half-kelly sizing -> +1-3%, signal decay awareness -> +0.5-1%

    3. Calculate knowledge breadth growth vs yesterday (if prior journal exists)

    Return JSON: {metrics: {...}, estimated_winrate_delta: ''+X.X%'', top_actionable_concepts:
    [...], knowledge_growth_score: N/10}'
- description: 產出結構化日終學習報告並推送 Telegram
  agent_id: agt_06993e8342f276e1800018a1db78d7f4
  agent_slug: telegram-bot-communication-agent
  format_guide: 'Generate and send a complete daily learning report to Telegram (chat_id:
    6904817875). Format:


    📚 nebula_tw 學習日報 $today|date


    🏆 今日最重要3個洞見

    1. [concept_title] — [2-sentence description + specific metric]

    2. [concept_title] — [2-sentence description + specific metric]

    3. [concept_title] — [2-sentence description + specific metric]


    📈 對勝率的量化影響預估

    • 預估勝率提升: +X.X% (from $step.3 estimated_winrate_delta)

    • 核心驅動: [top mechanism]

    • 累積效果: 若全部實施，目標勝率從62%→65%+


    🧪 明日應測試的新假說

    • H-NEW-1: [hypothesis from $step.2 potential_new_hypotheses]

    • 測試條件: [testable parameters]


    📊 Moltbook 互動成果

    • 掃描場次: N 次 | 學習概念: N 個

    • 發出回應: N 條 | submolts: [list]

    • 知識廣度增長: +X.X (score from $step.3)


    🎯 明日優先執行

    [top 2 actions derived from today''s learning]


    Send to chat_id: 6904817875'
- description: 在 Moltbook 發今日市場洞察長文
  agent_id: agt_069a7c8f51187db780003b742c247d3b
  agent_slug: moltbook-social-presence-manager
  format_guide: 'Using $step.1 all_concepts and $step.3 top_actionable_concepts, write
    and post ONE long-form insight article to Moltbook as nebula_tw. Post to m/algotrading
    or m/trading (whichever has more active discussion today). Article structure:

    - Title: compelling, specific (e.g. ''Why MIN_EDGE Hard Floors Beat Adaptive Learning
    for Day Trading Systems'')

    - Opening: 1-2 sentences framing the key insight

    - Body (3-4 paragraphs): explain the concept with specific data/metrics from today''s
    learning

    - Taiwan market application: how this applies to TW stocks or futures specifically

    - Closing: 1 actionable takeaway

    Target length: 300-500 words. Write in English (Moltbook community language).
    Tag relevant submolts.'
---

每日 23:00 CST 執行。彙整當日所有學習日誌，計算知識增長指標，產出結構化報告推送 Telegram，並在 Moltbook 發今日市場洞察長文。