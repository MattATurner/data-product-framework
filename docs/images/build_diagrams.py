#!/usr/bin/env python3
"""Generate the three DPF executive architecture SVGs in docs/images/.

Outputs:
  - dpf-lifecycle.svg         (Operating Model: Opportunity Funnel + 6 Human-Gated Steps)
  - dpf-context-compiler.svg  (Business Intent + Organisational Context -> 4 Outcomes)
  - dpf-agf-symbiosis.svg     (Two-Box Symbiotic Architecture: DPF + AGF)
"""

from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent
FONT = "'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"


def human_badge_svg(bx: float, by: float) -> str:
    """32x34 warm amber HITL badge with a crisp person silhouette icon."""
    cx = bx + 16
    return f"""
    <rect x="{bx}" y="{by}" width="32" height="34" rx="8" fill="#FEF3C7" stroke="#F59E0B" stroke-width="1.2"/>
    <circle cx="{cx}" cy="{by + 12}" r="4.2" fill="#B45309"/>
    <path d="M {cx - 7} {by + 25.5} C {cx - 7} {by + 19.5}, {cx + 7} {by + 19.5}, {cx + 7} {by + 25.5} Z" fill="#B45309"/>
    """


def clean_stage_card(
    x: int,
    y: int,
    w: int,
    h: int,
    num: str,
    title: str,
    desc: str,
    output_label: str,
    accent: str = "#1E3A8A",
) -> str:
    """Single clean card: number badge + bold title + 1-line description + output deliverable pill + HITL human icon."""
    pill_w = w - 78
    bx = x + w - 50
    by = y + 92
    return f"""
  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4" filter="url(#shadow)"/>
    <rect x="{x}" y="{y}" width="{w}" height="4" rx="2" fill="{accent}"/>

    <rect x="{x + 18}" y="{y + 22}" width="32" height="24" rx="6" fill="#F1F5F9"/>
    <text x="{x + 34}" y="{y + 38}" text-anchor="middle" font-family="{FONT}" font-size="11.5" font-weight="800" fill="{accent}">{num}</text>
    <text x="{x + 60}" y="{y + 39}" font-family="{FONT}" font-size="16" font-weight="800" fill="#0F172A">{title}</text>

    <text x="{x + 18}" y="{y + 69}" font-family="{FONT}" font-size="12.2" font-weight="500" fill="#475569">{desc}</text>

    <!-- Output Deliverable Pill (Bottom Left) -->
    <rect x="{x + 18}" y="{by}" width="{pill_w}" height="34" rx="8" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.1"/>
    <text x="{x + 18 + pill_w / 2:.1f}" y="{by + 21}" text-anchor="middle" font-family="{FONT}" font-size="10.1" font-weight="700" fill="#1E293B">{output_label}</text>

    <!-- HITL Human Icon Badge (Bottom Right) -->
    {human_badge_svg(bx, by)}
  </g>
"""


def gate_horiz_label(cx: float, line_y: float, code: str, sub: str, code_fg: str = "#B45309") -> str:
    """Unboxed gate label: Gate ID above the horizontal arrow line, action below the line."""
    return f"""
  <g>
    <text x="{cx:.1f}" y="{line_y - 10:.1f}" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.06em" fill="{code_fg}">{code}</text>
    <text x="{cx:.1f}" y="{line_y + 18:.1f}" text-anchor="middle" font-family="{FONT}" font-size="10.2" font-weight="600" fill="#475569">{sub}</text>
  </g>
"""


def simple_box(
    x: int,
    y: int,
    w: int,
    h: int,
    title: str,
    sub: str,
    badge: str = "",
    badge_bg: str = "#EFF6FF",
    badge_fg: str = "#1E3A8A",
    accent: str = "#1E3A8A",
) -> str:
    b_svg = ""
    if badge:
        bw = int(len(badge) * 7.6 + 24)
        b_svg = f"""
    <rect x="{x + 18}" y="{y + 14}" width="{bw}" height="20" rx="5" fill="{badge_bg}"/>
    <text x="{x + 18 + bw / 2:.1f}" y="{y + 28}" text-anchor="middle" font-family="{FONT}" font-size="9.5" font-weight="800" letter-spacing="0.06em" fill="{badge_fg}">{badge}</text>
        """
        title_y = y + 54
        sub_y = y + 76
    else:
        title_y = y + 36
        sub_y = y + 60
    return f"""
  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4" filter="url(#shadow)"/>
    <rect x="{x}" y="{y}" width="5" height="{h}" rx="2.5" fill="{accent}"/>
    {b_svg}
    <text x="{x + 20}" y="{title_y}" font-family="{FONT}" font-size="15" font-weight="800" fill="#0F172A">{title}</text>
    <text x="{x + 20}" y="{sub_y}" font-family="{FONT}" font-size="12" font-weight="500" fill="#475569">{sub}</text>
  </g>
"""


