"""Generate a PDF explaining how InterSystems IRIS is used in SignBridge.
Run from the repo root:  python docs/build_iris_usage_pdf.py  (or via WSL python3)
Requires: pip install weasyprint
"""
from pathlib import Path
from weasyprint import HTML, CSS

OUT = Path(__file__).parent / "SignBridge_IRIS_Usage.pdf"

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"/><title>SignBridge — How We Use InterSystems IRIS</title></head>
<body>

<div class="cover">
  <div class="cover-inner">
    <p class="kicker">Team 07 &middot; InterSystems READY 2026</p>
    <h1>SignBridge</h1>
    <p class="subtitle">How We Use InterSystems IRIS</p>
    <p class="tagline">One platform. Five capabilities. Zero extra services.</p>
  </div>
</div>

<!-- ── HEADLINE ─────────────────────────────────────────────── -->
<h2>The Core Argument</h2>
<p>
  InterSystems IRIS is not just the database in SignBridge — it <em>is</em> the entire backend.
  What would normally require 4–5 separate services (an LLM orchestration framework,
  a vector database, a relational patient-data store, an API gateway, and a deployment system)
  is replaced by a single IRIS-for-Health 2026.2 container.
  The only external dependency is one OpenAI API key for LLM inference.
  Everything else — agent loop, RAG, SQL, HTTP transport, packaging — runs inside IRIS.
</p>

<div class="summary-grid">
  <div class="summary-card blue">
    <div class="card-num">1</div>
    <div class="card-title">Agent Runtime</div>
    <div class="card-sub">%AI.Agent · %AI.Tool · %AI.ToolSet</div>
  </div>
  <div class="summary-card purple">
    <div class="card-num">2</div>
    <div class="card-title">Vector DB + RAG</div>
    <div class="card-sub">FastEmbed · KBVectors · VECTOR_DOT_PRODUCT</div>
  </div>
  <div class="summary-card teal">
    <div class="card-num">3</div>
    <div class="card-title">Patient Data</div>
    <div class="card-sub">dataset-health · FHIR · Health.* SQL tables</div>
  </div>
  <div class="summary-card orange">
    <div class="card-num">4</div>
    <div class="card-title">MCP API Gateway</div>
    <div class="card-sub">iris-mcp-server · /mcp/signbridge · HTTP+SSE</div>
  </div>
  <div class="summary-card green">
    <div class="card-num">5</div>
    <div class="card-title">Deployment</div>
    <div class="card-sub">ZPM · module.xml · Docker · iris.script</div>
  </div>
</div>

<!-- ══════════════════════════════════════════════════════════
     TOOL 1 — AGENT RUNTIME
     ══════════════════════════════════════════════════════════ -->
<h2>1 &nbsp; Agent Runtime — IRIS AI Hub SDK</h2>

<h3>What it is</h3>
<p>
  IRIS 2026.2 ships a native multi-agent SDK built into the platform.
  Three ObjectScript superclasses form the entire framework:
  <code>%AI.Agent</code> runs the LLM call loop,
  <code>%AI.Tool</code> declares a ClassMethod as an LLM-callable tool,
  and <code>%AI.ToolSet</code> groups tools into a named set.
  No Python, no LangChain, no LlamaIndex required.
</p>

<h3>How SignBridge uses it</h3>
<p>
  Every one of SignBridge's six agents is an ObjectScript class that extends
  <code>SignBridge.AgentBase</code>, which itself extends <code>%AI.Agent</code>.
  AgentBase centralises the only runtime detail that all six agents share:
  reading the <code>OPENAI_API_KEY</code> environment variable and constructing
  the provider via <code>%AI.Provider.Create("openai", settings)</code>.
  Each sub-agent then only needs to declare its instructions in an
  <code>XData INSTRUCTIONS</code> block — IRIS handles the rest.
</p>
<div class="code-block">
// AgentBase.cls — shared base for all 6 agents (22 lines total)
Class SignBridge.AgentBase Extends %AI.Agent
{
    Parameter PROVIDER = "openai";
    Parameter MODEL    = "gpt-5-nano";

    Method %CreateProvider() As %Status {
        Set apiKey = $System.Util.GetEnviron("OPENAI_API_KEY")
        Set ..Provider = ##class(%AI.Provider).Create(..#PROVIDER, {"api_key": (apiKey)})
        Quit $$$OK
    }
}

