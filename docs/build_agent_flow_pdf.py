"""Generate a simple PDF explaining the SignBridge agent flow.
Run from the repo root:  python docs/build_agent_flow_pdf.py
Requires: pip install weasyprint
"""
from pathlib import Path
from weasyprint import HTML, CSS

OUT = Path(__file__).parent / "SignBridge_AgentFlow.pdf"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><title>SignBridge — Agent Flow</title></head>
<body>

<div class="cover">
  <div class="cover-inner">
    <p class="kicker">Team 07 &middot; InterSystems READY 2026</p>
    <h1>SignBridge</h1>
    <p class="subtitle">Pre-Visit Triage for Deaf Patients</p>
    <p class="tagline">Agent Flow &amp; Architecture</p>
  </div>
</div>

<!-- ── OVERVIEW ───────────────────────────────────────────────── -->
<h2>What is SignBridge?</h2>
<p>
  SignBridge prepares a <strong>pre-visit clinical briefing</strong> before a deaf patient
  connects to a doctor through a sign-language interpreter. When the appointment is booked,
  one MCP call triggers a multi-agent pipeline inside IRIS that produces a structured brief
  covering symptoms, patient history, triage urgency, and a medical glossary tailored to
  the patient's sign language.
</p>
<p>
  The problem solved: interpreters arrive cold, doctors have no symptom context, and
  triage urgency is invisible until the call is already underway. SignBridge fixes all
  three — before the call starts.
</p>

<!-- ── AGENT MAP ─────────────────────────────────────────────── -->
<h2>The Six Agents</h2>
<table>
  <thead>
    <tr><th>Agent</th><th>Role</th><th>Tools</th><th>Output (JSON)</th></tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>Orchestrator</strong><br/><em>parent agent</em></td>
      <td>Plans the 9-step call sequence. Delegates to four specialists, reviews results,
          triggers a re-query loop when TriageScorer flags ESI&nbsp;≤&nbsp;2,
          then calls ReportWriterAgent.</td>
      <td>KbSearch · SqlListTables · SqlDescribe · SqlSelect ·
          AnalyzeSymptoms · SummarizeHistory · ScoreTriage ·
          BuildGlossary · AssembleReport</td>
      <td>Delegates — final output is the Markdown brief</td>
    </tr>
    <tr class="alt">
      <td><strong>SymptomAnalyzer</strong><br/><em>sub-agent</em></td>
      <td>Analyses the chief complaint against the medical knowledge base.
          Returns likely conditions, differential diagnoses, red flags,
          and topic keywords for downstream agents.</td>
      <td>KbSearch (RAG over local medical docs, 384-dim FastEmbed)</td>
      <td><code>likely_conditions · differential · red_flags · topic_keywords · citations</code></td>
    </tr>
    <tr>
      <td><strong>HistoryAgent</strong><br/><em>sub-agent</em></td>
      <td>Pulls the patient's clinical history from the FHIR-style
          <em>dataset-health</em> tables: prior visits, active problems,
          current medications, allergies, and relevant labs.</td>
      <td>SqlListTables · SqlDescribe · SqlSelect</td>
      <td><code>prior_visits · active_problems · current_meds · relevant_labs · context_for_doc</code></td>
    </tr>
    <tr class="alt">
      <td><strong>TriageScorer</strong><br/><em>sub-agent</em></td>
      <td>Scores urgency using the Emergency Severity Index (ESI 1–5).
          No retrieval tools — pure clinical reasoning over the symptom
          and history JSON. Sets <code>must_re_query_kb_for_red_flags</code>
          when ESI&nbsp;≤&nbsp;2 to trigger the agentic loop.</td>
      <td>None (pure reasoning)</td>
      <td><code>esi_level · label · justification · red_flags · escalations_applied · must_re_query_kb_for_red_flags</code></td>
    </tr>
    <tr>
      <td><strong>InterpreterBriefer</strong><br/><em>sub-agent</em></td>
      <td>Builds a sign-language glossary for the interpreter.
          Matches medical terms to ASL/BSL/PSL sign cues,
          sets the communication tone (calm vs urgent),
          and produces tips for the specific sign style requested.</td>
      <td>KbSearch (glossary &amp; communication docs)</td>
      <td><code>glossary[{term, plain_english, sign_cue}] · topic_summary · communication_tone · communication_tips</code></td>
    </tr>
    <tr class="alt">
      <td><strong>ReportWriterAgent</strong><br/><em>sub-agent</em></td>
      <td>Assembles all four JSON blocks into a single structured
          Markdown brief — one section for the doctor, one for the
          interpreter, plus sourced citations from the knowledge base.</td>
      <td>None (composition only)</td>
      <td>Markdown brief (the final deliverable)</td>
    </tr>
  </tbody>
