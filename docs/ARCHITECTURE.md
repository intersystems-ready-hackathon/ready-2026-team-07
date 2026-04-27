# SignBridge — Architecture

Pre-visit clinical triage for deaf patients on InterSystems IRIS-for-Health AI Hub. Five views, top-down: **system stack**, **agent topology**, **end-to-end sequence**, **data flow**, **class hierarchy**.

---

## 1. System architecture

End-to-end deployment view. The orchestration is server-side; the only thing the client (Streamlit) ever calls over MCP is `ProcessIntake`.

```mermaid
flowchart LR
    User(["Doctor + Interpreter<br/>(via Streamlit UI)"])

    subgraph Host["Client host"]
        Streamlit["streamlit_app.py<br/>two-pane UI<br/>:8501"]
    end

    subgraph Container["Docker container · IRIS-for-Health 2026.2.0AI"]
        direction TB
        MCPSrv["iris-mcp-server (Rust)<br/>HTTP streaming transport<br/>:8080/mcp/signbridge"]

        subgraph IRIS["IRIS · IRISAPP namespace"]
            direction TB
            Web["Web server<br/>:52773"]
            Native["Native server (WgProto)<br/>:1972"]
            App["Application classes<br/>(orchestrator, sub-agents, tools)"]
            KB[("FastEmbed KB<br/>SignBridge.KBVectors<br/>384-dim · 8 docs")]
            Health[("dataset-health<br/>FHIR tables<br/>Health.*")]
        end
    end

    OpenAI["OpenAI API<br/>gpt-5-nano"]:::external

    User --> Streamlit
    Streamlit -->|"MCP / HTTP+SSE"| MCPSrv
    MCPSrv -->|"WgProto"| Native
    Native --> App
    App <--> KB
    App <--> Health
    App -.->|"chat / tool_use"| OpenAI

    classDef external fill:#F59E0B,stroke:#B45309,color:#fff,stroke-width:2px
    classDef boundary fill:#F8FAFC,stroke:#64748B,stroke-dasharray:5 5
    class Container,IRIS,Host boundary
```

**What's notable:**
- One MCP tool exposed to the client (`ProcessIntake`); everything else stays inside IRIS.
- RAG corpus is local (FastEmbed, no API key). Patient data is local (`dataset-health`).
- Only the LLM is external — and we only need one provider key.

---

## 2. Agent topology

The "wow" view. One parent agent plans the call sequence; five specialist sub-agents do focused work. The orchestrator **reviews** sub-agent outputs and triggers a re-query loop when the triage scorer flags red-flag urgency — that's what makes this *agentic*, not a chained pipeline.

