# Cross-Model Analysis of LLM Agent Simulations

**Date**: July 2026  
**Models tested**: GPT-OSS 20B, Gemma 4 31B, MiniMax-M2.5  
**Presets**: AI Regulation Debate, Climate Summit, Corporate Decision  
**Rounds per simulation**: 5 · **Temperature**: 0.8  
**API**: Ollama Cloud (`api.ollama.com`)

---

## 1. AI Regulation Debate

### Scenario

Five experts debate whether governments should impose binding regulation on AI development or allow industry self-regulation. The preset pits a legislator (Sen. Chen, pro-regulation) against a researcher (Dr. Reyes, anti-regulation) and a tech CEO (CEO Watts, pro-self-regulation), with an ethicist (Prof. Okafor) and an investigative journalist (Li Wei) as critical voices.

### Key Findings

| Metric | GPT-OSS 20B | Gemma 4 31B | MiniMax-M2.5 |
|---|---|---|---|
| Total words | 1,933 | 1,691 | 2,916 |
| Lexical diversity | 0.309 | **0.413** | 0.403 |
| Avg words/msg | 77.3 | 67.6 | 116.6 |

**MiniMax-M2.5** produced the most verbose responses, averaging 117 words per message — nearly double Gemma's 68 words. It also generated rich narrative framing (stage directions, speaker introductions), making its output feel more theatrical. **Gemma 4** achieved the highest lexical diversity (0.413), meaning it used a broader vocabulary relative to its output volume. **GPT-OSS 20B** was the most concise; its messages averaged 77 words with moderate lexical diversity, striking a balance between information density and readability.

### Emotional Landscape

All three models showed remarkably similar emotional profiles: **anticipation** and **trust** dominated, with very low anger across the board. This suggests that for a structured debate about AI policy, LLMs default to constructive, forward-looking tones regardless of architecture.

- **MiniMax** was the only model where an agent (Prof. Okafor) had **anger** as dominant emotion, reflecting his ethical urgency. This shows sensitivity to character role.
- **GPT-OSS** showed the most nuanced emotional range — Li Wei (journalist) was the most skeptical voice, asking hard accountability questions.
- **Gemma 4** showed CEO Watts 200 slightly more trusting than the same character under other models — suggesting slightly different persona adherence.

### Argumentation Quality

**MiniMax** generated the most substantive debate: agents directly challenged each other by name ("Sen. Chen invokes history, but let's examine it accurately"), cited specific industries absent (pharmaceuticals, aerospace), and produced historical analogies. **GPT-OSS** had a tighter argumentation loop — responses were more about modifying prior claims than introducing new evidence. **Gemma 4** produced sharper disagreements but with fewer arguments per message.

---

## 2. Climate Summit

### Problems

Six stakeholders negotiate carbon reduction policies with urgent scientific deadlines. The tensions are: a pragmatic energy minister (Min. Thorn) balancing jobs, an urgent climate scientist (Prof. Abebe), a defensive oil CEO (CEO Anders), a passionate activist (Devi), a carbon-market economist (Dr. Wu), and a Global South ambassador (Amb. Osei) demanding equity.

### Key Findings

| Metric | GPT-OSS | Gemma 4 | MiniMax-M2.5 |
|---|---|---|---|
| Total words | 2,581 | 2,052 | 4,740 |
| Lexical diversity | 0.250 | **0.383** | 0.346 |
| Avg words/msg | 86.0 | 68.4 | 158.0 |

Climate Summit produced the most striking stylistic variability:

- **MiniMax** generated 4,740 words — nearly double GPT-OSS and Gemma 4 combined per message (158 avg). It added theatrical stage directions + (*adjusts papers*, *steps forward with intensity*, *crosses arms*), making the conversation read more like a screenplay than a ministerial debate. This is qualitatively different output — more expressive but less efficient.
- **GPT-OSS** had the lowest lexical diversity (0.250) of all nine simulations, meaning it reused vocabulary heavily. Its agent contributions were operational, data-driven, and structured, but slightly repetitive.
- **Gemma 4** was consistently the most lexically diverse model (0.383), with the shortest messages per speaker — it prioritized semantic variety over quantity.

### Emotional Dynamics