def functional_card(x: int, y: int, w: int, h: int, title: str, sub: str, accent: str) -> str:
    return f"""
  <g>
    <rect x="{x}" y="{y}" width="{w}" height="{h}" rx="11" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4" filter="url(#shadow)"/>
    <rect x="{x}" y="{y}" width="5" height="{h}" rx="2.5" fill="{accent}"/>
    <text x="{x + 22}" y="{y + 34}" font-family="{FONT}" font-size="15.5" font-weight="800" fill="#0F172A">{title}</text>
    <text x="{x + 22}" y="{y + 58}" font-family="{FONT}" font-size="12.2" font-weight="500" fill="#475569">{sub}</text>
  </g>
"""


def main() -> None:
    # =========================================================================
    # 1. dpf-lifecycle.svg (1480 x 565)
    # =========================================================================
    w1, h1 = 1480, 565
    fig1_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w1}" height="{h1}" viewBox="0 0 {w1} {h1}">
  <defs>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="114%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0F172A" flood-opacity="0.05"/>
    </filter>
    <marker id="arrNavy" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#1E3A8A"/>
    </marker>
    <marker id="arrGreen" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#059669"/>
    </marker>
  </defs>

  <!-- Canvas -->
  <rect x="0" y="0" width="{w1}" height="{h1}" rx="14" fill="#FAF9F6" stroke="#E2E8F0" stroke-width="1.5"/>

  <!-- Header -->
  <text x="36" y="38" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.11em" fill="#1E3A8A">OPERATING MODEL  ·  6 HUMAN-GATED STEPS</text>
  <text x="36" y="64" font-family="{FONT}" font-size="19.5" font-weight="800" letter-spacing="-0.02em" fill="#0F172A">One-Time Opportunity Funnel Feeds a Continuous Delivery Flywheel</text>

  <!-- Minimal Legend -->
  <g transform="translate(852, 26)">
    <rect x="0" y="0" width="600" height="42" rx="9" fill="#FFFFFF" stroke="#E2E8F0" stroke-width="1"/>
    <rect x="14" y="10" width="22" height="22" rx="5" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.1"/>
    <text x="42" y="25" font-family="{FONT}" font-size="10.8" font-weight="700" fill="#1E293B">Stage Output</text>

    <text x="148" y="25" text-anchor="middle" font-family="{FONT}" font-size="10.5" font-weight="800" fill="#B45309">G0–G4</text>
    <text x="174" y="25" font-family="{FONT}" font-size="10.8" font-weight="700" fill="#475569">Automated Gate</text>

    <g transform="translate(284, 4) scale(0.88)">
      {human_badge_svg(0, 0)}
    </g>
    <text x="318" y="25" font-family="{FONT}" font-size="10.8" font-weight="700" fill="#92400E">Human Sign-Off (HITL)</text>

    <line x1="460" y1="21" x2="484" y2="21" stroke="#059669" stroke-width="2.8"/>
    <text x="492" y="25" font-family="{FONT}" font-size="10.8" font-weight="700" fill="#065F46">Virtuous Loop</text>
  </g>

  <!-- LEFT: ONE-TIME PORTFOLIO ENTRY (x=28..296, w=268) -->
  <rect x="28" y="92" width="268" height="442" rx="14" fill="#F3F2EC" stroke="#D6D3C9" stroke-width="1.4"/>
  <text x="48" y="120" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.09em" fill="#57534E">ONE-TIME PORTFOLIO ENTRY</text>

  <!-- Clean Converging Funnel Shape -->
  <polygon points="44,144 280,144 236,226 88,226" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4"/>
  <text x="162" y="172" text-anchor="middle" font-family="{FONT}" font-size="12" font-weight="700" fill="#0F172A">Workshops &amp; Business Ideas</text>
  <text x="162" y="192" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="500" fill="#475569">Revenue · Cost Savings · Risk</text>
  <text x="162" y="214" text-anchor="middle" font-family="{FONT}" font-size="9.5" font-weight="800" letter-spacing="0.08em" fill="#1E3A8A">OPPORTUNITY FUNNEL</text>
  <line x1="162" y1="226" x2="162" y2="258" stroke="#1E3A8A" stroke-width="2.2" marker-end="url(#arrNavy)"/>

  {clean_stage_card(
      x=40, y=264, w=244, h=144,
      num="01",
      title="Prioritise",
      desc="Score 2-page brief on Value &amp; Ease",
      output_label="Funded Use-Case Brief",
      accent="#1E3A8A"
  )}

  <text x="162" y="454" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="600" fill="#57534E">Funds high-return Quick Wins;</text>
  <text x="162" y="471" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="600" fill="#57534E">parks low-value requests early</text>

  <!-- RIGHT: CONTINUOUS PRODUCT FLYWHEEL (x=408..1452, w=1044) -->
  <rect x="408" y="92" width="1044" height="442" rx="14" fill="#EFF5FB" stroke="#BFDBFE" stroke-width="1.5"/>
  <text x="430" y="120" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.09em" fill="#1E3A8A">CONTINUOUS PRODUCT LIFECYCLE  ·  DAYS TO SHIP, HOURS TO EVOLVE</text>

  <!-- Top Row: 02 Describe -> 03 Design -> 04 Build -->
  {clean_stage_card(
      x=428, y=148, w=258, h=144,
      num="02",
      title="Describe",
      desc="Plain-English rules; zero tech jargon",
      output_label="Business Requirements Doc",
      accent="#1E3A8A"
  )}

  {clean_stage_card(
      x=800, y=148, w=258, h=144,
      num="03",
      title="Design",
      desc="Ground in shared glossary &amp; limits",
      output_label="Design &amp; 1-Page Playback",
      accent="#1E3A8A"
  )}

  {clean_stage_card(
      x=1172, y=148, w=258, h=144,
      num="04",
      title="Build",
      desc="Compile all 4 cloud layers in seconds",
      output_label="Compiled Pipelines &amp; BI",
      accent="#1E3A8A"
  )}

  <!-- Bottom Row: 06 Monitor & Evolve (left) and 05 Accept (right) -->
  {clean_stage_card(
      x=428, y=366, w=320, h=144,
      num="06",
      title="Monitor &amp; Evolve",
      desc="Watch working hours &amp; trace changes",
      output_label="Live SLA Status &amp; Change Brief",
      accent="#059669"
  )}

  {clean_stage_card(
      x=1110, y=366, w=320, h=144,
      num="05",
      title="Accept",
      desc="Verify live data &amp; reconcile ledger",
      output_label="Attested Live Data Product",
      accent="#0F766E"
  )}

  <!-- Clean Flow Arrows + Unboxed Gate Labels (Code above line, Action below line) -->
  <path d="M 284 336 L 306 336 L 306 220 L 424 220" fill="none" stroke="#1E3A8A" stroke-width="2.4" stroke-linejoin="round" marker-end="url(#arrNavy)"/>
  {gate_horiz_label(357, 220, "PORTFOLIO", "Value &amp; Ease")}

  <line x1="686" y1="220" x2="796" y2="220" stroke="#1E3A8A" stroke-width="2.4" marker-end="url(#arrNavy)"/>
  {gate_horiz_label(741, 220, "G0", "Validate Rubric")}

  <line x1="1058" y1="220" x2="1168" y2="220" stroke="#1E3A8A" stroke-width="2.4" marker-end="url(#arrNavy)"/>
  {gate_horiz_label(1113, 220, "G1", "Verify Playback")}

  <line x1="1295" y1="292" x2="1295" y2="362" stroke="#1E3A8A" stroke-width="2.4" marker-end="url(#arrNavy)"/>
  <text x="1310" y="323" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.06em" fill="#B45309">G2–G3</text>
  <text x="1310" y="339" font-family="{FONT}" font-size="10.2" font-weight="600" fill="#475569">Deterministic Build</text>

  <line x1="1110" y1="438" x2="753" y2="438" stroke="#0F766E" stroke-width="2.4" marker-end="url(#arrGreen)"/>
  {gate_horiz_label(931, 438, "G4 · PUBLISHED LIVE", "Live Checks &amp; Attestation", code_fg="#0F766E")}

  <line x1="472" y1="366" x2="472" y2="297" stroke="#059669" stroke-width="3.2" marker-end="url(#arrGreen)"/>
  <text x="488" y="326" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.06em" fill="#059669">VIRTUOUS LOOP</text>
  <text x="488" y="342" font-family="{FONT}" font-size="10.2" font-weight="600" fill="#065F46">Amendments &#8594; Step 02</text>