```mermaid
flowchart TB
    Entry["<b>Entry.ProcessIntake</b><br/>MCP entry point"]:::entry

    subgraph OrchBox["Parent agent"]
        Orch["<b>Orchestrator</b><br/>%AI.Agent<br/>plan → delegate → review → re-query"]:::agent
    end

    subgraph ToolSet["SignBridge.ToolSet — 11 tools attached to Orchestrator"]
        direction LR
        T1["KbSearch"]:::tool
        T2["SqlListTables<br/>SqlDescribe<br/>SqlSelect"]:::tool
        T3["AnalyzeSymptoms"]:::deleg
        T4["SummarizeHistory"]:::deleg
        T5["ScoreTriage"]:::deleg
        T6["BuildGlossary"]:::deleg
        T7["AssembleReport"]:::deleg
    end

    subgraph SubAgents["Specialist sub-agents — each spawned, run, terminated per call"]
        direction LR
        SA1["<b>SymptomAnalyzer</b><br/>conditions · differential · citations"]:::agent
        SA2["<b>HistoryAgent</b><br/>visits · meds · labs · context"]:::agent
        SA3["<b>TriageScorer</b><br/>ESI 1–5 · escalation · re-query flag"]:::agent
        SA4["<b>InterpreterBriefer</b><br/>glossary · sign cues · tone"]:::agent
        SA5["<b>ReportWriterAgent</b><br/>Markdown brief composer"]:::agent
    end

    KB[("FastEmbed KB")]:::data
    Health[("Health.* tables")]:::data

    Entry -->|"Chat(intake)"| Orch
    Orch -.->|"tool_use"| T1
    Orch -.->|"tool_use"| T2
    Orch -.->|"tool_use"| T3
    Orch -.->|"tool_use"| T4
    Orch -.->|"tool_use"| T5
    Orch -.->|"tool_use"| T6
    Orch -.->|"tool_use"| T7

    T1 --> KB
    T2 --> Health
    T3 ==>|"%New + %Init + Chat"| SA1
    T4 ==>|"%New + %Init + Chat"| SA2
    T5 ==>|"%New + %Init + Chat"| SA3
    T6 ==>|"%New + %Init + Chat"| SA4
    T7 ==>|"%New + %Init + Chat"| SA5

    classDef entry fill:#0EA5E9,stroke:#0369A1,color:#fff,stroke-width:2px
    classDef agent fill:#3B82F6,stroke:#1E40AF,color:#fff,stroke-width:2px
    classDef tool fill:#10B981,stroke:#047857,color:#fff,stroke-width:2px
    classDef deleg fill:#14B8A6,stroke:#0F766E,color:#fff,stroke-width:2px
    classDef data fill:#8B5CF6,stroke:#6D28D9,color:#fff,stroke-width:2px
```

**Color key:** entry tool · parent + sub-agents · raw tools · delegate-task tools · data stores.

The orchestrator never talks to a sub-agent directly. It calls a **delegate tool** (e.g. `AnalyzeSymptoms`) which spawns the sub-agent, runs it, and returns its JSON output. This keeps every sub-agent invocation fully traceable in the activity log.

---

## 3. End-to-end sequence — the agentic flow

Nine-step plan with one re-query loop. The loop on the diagram is the centerpiece: when `TriageScorer` returns ESI ≤ 2 with `must_re_query_kb_for_red_flags = true`, the orchestrator goes back to the knowledge base for red-flag-only evidence and re-runs the symptom analyzer before assembling the brief.

```mermaid
sequenceDiagram
    autonumber
    participant U as Streamlit UI
    participant E as Entry.ProcessIntake
    participant O as Orchestrator
    participant KB as KbSearch
    participant SQL as SqlSelect
    participant SA as SymptomAnalyzer
    participant HA as HistoryAgent
    participant TS as TriageScorer
    participant IB as InterpreterBriefer
    participant RW as ReportWriterAgent

    U->>E: intake JSON (chief_complaint, age, sign_style, ...)
    E->>O: Chat(session, intake)

    O->>KB: KbSearch(complaint, topK=4)
    KB-->>O: evidence_v1
    O->>SA: AnalyzeSymptoms(intake, evidence_v1)
    SA-->>O: symptoms_v1<br/>{likely_conditions, differential, red_flags, topic_keywords}

    opt patient_id present
        O->>SQL: SqlListTables("Health%")
        O->>SQL: SqlSelect × 1–3 (visits / meds / labs)
        SQL-->>O: sql_results
    end
    O->>HA: SummarizeHistory(intake, sql_results)
    HA-->>O: history<br/>{prior_visits, active_problems, current_meds, allergies, context_for_doc}

    O->>TS: ScoreTriage(intake, symptoms_v1, history)
    TS-->>O: triage<br/>{esi_level, justification, red_flags, must_re_query_kb_for_red_flags}

    alt esi_level ≤ 2  ⚡ re-query loop
        rect rgb(254, 243, 199)
        O->>KB: KbSearch(complaint, redFlagOnly=true)
        KB-->>O: evidence_red_flag
        O->>SA: AnalyzeSymptoms(intake, evidence_v1 ∪ evidence_red_flag)
        SA-->>O: symptoms_final
        end
    else otherwise
        Note over O: symptoms_final ← symptoms_v1
    end

    O->>KB: KbSearch(topic_keywords + " glossary")
    KB-->>O: glossary_evidence
    O->>IB: BuildGlossary(intake, topic_keywords, glossary_evidence, triage)
    IB-->>O: glossary<br/>{glossary[], topic_summary, communication_tone, communication_tips}

    O->>RW: AssembleReport({intake, symptoms_final, history, triage, glossary})
    RW-->>O: report (Markdown)
    O-->>E: brief
    E-->>U: Pre-Visit Brief (rendered)
```