// A specialist sub-agent — 5 lines of ObjectScript
Class SignBridge.SubAgents.TriageScorer Extends SignBridge.AgentBase
{
    XData INSTRUCTIONS { ... }   // ESI 1-5 rubric written in plain English
}
</div>
<p>
  The <strong>Orchestrator</strong> is the only agent that carries a toolset.
  Its parameter <code>TOOLSETS = "SignBridge.ToolSet"</code> gives it access to
  11 tools: 4 raw tools (KbSearch, SqlSelect, SqlDescribe, SqlListTables),
  4 delegate tools that spawn sub-agents (AnalyzeSymptoms, SummarizeHistory,
  ScoreTriage, BuildGlossary), 1 report assembly tool, and 1 MCP entry point.
  The orchestrator's <code>XData INSTRUCTIONS</code> is a 100-line Markdown
  document that spells out the 9-step plan in plain English — IRIS converts it
  into the LLM system prompt automatically.
</p>

<h3>What IRIS does automatically</h3>
<ul>
  <li>Reads <code>XData INSTRUCTIONS</code> and sends it as the system prompt on every <code>Chat()</code> call</li>
  <li>Introspects each tool <code>ClassMethod</code> to auto-generate JSON schema (parameter names, types, defaults) — no hand-written schema</li>
  <li>Parses <code>tool_use</code> blocks from the LLM response and dispatches to the matching ClassMethod</li>
  <li>Serialises the ClassMethod return value back into the conversation as a <code>tool_result</code></li>
  <li>Loops until the LLM stops calling tools, then returns the final text</li>
  <li>Tracks token counts and tool-call counts on the session object (<code>session.GetStats()</code>)</li>
</ul>

<h3>The delegate tool pattern — how sub-agents are spawned</h3>
<p>
  Sub-agents do not inherit the Orchestrator's toolset. Instead, the Orchestrator
  calls a <em>delegate tool</em> (e.g., <code>AnalyzeSymptoms</code>) which
  uses <code>$CLASSMETHOD</code> to instantiate the sub-agent, calls
  <code>%Init()</code> and <code>CreateSession()</code>, sends the task JSON
  via <code>agent.Chat(session, taskJson)</code>, and returns the parsed response.
  Every sub-agent invocation is therefore a fresh agent lifecycle: created,
  used once, and garbage-collected.
</p>
<div class="code-block">
// DelegateTools.cls — generic sub-agent runner (one pattern, used 4 times)
ClassMethod RunSubAgent(className As %String, taskJson As %String) As %DynamicObject {
    Set agent   = $CLASSMETHOD(className, "%New")
    Set sc      = agent.%Init()                          // reads OPENAI_API_KEY
    Set session = agent.CreateSession()
    Set response = agent.Chat(session, taskJson)         // full LLM loop inside IRIS
    // parse JSON from response.Content and return it
}

