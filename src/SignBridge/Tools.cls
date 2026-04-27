/// SignBridge shared tools — RAG retrieval and read-only SQL.
/// All methods are ClassMethods so they are discovered correctly by %AI.ToolSet.
Class SignBridge.Tools Extends %AI.Tool
{

Parameter DESCRIPTION = "RAG and read-only SQL tools used by the SignBridge orchestrator.";

/// Search the SignBridge medical knowledge base.
/// Returns up to topK matching chunks with metadata and similarity score.
/// If redFlagOnly is true, only red-flag-tagged chunks are returned.
ClassMethod KbSearch(query As %String, topK As %Integer = 4, redFlagOnly As %Boolean = 0) As %DynamicObject
{
    Set result = {"query": (query), "top_k": (topK), "red_flag_only": (redFlagOnly), "results": []}
    Try {
        Set kb = ##class(SignBridge.KB).Open()
        If '$IsObject(kb) {
            Set result.error = "Knowledge base not built. Run SignBridge.KB.Build()."
            Return result
        }

        Set hits = ""
        Try {
            Set hits = kb.Search(query, topK)
        } Catch {
            Set hits = ""
        }

        If $IsObject(hits) {
            Set iter = hits.%GetIterator()
            While iter.%GetNext(.k, .hit) {
                If redFlagOnly, '##class(SignBridge.Tools).HitIsRedFlag(hit) Continue
                Do result.results.%Push(##class(SignBridge.Tools).NormalizeHit(hit))
            }
        } Else {
            Do ##class(SignBridge.Tools).FallbackSearch(query, topK, redFlagOnly, result.results)
        }
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

/// Read-only SQL tool. Blocks any write/DDL keyword via regex.
/// Returns at most maxRows rows.
ClassMethod SqlSelect(sql As %String, maxRows As %Integer = 50) As %DynamicObject
{
    Set result = {"sql": (sql), "rows": [], "row_count": 0}
    Try {
        Set guard = $ZCONVERT($ZSTRIP(sql, "<>W"), "U")
        If guard '? 1"SELECT".E {
            Set result.error = "sql_select only accepts SELECT statements."
            Return result
        }
        If guard [ ";" {
            Set tail = $ZSTRIP($PIECE(guard, ";", 2, *), "<>W")
            If tail '= "" {
                Set result.error = "sql_select rejects multi-statement SQL."
                Return result
            }
        }
        Set forbidden = $LISTBUILD("INSERT","UPDATE","DELETE","DROP","ALTER","CREATE","TRUNCATE","GRANT","REVOKE","MERGE","CALL","EXEC")
        Set ptr = 0, bad = ""
        While $LISTNEXT(forbidden, ptr, kw) {
            If guard [ (" "_kw_" ") || ($EXTRACT(guard,1,$LENGTH(kw)+1) = (kw_" ")) {
                Set bad = kw
                Quit
            }
        }
        If bad '= "" {
            Set result.error = "sql_select refuses keyword: " _ bad
            Return result
        }

        Set stmt = ##class(%SQL.Statement).%New()
        Set stmt.%SelectMode = 1
        Set sc = stmt.%Prepare(sql)
        If $$$ISERR(sc) {
            Set result.error = $SYSTEM.Status.GetErrorText(sc)
            Return result
        }
        Set rs = stmt.%Execute()
        If rs.%SQLCODE < 0 {
            Set result.error = "SQLCODE " _ rs.%SQLCODE _ ": " _ rs.%Message
            Return result
        }

        Set colCount = rs.%ResultColumnCount
        Set cols = []
        For i=1:1:colCount {
            Do cols.%Push(rs.%Metadata.columns.GetAt(i).colName)
        }
        Set result.columns = cols

        Set count = 0
        While rs.%Next() && (count < maxRows) {
            Set row = {}
            For i=1:1:colCount {
                Set name = cols.%Get(i-1)
                Set val = rs.%GetData(i)
                Do row.%Set(name, val)
            }
            Do result.rows.%Push(row)
            Set count = count + 1
        }
        Do result.%Set("row_count", count)
        Set result.truncated = (count = maxRows) && rs.%Next()
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

/// Describe a table — returns column names, types, and row count.
/// Useful when the orchestrator needs to discover schema before querying.
ClassMethod SqlDescribe(tableName As %String) As %DynamicObject
{
    Set result = {"table": (tableName), "columns": [], "row_count": 0}
    Try {
        Set schema = $PIECE(tableName, ".", 1)
        Set tname = $PIECE(tableName, ".", 2)
        If tname = "" {
            Set tname = schema
            Set schema = "SQLUser"
        }

        Set stmt = ##class(%SQL.Statement).%New()
        Set sc = stmt.%Prepare("SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = ? AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION")
        If $$$ISERR(sc) {
            Set result.error = $SYSTEM.Status.GetErrorText(sc)
            Return result
        }
        Set rs = stmt.%Execute(schema, tname)
        While rs.%Next() {
            Do result.columns.%Push({
                "name":     (rs.%Get("COLUMN_NAME")),
                "type":     (rs.%Get("DATA_TYPE")),
                "nullable": (rs.%Get("IS_NULLABLE"))
            })
        }

        Try {
            Set countStmt = ##class(%SQL.Statement).%New()
            Set sc = countStmt.%Prepare("SELECT COUNT(*) AS N FROM " _ tableName)
            If $$$ISOK(sc) {
                Set crs = countStmt.%Execute()
                If crs.%Next() {
                    Do result.%Set("row_count", crs.%Get("N"))
                }
            }
        } Catch {}

        If result.columns.%Size() = 0 {
            Set result.error = "Table not found or no columns: " _ tableName
        }
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

/// List tables matching a schema name pattern. Useful for schema discovery.
ClassMethod SqlListTables(schemaPattern As %String = "Health%") As %DynamicObject
{
    Set result = {"pattern": (schemaPattern), "tables": []}
    Try {
        Set stmt = ##class(%SQL.Statement).%New()
        Set sc = stmt.%Prepare("SELECT TABLE_SCHEMA, TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA LIKE ? ORDER BY TABLE_SCHEMA, TABLE_NAME")
        If $$$ISERR(sc) {
            Set result.error = $SYSTEM.Status.GetErrorText(sc)
            Return result
        }
        Set rs = stmt.%Execute(schemaPattern)
        While rs.%Next() {
            Do result.tables.%Push({
                "schema": (rs.%Get("TABLE_SCHEMA")),
                "name":   (rs.%Get("TABLE_NAME")),
                "fqn":    (rs.%Get("TABLE_SCHEMA") _ "." _ rs.%Get("TABLE_NAME"))
            })
        }
    } Catch ex {
        Set result.error = ex.DisplayString()
    }
    Return result
}

ClassMethod HitIsRedFlag(hit As %DynamicObject) As %Boolean
{
    Try {
        Set rf = hit.metadata.red_flag
        If (rf = 1) Return 1
        If (rf = "true") Return 1
    } Catch {}
    Return 0
}

ClassMethod NormalizeHit(hit As %DynamicObject) As %DynamicObject
{
    Set out = {}
    Try { Set out.content = hit.content } Catch { Try { Set out.content = hit.text } Catch {} }
    Try { Set out.score    = hit.score } Catch {}
    Try { Set out.source   = hit.metadata.source } Catch {}
    Try { Set out.category = hit.metadata.category } Catch {}
    Try { Set out.condition = hit.metadata.condition } Catch {}
    Try { Do out.%Set("red_flag", hit.metadata.red_flag) } Catch {}
    Return out
}

ClassMethod FallbackSearch(query As %String, topK As %Integer, redFlagOnly As %Boolean, results As %DynamicArray)
{
    Try {
        Set emb = ##class(%AI.RAG.Embedding.FastEmbed).Create()
        Set qvec = emb.Embed(query)

        Set table = "SignBridge.KBVectors"
        Set sql = "SELECT TOP " _ topK _ " content, source, category, condition, red_flag, " _
                  "VECTOR_DOT_PRODUCT(embedding, TO_VECTOR(?, 'DOUBLE', 384)) AS score " _
                  "FROM " _ table _ " " _
                  $SELECT(redFlagOnly: "WHERE red_flag = 1 ", 1: "") _
                  "ORDER BY score DESC"
        Set stmt = ##class(%SQL.Statement).%New()
        Set sc = stmt.%Prepare(sql)
        If $$$ISERR(sc) Return
        Set rs = stmt.%Execute($LISTTOSTRING(qvec, ","))
        While rs.%Next() {
            Do results.%Push({
                "content":   (rs.%Get("content")),
                "source":    (rs.%Get("source")),
                "category":  (rs.%Get("category")),
                "condition": (rs.%Get("condition")),
                "red_flag":  (rs.%Get("red_flag")),
                "score":     (rs.%Get("score"))
            })
        }
    } Catch {}
}

}
