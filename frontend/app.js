// Telegram Mini App — интеграция с WebApp SDK
const tg = window.Telegram?.WebApp;

if (tg) {
  tg.ready();
  tg.expand(); // Разворачиваем на весь экран
  tg.enableClosingConfirmation(); // Подтверждение закрытия при воспроизведении
}

// Получение User ID из Telegram (или fallback для локальной разработки)
async function getUserId() {
  // Если запущено в Telegram Mini App — используем initData
  if (tg?.initData) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/telegram/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData }),
      });
      if (res.ok) {
        const data = await res.json();
        return data.user_id;
      }
    } catch (err) {
      console.error("Ошибка валидации Telegram initData:", err);
    }
  }

  // Fallback для локальной разработки без Telegram
  let id = localStorage.getItem("audiobook_user_id");
  if (!id) {
    id = "dev_user_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("audiobook_user_id", id);
  }
  return id;
}

let USER_ID = null;

const listEl = document.getElementById("book-list");
const audioEl = document.getElementById("audio");
const playerBarEl = document.getElementById("player-bar");
const playerTitleEl = document.getElementById("player-title");
const playerTimeEl = document.getElementById("player-time");
const seekEl = document.getElementById("seek");
const speedEl = document.getElementById("speed");
const btnPlay = document.getElementById("btn-play");
const btnBack = document.getElementById("btn-back");
const btnForward = document.getElementById("btn-forward");
const btnNavBack = document.getElementById("btn-nav-back");
const appTitleEl = document.getElementById("app-title");
const appSubtitleEl = document.getElementById("app-subtitle");

// "books"   — экран списка книг (папок) верхнего уровня
// "chapters" — экран списка глав внутри выбранной книги
let currentView = "books";
let books = [];
let chapters = [];
let currentBookForChapters = null;
let currentChapter = null;
let progressSaveTimer = null;
let activeTag = null; // текущий активный тег фильтра

function formatTime(totalSeconds) {
  if (!isFinite(totalSeconds) || totalSeconds < 0) return "0:00";
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function escapeHtml(str) {
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function renderTagPanel() {
  // Собираем все уникальные теги из загруженных книг
  const tagSet = new Set();
  for (const book of books) {
    for (const tag of book.tags || []) {
      tagSet.add(tag);
    }
  }
  const tags = [...tagSet].sort();

  // Если тегов нет — скрываем панель
  let panel = document.getElementById("tag-panel");
  if (!panel) {
    panel = document.createElement("div");
    panel.id = "tag-panel";
    panel.className = "tag-panel";
    listEl.before(panel);
  }

  if (!tags.length) {
    panel.hidden = true;
    return;
  }

  panel.hidden = false;
  panel.innerHTML = `
    <button class="tag-btn${activeTag === null ? " tag-btn--active" : ""}" data-tag="">Все</button>
    ${tags.map(tag => `
      <button class="tag-btn${activeTag === tag ? " tag-btn--active" : ""}" data-tag="${escapeHtml(tag)}">${escapeHtml(tag)}</button>
    `).join("")}
  `;

  panel.querySelectorAll(".tag-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      activeTag = btn.dataset.tag || null;
      renderTagPanel();
      renderBookList();
    });
  });
}

// ---------- Экран 1: список книг ----------

