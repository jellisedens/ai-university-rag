const API_URL = "http://localhost:8000";

// --- Helper ---

async function request(endpoint: string, options: RequestInit = {}) {
  const token = localStorage.getItem("token");

  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // Don't set Content-Type for FormData (file uploads)
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || "Request failed");
  }

  if (res.status === 204) {
    return null;
  }

  return res.json();
}

// --- Auth ---

export async function signup(email: string, password: string) {
  const data = await request("/auth/signup", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("token", data.access_token);
  return data;
}

export async function login(email: string, password: string) {
  const data = await request("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  localStorage.setItem("token", data.access_token);
  return data;
}

export function logout() {
  localStorage.removeItem("token");
}

export function isLoggedIn() {
  return !!localStorage.getItem("token");
}

// --- Documents ---

export async function uploadDocument(file: File) {
  const formData = new FormData();
  formData.append("file", file);
  return request("/documents/upload", {
    method: "POST",
    body: formData,
  });
}

export async function listDocuments() {
  return request("/documents/");
}

export async function processDocument(documentId: string) {
  return request(`/documents/${documentId}/process`, {
    method: "POST",
  });
}

// --- Chat ---

export async function createChatSession() {
  return request("/chat/sessions", {
    method: "POST",
  });
}

export async function askQuestion(sessionId: string, question: string) {
  return request(`/chat/sessions/${sessionId}/ask`, {
    method: "POST",
    body: JSON.stringify({ question }),
  });
}

export async function deleteDocument(documentId: string) {
  return request(`/documents/${documentId}`, {
    method: "DELETE",
  });
}