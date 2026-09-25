// Telegram Mini App — интеграция с WebApp SDK
const tg = window.Telegram?.WebApp;
if (tg) {
  tg.ready();
  tg.expand();
  tg.enableClosingConfirmation();
}

async function getUserId() {
  if (tg?.initData) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/telegram/validate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ initData: tg.initData }),
      });
      if (res.ok) return (await res.json()).user_id;
    } catch (err) {
      console.error("Ошибка валидации Telegram initData:", err);
    }
  }
  let id = localStorage.getItem("audiobook_user_id");
  if (!id) {
    id = "dev_user_" + Math.random().toString(36).slice(2, 10);
    localStorage.setItem("audiobook_user_id", id);
  }
  return id;
}

let USER_ID = null;

// ---------- DOM ----------
const listEl        = document.getElementById("book-list");
const audioEl       = document.getElementById("audio");
const playerBarEl   = document.getElementById("player-bar");
const playerTitleEl = document.getElementById("player-title");
const playerTimeEl  = document.getElementById("player-time");
const seekEl        = document.getElementById("seek");
const speedEl       = document.getElementById("speed");
const btnPlay       = document.getElementById("btn-play");
const btnBack       = document.getElementById("btn-back");
const btnForward    = document.getElementById("btn-forward");
const btnNavBack    = document.getElementById("btn-nav-back");
const appTitleEl    = document.getElementById("app-title");
const appSubtitleEl = document.getElementById("app-subtitle");
const tagFilterBar  = document.getElementById("tag-filter-bar");
const tagSelect     = document.getElementById("tag-select");
const tagFooter     = document.getElementById("tag-footer");
const tagFooterList = document.getElementById("tag-footer-list");
const searchBar     = document.getElementById("search-bar");
const searchInput   = document.getElementById("book-search");

// ---------- Состояние ----------
let currentView            = "books";
let books                  = [];
let chapters               = [];
let currentBookForChapters = null;
let currentChapter         = null;
let progressSaveTimer      = null;
let activeTag              = "";
let searchQuery            = "";

// ---------- Утилиты ----------
function formatTime(s) {
  if (!isFinite(s) || s < 0) return "0:00";
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}
function escapeHtml(str) {
  const d = document.createElement("div");
  d.textContent = str;
  return d.innerHTML;
}
function allTags() {
  const set = new Set();
  for (const b of books) for (const t of b.tags || []) set.add(t);
  return [...set].sort();
}

// ---------- Локальный прогресс ----------
// Структура в localStorage:
//   lp_opened       = JSON Set ID книг которые открывали
//   lp_ch_{fileId}  = {pct: 0-100, done: bool}  — прогресс главы
//   lp_book_{bookId} = {done: bool}               — книга целиком прослушана

function lpGet(key, def) {
  try { return JSON.parse(localStorage.getItem(key)) ?? def; } catch { return def; }
}
function lpSet(key, val) {
  try { localStorage.setItem(key, JSON.stringify(val)); } catch {}
}

function markBookOpened(bookId) {
  const s = new Set(lpGet("lp_opened", []));
  s.add(bookId);
  lpSet("lp_opened", [...s]);
}
function wasBookOpened(bookId) {
  return new Set(lpGet("lp_opened", [])).has(bookId);
}

function getChapterProgress(fileId) {
  return lpGet(`lp_ch_${fileId}`, { pct: 0, done: false });
}
function setChapterProgress(fileId, pct, done) {
  lpSet(`lp_ch_${fileId}`, { pct, done });
}

function isBookFinished(bookId) {
  return lpGet(`lp_book_${bookId}`, { done: false }).done;
}
function setBookFinished(bookId) {
  lpSet(`lp_book_${bookId}`, { done: true });
}

function checkBookCompletion(bookId) {
  if (!chapters.length) return;
  const allDone = chapters.every(ch => getChapterProgress(ch.id).done);
  if (allDone) setBookFinished(bookId);
}

// ---------- UI-видимость ----------
function showBooksUI() {
  tagFilterBar.classList.remove("tag-filter-bar--hidden");
  tagFooter.classList.remove("tag-footer--hidden");
  searchBar.classList.remove("search-bar--hidden");
}
function hideBooksUI() {
  tagFilterBar.classList.add("tag-filter-bar--hidden");
  tagFooter.classList.add("tag-footer--hidden");
  searchBar.classList.add("search-bar--hidden");
}

