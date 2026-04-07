"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  isLoggedIn, logout, uploadDocument, processDocument,
  listDocuments, deleteDocument, createChatSession,
  listChatSessions, getSessionMessages, deleteChatSession,
  askQuestion, expandDataset,
} from "@/lib/api";
import type { ExpandResponse } from "@/lib/api";

// --- Types ---
interface Document { id: string; title: string; file_name: string; status: string; uploaded_at: string; }
interface Source { document_title: string; file_name: string; page_number: number; distance: number; }
interface StructuredData {
  columns: string[];
  rows: Record<string, string>[];
  total: number;
  titles: string[];
}
interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  structured_data?: StructuredData;
}
interface SessionPreview { id: string; preview: string; message_count: number; created_at: string; }

// ============================================================
// Main Dashboard
// ============================================================
export default function DashboardPage() {
  const router = useRouter();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sessions, setSessions] = useState<SessionPreview[]>([]);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/"); return; }
    loadDocuments(); loadSessions(); startNewChat();
  }, [router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadDocuments() { try { setDocuments(await listDocuments()); } catch {} }
  async function loadSessions() { try { setSessions(await listChatSessions()); } catch {} }

  async function startNewChat() {
    try { const data = await createChatSession(); setSessionId(data.session_id); setMessages([]); } catch {}
  }

  async function loadSession(id: string) {
    setLoadingMessages(true); setSessionId(id);
    try {
      const msgs = await getSessionMessages(id);
      setMessages(msgs.map((m: { role: string; content: string }) => ({
        role: m.role as "user" | "assistant", content: m.content,
      })));
      setActiveTab("chat");
    } catch {} finally { setLoadingMessages(false); }
  }

  async function handleDeleteSession(id: string, e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    try { await deleteChatSession(id); if (sessionId === id) await startNewChat(); await loadSessions(); } catch {}
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]; if (!file) return;
    setUploading(true);
    try { const doc = await uploadDocument(file); try { await processDocument(doc.id); } catch {} await loadDocuments();
    } catch {} finally { setUploading(false); e.target.value = ""; }
  }

  async function handleDelete(documentId: string, title: string) {
    if (!confirm(`Delete "${title}"?`)) return;
    try { await deleteDocument(documentId); await loadDocuments(); } catch {}
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || !sessionId || asking) return;
    const userQuestion = question; setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: userQuestion }]);
    setAsking(true);
    try {
      const result = await askQuestion(sessionId, userQuestion);
      setMessages((prev) => [...prev, {
        role: "assistant", content: result.answer,
        sources: result.sources, structured_data: result.structured_data || undefined,
      }]);
      await loadSessions();
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Sorry, something went wrong. Please try again." }]);
    } finally { setAsking(false); }
  }

  function handleLogout() { logout(); router.push("/"); }

  return (
    <div className="h-screen flex flex-col bg-gray-50">
      <header className="bg-white border-b border-gray-200 px-4 py-2.5 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          {activeTab === "chat" && (
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-1.5 rounded hover:bg-gray-100 text-gray-500">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 12h18M3 6h18M3 18h18" /></svg>
            </button>
          )}
          <h1 className="text-sm font-semibold text-gray-800 tracking-tight">AI University Knowledge Repository</h1>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex bg-gray-100 rounded-md p-0.5">
            {(["chat", "documents"] as const).map((tab) => (
              <button key={tab} onClick={() => setActiveTab(tab)}
                className={`px-3 py-1 text-xs font-medium rounded transition-colors ${
                  activeTab === tab ? "bg-white text-gray-800 shadow-sm" : "text-gray-500 hover:text-gray-700"}`}>
                {tab === "chat" ? "Chat" : `Docs${documents.length > 0 ? ` (${documents.length})` : ""}`}
              </button>
            ))}
          </div>
          <div className="w-px h-5 bg-gray-200" />
          <button onClick={handleLogout} className="text-xs text-gray-400 hover:text-gray-600">Log out</button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {sidebarOpen && activeTab === "chat" && (
          <aside className="w-64 bg-white border-r border-gray-200 flex flex-col shrink-0">
            <div className="p-3">
              <button onClick={startNewChat} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 border border-gray-200 rounded-md hover:bg-gray-50">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14" /></svg>
                New chat
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-2 pb-3">
              {sessions.length === 0 ? (
                <p className="text-xs text-gray-400 text-center mt-8">No conversations yet</p>
              ) : (
                <div className="space-y-0.5">
                  {sessions.map((s) => (
                    <div key={s.id} onClick={() => loadSession(s.id)}
                      className={`group flex items-center justify-between px-3 py-2 rounded-md cursor-pointer text-sm transition-colors ${
                        sessionId === s.id ? "bg-gray-100 text-gray-900" : "text-gray-600 hover:bg-gray-50"}`}>
                      <span className="truncate flex-1 mr-2">{s.preview}</span>
                      <button onClick={(e) => handleDeleteSession(s.id, e)}
                        className="opacity-0 group-hover:opacity-100 p-0.5 text-gray-400 hover:text-red-500 shrink-0">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </aside>
        )}

        {activeTab === "chat" && (
          <div className="flex-1 flex flex-col min-w-0">
            <div className="flex-1 overflow-y-auto">
              <div className="max-w-3xl mx-auto px-4 py-6">
                {loadingMessages ? (
                  <div className="flex justify-center mt-20"><p className="text-sm text-gray-400">Loading conversation...</p></div>
                ) : messages.length === 0 ? (
                  <div className="text-center mt-20">
                    <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-gray-100 mb-4">
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.5"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" /></svg>
                    </div>
                    <p className="text-gray-500 text-sm">Ask a question about your documents</p>
                    <p className="text-gray-400 text-xs mt-1">Upload files in the Docs tab, then ask questions here</p>
                  </div>
                ) : (
                  <div className="space-y-5">
                    {messages.map((msg, i) => <MessageBubble key={i} message={msg} />)}
                    {asking && (
                      <div className="flex justify-start">
                        <div className="bg-white border border-gray-200 rounded-lg px-4 py-3">
                          <div className="flex items-center gap-1.5">
                            <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                            <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                            <div className="w-1.5 h-1.5 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                          </div>
                        </div>
                      </div>
                    )}
                    <div ref={messagesEndRef} />
                  </div>
                )}
              </div>
            </div>
            <div className="border-t border-gray-200 bg-white p-3 shrink-0">
              <form onSubmit={handleAsk} className="max-w-3xl mx-auto flex gap-2">
                <input type="text" value={question} onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask a question..." disabled={asking}
                  className="flex-1 px-3.5 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-gray-300 text-gray-800 placeholder-gray-400 disabled:opacity-50" />
                <button type="submit" disabled={asking || !question.trim()}
                  className="px-4 py-2 text-sm font-medium bg-gray-800 text-white rounded-lg hover:bg-gray-700 disabled:opacity-40">Send</button>
              </form>
            </div>
          </div>
        )}

        {activeTab === "documents" && (
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-3xl mx-auto px-4 py-6">
              <div className="mb-6">
                <label className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium bg-gray-800 text-white rounded-lg cursor-pointer hover:bg-gray-700">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M17 8l-5-5-5 5M12 3v12" /></svg>
                  {uploading ? "Processing..." : "Upload document"}
                  <input type="file" accept=".pdf,.txt,.md,.docx,.doc,.xlsx,.xls,.csv" onChange={handleUpload} disabled={uploading} className="hidden" />
                </label>
                <p className="text-xs text-gray-400 mt-2">Supports PDF, DOCX, TXT, Markdown, Excel, and CSV</p>
              </div>
              {documents.length === 0 ? (
                <div className="text-center py-12"><p className="text-sm text-gray-400">No documents uploaded yet</p></div>
              ) : (
                <div className="space-y-2">
                  {documents.map((doc) => (
                    <div key={doc.id} className="bg-white border border-gray-200 rounded-lg px-4 py-3 flex items-center justify-between group hover:border-gray-300">
                      <div className="min-w-0 mr-3">
                        <p className="text-sm font-medium text-gray-800 truncate">{doc.title}</p>
                        <p className="text-xs text-gray-400 truncate">{doc.file_name}</p>
                      </div>
                      <div className="flex items-center gap-2.5 shrink-0">
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full uppercase tracking-wider ${
                          doc.status === "completed" ? "bg-emerald-50 text-emerald-600" :
                          doc.status === "processing" ? "bg-amber-50 text-amber-600" :
                          doc.status === "failed" ? "bg-red-50 text-red-600" : "bg-gray-50 text-gray-500"}`}>
                          {doc.status}
                        </span>
                        <button onClick={() => handleDelete(doc.id, doc.title)} className="opacity-0 group-hover:opacity-100 text-xs text-gray-400 hover:text-red-500">Delete</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Message Bubble
// ============================================================
function MessageBubble({ message }: { message: ChatMessage }) {
  const [showTable, setShowTable] = useState(false);
  const [expandedData, setExpandedData] = useState<ExpandResponse | null>(null);
  const [loadingExpand, setLoadingExpand] = useState(false);

  async function handleExpand() {
    if (showTable) {
      setShowTable(false);
      return;
    }

    setShowTable(true);

    // If we already loaded full data, just toggle visibility
    if (expandedData) return;

    // Fetch full details from the database
    if (message.structured_data?.titles) {
      setLoadingExpand(true);
      try {
        const fullData = await expandDataset(message.structured_data.titles);
        setExpandedData(fullData);
      } catch (err) {
        console.error("Failed to expand dataset:", err);
      } finally {
        setLoadingExpand(false);
      }
    }
  }

  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div className={`rounded-lg px-4 py-3 text-sm leading-relaxed ${
        message.role === "user"
          ? "max-w-[85%] bg-gray-800 text-white"
          : showTable
            ? "w-full bg-white border border-gray-200 text-gray-800"
            : "max-w-[85%] bg-white border border-gray-200 text-gray-800"
      }`}>
        <p className="whitespace-pre-wrap">{message.content}</p>

        {/* View full dataset button */}
        {message.structured_data && message.structured_data.total > 0 && (
          <div className="mt-3 pt-2.5 border-t border-gray-100">
            <button onClick={handleExpand}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-blue-600 hover:text-blue-700 transition-colors">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" /><path d="M3 9h18M3 15h18M9 3v18" />
              </svg>
              {showTable ? "Hide" : "View"} full dataset ({message.structured_data.total} records)
              <svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"
                className={`transition-transform ${showTable ? "rotate-180" : ""}`}>
                <path d="M7 10l5 5 5-5z" />
              </svg>
            </button>
          </div>
        )}

        {/* Expanded data table */}
        {showTable && (
          <div className="mt-3">
            {loadingExpand ? (
              <div className="py-8 text-center text-xs text-gray-400">Loading full dataset...</div>
            ) : expandedData ? (
              <FullDataTable data={expandedData} />
            ) : message.structured_data ? (
              <SummaryTable data={message.structured_data} />
            ) : null}
          </div>
        )}

        {/* Sources — only show when no structured data */}
        {message.sources && message.sources.length > 0 && !message.structured_data && (
          <div className="mt-3 pt-2.5 border-t border-gray-100">
            <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wider mb-1">Sources</p>
            {message.sources
              .filter((s, j, arr) => arr.findIndex((x) => x.document_title === s.document_title && x.page_number === s.page_number) === j)
              .map((s, j) => <p key={j} className="text-xs text-gray-400">{s.document_title} — Page {s.page_number}</p>)}
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Summary Table (from chat response — Title, Colleges, Level)
// ============================================================
function SummaryTable({ data }: { data: StructuredData }) {
  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
      <div className="px-3 py-2 bg-white border-b border-gray-100">
        <span className="text-xs text-gray-500"><span className="font-semibold text-gray-700">{data.total}</span> records</span>
      </div>
      <div className="overflow-x-auto max-h-64">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {data.columns.map((col) => (
                <th key={col} className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider border-b border-gray-200 whitespace-nowrap">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-white">
                {data.columns.map((col) => (
                  <td key={col} className="py-1.5 px-3 text-gray-700 max-w-[250px] truncate">{row[col] || "—"}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============================================================
// Full Data Table (from /explorer/expand — all columns)
// ============================================================
function FullDataTable({ data }: { data: ExpandResponse }) {
  const [sortBy, setSortBy] = useState("");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [filterText, setFilterText] = useState("");
  const [visibleCols, setVisibleCols] = useState<string[]>(() => data.columns.slice(0, 7));
  const [showColPicker, setShowColPicker] = useState(false);

  const filteredRows = data.rows.filter((row) => {
    if (!filterText) return true;
    const lower = filterText.toLowerCase();
    return Object.values(row.values).some((v) => v.toLowerCase().includes(lower));
  });

  const sortedRows = [...filteredRows].sort((a, b) => {
    if (!sortBy) return 0;
    const aVal = (a.values[sortBy] || "").toLowerCase();
    const bVal = (b.values[sortBy] || "").toLowerCase();
    return sortDir === "asc" ? aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
  });

  function handleSort(col: string) {
    if (sortBy === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortBy(col); setSortDir("asc"); }
  }

  // Stats by level
  const levelCounts: Record<string, number> = {};
  const levelCol = data.columns.find((c) => c.toLowerCase().includes("level"));
  if (levelCol) {
    for (const row of filteredRows) {
      const level = row.values[levelCol] || "Other";
      levelCounts[level] = (levelCounts[level] || 0) + 1;
    }
  }

  return (
    <div className="border border-gray-200 rounded-lg overflow-hidden bg-gray-50">
      {/* Stats */}
      <div className="px-3 py-2 bg-white border-b border-gray-100 flex items-center gap-4 flex-wrap">
        <span className="text-xs text-gray-500">
          <span className="font-semibold text-gray-700">{filteredRows.length}</span> records · all fields
        </span>
        {Object.entries(levelCounts).map(([level, count]) => (
          <span key={level} className="text-xs text-gray-400">{level}: <span className="text-gray-600">{count}</span></span>
        ))}
      </div>

      {/* Controls */}
      <div className="px-3 py-2 bg-white border-b border-gray-100 flex items-center gap-2">
        <div className="relative flex-1 max-w-xs">
          <input type="text" value={filterText} onChange={(e) => setFilterText(e.target.value)}
            placeholder="Filter..." className="w-full pl-7 pr-2 py-1 text-xs border border-gray-200 rounded focus:outline-none focus:ring-1 focus:ring-gray-300 text-gray-700" />
          <svg className="absolute left-2 top-1.5 text-gray-400" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
          </svg>
        </div>
        <div className="relative">
          <button onClick={() => setShowColPicker(!showColPicker)}
            className="text-xs border border-gray-200 rounded px-2 py-1 text-gray-500 hover:bg-gray-50">
            Columns ({visibleCols.length}/{data.columns.length})
          </button>
          {showColPicker && (
            <div className="absolute right-0 top-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg p-2 z-10 w-56 max-h-48 overflow-y-auto">
              {data.columns.map((col) => (
                <label key={col} className="flex items-center gap-2 py-0.5 cursor-pointer text-xs text-gray-600 hover:text-gray-800">
                  <input type="checkbox" checked={visibleCols.includes(col)}
                    onChange={() => setVisibleCols((prev) => prev.includes(col) ? prev.filter((c) => c !== col) : [...prev, col])}
                    className="rounded border-gray-300 text-blue-600" />
                  {col}
                </label>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Table */}
      <div className="overflow-x-auto max-h-96">
        <table className="w-full text-xs">
          <thead className="bg-gray-50 sticky top-0">
            <tr>
              {visibleCols.map((col) => (
                <th key={col} onClick={() => handleSort(col)}
                  className="text-left py-2 px-3 font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:text-gray-700 whitespace-nowrap select-none border-b border-gray-200">
                  <span className="inline-flex items-center gap-1">
                    {col}
                    {sortBy === col && (
                      <svg width="8" height="8" viewBox="0 0 24 24" fill="currentColor">
                        {sortDir === "asc" ? <path d="M7 14l5-5 5 5z" /> : <path d="M7 10l5 5 5-5z" />}
                      </svg>
                    )}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, i) => (
              <tr key={i} className="border-b border-gray-100 hover:bg-white">
                {visibleCols.map((col) => (
                  <td key={col} className="py-1.5 px-3 text-gray-700 max-w-[200px] truncate" title={row.values[col] || ""}>
                    {row.values[col] || "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}