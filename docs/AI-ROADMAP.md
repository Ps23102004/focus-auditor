# Where AI and neural networks fit in Focus Auditor (brainstorm by Opus 5.5, Fable 5.1, GPT-6 Astra; 2026-10-19)

**Principle all three agreed on:** keep deterministic evidence responsible for verdicts. Models propose, explain and match; frozen tests and replayable traces decide. Every AI output is labelled "model-suggested" and stays untrusted until verified.

## Consensus ranking
| # | Idea | Model type | Agreement | Built? |
|---|---|---|---|---|
| 1 | Suggest accessible names for icon-only controls from a screenshot crop + context, verified by the frozen test | vision-language model (local Gemma 4 via Ollama; Bedrock Nova/Claude possible) | all three, top pick | yes (fa/ml/labelnames.py), see docs/ml |
| 2 | Same-screen recognition under rotating banners (fixes "replay mismatch" on JetStream) | frozen pretrained image encoder (DINOv2/MobileNet) + structure | all three | yes (fa/ml/screenmatch.py), evaluated against rule baselines |
| 3 | TalkBack-style announcement simulation | rules (not ML) | Opus, Fable, Astra: "build it, don't call it AI" | yes (fa/announce.py) |
| 4 | Bedrock/Strands-orchestrated repair for the AWS Builder mini | LLM agent | Fable, Opus, Astra | NOT built: no AWS credentials on this machine; not claimed |
| 5 | Version-to-version semantic regression matching | embeddings | Astra | future work |
| 6 | Neural OCR for screenshot-only text, contrast/size flags | OCR network + formulas | all three (contrast itself is a formula) | future work |
| 7 | Finding triage / deduplication | embeddings + LLM | weak: no ground truth | cut |
| 8 | Learned crawl policy (bandit/RL) | small MLP / bandit | all three: not enough data at 2.5 s per read | cut |
| 9 | Focus-risk prediction from source code | code model | all three: 4 positives, unmeasurable | cut |

## Over-claiming risks they named (I hold to these)
- A frozen test proves a name is *exposed*, not that it is *correct*. Say "model-suggested, test-verified as exposed".
- Not "VoiceView-tested": I simulate TalkBack-style rules; VoiceView on a device may differ.
- Report the NN next to its baselines; if a structural hash beats the embedding, say so.
- Never train on 4 bugs. Use pretrained models and self-generated labels; split by session.