// ---------- Теги: select + footer ----------
function updateTagUI() {
  const tags = allTags();
  tagSelect.innerHTML =
    `<option value="">— Все книги —</option>` +
    tags.map(t =>
      `<option value="${escapeHtml(t)}"${activeTag === t ? " selected" : ""}>${escapeHtml(t)}</option>`
    ).join("");

  if (!tags.length) { tagFooter.classList.add("tag-footer--hidden"); return; }
  tagFooter.classList.remove("tag-footer--hidden");
  tagFooterList.innerHTML = tags.map(t =>
    `<button class="tag-chip${activeTag === t ? " tag-chip--active" : ""}" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`
  ).join("");
  tagFooterList.querySelectorAll(".tag-chip").forEach(btn => {
    btn.addEventListener("click", () => {
      activeTag = btn.dataset.tag === activeTag ? "" : btn.dataset.tag;
      searchQuery = "";
      searchInput.value = "";
      tagSelect.value = activeTag;
      updateTagUI();
      renderBookList();
    });
  });
}

tagSelect.addEventListener("change", () => {
  activeTag = tagSelect.value;
  updateTagUI();
  renderBookList();
});

// ---------- Поиск ----------
searchInput.addEventListener("input", () => {
  searchQuery = searchInput.value.trim().toLowerCase();
  renderBookList();
});

