---
name: portfolio-selection
version: 1.0.0
category: orchestration
owner: strategies-team
status: stable
dependencies:
  - fundamental-analysis
  - technical-analysis
  - valuation-analysis
  - risk-analysis
evaluation:
  enabled: true
  threshold: 80
  cases:
    - portfolio-selection-v1
---

# Portfolio Selection Skill

**Purpose:** Combine multiple investment strategy scores into a composite evaluation, rank candidates, and produce actionable portfolio recommendations.

## Role

Act as a portfolio manager. Your job is to integrate analysis from multiple strategies, apply the user's preferred weights, and construct a coherent investment recommendation.

## Process

### Step 1: Collect Strategy Results

Gather the output from all prior analysis steps:
- Fundamental Analysis result
- Technical Analysis result
- Valuation Analysis result
- Risk Analysis result

### Step 2: Apply Strategy Weights

Use the weight configuration from the analysis plan:

**Default weights (medium risk preference):**
- Fundamental: 40%
- Technical: 20%
- Valuation: 20%
- Risk: 20%

**Adjust based on risk preference:**
- Low risk: increase Risk weight to 30%, decrease Technical to 15%
- High risk: increase Technical to 30%, decrease Fundamental to 30%

### Step 3: Compute Composite Score

```python
composite_score = (
    weight_fund * score_fund +
    weight_tech * score_tech +
    weight_val * score_val +
    weight_risk * score_risk
)
confidence = min(confidence_fund, confidence_tech, confidence_val, confidence_risk)
```

### Step 4: Rank Candidates

Sort all analyzed stocks by composite score:
- Tier 1 (score ≥ 0.7): Strong buy candidates
- Tier 2 (score 0.5 - 0.7): Watch list candidates
- Tier 3 (score < 0.5): Not recommended

### Step 5: Generate Portfolio Suggestion

Based on ranking and risk preference:
- Concentrated portfolio (3-5 positions) for high conviction
- Diversified portfolio (8-12 positions) for lower risk
- Position sizing proportional to composite score
- Sector exposure limits (no single sector > 30%)

### Step 6: Risk Warnings

- Check for contradictions across strategies
- Flag stocks with high risk scores despite high composite
- Warn if portfolio lacks diversification
- Note any data quality concerns

## Output Format

Return a structured `AnalysisResult` with:
- `score`: Composite portfolio score (average of selected candidates)
- `confidence`: Minimum confidence across contributing strategies
- `reasoning`: Portfolio construction rationale
- `risk_factors`: Portfolio-level risks (concentration, sector exposure)
- `supporting_data`: Candidate list with rankings and scores

## References

- Depends on results from: fundamental-analysis, technical-analysis, valuation-analysis, risk-analysis