async function fetchBooks() {
  currentView = "books";
  btnNavBack.classList.add("nav-back--hidden");
  appTitleEl.textContent = "БИБЛИАРИУМ";
  appSubtitleEl.textContent = "Библиотека аудиокниг по вселенной WARHAMMER";

  listEl.innerHTML = `<p class="loading">Загрузка списка книг…</p>`;
  try {
    const res = await fetch(`${API_BASE_URL}/api/books`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Ошибка сервера: ${res.status}`);
    }
    books = await res.json();
    activeTag = null;
    renderTagPanel();
    renderBookList();
  } catch (err) {
    listEl.innerHTML = `<p class="error">Не удалось загрузить книги: ${escapeHtml(err.message)}</p>`;
  }
}

function renderBookList() {
  const filtered = activeTag
    ? books.filter((b) => (b.tags || []).includes(activeTag))
    : books;

  if (!filtered.length) {
    listEl.innerHTML = `<p class="empty">${activeTag ? `Книг с тегом «${escapeHtml(activeTag)}» не найдено.` : "На Google Drive не найдено папок с книгами."}</p>`;
    return;
  }

  listEl.innerHTML = "";
  for (const book of filtered) {
    const card = document.createElement("div");
    card.className = "book-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.dataset.bookId = book.id;

    const coverHtml = book.coverFileId
      ? `<img class="book-card__cover" src="${API_BASE_URL}/api/cover/${book.coverFileId}" alt="" loading="lazy" />`
      : `<span class="book-card__cover book-card__cover--placeholder">📖</span>`;

    const tagsHtml = (book.tags || []).length
      ? `<span class="book-card__tags">${book.tags.map((t) => `<span class="tag-badge">${escapeHtml(t)}</span>`).join("")}</span>`
      : "";

    card.innerHTML = `
      <span class="book-card__main">
        ${coverHtml}
        <span class="book-card__info">
          <span class="book-card__title">${escapeHtml(book.title)}</span>
          ${tagsHtml}
        </span>
      </span>
    `;

    card.addEventListener("click", () => openBook(book));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") openBook(book);
    });
    listEl.appendChild(card);
  }
}

// ---------- Экран 2: список глав внутри книги ----------

async function openBook(book) {
  currentView = "chapters";
  currentBookForChapters = book;
  btnNavBack.classList.remove("nav-back--hidden");
  appTitleEl.textContent = "БИБЛИАРИУМ";
  appSubtitleEl.textContent = currentBookForChapters
    ? "Выберите главу // WARHAMMER 40,000"
    : "Библиотека аудиокниг по вселенной WARHAMMER";

  listEl.innerHTML = `<p class="loading">Загрузка глав…</p>`;
  try {
    const res = await fetch(`${API_BASE_URL}/api/books/${book.id}/chapters`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Ошибка сервера: ${res.status}`);
    }
    const payload = await res.json();
    const chapterItems = Array.isArray(payload) ? payload : payload.chapters;
    chapters = (chapterItems || []).filter((chapter) => {
      const name = String(chapter.title || "").trim().toLowerCase();
      const mime = String(chapter.mimeType || "").toLowerCase();
      return mime.startsWith("audio/") || /\.(mp3|m4a|m4b|aac|ogg|oga|wav|flac|opus)$/i.test(name);
    });
    currentBookForChapters = {
      ...book,
      coverFileId: payload.coverFileId || book.coverFileId,
      annotation: payload.annotation || "",
      narrator: payload.narrator || "",
      tags: payload.tags || book.tags || [],
    };
    renderChapterList();
  } catch (err) {
    listEl.innerHTML = `<p class="error">Не удалось загрузить главы: ${escapeHtml(err.message)}</p>`;
  }
}

function renderChapterList() {
  if (!chapters.length) {
    listEl.innerHTML = `<p class="empty">В этой книге не найдено глав.</p>`;
    return;
  }

  const book = currentBookForChapters;
  const coverHtml = book?.coverFileId
    ? `<img class="book-detail__cover" src="${API_BASE_URL}/api/cover/${book.coverFileId}" alt="Обложка книги" />`
    : `<div class="book-detail__cover book-detail__cover--placeholder">NOCTIS</div>`;
  const annotation = book?.annotation || "Аннотация к этой книге пока не добавлена.";
  const narratorHtml = book?.narrator
    ? `<p class="book-detail__narrator">Читает: <strong>${escapeHtml(book.narrator)}</strong></p>`
    : "";
  const tagsHtml = (book?.tags || []).length
    ? `<div class="book-detail__tags">${book.tags.map((t) => `<span class="tag-badge tag-badge--detail">${escapeHtml(t)}</span>`).join("")}</div>`
    : "";

  listEl.innerHTML = `
    <section class="book-detail" aria-label="Описание книги">
      ${book?.coverFileId
        ? `<img class="book-detail__cover" src="${API_BASE_URL}/api/cover/${book.coverFileId}" alt="Обложка книги" />`
        : `<div class="book-detail__cover book-detail__cover--placeholder">NOCTIS</div>`}
      <div class="book-detail__copy">
        <span class="book-detail__eyebrow">ARCHIVE // AUDIO TOME</span>
        <h2>${escapeHtml(book.title)}</h2>
        ${narratorHtml}
        ${tagsHtml}
        <p>${escapeHtml(annotation)}</p>
      </div>
    </section>
    <div class="chapter-heading">
      <span>СОДЕРЖАНИЕ</span>
      <span>${chapters.length} глав</span>
    </div>
    <div class="chapter-list"></div>
  `;

  const chapterListEl = listEl.querySelector(".chapter-list");
  chapters.forEach((chapter, index) => {
    const card = document.createElement("div");
    card.className = "book-card chapter-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.dataset.fileId = chapter.id;

    const sizeLabel = chapter.sizeBytes
      ? `${(chapter.sizeBytes / (1024 * 1024)).toFixed(1)} МБ`
      : "";

    card.innerHTML = `
      <span class="chapter-card__index">${String(index + 1).padStart(2, "0")}</span>
      <span class="book-card__title">${escapeHtml(chapter.title)}</span>
      <span class="book-card__meta">${sizeLabel}</span>
    `;

    card.addEventListener("click", () => playChapter(chapter));
    card.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") playChapter(chapter);
    });
    chapterListEl.appendChild(card);
  });

  highlightActiveCard();
}