</table>

<!-- ── FLOW STEPS ─────────────────────────────────────────────── -->
<h2>Step-by-Step Flow</h2>
<ol class="steps">
  <li>
    <span class="step-label">Patient intake received</span>
    Streamlit sends a JSON intake object — <code>chief_complaint</code>, <code>duration</code>,
    <code>age</code>, <code>sex</code>, <code>sign_style</code>, <code>known_conditions</code>,
    <code>current_meds</code>, optional <code>patient_id</code> — to the IRIS MCP endpoint
    <code>/mcp/signbridge</code> via the <code>ProcessIntake</code> tool.
  </li>
  <li>
    <span class="step-label">Knowledge base search (initial)</span>
    The Orchestrator calls <strong>KbSearch</strong> with the chief complaint (topK=4).
    FastEmbed converts the query to a 384-dim vector and retrieves the most relevant
    chunks from the local <em>SignBridge.KBVectors</em> table.
    Result: <em>evidence_v1</em>.
  </li>
  <li>
    <span class="step-label">SymptomAnalyzer (first pass)</span>
    Orchestrator calls the <strong>AnalyzeSymptoms</strong> delegate tool with the intake and
    evidence_v1. A fresh SymptomAnalyzer sub-agent is spawned, runs, and returns
    <em>symptoms_v1</em> — a structured JSON with conditions, differentials, and red flags.
  </li>
  <li>
    <span class="step-label">History lookup (if patient_id present)</span>
    Orchestrator calls <strong>SqlListTables</strong> and then 1–3 <strong>SqlSelect</strong>
    queries to retrieve visit history, medications, and labs from the
    <em>dataset-health</em> FHIR tables. Results passed to the HistoryAgent delegate.
  </li>
  <li>
    <span class="step-label">HistoryAgent</span>
    Spawned with the intake and SQL results. Returns <em>history</em> JSON summarising
    prior visits, active problems, current meds, allergies, and a short context note
    for the doctor.
  </li>
  <li>
    <span class="step-label">TriageScorer</span>
    Receives intake + symptoms_v1 + history. Applies the ESI 1–5 rubric purely from
    reasoning (no tools). Returns <em>triage</em> JSON including ESI level, justification,
    red flags list, and the <code>must_re_query_kb_for_red_flags</code> flag.
  </li>
  <li>
    <span class="step-label agentic">⚡ Agentic re-query loop (ESI 1–2 only)</span>
    If ESI&nbsp;≤&nbsp;2 and the flag is set, the Orchestrator calls <strong>KbSearch</strong>
    again with <code>redFlagOnly=true</code> to surface high-urgency evidence, then
    re-runs <strong>AnalyzeSymptoms</strong> with the combined evidence set.
    The result (<em>symptoms_final</em>) replaces symptoms_v1 for the brief.
    For routine cases (ESI 3–5) this loop is skipped entirely.
  </li>
  <li>
    <span class="step-label">InterpreterBriefer</span>
    KbSearch for glossary + communication docs → BuildGlossary delegate.
    Returns a per-term sign-cue glossary, a communication tone rating, and
    interpreter tips tuned to the patient's sign style (ASL / BSL / PSL / …).
  </li>
  <li>
    <span class="step-label">ReportWriterAgent</span>
    AssembleReport tool packages intake + symptoms_final + history + triage + glossary
    into a Markdown brief. ReportWriterAgent composes two sections: one for the
    <strong>doctor</strong> (differential, urgency, history context) and one for the
    <strong>interpreter</strong> (glossary, communication tips, sign cues).
    The Orchestrator returns the brief to ProcessIntake, which returns it to Streamlit.
  </li>
