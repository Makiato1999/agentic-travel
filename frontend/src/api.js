const JSON_HEADERS = {
  "Content-Type": "application/json",
};

export async function createSession(userId = "default_user") {
  const response = await fetch("/api/v1/sessions", {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ user_id: userId }),
  });

  if (!response.ok) {
    throw new Error(`Create session failed: ${response.status}`);
  }

  return response.json();
}

export async function createTask(sessionId, message) {
  const response = await fetch(`/api/v1/sessions/${sessionId}/tasks`, {
    method: "POST",
    headers: JSON_HEADERS,
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const detail = await safeReadError(response);
    throw new Error(detail || `Create task failed: ${response.status}`);
  }

  return response.json();
}

export async function getTask(sessionId, taskId) {
  const response = await fetch(`/api/v1/sessions/${sessionId}/tasks/${taskId}`);

  if (!response.ok) {
    const detail = await safeReadError(response);
    throw new Error(detail || `Get task failed: ${response.status}`);
  }

  return response.json();
}

async function safeReadError(response) {
  try {
    const data = await response.json();
    return data.detail || JSON.stringify(data);
  } catch {
    return await response.text();
  }
}