btnNavBack.addEventListener("click", () => {
  fetchBooks();
});

// ---------- Плеер ----------

function highlightActiveCard() {
  document.querySelectorAll(".book-card").forEach((card) => {
    card.classList.toggle(
      "book-card--active",
      currentChapter && card.dataset.fileId === currentChapter.id
    );
  });
}

async function playChapter(chapter) {
  currentChapter = chapter;
  highlightActiveCard();

  audioEl.src = `${API_BASE_URL}/api/stream/${chapter.id}`;
  const bookTitle = currentBookForChapters ? `${currentBookForChapters.title} — ` : "";
  playerTitleEl.textContent = `${bookTitle}${chapter.title}`;
  playerBarEl.classList.remove("player-bar--hidden");

  // Telegram haptic feedback при старте воспроизведения
  if (tg?.HapticFeedback) {
    tg.HapticFeedback.impactOccurred("light");
  }

  // Восстанавливаем позицию прослушивания, если она была сохранена
  try {
    const res = await fetch(`${API_BASE_URL}/api/progress/${USER_ID}`);
    if (res.ok) {
      const allProgress = await res.json();
      const savedPosition = allProgress[chapter.id];
      if (savedPosition) {
        audioEl.addEventListener(
          "loadedmetadata",
          () => {
            audioEl.currentTime = savedPosition;
          },
          { once: true }
        );
      }
    }
  } catch {
    // Если прогресс не загрузился — просто начинаем с начала, не критично
  }

  audioEl.playbackRate = parseFloat(speedEl.value);
  await audioEl.play().catch(() => {
    // Автовоспроизведение может быть блокировано браузером — это нормально,
    // пользователь нажмёт play вручную.
  });
}

function togglePlay() {
  if (!currentChapter) return;
  if (audioEl.paused) {
    audioEl.play();
  } else {
    audioEl.pause();
  }
}

btnPlay.addEventListener("click", togglePlay);

btnBack.addEventListener("click", () => {
  audioEl.currentTime = Math.max(0, audioEl.currentTime - 15);
  if (tg?.HapticFeedback) {
    tg.HapticFeedback.impactOccurred("light");
  }
});

btnForward.addEventListener("click", () => {
  audioEl.currentTime = Math.min(audioEl.duration || Infinity, audioEl.currentTime + 30);
  if (tg?.HapticFeedback) {
    tg.HapticFeedback.impactOccurred("light");
  }
});

speedEl.addEventListener("change", () => {
  audioEl.playbackRate = parseFloat(speedEl.value);
});

seekEl.addEventListener("input", () => {
  if (!audioEl.duration) return;
  audioEl.currentTime = (parseFloat(seekEl.value) / 100) * audioEl.duration;
});

audioEl.addEventListener("play", () => {
  btnPlay.textContent = "⏸";
});

audioEl.addEventListener("pause", () => {
  btnPlay.textContent = "▶";
});

audioEl.addEventListener("timeupdate", () => {
  if (audioEl.duration) {
    seekEl.value = (audioEl.currentTime / audioEl.duration) * 100;
  }
  playerTimeEl.textContent = `${formatTime(audioEl.currentTime)} / ${formatTime(audioEl.duration)}`;
  scheduleProgressSave();
});

audioEl.addEventListener("ended", () => {
  btnPlay.textContent = "▶";
  saveProgress();
  playNextChapter();
});

function playNextChapter() {
  if (!currentChapter) return;
  const currentIndex = chapters.findIndex((c) => c.id === currentChapter.id);
  const next = chapters[currentIndex + 1];
  if (next) {
    playChapter(next);
  }
}

function scheduleProgressSave() {
  if (progressSaveTimer) return;
  // Сохраняем прогресс не чаще раза в 5 секунд, чтобы не спамить backend
  progressSaveTimer = setTimeout(() => {
    saveProgress();
    progressSaveTimer = null;
  }, 5000);
}

async function saveProgress() {
  if (!currentChapter || !USER_ID) return;
  try {
    await fetch(`${API_BASE_URL}/api/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: USER_ID,
        file_id: currentChapter.id,
        position_seconds: audioEl.currentTime,
      }),
    });
  } catch {
    // Не критично, если один раз не сохранилось — попробуем на следующем тике
  }
}

// Сохраняем прогресс перед закрытием страницы
window.addEventListener("beforeunload", () => {
  if (currentChapter) saveProgress();
});

// Инициализация: получаем USER_ID, затем загружаем книги
getUserId().then((id) => {
  USER_ID = id;
  fetchBooks();
});
