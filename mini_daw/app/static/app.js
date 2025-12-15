/**
 * app.js (Step 3)
 *
 * 목표:
 * - 서버(ProjectState)를 source of truth로 사용
 * - 채팅 명령(/chat) 결과의 state.events를 타임라인에 렌더
 * - 트랙 컨트롤(볼륨/팬/뮤트/솔로)을 서버와 동기화
 *
 * 가정:
 * - index.html에는 inline script(가짜 채팅/프로그레스 시뮬레이션)가 제거되어 있음
 * - index.html 마지막에 <script src="/static/app.js"></script> 가 존재
 */

let PROJECT_ID = null;
let LAST_STATE = null;

// track name -> track_id
const TRACK_ID = { drums: 1, bass: 2, pad: 3, lead: 4 };
// track_id -> data-track attribute
const TRACK_KEY = { 1: "drums", 2: "bass", 3: "pad", 4: "lead" };

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const txt = await res.text();
    throw new Error(txt);
  }
  return res.json();
}

/** 채팅 메시지 UI 출력 */
function addChatMessage(text, isUser) {
  const chatContainer = document.getElementById("chatContainer");
  if (!chatContainer) return;

  const message = document.createElement("div");
  message.className = `chat-message ${isUser ? "user-message" : "ai-message"}`;
  message.innerHTML = `
    <div class="message-sender">${isUser ? "You" : "AI Assistant"}</div>
    <div class="message-bubble"></div>
  `;
  message.querySelector(".message-bubble").textContent = text;

  chatContainer.appendChild(message);
  chatContainer.scrollTop = chatContainer.scrollHeight;
}

/** (선택) 상단 진행 UI */
function showProgress(text) {
  const overlay = document.getElementById("progressOverlay");
  const progressText = document.getElementById("progressText");
  const progressBar = document.getElementById("progressBar");
  if (!overlay || !progressText || !progressBar) return;

  progressText.textContent = text;
  progressBar.style.width = "15%";
  overlay.classList.add("active");
}
function hideProgress() {
  const overlay = document.getElementById("progressOverlay");
  const progressBar = document.getElementById("progressBar");
  if (!overlay || !progressBar) return;
  overlay.classList.remove("active");
  progressBar.style.width = "0%";
}

/** 프로젝트가 없으면 생성 */
async function ensureProject() {
  if (PROJECT_ID) return PROJECT_ID;

  const data = await api("/api/projects", {
    method: "POST",
    body: JSON.stringify({ name: "My Project", bpm: 120, bars: 4 }),
  });

  PROJECT_ID = data.state.id;
  LAST_STATE = data.state;

  renderAll(LAST_STATE);
  addChatMessage(`Project created: ${PROJECT_ID}`, false);
  return PROJECT_ID;
}

/** 서버에서 프로젝트 상태 다시 로드 */
async function reloadState() {
  const id = await ensureProject();
  const data = await api(`/api/projects/${id}`, { method: "GET" });
  LAST_STATE = data.state;
  renderAll(LAST_STATE);
  return LAST_STATE;
}

/** /chat 호출 */
async function sendChatCommand(text) {
  const id = await ensureProject();
  showProgress("Processing...");
  const data = await api(`/api/projects/${id}/chat`, {
    method: "POST",
    body: JSON.stringify({ message: text }),
  });
  hideProgress();

  LAST_STATE = data.state;
  renderAll(LAST_STATE);

  // 서버 로그를 채팅에 출력
  if (data.messages && data.messages.length) {
    data.messages.forEach((m) => addChatMessage(m, false));
  } else {
    addChatMessage("No actions executed.", false);
  }
  return data;
}