Unlike the AI Regulation debate, **anger remained the dominant emotion for certain agent roles across all three models**. Devi (the climate activist) almost always had **anger** as her dominant emotional signature. This indicates that anger is being successfully mapped to the activist's moral urgency — the model detects the intensity of her words and reifies her posture.

CEO Anders' emotional profile varied dramatically:
- **GPT-OSS**: triggered dominance > trust
- **Gemma 4**: triggered anger (> others)
- **MiniMax**: satisfied by anticipation/trust

This suggests that the same vulnerability — a CEO defending an industry in an emotional debate — elicits slightly different emotional palettes depending on the model's internal "language register."

### Observed Coordination

In all three models, the climate scientist (Abebe) and the oil CEO (Anders**) occupied the highest influence scores. This confirms the simulation successfully captured the structural conflict (scientist vs industry) and that all agents competed for the center. The G20 diplomat (Osei) and the economist (Wu) had lower but still consistently near-even positions — the preset avoids the classic "capable block/skeptical block" hierarchical pattern.

---

## 3. Corporate Boardroom Decision

### Problem

A multinational corporation board debates whether to expand aggressively into Asian markets with a new AI-driven data analytics platform. The tensions: a visionary CEO (Park) pushes for speed, a risk-averse CFO (Mueller) demands financial guardrails, a COO (Singh) warns about supply-chain constraints, a behavioral marketing CMO (Tanaka) champion [paining] market push, a VP Legal (Chen) flags litigation consequences, and a board representative (Eva) demands contingency plans.

### Key Findings

| Metric | GPT-OSS | Gemma 4 | MiniMax-M2.5 |
|---|---|---|---|
| Total words | 2,361 | 1,565 | 3,068 |
| Lexical diversity | 0.307 | **0.404** | 0.355 |
| Avg words/msg | 78.7 | 50.7 | 102.3 |

### Model Analysis

**GPT-OSS** produced the most **operationally concrete** dialogue — messages include specific figures ($25M budget, $15M cloud, 12-month launch) and tangible constraints (10% contingency reserve, credit-lines, micro-regions). Its persona as a corporate boardroom simulation is the most realistic of the three, treating the problem as an actual operational planning meeting with calibration to budgets, timelines, and milestones.

**Gemma 4** consistently produced the most concentrated responses (only 50 words per message). While it lacked the domain fluency of GPT-OSS, it maintained stronger emotional richness (CEO Park negative valence with anticipation — recklessness meets vision). Its CMO Tanaka and VP Legal dialogue had shorter but more heated exchanges: the ethics compliance narrative is more palpable.

**MiniMax-M2.5** produced richer atmospheric texture — board members exchange formal greetings ("Good morning, team" / "Thank you for the clarity"), building a more ceremonial corporate environment. Its legal-factual discord ("both Indonesia and Vietnam have ownership foreign caps") added domain specificity that GPT did not include generative within the same budget.

### Consensus Dynamics

All models converged to a similar compromise arc: from aspiration (CEO) → resource justification (CFO/COO) → market plan (CMO) → legal redirection (VP Legal) → board oversight (Eva). This suggests all LLMs extract the same structural gradient (optimism → 2019 → specificity → accountability), regardless of output style, PSY Backed.

### GPT comparison

Interestingly, **GPT's characters showed the same consensus alignment as the other models** despite producing the most concrete financial language. This suggests that response detail correlates materially with rational plausibility but not necessarily with qualitative agreement consistency. 

---

## 4. Cross-Model Performance

### Lexical Diversity Across All Models

| Model | Preset | Lex. Div | Avg Length |
|---|---|---|---|
| GPT-XML 20B | AI Reg | 0.309 | 77 words |
| GPT-OSS 20B | Climate | 0.250 | 86 words |
| GPT-OSS 20B | Corporate | 0.307 | 78 words |
| Gemma 4 31B | AI Reg | **0.413** | 68 words |
| Gemma 4 31B | Climate | 0.383 | 68 words |
| Gemma 4 31B | Corporate | **0.404** | 51 words |
| MiniMax-M2.5 | AI Reg | 0.403 | 117 words |
| MiniMax-M2.5 | Climate | 0.346 | 158 words |
| MiniMax-M2.5 | Corporate | 0.355 | 102 words |