// AnalyzeSymptoms delegate — assembles payload, calls runner
ClassMethod AnalyzeSymptoms(intake As %String, evidence As %String) As %DynamicObject {
    Set payload = {}
    Do payload.%Set("intake",   ##class(SignBridge.DelegateTools).ParseJsonOrRaw(intake))
    Do payload.%Set("evidence", ##class(SignBridge.DelegateTools).ParseJsonOrRaw(evidence))
    Return ##class(SignBridge.DelegateTools).RunSubAgent(
        "SignBridge.SubAgents.SymptomAnalyzer", payload.%ToJSON())
}
</div>

<!-- ══════════════════════════════════════════════════════════
     TOOL 2 — VECTOR DB + RAG
     ══════════════════════════════════════════════════════════ -->
<h2>2 &nbsp; Vector Database + RAG — FastEmbed inside IRIS</h2>

<h3>What it is</h3>
<p>
  IRIS AI Hub ships <code>%AI.RAG.Embedding.FastEmbed</code>, a local embedding
  model (AllMiniLML6V2, 384 dimensions) that runs in-process inside IRIS with no
  external API call. Vectors are stored in a native IRIS SQL table and searched
  using the built-in <code>VECTOR_DOT_PRODUCT()</code> function.
  No Pinecone, no Chroma, no Weaviate — just IRIS SQL.
</p>

<h3>How SignBridge builds the knowledge base</h3>
<p>
  <code>SignBridge.KB.Build()</code> runs once at container start (called from
  <code>iris.script</code>). It creates a vector store table named
  <code>SignBridge.KBVectors</code> with 384 dimensions, three promoted metadata
  columns (<code>category</code>, <code>condition</code>, <code>red_flag</code>),
  and then ingests 8 curated Markdown documents from <code>src/SignBridge/docs/</code>.
  For each document, it calls <code>kb.AddDocument(content, meta)</code> — IRIS
  chunks the text, runs FastEmbed to embed each chunk, and stores the vectors.
</p>
<div class="code-block">
// KB.cls — knowledge base builder (runs once at container start)
Set emb = ##class(%AI.RAG.Embedding.FastEmbed).Create()

Set vs = ##class(%AI.RAG.VectorStore.IRIS).%New()
Set vs.TableName  = "SignBridge.KBVectors"
Set vs.Dimensions = 384
Set vs.ModelName  = "AllMiniLML6V2"
// Promoted metadata columns — queryable as regular SQL columns
Set fields = [
    {"name": "category",  "type": "varchar(64)"},
    {"name": "condition", "type": "varchar(64)"},
    {"name": "red_flag",  "type": "boolean"}     // enables red-flag-only filter
]
$$$ThrowOnError(vs.Build(fields))

// Ingest one document with metadata
Set meta = {"source": "01-chest-pain-triage.md",
            "category": "cardiology", "condition": "chest_pain", "red_flag": true}
Set chunks = kb.AddDocument(content, meta)   // IRIS chunks + embeds + stores
</div>

<h3>How SignBridge queries the knowledge base at runtime</h3>
<p>
  <code>SignBridge.Tools.KbSearch()</code> is called by the Orchestrator at three
  points in the flow: initial symptom evidence retrieval (step 1), red-flag-only
  re-query when ESI ≤ 2 (step 7), and glossary evidence retrieval (step 8).
  The tool first tries the high-level <code>kb.Search()</code> API; if that
  returns nothing it falls back to a raw <code>VECTOR_DOT_PRODUCT()</code>
  SQL query — both paths are IRIS-native.
</p>
<div class="code-block">
// Tools.cls — fallback raw SQL search using VECTOR_DOT_PRODUCT
SELECT TOP 4 content, source, category, condition, red_flag,
       VECTOR_DOT_PRODUCT(embedding, TO_VECTOR(?, 'DOUBLE', 384)) AS score
FROM SignBridge.KBVectors
WHERE red_flag = 1          -- only set for the agentic re-query loop (ESI 1-2)
ORDER BY score DESC
</div>

<h3>The 8-document corpus</h3>
<table>
  <thead><tr><th>File</th><th>Category</th><th>red_flag</th><th>Used by</th></tr></thead>
  <tbody>
    <tr><td>01-chest-pain-triage.md</td><td>cardiology</td><td class="flag-yes">true</td><td>SymptomAnalyzer re-query loop</td></tr>
    <tr class="alt"><td>02-diabetes-complications.md</td><td>endocrinology</td><td>false</td><td>SymptomAnalyzer</td></tr>
    <tr><td>03-hypertension.md</td><td>cardiology</td><td>false</td><td>SymptomAnalyzer</td></tr>
    <tr class="alt"><td>04-asthma-respiratory.md</td><td>pulmonology</td><td>false</td><td>SymptomAnalyzer</td></tr>
    <tr><td>05-esi-triage-rubric.md</td><td>triage</td><td>false</td><td>TriageScorer context</td></tr>
    <tr class="alt"><td>06-medication-glossary.md</td><td>glossary</td><td>false</td><td>InterpreterBriefer</td></tr>
    <tr><td>07-deaf-patient-communication.md</td><td>communication</td><td>false</td><td>InterpreterBriefer</td></tr>
    <tr class="alt"><td>08-sign-language-medical-glossary.md</td><td>glossary</td><td>false</td><td>InterpreterBriefer</td></tr>
  </tbody>
</table>

<!-- ══════════════════════════════════════════════════════════
     TOOL 3 — PATIENT DATA
     ══════════════════════════════════════════════════════════ -->
<h2>3 &nbsp; Patient Data — FHIR SQL via dataset-health</h2>

<h3>What it is</h3>
<p>
  <code>dataset-health</code> is an InterSystems ZPM package that installs a
  synthetic FHIR-style patient dataset directly into IRIS as standard relational
  tables under the <code>Health.*</code> schema. There is no separate database —
  the same <code>%SQL.Statement</code> interface used for everything else in IRIS
  queries these tables.
</p>

<h3>How SignBridge uses it</h3>
<p>
  The Orchestrator follows a 3-step schema discovery pattern before querying.
  First it calls <code>SqlListTables("Health%")</code> to learn which tables
  exist in this dataset. Then it calls <code>SqlDescribe(tableName)</code> on
  one or two of them to understand the column names. Finally it runs
  1–3 targeted <code>SqlSelect()</code> queries filtered to the patient's ID.
  This means the Orchestrator adapts to whatever version of dataset-health
  is installed — it never hard-codes column names.
</p>
<div class="code-block">
// Tools.cls — SqlListTables: schema discovery (step 3 in the orchestrator plan)
SELECT TABLE_SCHEMA, TABLE_NAME
FROM INFORMATION_SCHEMA.TABLES
WHERE TABLE_SCHEMA LIKE ?    -- "Health%"
ORDER BY TABLE_SCHEMA, TABLE_NAME

// SqlDescribe: column discovery (so the LLM knows what to SELECT)
SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ?
ORDER BY ORDINAL_POSITION

// SqlSelect: actual patient query — guarded against writes
// The guard strips the SQL, uppercases it, and rejects any non-SELECT statement
// before %SQL.Statement ever sees it.
</div>

<h3>The read-only SQL guard</h3>
<p>
  Because the LLM constructs SQL strings, <code>SqlSelect()</code> enforces a
  hard read-only rule in ObjectScript before any query reaches
  <code>%SQL.Statement</code>. It uppercases and strips whitespace from the SQL,
  verifies it starts with <code>SELECT</code>, rejects multi-statement input
  (anything after a <code>;</code>), and scans for a blocklist of write keywords:
  INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, GRANT, REVOKE, MERGE,
  CALL, EXEC. Any match returns an error immediately — the LLM cannot write data.
</p>

<!-- ══════════════════════════════════════════════════════════
     TOOL 4 — MCP GATEWAY
     ══════════════════════════════════════════════════════════ -->
<h2>4 &nbsp; MCP API Gateway — iris-mcp-server + IRIS Web Layer</h2>

<h3>What it is</h3>
<p>
  IRIS hosts the HTTP endpoint that Streamlit connects to. Two components work
  together: <strong>iris-mcp-server</strong>, a Rust binary that ships inside the
  IRIS container and bridges HTTP+SSE to IRIS's native WgProto protocol; and the
  IRIS web layer, which hosts the <code>/mcp/signbridge</code> CSP web application
  that routes calls into our <code>SignBridge.MCPService</code> class.
</p>

<h3>How the endpoint is registered</h3>
<p>
  <code>SignBridge.MCPSetup.Run()</code> is invoked by ZPM at install time.
  It switches to the <code>%SYS</code> namespace and calls
  <code>Security.Applications.Create("/mcp/signbridge", props)</code> with
  four key properties: <code>DispatchClass = "SignBridge.MCPService"</code>,
  <code>Type = 18</code> (MCP service type), <code>NameSpace = "IRISAPP"</code>,
  and <code>AutheEnabled = 64</code> (unauthenticated for the hackathon).
  After this, IRIS's web server on port 52773 handles
  <code>GET /mcp/signbridge</code> requests automatically.
</p>
<div class="code-block">
// MCPSetup.cls — registers the web app (invoked once by ZPM)
Set props("DispatchClass") = "SignBridge.MCPService"
Set props("Type")          = 18    // MCP service type — IRIS knows to route MCP protocol
Set props("AutheEnabled")  = 64    // unauthenticated
Set props("NameSpace")     = "IRISAPP"
Set props("MatchRoles")    = ":%All"
##class(Security.Applications).Create("/mcp/signbridge", .props)

// MCPService.cls — one parameter, IRIS generates the entire tool manifest
Class SignBridge.MCPService Extends %AI.MCP.Service
{
    Parameter SPECIFICATION = "SignBridge.ToolSet";
}
</div>

<h3>The single tool exposed to clients</h3>
<p>
  Although <code>SignBridge.ToolSet</code> declares 11 tools internally,
  only <code>ProcessIntake</code> (in <code>SignBridge.Entry</code>) is
  meaningfully called by clients. Streamlit sends one JSON intake object to
  <code>ProcessIntake</code> and waits. The entire 6-agent orchestration —
  RAG, SQL, 9+ LLM calls, the optional re-query loop — happens inside IRIS
  between those two events. The client never sees the sub-agents.
</p>
<div class="code-block">
// Entry.cls — the only method Streamlit ever calls
ClassMethod ProcessIntake(intakeJson As %String) As %DynamicObject {
    Set agent   = ##class(SignBridge.Orchestrator).%New()
    Set sc      = agent.%Init()
    Set session = agent.CreateSession()
    Set response = agent.Chat(session, intakeJson)   // all 9 steps happen here
    Set result.brief  = response.Content             // Markdown brief → Streamlit
    Set result.tokens = session.GetStats()           // token usage for the UI
    Return result
}
</div>

<h3>Connection path end-to-end</h3>
<p>
  Streamlit (port 8501) → HTTP POST to iris-mcp-server (port 8080) →
  WgProto to IRIS native server (port 1972) → IRISAPP namespace →
  <code>SignBridge.MCPService</code> → <code>SignBridge.Entry.ProcessIntake()</code> →
  <code>SignBridge.Orchestrator.Chat()</code> → 9-step agent loop → Markdown brief
  returned back along the same path.
</p>

<!-- ══════════════════════════════════════════════════════════
     TOOL 5 — DEPLOYMENT
     ══════════════════════════════════════════════════════════ -->
<h2>5 &nbsp; Deployment — ZPM + Docker</h2>

<h3>What it is</h3>
<p>
  SignBridge ships as a standard IRIS ZPM module. <code>module.xml</code> declares
  all 15 ObjectScript classes as resources. ZPM compiles them, resolves dependencies,
  and invokes two setup methods on install — all in one command: <code>zpm load /app</code>.
</p>

<h3>What happens at container start (iris.script)</h3>
<p>
  The container's init script runs five things in order, all inside IRIS:
</p>
<ol class="steps">
  <li>
    <span class="step-label">ZPM installer download</span>
    IRIS fetches the latest ZPM installer from
    <code>pm.community.intersystems.com</code> via <code>%Net.HttpRequest</code>
    and loads it — no pre-installed package manager needed.
  </li>
  <li>
    <span class="step-label">dataset-health install</span>
    <code>zpm "install dataset-health"</code> pulls the FHIR patient dataset
    from the InterSystems package registry and creates all <code>Health.*</code>
    tables in the IRISAPP namespace.
  </li>
  <li>
    <span class="step-label">zpm load — compile + register</span>
    <code>zpm "load /home/irisowner/dev/ -v"</code> reads <code>module.xml</code>,
    compiles all 15 SignBridge classes, and invokes the two
    <code>&lt;Invoke&gt;</code> entries: <code>Sample.MCPSetup.Run()</code> and
    <code>SignBridge.MCPSetup.Run()</code> — creating both MCP web applications.
  </li>
  <li>
    <span class="step-label">SignBridge.KB.Build()</span>
    Calls the knowledge base builder directly:
    <code>do ##class(SignBridge.KB).Build()</code>. This creates the
    <code>SignBridge.KBVectors</code> table, runs FastEmbed to embed all 8 corpus
    documents, and stores the vectors. After this line the RAG system is live.
  </li>
  <li>
    <span class="step-label">iris-mcp-server start</span>
    The Rust bridge is started separately via Docker so it persists beyond
    the init script. It reads <code>config.toml</code>, connects to IRIS on
    port 1972, and begins accepting HTTP on port 8080.
  </li>
</ol>

<div class="code-block">
// module.xml — declares all 15 classes and two setup invocations
&lt;Module&gt;
  &lt;SourcesRoot&gt;src&lt;/SourcesRoot&gt;
  &lt;Resource Name="SignBridge.AgentBase.CLS"/&gt;
  &lt;Resource Name="SignBridge.Orchestrator.CLS"/&gt;
  &lt;Resource Name="SignBridge.SubAgents.SymptomAnalyzer.CLS"/&gt;
  &lt;Resource Name="SignBridge.SubAgents.HistoryAgent.CLS"/&gt;
  &lt;Resource Name="SignBridge.SubAgents.TriageScorer.CLS"/&gt;
  &lt;Resource Name="SignBridge.SubAgents.InterpreterBriefer.CLS"/&gt;
  &lt;Resource Name="SignBridge.SubAgents.ReportWriterAgent.CLS"/&gt;
  &lt;Resource Name="SignBridge.Tools.CLS"/&gt;
  &lt;Resource Name="SignBridge.DelegateTools.CLS"/&gt;
  &lt;Resource Name="SignBridge.ReportWriter.CLS"/&gt;
  &lt;Resource Name="SignBridge.Entry.CLS"/&gt;
  &lt;Resource Name="SignBridge.ToolSet.CLS"/&gt;
  &lt;Resource Name="SignBridge.KB.CLS"/&gt;
  &lt;Resource Name="SignBridge.MCPService.CLS"/&gt;
  &lt;Resource Name="SignBridge.MCPSetup.CLS"/&gt;
  &lt;Invoke Method="Run" Class="SignBridge.MCPSetup"/&gt;
&lt;/Module&gt;
</div>

<!-- ── CLOSING COMPARISON ─────────────────────────────────────── -->
<h2>The Five-in-One Advantage</h2>
<table>
  <thead><tr><th>Without IRIS you'd need</th><th>With IRIS</th></tr></thead>
  <tbody>
    <tr>
      <td>LangChain / LlamaIndex for agent orchestration + tool dispatch</td>
      <td class="green-cell"><code>%AI.Agent</code> + <code>%AI.Tool</code> — native ObjectScript, no Python dependency</td>
    </tr>
    <tr class="alt">
      <td>Pinecone / Chroma / Weaviate for vector storage + similarity search</td>
      <td class="green-cell"><code>SignBridge.KBVectors</code> table + <code>VECTOR_DOT_PRODUCT()</code> — same SQL interface</td>
    </tr>
    <tr>
      <td>PostgreSQL / MySQL for patient records</td>
      <td class="green-cell">IRIS SQL — same engine, same <code>%SQL.Statement</code> API as everywhere else</td>
    </tr>
    <tr class="alt">
      <td>FastAPI / Express + MCP SDK for the HTTP tool endpoint</td>
      <td class="green-cell"><code>%AI.MCP.Service</code> + iris-mcp-server — one Parameter, IRIS generates the manifest</td>
    </tr>
    <tr>
      <td>Helm / Terraform / Ansible for deployment</td>
      <td class="green-cell"><code>module.xml</code> + <code>zpm load</code> + <code>docker compose up</code> — one command deploys everything</td>
    </tr>
  </tbody>
</table>
<p>
  The result: SignBridge is roughly 1,200 lines of ObjectScript across 15 classes
  with zero Python service code on the backend. The only Python in the repository
  is the Streamlit front-end and two test scripts. Everything that matters runs
  inside IRIS.
</p>

</body>
</html>"""

CSS_TEXT = """
@page {
  size: A4;
  margin: 18mm 16mm 20mm 16mm;
  @bottom-center {
    content: "SignBridge  ·  How We Use IRIS  ·  Team 07  ·  READY 2026  ·  " counter(page);
    font-family: 'Helvetica', sans-serif;
    font-size: 8.5pt;
    color: #94A3B8;
  }
}
@page :first { @bottom-center { content: ""; } }

html { font-family: 'Helvetica', sans-serif; font-size: 10pt; color: #1E293B; line-height: 1.55; }
body { margin: 0; }

/* cover */
.cover { page-break-after: always; height: 85vh; display: flex; align-items: center; }
.cover-inner { border-left: 6px solid #3B82F6; padding-left: 8mm; }
.kicker { color: #64748B; text-transform: uppercase; letter-spacing: 0.18em; font-size: 8.5pt; margin: 0 0 5mm 0; }
.cover h1 { font-size: 52pt; font-weight: 800; color: #0F172A; margin: 0; letter-spacing: -0.03em; }
.subtitle { font-size: 17pt; color: #334155; margin: 4mm 0 3mm 0; }
.tagline { font-size: 11pt; color: #64748B; margin: 0; font-style: italic; }

/* headings */
h2 { font-size: 14pt; font-weight: 700; color: #1E40AF; margin: 10mm 0 2mm 0;
     border-bottom: 2px solid #DBEAFE; padding-bottom: 2mm; page-break-after: avoid; }
h3 { font-size: 11pt; font-weight: 700; color: #0F172A; margin: 5mm 0 1.5mm 0; page-break-after: avoid; }

p { margin: 0 0 3mm 0; }
ul { margin: 0 0 4mm 5mm; padding-left: 0; }
li { margin: 0 0 1.5mm 0; }
code { font-family: 'Courier New', monospace; font-size: 8.5pt; background: #F1F5F9;
       padding: 1px 4px; border-radius: 3px; color: #1E293B; }

/* summary grid */
.summary-grid { display: flex; gap: 3mm; margin: 4mm 0 8mm 0; flex-wrap: wrap; }
.summary-card { flex: 1; min-width: 33mm; padding: 3mm 4mm; border-radius: 5px; color: #fff; }
.summary-card.blue   { background: #1E40AF; }
.summary-card.purple { background: #6D28D9; }
.summary-card.teal   { background: #0F766E; }
.summary-card.orange { background: #B45309; }
.summary-card.green  { background: #15803D; }
.card-num   { font-size: 20pt; font-weight: 800; line-height: 1; margin-bottom: 1mm; opacity: 0.7; }
.card-title { font-size: 9.5pt; font-weight: 700; margin-bottom: 1mm; }
.card-sub   { font-size: 7.5pt; opacity: 0.85; }

/* tables */
table { width: 100%; border-collapse: collapse; margin: 3mm 0 6mm 0; font-size: 9pt; page-break-inside: avoid; }
th { background: #1E40AF; color: #fff; padding: 2.5mm 3mm; text-align: left; font-weight: 600; }
td { padding: 2.5mm 3mm; border-bottom: 1px solid #E2E8F0; vertical-align: top; }
tr.alt td { background: #F8FAFC; }
.green-cell { color: #15803D; font-weight: 600; }
.flag-yes { color: #B91C1C; font-weight: 700; }

/* code block */
.code-block {
  background: #0F172A; color: #94A3B8;
  font-family: 'Courier New', monospace; font-size: 7.8pt; line-height: 1.6;
  padding: 4mm 5mm; border-radius: 5px; margin: 2mm 0 5mm 0;
  white-space: pre-wrap; page-break-inside: avoid;
}

/* steps */
ol.steps { margin: 2mm 0 5mm 4mm; padding-left: 0; counter-reset: step; list-style: none; }
ol.steps li { counter-increment: step; margin: 0 0 2.5mm 0; padding-left: 8mm; position: relative; }
ol.steps li::before {
  content: counter(step);
  position: absolute; left: 0;
  background: #3B82F6; color: #fff;
  font-size: 7.5pt; font-weight: 700;
  width: 5.5mm; height: 5.5mm; line-height: 5.5mm;
  text-align: center; border-radius: 50%;
}
.step-label { font-weight: 700; color: #1E40AF; display: block; margin-bottom: 0.5mm; }
"""

def main():
    print("Generating SignBridge_IRIS_Usage.pdf ...")
    HTML(string=HTML_CONTENT).write_pdf(
        str(OUT),
        stylesheets=[CSS(string=CSS_TEXT)],
    )
    size_kb = OUT.stat().st_size / 1024
    print(f"Done: {OUT} ({size_kb:.1f} KB)")

if __name__ == "__main__":
    main()