// ---------- Экран 1: список книг ----------
async function fetchBooks() {
  currentView = "books";
  btnNavBack.classList.add("nav-back--hidden");
  appTitleEl.textContent = "БИБЛИАРИУМ";
  appSubtitleEl.textContent = "Библиотека аудиокниг по вселенной WARHAMMER";
  showBooksUI();

  listEl.innerHTML = `<p class="loading">Загрузка списка книг…</p>`;
  try {
    const res = await fetch(`${API_BASE_URL}/api/books`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Ошибка сервера: ${res.status}`);
    }
    books = await res.json();
    updateTagUI();
    renderBookList();
  } catch (err) {
    listEl.innerHTML = `<p class="error">Не удалось загрузить книги: ${escapeHtml(err.message)}</p>`;
  }
}

function renderBookList() {
  let filtered = books;
  if (activeTag) filtered = filtered.filter(b => (b.tags || []).includes(activeTag));
  if (searchQuery) filtered = filtered.filter(b => b.title.toLowerCase().includes(searchQuery));

  if (!filtered.length) {
    listEl.innerHTML = `<p class="empty">${
      searchQuery ? `По запросу «${escapeHtml(searchQuery)}» ничего не найдено.` :
      activeTag   ? `Книг с тегом «${escapeHtml(activeTag)}» не найдено.` :
                    "На Google Drive не найдено папок с книгами."
    }</p>`;
    return;
  }

  listEl.innerHTML = "";
  for (const book of filtered) {
    const card = document.createElement("div");
    card.className = "book-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");
    card.dataset.bookId = book.id;

    const opened   = wasBookOpened(book.id);
    const finished = isBookFinished(book.id);

    const coverHtml = book.coverFileId
      ? `<img class="book-card__cover" src="${API_BASE_URL}/api/cover/${book.coverFileId}" alt="" loading="lazy" />`
      : `<span class="book-card__cover book-card__cover--placeholder">📖</span>`;

    const tagsHtml = (book.tags || []).length
      ? `<span class="book-card__tags">${book.tags.map(t =>
          `<span class="tag-badge">${escapeHtml(t)}</span>`
        ).join("")}</span>`
      : "";

    card.innerHTML = `
      <span class="book-card__main">
        <span class="book-card__cover-wrap">
          ${coverHtml}
          ${finished ? `<span class="book-badge book-badge--done" title="Прослушано">✓</span>` : ""}
          ${!opened  ? `<span class="book-badge book-badge--new" title="Новинка">!</span>` : ""}
        </span>
        <span class="book-card__info">
          <span class="book-card__title">${escapeHtml(book.title)}</span>
          ${tagsHtml}
        </span>
      </span>
    `;

    card.addEventListener("click", () => openBook(book));
    card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") openBook(book); });
    listEl.appendChild(card);
  }
}

// ---------- Экран 2: главы книги ----------
async function openBook(book) {
  markBookOpened(book.id);
  currentView = "chapters";
  currentBookForChapters = book;
  btnNavBack.classList.remove("nav-back--hidden");
  appTitleEl.textContent = "БИБЛИАРИУМ";
  appSubtitleEl.textContent = "Выберите главу // WARHAMMER 40,000";
  hideBooksUI();

  listEl.innerHTML = `<p class="loading">Загрузка глав…</p>`;
  try {
    const res = await fetch(`${API_BASE_URL}/api/books/${book.id}/chapters`);
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail || `Ошибка сервера: ${res.status}`);
    }
    const payload = await res.json();
    const chapterItems = Array.isArray(payload) ? payload : (payload.chapters || []);
    chapters = chapterItems.filter(ch => {
      const name = String(ch.title || "").toLowerCase();
      const mime = String(ch.mimeType || "").toLowerCase();
      return mime.startsWith("audio/") || /\.(mp3|m4a|m4b|aac|ogg|oga|wav|flac|opus)$/i.test(name);
    });
    currentBookForChapters = {
      ...book,
      coverFileId: payload.coverFileId || book.coverFileId,
      annotation:  payload.annotation  || "",
      narrator:    payload.narrator    || "",
      tags:        payload.tags        || book.tags || [],
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

  const narratorHtml = book?.narrator
    ? `<p class="book-detail__narrator">Читает: <strong>${escapeHtml(book.narrator)}</strong></p>`
    : "";

  // Теги на странице книги — кликабельные, возвращают на главную с фильтром
  const detailTagsHtml = (book?.tags || []).length
    ? `<div class="book-detail__tags">${book.tags.map(t =>
        `<button class="tag-badge tag-badge--detail tag-badge--link" data-tag="${escapeHtml(t)}">${escapeHtml(t)}</button>`
      ).join("")}</div>`
    : "";

  const annotation = book?.annotation || "Аннотация к этой книге пока не добавлена.";

  // Общий прогресс книги
  const doneCnt  = chapters.filter(ch => getChapterProgress(ch.id).done).length;
  const totalCnt = chapters.length;
  const pctBook  = totalCnt > 0 ? Math.round((doneCnt / totalCnt) * 100) : 0;
  const progressBarHtml = `
    <div class="book-progress">
      <div class="book-progress__bar">
        <div class="book-progress__fill" style="width:${pctBook}%"></div>
      </div>
      <span class="book-progress__label">${doneCnt} / ${totalCnt} глав</span>
    </div>`;

  listEl.innerHTML = `
    <section class="book-detail" aria-label="Описание книги">
      ${coverHtml}
      <div class="book-detail__copy">
        <span class="book-detail__eyebrow">ARCHIVE // AUDIO TOME</span>
        <h2>${escapeHtml(book.title)}</h2>
        ${narratorHtml}
        ${detailTagsHtml}
        ${progressBarHtml}
        <p>${escapeHtml(annotation)}</p>
      </div>
    </section>
    <div class="chapter-heading">
      <span>СОДЕРЖАНИЕ</span>
      <span>${totalCnt} глав</span>
    </div>
    <div class="chapter-list"></div>
  `;

  // Привязываем клики по тегам → возврат на главную с фильтром
  listEl.querySelectorAll(".tag-badge--link").forEach(btn => {
    btn.addEventListener("click", e => {
      e.stopPropagation();
      activeTag = btn.dataset.tag;
      searchQuery = "";
      fetchBooks().then(() => {
        tagSelect.value = activeTag;
        updateTagUI();
        renderBookList();
      });
    });
  });

  const chapterListEl = listEl.querySelector(".chapter-list");
  chapters.forEach((chapter, index) => {
    const cp = getChapterProgress(chapter.id);
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
      <span class="chapter-card__body">
        <span class="chapter-card__top">
          <span class="book-card__title">${escapeHtml(chapter.title)}</span>
          <span class="chapter-card__right">
            <span class="book-card__meta">${sizeLabel}</span>
            ${cp.done ? `<span class="chapter-done" title="Прослушано">✓</span>` : ""}
          </span>
        </span>
        <span class="chapter-progress" style="--pct:${cp.pct}%"></span>
      </span>
    `;

    card.addEventListener("click", () => playChapter(chapter));
    card.addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") playChapter(chapter); });
    chapterListEl.appendChild(card);
  });

  highlightActiveCard();
}

btnNavBack.addEventListener("click", () => {
  currentView = "books";
  currentBookForChapters = null;
  fetchBooks();
});

// ---------- Подсветка активной главы ----------
function highlightActiveCard() {
  document.querySelectorAll(".book-card").forEach(card => {
    card.classList.toggle(
      "book-card--active",
      !!currentChapter && card.dataset.fileId === currentChapter.id
    );
  });
}