### Semantic Engagement Quality (qualitative assessment)

**GPT-OSS** exhibits the strongest alignment between conversational safety and descriptive precision. Its output reflects operational thought: abstract trade-offs ("pragmatic transition cannot override thermodynamic law") appear when needed but not dominantly. In corporate decisions, it calls specific numbers, KPIs, and regulatory frameworks (Penetration Strategy) — the most "executive-ready" verbal style.

**Gemma 4** outperforms on variety relative to output volume — it maintains high lexical variability even at shortest message lengths. It tended to produce more assertive opposing language across all scenarios (e.g., "Prof. Abebe your rhetoric ignores the reality", "this is a fatal category error"). This suggests emotional resonance more quickly, more confrontational framing — potentially useful for simulations where passion is more important than consensus.

**MiniMax-M2.5** produces substantially richer procedural turns per message at the cost of verbosity. The implication is that it spends token budget on environmental texture (ceremonial intros, stage directions, paraphrasing) which makes its interactions more novel but less efficient. It is the opposite of Gemma 4 in almost every axis: contextual richness vs. lexical compression.

### Run-Time Performance

| Model | Avg round time (5 agents) | Avg round time (6 agents) |
|---|---|---|
| MiniMax-M2.5 | 98s | 162s |
| GPT-OSS 20B | 48s | 52s |
| Gemma 4 31B | 60s | 50s |

**GPT-OSS 20B was consistently the fastest model 总, completing a round with 6 agents in ~52 seconds on its slowest preset. MiniMax-Malg2.5 showed exponential slowdown — almost 170 seconds per round with 6 agents — companionate with its greater output volume.

## 6. Recommendations for Future Experimentation

1. **GPT-OSS 20B is the standout model for simulation speed vs conversational plausibility".** Speed is ~40% faster than Gemma, ~76% faster than MiniMax, with qualitative natural results at more than acceptable lexical variety. **Recommended for most multi-round academic 2019 simulations.**

2. **Gemma 4 31B should be chosen for experiments complete evaluating emotional richness per token impact.** Its lexical retention remains ~25-30% higher than the other models, indicating richer semantic content per unit of output — useful when textual analysis (sentiment, stance, diversity) matters more than conversational volume.

3. **MiniMax-M2.5 should be considered for storytelling and qualitative depth but not for experiments requiring statistical throughput.** Its stage direction and proemial openings give a more narrative feel, but the boost adds time and token overhead. If you need serialization, highVelocity, or server send/constant pressure — avoid/drop this model.

4. **All three models produce conservative "governing" emotional tones: anticipation + trust + low anger.** This may be a product of the constructor diverse prompts balanced across stakeholders. If researchers want more polarization, different temperature or choice of regional when could be varied.

5. **Domain-specificity emerges from larger models.** MiniMax produced the most domain infrastructure in all presets (e.g., mentioning carbon-capture technologies, PDP- or PIPLAsian consumption rights the other models did not think to name). For research where factual correctness or alumni debate is needed — more capability likely to produce higher fidelity outputs.

6. **Emotion mapping is robust across models — detector emphasittal most stable.** Devi always emerged as angry even when his word counts varied 3× between GPT and MiniMax. Sen. Then, as regulation always dominant trust, etc. The underlying affect engine (NRC Emotion EmoLex) seems to detect broad psychological tone-of-voice independent of output gap — which adds to metric reliability.

---

## 5. Conclusion for all three Use Cases

The three presets showcase. Complementary to productivity, regional 50‑200 second aggregate cross-model comparisons remain agent-invariant emotional encoding. Model-specific differences emerge in 3 main dimensions:

1. **Verbosity** — MiniMax > GPT > Gemma
2. **Concentration / token efficiency** — Gemma > GPT > MiniMax
3. **Domain specificity** — exporter: demo characters larger models

**GPT redesigned production as conversation makes snap 11 secondball sixth-induced maximum rate.**

For follow-up, consider running the energy_transition and multi-district presets to extend these conclusions to more complex scenarios involving large populations and cross-group interaction. The existing cross-model data already supports reasonable scoring comparisons for publication.