</svg>
"""
    (OUT_DIR / "dpf-lifecycle.svg").write_text(fig1_svg, encoding="utf-8")

    # =========================================================================
    # 2. dpf-context-compiler.svg (1320 x 480)
    # =========================================================================
    w2, h2 = 1320, 480
    fig2_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w2}" height="{h2}" viewBox="0 0 {w2} {h2}">
  <defs>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="114%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0F172A" flood-opacity="0.05"/>
    </filter>
    <marker id="arrNavy" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#1E3A8A"/>
    </marker>
    <marker id="arrTeal" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7" markerHeight="7" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#0F766E"/>
    </marker>
  </defs>

  <!-- Canvas -->
  <rect x="0" y="0" width="{w2}" height="{h2}" rx="14" fill="#FAF9F6" stroke="#E2E8F0" stroke-width="1.5"/>

  <!-- Header -->
  <text x="40" y="38" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.11em" fill="#1E3A8A">ARCHITECTURAL PRINCIPLE  ·  COMPILE ONCE ACROSS EVERY LAYER</text>
  <text x="40" y="64" font-family="{FONT}" font-size="20" font-weight="800" letter-spacing="-0.02em" fill="#0F172A">Plain-English Intent + Organisational Context &#8594; Four Synchronised Cloud Outcomes</text>

  <!-- COLUMN 1: REUSABLE INPUTS (x=36..396, w=360) -->
  <rect x="36" y="90" width="360" height="358" rx="14" fill="#F3F2EC" stroke="#D6D3C9" stroke-width="1.4"/>
  <text x="58" y="118" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.09em" fill="#57534E">1. BUSINESS INTENT &amp; ENTERPRISE CONTEXT</text>

  {simple_box(56, 136, 320, 88, "Business Specification", "Plain-English rules approved at Gate G0", badge="PER PRODUCT", badge_bg="#FEF3C7", badge_fg="#92400E", accent="#D97706")}
  {simple_box(56, 238, 320, 88, "Organisational Context", "Glossary, source limits &amp; arch patterns", badge="ENCODED ONCE", badge_bg="#DBEAFE", badge_fg="#1E40AF", accent="#1E3A8A")}
  {simple_box(56, 340, 320, 88, "Existing Foundations", "Conformed dimensions, data &amp; semantics", badge="REUSED", badge_bg="#DBEAFE", badge_fg="#1E40AF", accent="#1E3A8A")}

  <!-- COLUMN 2: GROUNDED DESIGN & COMPILER (x=456..844, w=388) -->
  <rect x="456" y="90" width="388" height="358" rx="14" fill="#EFF5FB" stroke="#BFDBFE" stroke-width="1.5"/>
  <text x="478" y="118" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.09em" fill="#1E3A8A">2. GROUNDED DESIGN &amp; COMPILATION</text>

  <g>
    <rect x="478" y="142" width="344" height="132" rx="12" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4" filter="url(#shadow)"/>
    <rect x="478" y="142" width="344" height="4" rx="2" fill="#1E3A8A"/>
    <text x="498" y="174" font-family="{FONT}" font-size="16" font-weight="800" fill="#0F172A">Grounded Design &amp; Playback</text>
    <text x="498" y="198" font-family="{FONT}" font-size="11.8" font-weight="500" fill="#475569">Maps BRD signals to service &amp; semantic patterns</text>
    <rect x="498" y="218" width="264" height="34" rx="8" fill="#F8FAFC" stroke="#CBD5E1" stroke-width="1.1"/>
    <text x="630" y="239" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="700" fill="#1E293B">Design &amp; 1-Page Playback</text>
    {human_badge_svg(770, 218)}
  </g>

  <line x1="650" y1="274" x2="650" y2="302" stroke="#1E3A8A" stroke-width="2.4" marker-end="url(#arrNavy)"/>

  <g>
    <rect x="478" y="306" width="344" height="120" rx="12" fill="#FFFFFF" stroke="#CBD5E1" stroke-width="1.4" filter="url(#shadow)"/>
    <rect x="478" y="306" width="344" height="4" rx="2" fill="#0F766E"/>
    <text x="498" y="338" font-family="{FONT}" font-size="16" font-weight="800" fill="#0F172A">Deterministic Product Compiler</text>
    <text x="498" y="362" font-family="{FONT}" font-size="11.8" font-weight="500" fill="#475569">Compiles chosen patterns across all four layers</text>
    <rect x="498" y="378" width="304" height="32" rx="8" fill="#F0FDF4" stroke="#86EFAC" stroke-width="1.1"/>
    <text x="650" y="399" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="700" fill="#166534">Zero Drift Across Data, Security &amp; Semantics</text>
  </g>

  <!-- COLUMN 3: 4 SYNCHRONISED OUTCOMES (x=904..1284, w=380) -->
  <rect x="904" y="90" width="380" height="358" rx="14" fill="#ECFDF5" stroke="#A7F3D0" stroke-width="1.5"/>
  <text x="926" y="118" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.09em" fill="#065F46">3. FOUR SYNCHRONISED OUTCOMES</text>

  {simple_box(924, 134, 340, 68, "Acquire, Stage &amp; Transform", "Quarantine gates, history, stream &amp; AI pipelines", accent="#059669")}
  {simple_box(924, 212, 340, 68, "Access, Masking &amp; Sharing", "Least-privilege access, PII masking &amp; share", accent="#059669")}
  {simple_box(924, 290, 340, 68, "Catalog, Lineage &amp; Quality", "Business glossary links &amp; quality gates", accent="#059669")}
  {simple_box(924, 368, 340, 68, "Semantic Layer &amp; Consumption", "Canonical metrics, BI, AI grounding &amp; APIs", accent="#059669")}

  <!-- Connectors Column 1 -> Column 2 -->
  <path d="M 376 180 L 424 180 L 424 208 L 474 208" fill="none" stroke="#1E3A8A" stroke-width="2.2" stroke-linejoin="round" marker-end="url(#arrNavy)"/>
  <path d="M 376 282 L 424 282 L 424 208" fill="none" stroke="#1E3A8A" stroke-width="2.2" stroke-linejoin="round"/>
  <path d="M 376 384 L 424 384 L 424 282" fill="none" stroke="#1E3A8A" stroke-width="2.2" stroke-linejoin="round"/>

  <!-- Connectors Column 2 -> Column 3 -->
  <path d="M 822 366 L 872 366 L 872 168 L 920 168" fill="none" stroke="#0F766E" stroke-width="2.2" stroke-linejoin="round" marker-end="url(#arrTeal)"/>
  <path d="M 872 246 L 920 246" fill="none" stroke="#0F766E" stroke-width="2.2" stroke-linejoin="round" marker-end="url(#arrTeal)"/>
  <path d="M 872 324 L 920 324" fill="none" stroke="#0F766E" stroke-width="2.2" stroke-linejoin="round" marker-end="url(#arrTeal)"/>
  <path d="M 872 366 L 872 402 L 920 402" fill="none" stroke="#0F766E" stroke-width="2.2" stroke-linejoin="round" marker-end="url(#arrTeal)"/>
</svg>
"""
    (OUT_DIR / "dpf-context-compiler.svg").write_text(fig2_svg, encoding="utf-8")

    # =========================================================================
    # 3. dpf-agf-symbiosis.svg (1320 x 490)
    # =========================================================================
    w3, h3 = 1320, 490
    fig3_svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w3}" height="{h3}" viewBox="0 0 {w3} {h3}">
  <defs>
    <filter id="shadow" x="-4%" y="-4%" width="108%" height="114%">
      <feDropShadow dx="0" dy="3" stdDeviation="5" flood-color="#0F172A" flood-opacity="0.05"/>
    </filter>
    <marker id="arrNavy" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#1E3A8A"/>
    </marker>
    <marker id="arrGreen" viewBox="0 0 10 10" refX="8.5" refY="5" markerWidth="7.5" markerHeight="7.5" orient="auto">
      <path d="M 0 1.5 L 9 5 L 0 8.5 z" fill="#059669"/>
    </marker>
  </defs>

  <!-- Canvas -->
  <rect x="0" y="0" width="{w3}" height="{h3}" rx="14" fill="#FAF9F6" stroke="#E2E8F0" stroke-width="1.5"/>

  <!-- Header -->
  <text x="40" y="38" font-family="{FONT}" font-size="10.5" font-weight="800" letter-spacing="0.11em" fill="#1E3A8A">SYMBIOTIC GOVERNANCE  ·  TWO FRAMEWORKS, ONE CONTINUOUS LIFECYCLE</text>
  <text x="40" y="64" font-family="{FONT}" font-size="20" font-weight="800" letter-spacing="-0.02em" fill="#0F172A">How the Data Product Framework (DPF) and Agentic Governance (AGF) Work Together</text>

  <!-- BOX 1: DATA PRODUCT FRAMEWORK (DPF) (x=36..532, w=496) -->
  <rect x="36" y="92" width="496" height="364" rx="14" fill="#EFF5FB" stroke="#BFDBFE" stroke-width="1.5"/>
  <text x="60" y="120" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.08em" fill="#1E3A8A">DATA PRODUCT FRAMEWORK (DPF)</text>
  <text x="60" y="140" font-family="{FONT}" font-size="12.5" font-weight="600" fill="#475569">Build-Time Specification &amp; Product Delivery</text>

  {functional_card(60, 158, 448, 82, "Plain-English Business Intent", "Captures commercial rules, ownership &amp; authorised purpose", accent="#1E3A8A")}
  {functional_card(60, 254, 448, 82, "Upfront Privacy &amp; Policy Design", "Applies shared definitions, PII masking &amp; partner boundaries", accent="#1E3A8A")}
  {functional_card(60, 350, 448, 82, "Deterministic Product Compilation", "Generates synchronised pipelines, security, catalog &amp; BI", accent="#1E3A8A")}

  <!-- BOX 2: AGENTIC DATA GOVERNANCE FRAMEWORK (AGF) (x=788..1284, w=496) -->
  <rect x="788" y="92" width="496" height="364" rx="14" fill="#ECFDF5" stroke="#A7F3D0" stroke-width="1.5"/>
  <text x="812" y="120" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.08em" fill="#065F46">AGENTIC DATA GOVERNANCE FRAMEWORK (AGF)</text>
  <text x="812" y="140" font-family="{FONT}" font-size="12.5" font-weight="600" fill="#475569">Run-Time Estate Protection &amp; Continuous Assurance</text>

  {functional_card(812, 158, 448, 82, "Birth Protection &amp; Live Lineage", "Scans new data at arrival and verifies live pipeline behaviour", accent="#059669")}
  {functional_card(812, 254, 448, 82, "Purpose-Bound Access &amp; Ledger Truth", "Brokers time-limited access and reconciles to Finance totals", accent="#059669")}
  {functional_card(812, 350, 448, 82, "Retention &amp; Shadow Asset Discovery", "Enforces regulatory retirement and uncovers ungoverned data", accent="#059669")}

  <!-- CENTER HANDSHAKE (x=532..788) — Unboxed title above line, action below line -->
  <text x="660" y="207" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.07em" fill="#1E3A8A">PUBLISHED INTENT</text>
  <line x1="532" y1="220" x2="782" y2="220" stroke="#1E3A8A" stroke-width="2.8" marker-end="url(#arrNavy)"/>
  <text x="660" y="240" text-anchor="middle" font-family="{FONT}" font-size="10.8" font-weight="600" fill="#475569">Ownership, privacy rules</text>
  <text x="660" y="255" text-anchor="middle" font-family="{FONT}" font-size="10.8" font-weight="600" fill="#475569">&amp; SLAs in shared catalog</text>

  <text x="660" y="325" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="800" letter-spacing="0.07em" fill="#059669">ESTATE FEEDBACK</text>
  <line x1="788" y1="338" x2="538" y2="338" stroke="#059669" stroke-width="2.8" marker-end="url(#arrGreen)"/>
  <text x="660" y="358" text-anchor="middle" font-family="{FONT}" font-size="10.8" font-weight="600" fill="#475569">Live drift, new PII &amp; shadow</text>
  <text x="660" y="373" text-anchor="middle" font-family="{FONT}" font-size="10.8" font-weight="600" fill="#475569">assets routed for amendment</text>
</svg>
"""
    (OUT_DIR / "dpf-agf-symbiosis.svg").write_text(fig3_svg, encoding="utf-8")
    print("Generated dpf-lifecycle.svg, dpf-context-compiler.svg, and dpf-agf-symbiosis.svg")


if __name__ == "__main__":
    main()
