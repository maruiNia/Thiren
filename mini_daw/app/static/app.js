/**
 * app.js
 *
 * 현재 UI 버튼들을 실제 FastAPI API에 연결합니다.
 * Step1에서는 "프로젝트 생성 → 상태 불러오기 → 트랙 조절 반영"까지만 합니다.
 */

let PROJECT_ID = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const msg = await res.text();
    throw new Error(msg);
  }
  return res.json();
}

function setMetaUI(state) {
  // 상단 프로젝트명
  const projectNameEl = document.getElementById("projectName");
  if (projectNameEl) projectNameEl.textContent = state.name;

  // meta 표시는 ui.html에서 id가 없어서(지금은 고정 텍스트),
  // Step2에서 meta 영역에도 id 부여해서 업데이트하도록 개선할게요.
}

function showToastChat(text, isUser) {
  // ui.html의 채팅 추가 로직을 그대로 써도 되지만,
  // Step1에서는 최소로만: "Command received" 정도 찍기 용도.
  const chatContainer = document.getElementById("chatContainer");
  if (!chatContainer) return;

  const message = document.createElement("div");
  message.className = `chat-message ${isUser ? "user-message" : "ai-message"}`;
  message.innerHTML = `
    <div class="message-sender">${isUser ? "You" : "Server"}</div>
    <div class="message-bubble">${text}</div>
  `;
  chatContainer.appendChild(message);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function ensureProject() {
  if (PROJECT_ID) return PROJECT_ID;

  // 기본 프로젝트 생성
  const data = await api("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name: "My Project", bpm: 120, bars: 4 }),
  });

  PROJECT_ID = data.state.id;
  setMetaUI(data.state);
  showToastChat(`Project created: ${PROJECT_ID}`, false);

  return PROJECT_ID;
}

async function patchTrack(trackName, patch) {
  const id = await ensureProject();

  const trackIdMap = { drums: 1, bass: 2, pad: 3, lead: 4 };
  const track_id = trackIdMap[trackName];

  const data = await api(`/api/projects/${id}/tracks/${track_id}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });

  showToastChat(`${trackName} updated`, false);
  setMetaUI(data.state);
}

function wireTrackControls() {
  const tracks = ["drums", "bass", "pad", "lead"];

  tracks.forEach((t) => {
    const vol = document.getElementById(`${t}Vol`);
    const pan = document.getElementById(`${t}Pan`);
    const mute = document.getElementById(`${t}Mute`);
    const solo = document.getElementById(`${t}Solo`);

    if (vol) {
      vol.addEventListener("change", async (e) => {
        const value = parseInt(e.target.value, 10) / 100.0;
        await patchTrack(t, { volume: value });
      });
    }

    if (pan) {
      pan.addEventListener("change", async (e) => {
        // UI pan: -50~50 => -1~1
        const value = parseInt(e.target.value, 10) / 50.0;
        await patchTrack(t, { pan: value });
      });
    }

    if (mute) {
      mute.addEventListener("click", async () => {
        const isActive = mute.classList.contains("active");
        await patchTrack(t, { mute: isActive });
      });
    }

    if (solo) {
      solo.addEventListener("click", async () => {
        const isActive = solo.classList.contains("active");
        await patchTrack(t, { solo: isActive });
      });
    }
  });
}

function wireChatSend() {
  const chatInput = document.getElementById("chatInput");
  const sendButton = document.getElementById("sendButton");

  if (!chatInput || !sendButton) return;

  sendButton.addEventListener("click", async () => {
    const text = chatInput.value.trim();
    if (!text) return;

    await ensureProject();
    showToastChat(text, true);

    // Step1: 아직 /chat은 없음 → 다음 단계에서 붙일 예정
    showToastChat("Step1: chat endpoint not wired yet. Next step will execute plans.", false);

    chatInput.value = "";
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  await ensureProject();
  wireTrackControls();
  wireChatSend();
});