// ---------- Плеер ----------
async function playChapter(chapter) {
  currentChapter = chapter;
  highlightActiveCard();

  audioEl.src = `${API_BASE_URL}/api/stream/${chapter.id}`;
  const bookTitle = currentBookForChapters ? `${currentBookForChapters.title} — ` : "";
  playerTitleEl.textContent = `${bookTitle}${chapter.title}`;
  playerBarEl.classList.remove("player-bar--hidden");

  if (tg?.HapticFeedback) tg.HapticFeedback.impactOccurred("light");

  try {
    const res = await fetch(`${API_BASE_URL}/api/progress/${USER_ID}`);
    if (res.ok) {
      const allProgress = await res.json();
      const saved = allProgress[chapter.id];
      if (saved) audioEl.addEventListener("loadedmetadata", () => { audioEl.currentTime = saved; }, { once: true });
    }
  } catch {}

  audioEl.playbackRate = parseFloat(speedEl.value);
  await audioEl.play().catch(() => {});
}

function togglePlay() {
  if (!currentChapter) return;
  audioEl.paused ? audioEl.play() : audioEl.pause();
}

btnPlay.addEventListener("click",    togglePlay);
btnBack.addEventListener("click",    () => { audioEl.currentTime = Math.max(0, audioEl.currentTime - 15); });
btnForward.addEventListener("click", () => { audioEl.currentTime = Math.min(audioEl.duration || Infinity, audioEl.currentTime + 30); });
speedEl.addEventListener("change",   () => { audioEl.playbackRate = parseFloat(speedEl.value); });
seekEl.addEventListener("input",     () => { if (audioEl.duration) audioEl.currentTime = (parseFloat(seekEl.value) / 100) * audioEl.duration; });
audioEl.addEventListener("play",     () => { btnPlay.textContent = "⏸"; });
audioEl.addEventListener("pause",    () => { btnPlay.textContent = "▶"; });

audioEl.addEventListener("timeupdate", () => {
  if (!currentChapter) return;
  const dur = audioEl.duration;
  if (dur) {
    const pct = (audioEl.currentTime / dur) * 100;
    seekEl.value = pct;

    // Обновляем локальный прогресс каждые ~5 сек через scheduleProgressSave
    const cp = getChapterProgress(currentChapter.id);
    if (!cp.done) setChapterProgress(currentChapter.id, Math.round(pct), false);

    // Обновляем прогресс-бар главы в списке
    const card = document.querySelector(`.chapter-card[data-file-id="${currentChapter.id}"]`);
    if (card) {
      const bar = card.querySelector(".chapter-progress");
      if (bar) bar.style.setProperty("--pct", `${Math.round(pct)}%`);
    }
  }
  playerTimeEl.textContent = `${formatTime(audioEl.currentTime)} / ${formatTime(audioEl.duration)}`;
  scheduleProgressSave();
});

audioEl.addEventListener("ended", () => {
  btnPlay.textContent = "▶";

  if (currentChapter) {
    // Отмечаем главу как прослушанную
    setChapterProgress(currentChapter.id, 100, true);

    // Обновляем галочку в списке
    const card = document.querySelector(`.chapter-card[data-file-id="${currentChapter.id}"]`);
    if (card) {
      const right = card.querySelector(".chapter-card__right");
      if (right && !right.querySelector(".chapter-done")) {
        const mark = document.createElement("span");
        mark.className = "chapter-done";
        mark.title = "Прослушано";
        mark.textContent = "✓";
        right.appendChild(mark);
      }
      const bar = card.querySelector(".chapter-progress");
      if (bar) bar.style.setProperty("--pct", "100%");
    }

    // Проверяем завершение книги
    if (currentBookForChapters) {
      checkBookCompletion(currentBookForChapters.id);
      // Обновляем счётчик прогресса
      const doneCnt = chapters.filter(ch => getChapterProgress(ch.id).done).length;
      const label = document.querySelector(".book-progress__label");
      const fill  = document.querySelector(".book-progress__fill");
      if (label) label.textContent = `${doneCnt} / ${chapters.length} глав`;
      if (fill)  fill.style.width = `${Math.round(doneCnt / chapters.length * 100)}%`;
    }
  }

  saveProgressNow();
  playNextChapter();
});

function playNextChapter() {
  if (!currentChapter) return;
  const idx  = chapters.findIndex(c => c.id === currentChapter.id);
  const next = chapters[idx + 1];
  if (next) playChapter(next);
}

function scheduleProgressSave() {
  if (progressSaveTimer) return;
  progressSaveTimer = setTimeout(() => { progressSaveTimer = null; saveProgressNow(); }, 5000);
}

async function saveProgressNow() {
  if (!currentChapter || !audioEl.currentTime || !USER_ID) return;
  try {
    await fetch(`${API_BASE_URL}/api/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: USER_ID, file_id: currentChapter.id, position_seconds: audioEl.currentTime }),
    });
  } catch {}
}

// ---------- Запуск ----------
(async () => {
  USER_ID = await getUserId();
  await fetchBooks();
})();