</ol>

<!-- ── AGENTIC LOOP HIGHLIGHT ─────────────────────────────────── -->
<h2>The Agentic Loop — Why This Is Not a Pipeline</h2>
<div class="callout">
  <p>
    A chained pipeline always executes the same steps in the same order.
    SignBridge's Orchestrator <strong>reviews</strong> the TriageScorer output and makes
    a conditional decision: if the patient is flagged ESI&nbsp;1 or 2 (immediate / emergent),
    it goes back to the knowledge base with a red-flag filter and re-runs the symptom
    analysis before composing the brief. This loop is driven by the Orchestrator's
    INSTRUCTIONS XData — not hard-coded in ObjectScript — so it is genuine
    LLM-mediated planning, not a fixed branch.
  </p>
  <p>
    Demo prompt that triggers it: <em>"BSL speaker, age 58, diabetic on metformin,
    chest pain radiating to left arm for 2&nbsp;hours."</em>
    TriageScorer returns ESI&nbsp;1 → loop fires → cardiac red-flag evidence retrieved →
    SymptomAnalyzer adds aortic dissection and STEMI to the differential →
    brief surfaces emergency interpreter preparation notes.
  </p>
</div>

<!-- ── TECH STACK ─────────────────────────────────────────────── -->
<h2>Technology Stack</h2>
<table>
  <thead><tr><th>Layer</th><th>Technology</th><th>Detail</th></tr></thead>
  <tbody>
    <tr><td>Agent framework</td><td>IRIS AI Hub 2026.2</td><td><code>%AI.Agent</code>, <code>%AI.Tool</code>, <code>%AI.ToolSet</code></td></tr>
    <tr class="alt"><td>LLM</td><td>OpenAI gpt-5-nano</td><td>One provider key; all 6 agents share the same model</td></tr>
    <tr><td>RAG / embeddings</td><td>FastEmbed (local)</td><td>384-dim, no API key, <code>SignBridge.KBVectors</code> table</td></tr>
    <tr class="alt"><td>Patient data</td><td>dataset-health (FHIR)</td><td>IRIS SQL, <code>Health.*</code> tables, read-only guard</td></tr>
    <tr><td>MCP transport</td><td>iris-mcp-server (Rust)</td><td>HTTP+SSE on :8080, WgProto to IRIS :1972</td></tr>
    <tr class="alt"><td>UI</td><td>Streamlit</td><td>Two-pane: intake form + live brief, :8501</td></tr>
    <tr><td>Container</td><td>IRIS-for-Health 2026.2.0AI</td><td>Docker, IRISAPP namespace</td></tr>
  </tbody>
</table>

<!-- ── KB CORPUS ──────────────────────────────────────────────── -->
<h2>Knowledge Base Corpus (8 documents)</h2>
<ul>
  <li><strong>chest_pain_triage.md</strong> — Red flags, differential, cardiac vs non-cardiac signs</li>
  <li><strong>diabetes_complications.md</strong> — DKA, hypoglycaemia, neuropathy, renal involvement</li>
  <li><strong>hypertension.md</strong> — Hypertensive urgency vs emergency, BP thresholds</li>
  <li><strong>asthma_exacerbation.md</strong> — Severity grading, peak flow, albuterol dosing</li>
  <li><strong>common_medications.md</strong> — 20+ drugs: class, indication, common side-effects</li>
  <li><strong>esi_reference.md</strong> — ESI 1–5 rubric with clinical examples</li>
  <li><strong>deaf_communication_tips.md</strong> — Doctor/interpreter communication guidance</li>
  <li><strong>sign_language_medical_glossary.md</strong> — 30 terms in ASL / BSL / PSL with sign cues</li>