The yellow band is the agentic step. It does not fire for routine cases (ESI 3–5) — only when the triage scorer escalates. That conditional is in the orchestrator's instructions, not hard-coded in ObjectScript.

---

## 4. Data flow — what travels between agents

Each arrow shows the **shape** of the JSON passed between agents. Sub-agents always emit strict JSON (no prose) — only the report writer emits Markdown.

```mermaid
flowchart LR
    Intake["<b>intake</b><br/>chief_complaint<br/>duration<br/>age, sex<br/>sign_style<br/>known_conditions[]<br/>current_meds[]"]:::input

    Evidence["<b>evidence</b><br/>RAG hits<br/>{content,source,score,red_flag}[]"]:::data
    SqlR["<b>sql_results</b><br/>{query, rows[]}[]"]:::data

    Symptoms["<b>symptoms</b><br/>likely_conditions[]<br/>differential[]<br/>red_flags[]<br/>topic_keywords[]<br/>citations[]"]:::stage
    History["<b>history</b><br/>prior_visits[]<br/>active_problems[]<br/>current_meds[]<br/>relevant_labs[]<br/>context_for_doc"]:::stage
    Triage["<b>triage</b><br/>esi_level (1–5)<br/>label<br/>justification<br/>red_flags[]<br/>escalations_applied[]<br/>must_re_query_kb_for_red_flags"]:::stage
    Glossary["<b>glossary</b><br/>sign_style<br/>glossary[]{term,plain_english,sign_cue}<br/>topic_summary<br/>communication_tone<br/>communication_tips[]"]:::stage

    Brief["<b>Pre-Visit Brief</b><br/>(Markdown)<br/>For the Doctor<br/>For the Interpreter<br/>Sources"]:::output

    Intake --> Evidence
    Intake --> SqlR
    Intake --> Symptoms
    Evidence --> Symptoms

    Intake --> History
    SqlR --> History

    Intake --> Triage
    Symptoms --> Triage
    History --> Triage

    Triage -.->|"if esi ≤ 2"| Evidence

    Symptoms --> Glossary
    Triage --> Glossary
    Intake --> Glossary

    Symptoms --> Brief
    History --> Brief
    Triage --> Brief
    Glossary --> Brief

    classDef input fill:#0EA5E9,stroke:#0369A1,color:#fff
    classDef data fill:#8B5CF6,stroke:#6D28D9,color:#fff
    classDef stage fill:#3B82F6,stroke:#1E40AF,color:#fff
    classDef output fill:#22C55E,stroke:#15803D,color:#fff,stroke-width:3px
```

**Read it as:** the intake fans out to four parallel-ish sub-agents (symptoms, history, triage, glossary) whose outputs all converge on the report writer. The dotted feedback arrow from `triage` back to `evidence` is the agentic re-query loop.

---

## 5. Class hierarchy — the IRIS implementation

Every agent shares one base class; every tool extends one framework class; one toolset wires it all up. The whole system is 15 classes.