// job 폴링 유틸 추가
async function pollJob(job_id, onUpdate, intervalMs = 250) {
  while (true) {
    const data = await api(`/api/jobs/${job_id}`, { method: "GET" });
    onUpdate(data);

    if (data.status === "done") return data;
    if (data.status === "failed") throw new Error(data.error || "job failed");

    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** meta UI 표시(현재 index.html에서 meta-value들이 id가 없어서 최소만) */
function renderMeta(state) {
  const projectNameEl = document.getElementById("projectName");
  if (projectNameEl) projectNameEl.textContent = state.name;

  // BPM 입력(transport bar에 type=number가 있지만 id가 없어서 querySelector로 잡음)
  const bpmInput = document.querySelector(".transport-input");
  if (bpmInput) bpmInput.value = state.meta.bpm;

  // Swing slider도 id가 없어서 class로 잡음
  const swingSlider = document.querySelector(".swing-slider");
  if (swingSlider) {
    // 서버 swing 0~0.5 -> UI 0~100 변환(대충)
    swingSlider.value = Math.round((state.meta.swing / 0.5) * 100);
  }
}

/** 트랙 컨트롤(볼륨/팬/뮤트/솔로) UI 렌더 */
function renderTrackControls(state) {
  for (const t of state.tracks) {
    const key = TRACK_KEY[t.id];

    // volume slider
    const vol = document.getElementById(`${key}Vol`);
    const volValue = document.getElementById(`${key}VolValue`);
    if (vol) vol.value = Math.round(t.volume * 100);
    if (volValue) volValue.textContent = Math.round(t.volume * 100);

    // pan slider: -1..1 -> -50..50
    const pan = document.getElementById(`${key}Pan`);
    const panValue = document.getElementById(`${key}PanValue`);
    if (pan) pan.value = Math.round(t.pan * 50);
    if (panValue) {
      const v = Math.round(t.pan * 50);
      if (v === 0) panValue.textContent = "C";
      else if (v < 0) panValue.textContent = `L${Math.abs(v)}`;
      else panValue.textContent = `R${v}`;
    }

    // mute/solo toggle class
    const muteBtn = document.getElementById(`${key}Mute`);
    const soloBtn = document.getElementById(`${key}Solo`);
    if (muteBtn) muteBtn.classList.toggle("active", !!t.mute);
    if (soloBtn) soloBtn.classList.toggle("active", !!t.solo);
  }
}

/** 타임라인 렌더: state.events -> 각 track-grid에 event-block 생성 */
function renderTimeline(state) {
  // 기존 event-block(샘플로 박혀 있던 것 포함) 전부 제거
  document.querySelectorAll(".track-grid").forEach((grid) => {
    grid.querySelectorAll(".event-block").forEach((b) => b.remove());
  });

  const totalTicks = state.meta.total_ticks; // bars * ticks_per_bar
  if (!totalTicks) return;

  for (const ev of state.events) {
    const trackKey = TRACK_KEY[ev.track_id];
    const grid = document.querySelector(`.track-grid[data-track="${trackKey}"]`);
    if (!grid) continue;

    // left/width percent 계산
    const leftPct = (ev.start_tick / totalTicks) * 100;
    const widthPct = (ev.duration_tick / totalTicks) * 100;

    const block = document.createElement("div");
    block.className = "event-block";
    block.style.left = `${leftPct}%`;
    block.style.width = `${Math.max(widthPct, 1.5)}%`; // 너무 얇으면 안 보이니 최소 폭

    // 아이콘(드럼/멜로디) 간단 구분
    if (ev.type === "drum") {
      block.textContent = "🥁";
    } else {
      block.textContent = "♪";
    }

    block.dataset.eventId = ev.id;
    block.title = `${ev.id}\ntrack=${ev.track_id}\nstart=${ev.start_tick}\ndur=${ev.duration_tick}\n${ev.pitch || ""}`;

    // 클릭하면 선택 표시(선택 저장은 Step4에서 서버로도 보냄)
    block.addEventListener("click", () => {
      document.querySelectorAll(".event-block").forEach((b) => b.classList.remove("selected"));
      block.classList.add("selected");
    });

    grid.appendChild(block);
  }
}

/** 전체 렌더 */
function renderAll(state) {
  renderMeta(state);
  renderTrackControls(state);
  renderTimeline(state);
}

/** 서버에 트랙 PATCH */
async function patchTrack(trackKey, patch) {
  const id = await ensureProject();
  const trackId = TRACK_ID[trackKey];
  showProgress("Updating track...");
  const data = await api(`/api/projects/${id}/tracks/${trackId}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
  hideProgress();
  LAST_STATE = data.state;
  renderAll(LAST_STATE);
}

/** UI 이벤트 연결 */
function wireUI() {
  // 채팅 Send/Enter
  const chatInput = document.getElementById("chatInput");
  const sendButton = document.getElementById("sendButton");
  const undoButton = document.getElementById("undoButton");

  if (sendButton && chatInput) {
    sendButton.addEventListener("click", async () => {
      const text = chatInput.value.trim();
      if (!text) return;
      addChatMessage(text, true);
      chatInput.value = "";
      await sendChatCommand(text);
    });

    chatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") sendButton.click();
    });
  }

  if (undoButton) {
    undoButton.addEventListener("click", async () => {
      addChatMessage("undo", true);
      await sendChatCommand("undo");
    });
  }

  // 트랙 슬라이더/버튼
  ["drums", "bass", "pad", "lead"].forEach((trackKey) => {
    const vol = document.getElementById(`${trackKey}Vol`);
    const pan = document.getElementById(`${trackKey}Pan`);
    const muteBtn = document.getElementById(`${trackKey}Mute`);
    const soloBtn = document.getElementById(`${trackKey}Solo`);

    if (vol) {
      vol.addEventListener("change", async (e) => {
        const v = parseInt(e.target.value, 10) / 100.0;
        await patchTrack(trackKey, { volume: v });
      });
    }

    if (pan) {
      pan.addEventListener("change", async (e) => {
        const p = parseInt(e.target.value, 10) / 50.0;
        await patchTrack(trackKey, { pan: p });
      });
    }

    if (muteBtn) {
      muteBtn.addEventListener("click", async () => {
        const next = !muteBtn.classList.contains("active");
        await patchTrack(trackKey, { mute: next });
      });
    }

    if (soloBtn) {
      soloBtn.addEventListener("click", async () => {
        const next = !soloBtn.classList.contains("active");
        await patchTrack(trackKey, { solo: next });
      });
    }
  });

  // Render Preview Step4 에서 붙임
  const renderButton = document.getElementById("renderButton");
  if (renderButton) {
    renderButton.addEventListener("click", async () => {
      const id = await ensureProject();
      addChatMessage("Render Preview", true);

      const job = await api(`/api/projects/${id}/jobs/render_preview`, {
        method: "POST",
        body: JSON.stringify({ bar_start: 1, bars: 2, seconds: 2.0 }),
      });

      const done = await pollJob(job.job_id, (j) => {
        showProgress(`${j.message} (${j.progress}%)`);
        const bar = document.getElementById("progressBar");
        if (bar) bar.style.width = `${j.progress}%`;
      });

      hideProgress();
      addChatMessage(`Preview ready: ${done.result.wav_url}`, false);

      // 오디오 플레이어에 반영(하단 audio 태그가 있으면 src 설정)
      const audio = document.getElementById("audioPlayer");
      if (audio && done.result && done.result.wav_url) {
        audio.src = done.result.wav_url;
        audio.load();
      }
    });
  }

  // Mixdown
  const mixdownButton = document.getElementById("mixdownButton");
  if (mixdownButton) {
    mixdownButton.addEventListener("click", async () => {
      const id = await ensureProject();
      addChatMessage("Render Mixdown", true);

      const job = await api(`/api/projects/${id}/jobs/render_mixdown`, {
        method: "POST",
        body: JSON.stringify({ bar_start: 1, bars: 4, seconds: 6.0 }),
      });

      const done = await pollJob(job.job_id, (j) => {
        showProgress(`${j.message} (${j.progress}%)`);
        const bar = document.getElementById("progressBar");
        if (bar) bar.style.width = `${j.progress}%`;
      });

      hideProgress();
      addChatMessage(`Mixdown ready: ${done.result.wav_url}`, false);

      // 다운로드 버튼 동작(간단히 새 탭 오픈)
      window.open(done.result.wav_url, "_blank");
    });
  }

  // Generate Sample
  const generateSampleButton = document.getElementById("generateSample");
  if (generateSampleButton) {
    generateSampleButton.addEventListener("click", async () => {
      const id = await ensureProject();
      addChatMessage("Generate Sample", true);

      const job = await api(`/api/projects/${id}/jobs/generate_sample`, {
        method: "POST",
        body: JSON.stringify({
          instrument: "bass",
          base_pitch: "A1",
          prompt: "warm bass (stub)",
          seconds: 1.5
        }),
      });

      const done = await pollJob(job.job_id, (j) => {
        showProgress(`${j.message} (${j.progress}%)`);
        const bar = document.getElementById("progressBar");
        if (bar) bar.style.width = `${j.progress}%`;
      });

      hideProgress();
      addChatMessage(`Sample generated: ${done.result.sample_id}`, false);

      // 샘플 리스트 UI 반영은 Step5에서(지금은 reloadState로 충분)
      await reloadState();
    });
  }

  // // (지금은 렌더/샘플 버튼은 Step4에서 job 붙일 예정)
  // const renderButton = document.getElementById("renderButton");
  // const mixdownButton = document.getElementById("mixdownButton");
  // const generateSampleButton = document.getElementById("generateSample");

  // if (renderButton) {
  //   renderButton.addEventListener("click", () => {
  //     addChatMessage("Render Preview (Step4 예정)", false);
  //   });
  // }
  // if (mixdownButton) {
  //   mixdownButton.addEventListener("click", () => {
  //     addChatMessage("Mixdown (Step4 예정)", false);
  //   });
  // }
  // if (generateSampleButton) {
  //   generateSampleButton.addEventListener("click", () => {
  //     addChatMessage("Generate Sample (Step4 예정)", false);
  //   });
  // }
}

window.addEventListener("DOMContentLoaded", async () => {
  await ensureProject();
  wireUI();
});

// /**
//  * app.js
//  *
//  * 현재 UI 버튼들을 실제 FastAPI API에 연결합니다.
//  * Step1에서는 "프로젝트 생성 → 상태 불러오기 → 트랙 조절 반영"까지만 합니다.
//  */

// let PROJECT_ID = null;

// async function api(path, options = {}) {
//   const res = await fetch(path, {
//     headers: { "Content-Type": "application/json" },
//     ...options,
//   });
//   if (!res.ok) {
//     const msg = await res.text();
//     throw new Error(msg);
//   }
//   return res.json();
// }

// function setMetaUI(state) {
//   // 상단 프로젝트명
//   const projectNameEl = document.getElementById("projectName");
//   if (projectNameEl) projectNameEl.textContent = state.name;

//   // meta 표시는 ui.html에서 id가 없어서(지금은 고정 텍스트),
//   // Step2에서 meta 영역에도 id 부여해서 업데이트하도록 개선할게요.
// }

// function showToastChat(text, isUser) {
//   // ui.html의 채팅 추가 로직을 그대로 써도 되지만,
//   // Step1에서는 최소로만: "Command received" 정도 찍기 용도.
//   const chatContainer = document.getElementById("chatContainer");
//   if (!chatContainer) return;

//   const message = document.createElement("div");
//   message.className = `chat-message ${isUser ? "user-message" : "ai-message"}`;
//   message.innerHTML = `
//     <div class="message-sender">${isUser ? "You" : "Server"}</div>
//     <div class="message-bubble">${text}</div>
//   `;
//   chatContainer.appendChild(message);
//   chatContainer.scrollTop = chatContainer.scrollHeight;
// }

// async function ensureProject() {
//   if (PROJECT_ID) return PROJECT_ID;

//   // 기본 프로젝트 생성
//   const data = await api("/api/projects", {
//     method: "POST",
//     body: JSON.stringify({ name: "My Project", bpm: 120, bars: 4 }),
//   });

//   PROJECT_ID = data.state.id;
//   setMetaUI(data.state);
//   showToastChat(`Project created: ${PROJECT_ID}`, false);

//   return PROJECT_ID;
// }

// async function patchTrack(trackName, patch) {
//   const id = await ensureProject();

//   const trackIdMap = { drums: 1, bass: 2, pad: 3, lead: 4 };
//   const track_id = trackIdMap[trackName];

//   const data = await api(`/api/projects/${id}/tracks/${track_id}`, {
//     method: "PATCH",
//     body: JSON.stringify(patch),
//   });

//   showToastChat(`${trackName} updated`, false);
//   setMetaUI(data.state);
// }

// function wireTrackControls() {
//   const tracks = ["drums", "bass", "pad", "lead"];

//   tracks.forEach((t) => {
//     const vol = document.getElementById(`${t}Vol`);
//     const pan = document.getElementById(`${t}Pan`);
//     const mute = document.getElementById(`${t}Mute`);
//     const solo = document.getElementById(`${t}Solo`);

//     if (vol) {
//       vol.addEventListener("change", async (e) => {
//         const value = parseInt(e.target.value, 10) / 100.0;
//         await patchTrack(t, { volume: value });
//       });
//     }

//     if (pan) {
//       pan.addEventListener("change", async (e) => {
//         // UI pan: -50~50 => -1~1
//         const value = parseInt(e.target.value, 10) / 50.0;
//         await patchTrack(t, { pan: value });
//       });
//     }

//     if (mute) {
//       mute.addEventListener("click", async () => {
//         const isActive = mute.classList.contains("active");
//         await patchTrack(t, { mute: isActive });
//       });
//     }

//     if (solo) {
//       solo.addEventListener("click", async () => {
//         const isActive = solo.classList.contains("active");
//         await patchTrack(t, { solo: isActive });
//       });
//     }
//   });
// }

// // Step 2: 채팅 전송 함수
// async function sendChat(text) {
//   const id = await ensureProject();

//   const data = await api(`/api/projects/${id}/chat`, {
//     method: "POST",
//     body: JSON.stringify({ message: text }),
//   });

//   // 서버 메시지(실행 로그)
//   if (data.messages && data.messages.length) {
//     data.messages.forEach((m) => showToastChat(m, false));
//   } else {
//     showToastChat("No actions executed.", false);
//   }

//   return data;
// }

// function wireChatSend() {
//   const chatInput = document.getElementById("chatInput");
//   const sendButton = document.getElementById("sendButton");
//   const undoButton = document.getElementById("undoButton");

//   if (sendButton) {
//     sendButton.addEventListener("click", async () => {
//       const text = chatInput.value.trim();
//       if (!text) return;

//       await ensureProject();
//       showToastChat(text, true);

//       await sendChat(text);

//       chatInput.value = "";
//     });
//   }

//   if (undoButton) {
//     undoButton.addEventListener("click", async () => {
//       await ensureProject();
//       showToastChat("undo", true);
//       await sendChat("undo");
//     });
//   }
// }


// // Step1에서는 채팅 기능은 아직 구현하지 않음
// // function wireChatSend() {
// //   const chatInput = document.getElementById("chatInput");
// //   const sendButton = document.getElementById("sendButton");

// //   if (!chatInput || !sendButton) return;

// //   sendButton.addEventListener("click", async () => {
// //     const text = chatInput.value.trim();
// //     if (!text) return;

// //     await ensureProject();
// //     showToastChat(text, true);

// //     // Step1: 아직 /chat은 없음 → 다음 단계에서 붙일 예정
// //     showToastChat("Step1: chat endpoint not wired yet. Next step will execute plans.", false);

// //     chatInput.value = "";
// //   });
// // }

// window.addEventListener("DOMContentLoaded", async () => {
//   await ensureProject();
//   wireTrackControls();
//   wireChatSend();
// });