</ul>

</body>
</html>"""

CSS_TEXT = """
@page {
  size: A4;
  margin: 18mm 16mm 20mm 16mm;
  @bottom-center {
    content: "SignBridge Agent Flow  ·  Team 07  ·  READY 2026  ·  " counter(page);
    font-family: 'Helvetica', sans-serif;
    font-size: 8.5pt;
    color: #94A3B8;
  }
}
@page :first { @bottom-center { content: ""; } }

html { font-family: 'Helvetica', sans-serif; font-size: 10pt; color: #1E293B; line-height: 1.55; }
body { margin: 0; }

/* ── cover ── */
.cover {
  page-break-after: always;
  height: 85vh;
  display: flex;
  align-items: center;
}
.cover-inner {
  border-left: 6px solid #3B82F6;
  padding-left: 8mm;
}
.kicker { color: #64748B; text-transform: uppercase; letter-spacing: 0.18em; font-size: 8.5pt; margin: 0 0 5mm 0; }
.cover h1 { font-size: 52pt; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.03em; }
.subtitle { font-size: 17pt; color: #334155; margin: 4mm 0 3mm 0; }
.tagline { font-size: 11pt; color: #64748B; margin: 0; }

/* ── headings ── */
h2 { font-size: 14pt; font-weight: 700; color: #1E40AF; margin: 10mm 0 3mm 0;
     border-bottom: 2px solid #DBEAFE; padding-bottom: 2mm; page-break-after: avoid; }

/* ── body text ── */
p { margin: 0 0 3mm 0; }
code { font-family: 'Courier New', monospace; font-size: 8.5pt; background: #F1F5F9;
       padding: 1px 4px; border-radius: 3px; }

/* ── tables ── */
table { width: 100%; border-collapse: collapse; margin: 3mm 0 6mm 0;
        font-size: 9pt; page-break-inside: avoid; }
th { background: #1E40AF; color: #fff; padding: 2.5mm 3mm; text-align: left;
     font-weight: 600; }
td { padding: 2.5mm 3mm; border-bottom: 1px solid #E2E8F0; vertical-align: top; }
tr.alt td { background: #F8FAFC; }

/* ── steps list ── */
ol.steps { margin: 0 0 6mm 5mm; padding-left: 0; counter-reset: step; list-style: none; }
ol.steps li { counter-increment: step; margin: 0 0 3mm 0; padding-left: 8mm; position: relative; }
ol.steps li::before {
  content: counter(step);
  position: absolute; left: 0;
  background: #3B82F6; color: #fff;
  font-size: 8pt; font-weight: 700;
  width: 5.5mm; height: 5.5mm; line-height: 5.5mm;
  text-align: center; border-radius: 50%;
}
.step-label { font-weight: 700; color: #1E40AF; display: block; margin-bottom: 1mm; }
.step-label.agentic { color: #B45309; }

/* ── callout box ── */
.callout { background: #FFF7ED; border-left: 5px solid #F59E0B;
           padding: 4mm 5mm; margin: 3mm 0 6mm 0; border-radius: 0 4px 4px 0; }
.callout p { margin: 0 0 2mm 0; }
.callout p:last-child { margin-bottom: 0; }

/* ── lists ── */
ul { margin: 0 0 4mm 5mm; padding-left: 0; }
li { margin: 0 0 1.5mm 0; }
"""

def main():
    print("Generating SignBridge_AgentFlow.pdf ...")
    HTML(string=HTML_CONTENT).write_pdf(
        str(OUT),
        stylesheets=[CSS(string=CSS_TEXT)],
    )
    size_kb = OUT.stat().st_size / 1024
    print(f"Done: {OUT} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
