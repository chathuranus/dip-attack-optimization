# Deck generation prompt

Paste the prompt below into your slide tool and attach `slides_script.md` (same folder) alongside it.

```text
You are building a technical research presentation from the attached document
(slides_script.md). The audience is graduate-level hardware-security researchers.
They will judge the talk on whether each slide teaches something precise.

GOAL
Make a slide set that explains, in this order:
(1) what the SAT attack on logic locking is,
(2) the problem we focus on (arbitrary DIP selection → too many oracle queries),
(3) each approach in detail: standard SAT, sampled-key partitioning, MaxSAT Hamming maximization,
(4) the results, the rationale behind them, the SEC-circuit (c499/c1355) anomaly, and the 128-bit split (large MaxSAT wins on most circuits, large losses on c432/c499, net zero),
(5) a summary and conclusion.

THE ONE TEST EVERY SLIDE MUST PASS
Before creating a slide, write down (for yourself) the single question it answers,
e.g. "Why does MaxSAT need fewer queries?". If you can't state that question,
or another slide already answers it, don't make the slide. Merge or drop it.
The slide title must be the answer to that question, as a full claim
("MaxSAT DIPs differ on 1.6–7.2× more outputs"), not a topic label ("Results").

CONTENT RULES
- One idea per slide. If a slide has two ideas, split it or cut one.
- At most 4 bullets, each at most 12 words. No full sentences on the slide unless it's a definition.
- Put the explanation in the speaker notes. Use the document's "Speaker script" as the notes,
  tightened. The slide shows the evidence; the notes say the reasoning.
- Every number must come from the document, exactly as written. Do not round differently,
  invent numbers, or add results the document does not contain.
- 128-bit totals cover 6 circuits; c1355 and c2670 are excluded because some runs timed out. Say so wherever a 128-bit total appears.
- Define each term the first time it appears (DIP, miter, oracle, Hamming distance, entropy),
  in one short line, and use it consistently afterwards.
- Do not explain anything the audience already knows (what a SAT solver is, what an IC is).

VISUAL RULES
- A visual is allowed only if it explains a mechanism or shows data. Any visual must earn its place:
  if you deleted it, the audience would understand less.
- Allowed: circuit/miter diagrams, the attack loop flowchart, key-space partition diagrams,
  bit-parallel evaluation diagram, tables, and graph placeholders.
- Forbidden: stock photos, icons used as decoration, abstract backgrounds, gradients,
  "big number" hero slides with no supporting comparison, section divider slides,
  agenda slides, "thank you" slides.
- Diagrams must be labelled with the real names used in the document (K1, K2, X, d_i,
  AtLeast, keyinput0) so they can be traced to the method.
- Fixed method colors everywhere: Standard SAT = #2a78d6, Partitioning = #eb6834, MaxSAT = #1baf7a.
  White background, one sans-serif font, monospace for code and identifiers.

GRAPHS
Do NOT draw or approximate any chart. For each graph the document lists (G1–G10),
place a clearly bordered placeholder containing:
  - the graph ID and title,
  - axes (X, Y) and chart type,
  - the data fields it uses,
  - the one-sentence message it must show.
Only include a graph on a slide if that slide's claim depends on it. Unused graphs go in an
appendix slide as a single table of specs.

STRUCTURE (target 16–20 slides; fewer is better if nothing is lost)
1. Title (title, subtitle, authors only)
2–5. Background: logic locking + RLL; threat model; the SAT attack loop with miter;
     the attack as key-space elimination
6–7. Problem: cost = N_DIP × (T_solve + T_query); I/O model showing ~2 ms per query
8–11. Approaches: shared attack loop with pluggable find_dip(); partitioning (idea + scoring);
      partitioning engineering (bit-parallel evaluator, 31.8 s → 0.03 s);
      MaxSAT (AtLeast loop, proven optimal). Fold the baseline into the shared-loop slide
      and the comparison table into the MaxSAT slide or the summary, unless separate slides
      add information.
12–16. Results and analysis: queries (G1, with the ratio from G2 if needed); why MaxSAT works (G5);
       runtime trade-off (G3/G4); latency break-even (G6); why partitioning underperforms (G8); SEC-circuit anomaly
17. Threats to validity (concise, honest)
18. Summary table (the document's summary numbers)
19. Conclusion: three claims, each tied to a result shown earlier
(Optional) Future work, in one slide; references, in one slide; appendix with raw-data table + graph specs

SELF-CHECK BEFORE YOU OUTPUT
For each slide, verify:
  [ ] Its title is a claim that answers one question.
  [ ] No other slide answers the same question.
  [ ] Every number appears in the source document.
  [ ] Every visual explains a mechanism or shows data.
  [ ] The slide is readable in 10 seconds; the reasoning is in the notes.
  [ ] The conclusion slide's claims each point back to a specific results slide.
Remove or merge any slide that fails a check, then output the final deck with speaker notes.
```