```mermaid
classDiagram
    class AIAgent["%AI.Agent"] {
        <<framework>>
        +Provider
        +Toolsets
        +CreateSession()
        +Chat(session, prompt)
    }
    class AITool["%AI.Tool"] {
        <<framework>>
    }
    class AIToolSet["%AI.ToolSet"] {
        <<framework>>
    }

    class AgentBase {
        +PROVIDER = openai
        +MODEL = gpt-5-nano
        +CreateProvider()
    }
    class Orchestrator {
        +TOOLSETS = SignBridge.ToolSet
        +XData INSTRUCTIONS
    }
    class SymptomAnalyzer { +XData INSTRUCTIONS }
    class HistoryAgent { +XData INSTRUCTIONS }
    class TriageScorer { +XData INSTRUCTIONS }
    class InterpreterBriefer { +XData INSTRUCTIONS }
    class ReportWriterAgent { +XData INSTRUCTIONS }

    class Tools {
        +KbSearch()
        +SqlSelect()
        +SqlDescribe()
        +SqlListTables()
    }
    class DelegateTools {
        +AnalyzeSymptoms()
        +SummarizeHistory()
        +ScoreTriage()
        +BuildGlossary()
        -RunSubAgent()
    }
    class ReportWriter { +AssembleReport() }
    class Entry { +ProcessIntake() }

    class SignBridgeToolSet["SignBridge.ToolSet"] {
        +XData Definition
    }
    class KB {
        +Build()
        +Open()
        +IngestCorpus()
    }
    class MCPService { +SPECIFICATION = ToolSet }
    class MCPSetup { +Run() }

    AIAgent <|-- AgentBase
    AgentBase <|-- Orchestrator
    AgentBase <|-- SymptomAnalyzer
    AgentBase <|-- HistoryAgent
    AgentBase <|-- TriageScorer
    AgentBase <|-- InterpreterBriefer
    AgentBase <|-- ReportWriterAgent

    AITool <|-- Tools
    AITool <|-- DelegateTools
    AITool <|-- ReportWriter
    AITool <|-- Entry

    AIToolSet <|-- SignBridgeToolSet
    SignBridgeToolSet --> Tools
    SignBridgeToolSet --> DelegateTools
    SignBridgeToolSet --> ReportWriter
    SignBridgeToolSet --> Entry

    Orchestrator --> SignBridgeToolSet
    DelegateTools --> SymptomAnalyzer
    DelegateTools --> HistoryAgent
    DelegateTools --> TriageScorer
    DelegateTools --> InterpreterBriefer
    ReportWriter --> ReportWriterAgent
```

**Why the design holds up:**
- **One base for all six agents** (`AgentBase`) — provider/model/key are configured once.
- **Sub-agents stay tool-free** — they receive evidence as JSON; the orchestrator owns retrieval. This makes their outputs reproducible and easy to unit-test.
- **One toolset** (`SignBridge.ToolSet`) is the entire MCP surface. Adding a new specialist is: write one `XData INSTRUCTIONS`, add one delegate tool method, ship.

---

## 6. Repository layout

```
ready-2026-team-07/
├── src/SignBridge/
│   ├── AgentBase.cls              ← shared %AI.Agent base
│   ├── Orchestrator.cls           ← parent agent + 9-step plan
│   ├── SubAgents/
│   │   ├── SymptomAnalyzer.cls
│   │   ├── HistoryAgent.cls
│   │   ├── TriageScorer.cls
│   │   ├── InterpreterBriefer.cls
│   │   └── ReportWriterAgent.cls
│   ├── Tools.cls                  ← KbSearch + SQL tools
│   ├── DelegateTools.cls          ← 4 sub-agent delegates
│   ├── ReportWriter.cls           ← AssembleReport tool
│   ├── Entry.cls                  ← ProcessIntake (MCP entry)
│   ├── ToolSet.cls                ← single MCP surface
│   ├── KB.cls                     ← FastEmbed builder
│   ├── MCPService.cls
│   ├── MCPSetup.cls
│   └── docs/                      ← 8-doc RAG corpus (.md)
├── app/
│   ├── streamlit_app.py           ← demo UI
│   └── test_signbridge.py         ← MCP smoke test
├── module.xml                     ← ZPM module spec
├── iris.script                    ← container init
├── config.toml                    ← iris-mcp-server config
└── docker-compose.yml
```
