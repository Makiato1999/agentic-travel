<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { createSession, createTask, getTask } from "./api";

const userId = ref("default_user");
const sessionId = ref("");
const draft = ref("");
const loading = ref(false);
const taskState = ref(null);
const activeTaskId = ref("");
const messages = ref([]);
const timeline = ref([]);
const currentView = ref("landing");
const sessionOwnerUserId = ref("");
let pollTimer = null;
let resetTimer = null;

const canSend = computed(() => sessionId.value && draft.value.trim() && !loading.value);
const intentionCard = computed(() => taskState.value?.intention || null);
const latestResults = computed(() => taskState.value?.latest_results || []);
const finalResult = computed(() => taskState.value?.result || null);
const plannedAgents = computed(() => taskState.value?.agents_planned || []);
const completedAgents = computed(() => taskState.value?.agents_completed || []);

onMounted(async () => {
  await initSession();
});

onBeforeUnmount(() => {
  stopPolling();
  if (resetTimer) {
    window.clearTimeout(resetTimer);
    resetTimer = null;
  }
});

async function initSession() {
  const session = await createSession(userId.value);
  sessionId.value = session.session_id;
  sessionOwnerUserId.value = userId.value;
}

async function handleResetSession() {
  stopPolling();
  sessionId.value = "";
  draft.value = "";
  loading.value = false;
  activeTaskId.value = "";
  taskState.value = null;
  messages.value = [];
  timeline.value = [];
  currentView.value = "landing";
  sessionOwnerUserId.value = "";
  await initSession();
}

watch(userId, (nextValue, previousValue) => {
  if (!previousValue || !sessionId.value) {
    return;
  }

  const normalized = nextValue.trim();
  if (!normalized || normalized === sessionOwnerUserId.value) {
    return;
  }

  if (resetTimer) {
    window.clearTimeout(resetTimer);
  }

  resetTimer = window.setTimeout(() => {
    handleResetSession().catch(() => {
      loading.value = false;
    });
    resetTimer = null;
  }, 350);
});

async function handleSubmit() {
  const message = draft.value.trim();
  if (!message || !sessionId.value || loading.value) {
    return;
  }

  messages.value.push({ role: "user", content: message });
  timeline.value = [];
  taskState.value = null;
  currentView.value = "workspace";
  loading.value = true;
  draft.value = "";

  try {
    const task = await createTask(sessionId.value, message);
    activeTaskId.value = task.task_id;
    await pollTask();
    startPolling();
  } catch (error) {
    pushAssistantMessage(`任务创建失败：${error.message}`);
    loading.value = false;
  }
}

async function pollTask() {
  if (!sessionId.value || !activeTaskId.value) {
    return;
  }

  const nextState = await getTask(sessionId.value, activeTaskId.value);
  taskState.value = nextState;
  upsertTimeline(nextState);

  if (nextState.status === "completed") {
    stopPolling();
    loading.value = false;
    pushAssistantMessage(nextState.display_text || "已完成处理");
  } else if (nextState.status === "failed") {
    stopPolling();
    loading.value = false;
    pushAssistantMessage(`任务失败：${nextState.error || nextState.message || "未知错误"}`);
  }
}

function startPolling() {
  stopPolling();
  pollTimer = window.setInterval(() => {
    pollTask().catch((error) => {
      stopPolling();
      loading.value = false;
      pushAssistantMessage(`轮询失败：${error.message}`);
    });
  }, 900);
}

function stopPolling() {
  if (pollTimer) {
    window.clearInterval(pollTimer);
    pollTimer = null;
  }
}

function upsertTimeline(state) {
  const key = `${state.stage}-${state.updated_at}`;
  if (timeline.value.some((item) => item.key === key)) {
    return;
  }

  timeline.value.unshift({
    key,
    stage: state.stage,
    message: state.message,
    progress: state.progress,
    updatedAt: formatTime(state.updated_at),
  });
}

function pushAssistantMessage(content) {
  const last = messages.value[messages.value.length - 1];
  if (last && last.role === "assistant" && last.content === content) {
    return;
  }
  messages.value.push({ role: "assistant", content });
}

function formatTime(value) {
  if (!value) {
    return "--:--:--";
  }
  return new Date(value * 1000).toLocaleTimeString("zh-CN", { hour12: false });
}

