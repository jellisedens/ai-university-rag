"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import {
  isLoggedIn,
  logout,
  uploadDocument,
  processDocument,
  listDocuments,
  deleteDocument,
  createChatSession,
  askQuestion,
} from "@/lib/api";

interface Document {
  id: string;
  title: string;
  file_name: string;
  status: string;
  uploaded_at: string;
}

interface Source {
  document_title: string;
  file_name: string;
  page_number: number;
  distance: number;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
}

export default function DashboardPage() {
  const router = useRouter();
  const [documents, setDocuments] = useState<Document[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [question, setQuestion] = useState("");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [asking, setAsking] = useState(false);
  const [activeTab, setActiveTab] = useState<"chat" | "documents">("chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.push("/");
      return;
    }
    loadDocuments();
    initSession();
  }, [router]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  async function loadDocuments() {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      console.error("Failed to load documents");
    }
  }

  async function initSession() {
    try {
      const data = await createChatSession();
      setSessionId(data.session_id);
    } catch {
      console.error("Failed to create chat session");
    }
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    try {
      const doc = await uploadDocument(file);
      try {
        await processDocument(doc.id);
      } catch (processErr) {
        console.error("Processing failed:", processErr);
      }
      await loadDocuments();
    } catch (err) {
      console.error("Upload failed:", err);
    } finally {
      setUploading(false);
      e.target.value = "";
    }
  }

  async function handleAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || !sessionId || asking) return;

    const userQuestion = question;
    setQuestion("");
    setMessages((prev) => [...prev, { role: "user", content: userQuestion }]);
    setAsking(true);

    try {
      const result = await askQuestion(sessionId, userQuestion);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: result.answer, sources: result.sources },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Sorry, something went wrong. Please try again." },
      ]);
    } finally {
      setAsking(false);
    }
  }
  async function handleDelete(documentId: string, title: string) {
    if (!confirm(`Are you sure you want to delete "${title}"? This cannot be undone.`)) {
      return;
    }
    try {
      await deleteDocument(documentId);
      await loadDocuments();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  }

  function handleLogout() {
    logout();
    router.push("/");
  }

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-3 flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-800">
          AI University Knowledge Repository
        </h1>
        <button
          onClick={handleLogout}
          className="text-sm text-gray-500 hover:text-gray-700"
        >
          Log Out
        </button>
      </header>

      {/* Tab Navigation */}
      <div className="bg-white border-b border-gray-200 px-6">
        <div className="flex space-x-4">
          <button
            onClick={() => setActiveTab("chat")}
            className={`py-3 px-1 border-b-2 text-sm font-medium ${
              activeTab === "chat"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Chat
          </button>
          <button
            onClick={() => setActiveTab("documents")}
            className={`py-3 px-1 border-b-2 text-sm font-medium ${
              activeTab === "documents"
                ? "border-blue-600 text-blue-600"
                : "border-transparent text-gray-500 hover:text-gray-700"
            }`}
          >
            Documents ({documents.length})
          </button>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {activeTab === "chat" ? (
          <div className="flex-1 flex flex-col max-w-4xl w-full mx-auto">
            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {messages.length === 0 && (
                <div className="text-center text-gray-400 mt-20">
                  <p className="text-lg">Ask a question about your documents</p>
                  <p className="text-sm mt-2">
                    Upload PDFs in the Documents tab, then ask questions here
                  </p>
                </div>
              )}

              {messages.map((msg, i) => (
                <div
                  key={i}
                  className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                >
                  <div
                    className={`max-w-[80%] rounded-lg px-4 py-3 ${
                      msg.role === "user"
                        ? "bg-blue-600 text-white"
                        : "bg-white border border-gray-200 text-gray-800"
                    }`}
                  >
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-gray-100">
                        <p className="text-xs font-medium text-gray-500 mb-1">Sources:</p>
                        {msg.sources
                          .filter((source, j, arr) =>
                            arr.findIndex(
                              (s) => s.document_title === source.document_title && s.page_number === source.page_number
                            ) === j
                          )
                          .map((source, j) => (
                            <p key={j} className="text-xs text-gray-400">
                              {source.document_title} — Page {source.page_number}
                            </p>
                          ))}
                      </div>
                    )}
                  </div>
                </div>
              ))}

              {asking && (
                <div className="flex justify-start">
                  <div className="bg-white border border-gray-200 rounded-lg px-4 py-3 text-gray-500">
                    Thinking...
                  </div>
                </div>
              )}

              <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-gray-200 bg-white p-4">
              <form onSubmit={handleAsk} className="flex space-x-3 max-w-4xl mx-auto">
                <input
                  type="text"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask a question about your documents..."
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-gray-800"
                />
                <button
                  type="submit"
                  disabled={asking || !question.trim()}
                  className="px-6 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:opacity-50"
                >
                  Send
                </button>
              </form>
            </div>
          </div>
        ) : (
          /* Documents Tab */
          <div className="max-w-4xl w-full mx-auto p-6">
            <div className="mb-6">
              <label className="inline-block px-4 py-2 bg-blue-600 text-white rounded-md cursor-pointer hover:bg-blue-700">
                {uploading ? "Processing..." : "Upload Document (.pdf, .docx, .txt, .md, .xlsx, .csv)"}
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.docx,.doc,.xlsx,.xls,.csv"
                  onChange={handleUpload}
                  disabled={uploading}
                  className="hidden"
                />
              </label>
            </div>

            {documents.length === 0 ? (
              <p className="text-gray-400">No documents uploaded yet</p>
            ) : (
              <div className="space-y-3">
                {documents.map((doc) => (
                  <div
                    key={doc.id}
                    className="bg-white border border-gray-200 rounded-lg p-4 flex items-center justify-between"
                  >
                    <div>
                      <p className="font-medium text-gray-800">{doc.title}</p>
                      <p className="text-sm text-gray-400">{doc.file_name}</p>
                    </div>
                    <div className="flex items-center space-x-3">
                      <span
                        className={`text-xs px-2 py-1 rounded-full ${
                          doc.status === "completed"
                            ? "bg-green-100 text-green-700"
                            : doc.status === "processing"
                            ? "bg-yellow-100 text-yellow-700"
                            : doc.status === "failed"
                            ? "bg-red-100 text-red-700"
                            : "bg-gray-100 text-gray-600"
                        }`}
                      >
                        {doc.status}
                      </span>
                      <button
                        onClick={() => handleDelete(doc.id, doc.title)}
                        className="text-xs text-red-400 hover:text-red-600"
                      >
                        Delete
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}