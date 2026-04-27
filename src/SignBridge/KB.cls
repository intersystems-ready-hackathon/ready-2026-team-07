/// SignBridge Knowledge Base - FastEmbed RAG over curated medical reference docs.
/// Build() is invoked once during container init from iris.script.
/// Re-running Build() is a no-op against an existing vector table; use Reseed() to wipe-and-rebuild.
Class SignBridge.KB Extends %RegisteredObject
{

Parameter VECTORTABLE = "SignBridge.KBVectors";

Parameter KBNAME = "signbridge_medical_kb";

Parameter DOCSDIR = "/home/irisowner/dev/src/SignBridge/docs/";

/// Build the FastEmbed-backed knowledge base and ingest the curated corpus.
ClassMethod Build() As %Status
{
    Set sc = $$$OK
    Try {
        Write "[SignBridge.KB] Building FastEmbed knowledge base...", !

        Set emb = ##class(%AI.RAG.Embedding.FastEmbed).Create()

        Set vs = ##class(%AI.RAG.VectorStore.IRIS).%New()
        Set vs.TableName = ..#VECTORTABLE
        Set vs.Dimensions = 384
        Set vs.ModelName = "AllMiniLML6V2"

        Set fields = [
            {"name": "category",  "type": "varchar(64)", "description": "Clinical category, e.g. cardiology, endocrinology, triage, glossary, communication"},
            {"name": "condition", "type": "varchar(64)", "description": "Specific condition keyword, e.g. chest_pain, diabetes, hypertension"},
            {"name": "red_flag",  "type": "boolean",     "description": "True for red-flag / emergency-tier evidence"}
        ]

        $$$ThrowOnError(vs.Build(fields))

        Set kb = ##class(%AI.RAG.KnowledgeBase).%New()
        Set kb.Name = ..#KBNAME
        Set kb.Description = "Medical reference knowledge base for SignBridge pre-visit triage. Covers chest pain, diabetes, hypertension, asthma, ESI rubric, medication glossary, deaf-patient communication, and sign-language cues."
        Set kb.TopK = 4
        $$$ThrowOnError(kb.Build(emb, vs))

        Do ..IngestCorpus(kb)

        Write "[SignBridge.KB] Knowledge base ready.", !
    } Catch ex {
        Set sc = ex.AsStatus()
        Write "[SignBridge.KB] BUILD FAILED: ", ex.DisplayString(), !
    }
    Quit sc
}

/// Wipe and rebuild — use during dev when corpus changes.
ClassMethod Reseed() As %Status
{
    Set sc = $$$OK
    Try {
        // Drop the vector table if it exists; ignore errors.
        Do $SYSTEM.SQL.Execute("DROP TABLE " _ ..#VECTORTABLE)
        Do $SYSTEM.SQL.Execute("DROP TABLE " _ ..#VECTORTABLE _ "_Config")
    } Catch {}
    Quit ..Build()
}

/// Open the existing knowledge base by name (used by tools at query time).
ClassMethod Open() As %AI.RAG.KnowledgeBase
{
    Quit ##class(%AI.RAG.KnowledgeBase).%OpenId(..#KBNAME)
}

/// Walk DOCSDIR and ingest each markdown file with hand-curated metadata.
ClassMethod IngestCorpus(kb As %AI.RAG.KnowledgeBase) As %Status
{
    Set manifest = ..Manifest()
    Set total = 0
    Set iter = manifest.%GetIterator()
    While iter.%GetNext(.key, .entry) {
        Set path = ..#DOCSDIR _ entry.file
        Set content = ..ReadFile(path)
        If content = "" {
            Write "[SignBridge.KB] WARNING: empty or missing file ", path, !
            Continue
        }
        Set meta = {
            "source":    (entry.file),
            "category":  (entry.category),
            "condition": (entry.condition),
            "red_flag":  (entry.red_flag)
        }
        Set chunks = kb.AddDocument(content, meta)
        Write "[SignBridge.KB]   indexed ", entry.file, " -> ", chunks, " chunks", !
        Set total = total + chunks
    }
    Write "[SignBridge.KB] Total chunks indexed: ", total, !
    Quit $$$OK
}

/// Hand-curated manifest of corpus docs and their metadata.
ClassMethod Manifest() As %DynamicArray
{
    Quit [
        {"file": "01-chest-pain-triage.md",            "category": "cardiology",     "condition": "chest_pain",         "red_flag": true},
        {"file": "02-diabetes-complications.md",       "category": "endocrinology",  "condition": "diabetes",           "red_flag": false},
        {"file": "03-hypertension.md",                 "category": "cardiology",     "condition": "hypertension",       "red_flag": false},
        {"file": "04-asthma-respiratory.md",           "category": "pulmonology",    "condition": "asthma",             "red_flag": false},
        {"file": "05-esi-triage-rubric.md",            "category": "triage",         "condition": "rubric",             "red_flag": false},
        {"file": "06-medication-glossary.md",          "category": "glossary",       "condition": "medications",        "red_flag": false},
        {"file": "07-deaf-patient-communication.md",   "category": "communication",  "condition": "deaf_communication", "red_flag": false},
        {"file": "08-sign-language-medical-glossary.md","category": "glossary",       "condition": "sign_cues",          "red_flag": false}
    ]
}

ClassMethod ReadFile(path As %String) As %String
{
    Set stream = ##class(%Stream.FileCharacter).%New()
    Set sc = stream.LinkToFile(path)
    If $$$ISERR(sc) Quit ""
    Set content = ""
    While 'stream.AtEnd {
        Set content = content _ stream.Read(32000)
    }
    Quit content
}

}