function stageLabel(stage) {
  const mapping = {
    queued: "排队中",
    intent_recognizing: "理解需求中",
    intent_recognition_completed: "已理解需求",
    orchestrating: "安排执行中",
    agent_running: "正在处理",
    completed: "已完成",
    failed: "处理失败",
  };
  return mapping[stage] || stage;
}

function statusClass(status) {
  return {
    pending: status === "queued",
    running: status === "running",
    completed: status === "completed",
    failed: status === "failed",
  };
}

function readableJson(value) {
  return JSON.stringify(value, null, 2);
}

function formatAssistantContent(content) {
  if (!content) {
    return "";
  }

  return content
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line, index, arr) => !(line === "" && arr[index - 1] === ""))
    .join("\n");
}
</script>

<template>
  <div class="aurora-layer aurora-a"></div>
  <div class="aurora-layer aurora-b"></div>
  <div class="aurora-layer aurora-c"></div>

  <main v-if="currentView === 'landing'" class="landing-shell">
    <section class="hero-copy">
      <p class="eyebrow">Agentic Travel</p>
      <h1>一位能规划、查询、记住偏好的商旅助手</h1>
      <p class="lead">
        用自然语言描述你的出差需求，系统会先理解意图，再调用多种能力完成查询、规划和结果整理。
      </p>
      <div class="value-row">
        <span>对话式体验</span>
        <span>过程可见</span>
        <span>结果可追踪</span>
      </div>
    </section>

    <section class="launch-card surface-card">
      <div class="launch-head">
        <div>
          <p class="eyebrow">Start</p>
          <h2>开始一轮商旅任务</h2>
        </div>
        <span class="soft-chip">Session {{ sessionId || "准备中" }}</span>
      </div>

      <label class="field">
        <span>用户 ID</span>
        <input v-model="userId" class="soft-input" />
      </label>

      <label class="field">
        <span>告诉我你想做什么</span>
        <textarea
          v-model="draft"
          class="soft-input launch-textarea"
          placeholder="例如：我下周从上海去武汉出差 5 天，想住安静一点、离地铁近的酒店，顺便告诉我武汉下周天气"
        />
      </label>

      <div class="quick-tips">
        <button class="tip-chip" @click="draft = '下周从上海去武汉出差 5 天，帮我规划行程并推荐酒店区域'">
          行程规划
        </button>
        <button class="tip-chip" @click="draft = '武汉下周天气怎么样，适合出差入住哪个区域？'">
          信息查询
        </button>
        <button class="tip-chip" @click="draft = '我偏好安静商务房，喜欢靠近地铁，请记住'">
          偏好记忆
        </button>
      </div>

      <div class="launch-actions">
        <button class="secondary-button" @click="handleResetSession">重建 Session</button>
        <button class="primary-button" :disabled="!canSend" @click="handleSubmit">开始处理</button>
      </div>
    </section>
  </main>

  <main v-else class="workspace-shell">
    <aside class="left-rail">
      <section class="surface-card rail-card rail-brand">
        <p class="eyebrow">Assistant</p>
        <h2>商旅助手</h2>
        <p class="muted">面向用户的产品体验，保留适度执行反馈和可信度细节。</p>
      </section>

      <section class="surface-card rail-card">
        <div class="rail-head">
          <span>当前状态</span>
          <span>{{ taskState?.progress ?? 0 }}%</span>
        </div>
        <div class="progress-track">
          <div class="progress-bar" :style="{ width: `${taskState?.progress ?? 0}%` }"></div>
        </div>
        <div class="status-pill" :class="statusClass(taskState?.status)">
          <span class="status-dot"></span>
          {{ taskState?.message || "等待开始" }}
        </div>
        <div class="meta-grid">
          <div>
            <span class="meta-label">用户</span>
            <strong>{{ userId }}</strong>
          </div>
          <div>
            <span class="meta-label">任务</span>
            <strong>{{ activeTaskId || "未创建" }}</strong>
          </div>
        </div>
      </section>

      <section class="surface-card rail-card">
        <div class="rail-head">
          <span>执行步骤</span>
          <span>{{ completedAgents.length }}/{{ plannedAgents.length }}</span>
        </div>
        <ul class="step-list">
          <li v-for="agent in plannedAgents" :key="agent">
            <span>{{ agent }}</span>
            <span class="mini-state" :class="{ done: completedAgents.includes(agent) }">
              {{ completedAgents.includes(agent) ? "已完成" : "待处理" }}
            </span>
          </li>
        </ul>
      </section>

      <section class="surface-card rail-card">
        <button class="secondary-button full-width" @click="handleResetSession">开始新对话</button>
      </section>
    </aside>

    <section class="chat-stage">
      <header class="surface-card top-strip">
        <div>
          <p class="eyebrow">Task Flow</p>
          <h1>{{ stageLabel(taskState?.stage || "queued") }}</h1>
        </div>
        <div class="strip-meta">
          <span class="soft-chip">{{ loading ? "执行中" : "空闲" }}</span>
          <span class="soft-chip subtle">Session {{ sessionId }}</span>
        </div>
      </header>

      <section class="surface-card conversation-card">
        <div class="conversation-scroll">
          <article
            v-for="(message, index) in messages"
            :key="index"
            class="chat-bubble"
            :class="message.role"
          >
            <span class="bubble-label">{{ message.role === "user" ? "你" : "助手" }}</span>
            <template v-if="message.role === 'assistant'">
              <div class="assistant-rich">{{ formatAssistantContent(message.content) }}</div>
            </template>
            <p v-else>{{ message.content }}</p>
          </article>
        </div>

        <div class="composer">
          <textarea
            v-model="draft"
            class="soft-input composer-input"
            placeholder="继续输入新的商旅需求..."
          />
          <div class="composer-actions">
            <button class="primary-button" :disabled="!canSend" @click="handleSubmit">
              {{ loading ? "处理中..." : "发送" }}
            </button>
          </div>
        </div>
      </section>

      <section class="summary-grid single-column">
        <article class="surface-card summary-card">
          <div class="card-head">
            <h3>系统进展</h3>
            <span class="helper">轻量工程感</span>
          </div>
          <ol class="timeline">
            <li v-for="entry in timeline" :key="entry.key">
              <div class="timeline-dot"></div>
              <div class="timeline-body">
                <div class="timeline-head">
                  <strong>{{ stageLabel(entry.stage) }}</strong>
                  <span>{{ entry.updatedAt }}</span>
                </div>
                <p>{{ entry.message }}</p>
              </div>
            </li>
          </ol>
        </article>
      </section>

      <section class="details-stack">
        <details class="surface-card detail-panel" :open="Boolean(intentionCard)">
          <summary>
            <span>需求理解</span>
            <span class="helper">意图识别完成后优先展示</span>
          </summary>
          <div v-if="intentionCard" class="detail-content">
            <div class="pill-row">
              <span class="capsule" v-for="intent in intentionCard.intents || []" :key="intent.type">
                {{ intent.type }} · {{ Math.round((intent.confidence || 0) * 100) }}%
              </span>
            </div>
            <div class="entity-grid">
              <div class="entity-card" v-for="(value, key) in intentionCard.key_entities || {}" :key="key">
                <span>{{ key }}</span>
                <strong>{{ value || "未识别" }}</strong>
              </div>
            </div>
            <div class="mono-block">{{ intentionCard.rewritten_query || "暂无改写结果" }}</div>
          </div>
          <p v-else class="empty-hint">系统理解完需求后，这里会显示结构化判断。</p>
        </details>

        <details class="surface-card detail-panel">
          <summary>
            <span>执行细节</span>
            <span class="helper">查看各能力模块的中间结果</span>
          </summary>
          <div v-if="latestResults.length" class="detail-content result-stack">
            <article v-for="item in latestResults" :key="item.agent_name" class="result-item">
              <div class="result-meta">
                <strong>{{ item.agent_name }}</strong>
                <span class="soft-chip subtle">{{ item.status }}</span>
              </div>
              <pre class="mono-block compact">{{ readableJson(item.data) }}</pre>
            </article>
          </div>
          <p v-else class="empty-hint">执行开始后，这里会出现过程结果。</p>
        </details>

        <details class="surface-card detail-panel">
          <summary>
            <span>原始数据</span>
            <span class="helper">用于排查和验证</span>
          </summary>
          <pre v-if="finalResult" class="mono-block">{{ readableJson(finalResult) }}</pre>
          <p v-else class="empty-hint">结果尚未完成。</p>
        </details>
      </section>
    </section>
  </main>
</template>
