const tg = window.Telegram?.WebApp ?? null;

const state = {
  loading: true,
  error: null,
  meta: null,
  items: [],
  screen: "home",
  formMode: "create",
  editingId: null,
  form: createEmptyForm(),
  formErrors: {},
  formError: "",
  submitting: false,
  dirty: false,
};

const refs = {
  app: document.getElementById("app"),
  pageSubtitle: document.getElementById("pageSubtitle"),
  statusBanner: document.getElementById("statusBanner"),
  homeScreen: document.getElementById("homeScreen"),
  formScreen: document.getElementById("formScreen"),
  loadingState: document.getElementById("loadingState"),
  errorState: document.getElementById("errorState"),
  errorText: document.getElementById("errorText"),
  emptyState: document.getElementById("emptyState"),
  filtersList: document.getElementById("filtersList"),
  skeletonList: document.getElementById("skeletonList"),
  retryButton: document.getElementById("retryButton"),
  emptyCreateButton: document.getElementById("emptyCreateButton"),
  refreshButton: document.getElementById("refreshButton"),
  fallbackAction: document.getElementById("fallbackAction"),
  filterForm: document.getElementById("filterForm"),
  categoryChips: document.getElementById("categoryChips"),
  dealTypeChips: document.getElementById("dealTypeChips"),
  cityInput: document.getElementById("cityInput"),
  cityOptions: document.getElementById("cityOptions"),
  roomChips: document.getElementById("roomChips"),
  priceFromInput: document.getElementById("priceFromInput"),
  priceToInput: document.getElementById("priceToInput"),
  formSummary: document.getElementById("formSummary"),
  formError: document.getElementById("formError"),
};

const ui = {
  mainButtonReady: false,
  mainButtonHandler: null,
  backButtonHandler: null,
};

function createEmptyForm() {
  return {
    category: "",
    deal_type: "",
    city: "",
    rooms: [],
    price_from: "",
    price_to: "",
  };
}

function cloneForm(form) {
  return {
    category: form.category,
    deal_type: form.deal_type,
    city: form.city,
    rooms: [...form.rooms],
    price_from: form.price_from,
    price_to: form.price_to,
  };
}

function formatNumber(value) {
  if (value === null || value === undefined || value === "") {
    return "";
  }
  const digits = String(value).replace(/\D+/g, "");
  if (!digits) {
    return "";
  }
  return digits.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
}

function parseNumber(value) {
  const digits = String(value ?? "").replace(/\s+/g, "").replace(/[^\d]/g, "");
  return digits ? Number.parseInt(digits, 10) : null;
}

function normalizeText(value) {
  return String(value ?? "").trim().toLowerCase();
}

function translatePrice(value) {
  const parsed = parseNumber(value);
  if (parsed === null) {
    return "Любой бюджет";
  }
  return `${formatNumber(parsed)} USD`;
}

function getMeta() {
  return state.meta ?? { categories: [], cities: [], rooms: [] };
}

function getCategoryOptions() {
  return getMeta().categories ?? [];
}

function getActiveCategory() {
  return state.form.category || getCategoryOptions()[0]?.key || "";
}

function getDealTypeOptions(categoryKey) {
  const category = getCategoryOptions().find((item) => item.key === categoryKey);
  return category?.deal_types ?? [];
}

function getCityOptions() {
  return getMeta().cities ?? [];
}

function getRoomOptions() {
  return getMeta().rooms ?? [];
}

function getCityLabel(cityKey) {
  return getCityOptions().find((item) => item.key === cityKey)?.label || cityKey;
}

function getCategoryLabel(categoryKey) {
  return getCategoryOptions().find((item) => item.key === categoryKey)?.label || categoryKey;
}

function getDealTypeLabel(categoryKey, dealTypeKey) {
  const option = getDealTypeOptions(categoryKey).find((item) => item.key === dealTypeKey);
  return option?.label || dealTypeKey;
}

function getRoomLabel(roomKey) {
  return getRoomOptions().find((item) => item.key === roomKey)?.label || roomKey;
}

function getRoomSelectionLabel() {
  if (!state.form.rooms.length) {
    return "Любые комнаты";
  }
  const labels = state.form.rooms.map(getRoomLabel);
  if (labels.length === 1) {
    return labels[0];
  }
  if (labels.length === 2) {
    return `${labels[0]} или ${labels[1]}`;
  }
  return `${labels.slice(0, -1).join(", ")} или ${labels[labels.length - 1]}`;
}

function buildSummary(form) {
  const categoryLabel = getCategoryLabel(form.category);
  const dealTypeLabel = getDealTypeLabel(form.category, form.deal_type);
  const cityLabel = form.city || "Любой город";
  const roomsLabel = form.rooms.length ? getRoomSelectionLabelFrom(form.rooms) : "любые комнаты";
  const priceFrom = parseNumber(form.price_from);
  const priceTo = parseNumber(form.price_to);
  let priceLabel = "Любой бюджет";
  if (priceFrom !== null && priceTo !== null) {
    priceLabel = `${formatNumber(priceFrom)} - ${formatNumber(priceTo)} USD`;
  } else if (priceFrom !== null) {
    priceLabel = `от ${formatNumber(priceFrom)} USD`;
  } else if (priceTo !== null) {
    priceLabel = `до ${formatNumber(priceTo)} USD`;
  }
  return [categoryLabel, dealTypeLabel, cityLabel, roomsLabel, priceLabel].filter(Boolean).join(", ");
}

function getRoomSelectionLabelFrom(roomKeys) {
  const labels = roomKeys.map(getRoomLabel);
  if (!labels.length) {
    return "Любые комнаты";
  }
  if (labels.length === 1) {
    return labels[0];
  }
  if (labels.length === 2) {
    return `${labels[0]} или ${labels[1]}`;
  }
  return `${labels.slice(0, -1).join(", ")} или ${labels[labels.length - 1]}`;
}

function setTheme() {
  if (!tg) {
    return;
  }

  const theme = tg.themeParams ?? {};
  const root = document.documentElement.style;
  root.setProperty("--app-bg", theme.bg_color || "Canvas");
  root.setProperty("--app-fg", theme.text_color || "CanvasText");
  root.setProperty("--app-hint", theme.hint_color || "GrayText");
  root.setProperty("--app-accent", theme.link_color || theme.button_color || "LinkText");
  root.setProperty("--app-surface", theme.secondary_bg_color || "ButtonFace");
  root.setProperty("--app-button-bg", theme.button_color || "ButtonFace");
  root.setProperty("--app-button-fg", theme.button_text_color || "ButtonText");
  root.setProperty("--viewport-height", `${tg.viewportStableHeight || window.innerHeight}px`);
  root.setProperty(
    "--safe-bottom",
    `${tg.contentSafeAreaInset?.bottom ?? 0}px`,
  );
  tg.setHeaderColor?.(theme.bg_color || theme.secondary_bg_color || "#ffffff");
  tg.setBackgroundColor?.(theme.bg_color || "#ffffff");
}

function syncViewport() {
  const root = document.documentElement.style;
  root.setProperty("--viewport-height", `${window.visualViewport?.height || window.innerHeight}px`);
  if (tg) {
    root.setProperty(
      "--safe-bottom",
      `${tg.contentSafeAreaInset?.bottom ?? 0}px`,
    );
  }
}

function setScreen(screen) {
  state.screen = screen;
  refs.app.dataset.screen = screen;
  refs.homeScreen.hidden = screen !== "home";
  refs.formScreen.hidden = screen !== "form";
  refs.pageSubtitle.textContent = screen === "form"
    ? (state.formMode === "edit" ? "Редактирование фильтра" : "Создание нового фильтра")
    : "Управление фильтрами поиска";
  syncControls();
  if (screen === "form" && state.meta) {
    renderMeta();
  }
  renderForm();
  renderHome();
}

function setDirty(value) {
  state.dirty = value;
  tg?.enableClosingConfirmation?.(value);
  syncControls();
}

function showBanner(message, kind = "info") {
  refs.statusBanner.hidden = !message;
  refs.statusBanner.textContent = message || "";
  refs.statusBanner.dataset.kind = kind;
}

function hideBanner() {
  showBanner("");
}

function showToast(message) {
  showBanner(message, "info");
  window.clearTimeout(showToast._timer);
  showToast._timer = window.setTimeout(() => hideBanner(), 2200);
}

function haptic(type, impact = "light") {
  if (!tg?.HapticFeedback) {
    return;
  }
  if (type === "impact") {
    tg.HapticFeedback.impactOccurred?.(impact);
    return;
  }
  tg.HapticFeedback.notificationOccurred?.(type);
}

function createMainButtonAction() {
  if (state.screen === "form") {
    return submitForm;
  }
  return openCreateForm;
}

function setMainButtonText(text) {
  if (!tg?.MainButton) {
    return;
  }
  if (typeof tg.MainButton.setText === "function") {
    tg.MainButton.setText(text);
    return;
  }
  tg.MainButton.setParams?.({ text });
}

function syncControls() {
  const shouldUseTelegram = Boolean(tg);
  refs.fallbackAction.hidden = shouldUseTelegram;

  if (!shouldUseTelegram) {
    refs.fallbackAction.textContent = state.screen === "form"
      ? (state.formMode === "edit" ? "Сохранить изменения" : "Сохранить фильтр")
      : "Создать фильтр";
    refs.fallbackAction.disabled = state.screen === "form" && (state.submitting || !isFormValid(false));
  }

  if (!tg?.MainButton) {
    return;
  }

  if (state.loading) {
    tg.MainButton.hide?.();
    tg.BackButton.hide?.();
    return;
  }

  if (state.screen === "form") {
    tg.BackButton.show?.();
    setMainButtonText(state.formMode === "edit" ? "Сохранить изменения" : "Сохранить фильтр");
    if (state.submitting) {
      tg.MainButton.showProgress?.();
      tg.MainButton.enable?.();
    } else {
      tg.MainButton.hideProgress?.();
      if (isFormValid(false)) {
        tg.MainButton.enable?.();
      } else {
        tg.MainButton.disable?.();
      }
    }
    tg.MainButton.show?.();
    return;
  }

  tg.BackButton.hide?.();
  tg.MainButton.hideProgress?.();
  setMainButtonText("Создать фильтр");
  tg.MainButton.enable?.();
  tg.MainButton.show?.();
}

function getSelectedCategory() {
  return state.form.category || getCategoryOptions()[0]?.key || "";
}

function setFormField(name, value) {
  state.form = {
    ...state.form,
    [name]: value,
  };
  setDirty(true);
  state.formErrors = {};
  state.formError = "";
  renderForm();
  syncControls();
}

function applyFormPayload(form, mode, editingId = null) {
  // Reset form state completely before applying new values
  state.formMode = mode;
  state.editingId = editingId;
  state.form = createEmptyForm();
  
  // Apply new values
  state.form.category = form.category || getCategoryOptions()[0]?.key || "";
  state.form.deal_type = form.deal_type || "";
  state.form.city = form.city || "";
  state.form.rooms = Array.isArray(form.rooms) ? [...form.rooms] : [];
  state.form.price_from = form.price_from || "";
  state.form.price_to = form.price_to || "";
  
  // Auto-select first deal type if not provided
  if (!state.form.deal_type) {
    const categoryOptions = getDealTypeOptions(state.form.category);
    state.form.deal_type = categoryOptions[0]?.key || "";
  }
  setDirty(false);
  state.formErrors = {};
  state.formError = "";
  setScreen("form");
}

function openCreateForm() {
  if (!state.meta) {
    showBanner("Загрузка данных... Попробуйте через мгновение.", "info");
    return;
  }
  const category = getCategoryOptions()[0]?.key || "";
  const dealType = getDealTypeOptions(category)[0]?.key || "";
  applyFormPayload(
    {
      category,
      deal_type: dealType,
      city: "",
      rooms: [],
      price_from: "",
      price_to: "",
    },
    "create",
    null,
  );
}

function openEditForm(item) {
  // Use direct fields from item, not query_params (which is for Kufar API)
  const category = item.category || getCategoryOptions()[0]?.key || "";
  const dealTypes = getDealTypeOptions(category);
  const normalizedRooms = Array.isArray(item.rooms)
    ? item.rooms
    : item.rooms
      ? [item.rooms]
      : [];

  const priceFrom = item.price_from != null ? String(item.price_from) : "";
  const priceTo = item.price_to != null ? String(item.price_to) : "";

  // Convert city key to label for form state (validation expects label)
  const cityLabel = item.city ? getCityLabel(item.city) : "";

  applyFormPayload(
    {
      category,
      deal_type: dealTypes.some((option) => option.key === item.deal_type)
        ? item.deal_type
        : dealTypes[0]?.key || "",
      city: cityLabel,
      rooms: normalizedRooms,
      price_from: priceFrom,
      price_to: priceTo,
    },
    "edit",
    item.id,
  );
  state.formErrors = {};
  renderForm();
  syncControls();
}

function validateForm() {
  const errors = {};
  const category = state.form.category;
  const dealTypes = getDealTypeOptions(category);

  if (!getCategoryOptions().some((item) => item.key === category)) {
    errors.category = "Выберите категорию";
  }

  if (!dealTypes.some((item) => item.key === state.form.deal_type)) {
    errors.deal_type = "Выберите тип сделки";
  }

  const cityMatch = getCityOptions().find((item) => normalizeText(item.label) === normalizeText(state.form.city));
  if (!cityMatch) {
    errors.city = "Выберите город из списка";
  }

  if (state.form.rooms.some((room) => room !== "any" && !getRoomOptions().some((item) => item.key === room))) {
    errors.rooms = "Выберите допустимые варианты комнат";
  }

  const priceFrom = parseNumber(state.form.price_from);
  const priceTo = parseNumber(state.form.price_to);
  if (priceFrom !== null && priceTo !== null && priceFrom > priceTo) {
    errors.price_to = "Максимальная цена не может быть меньше минимальной";
  }

  return errors;
}

function isFormValid(updateErrors = true) {
  const errors = validateForm();
  if (updateErrors) {
    state.formErrors = errors;
    renderForm();
  }
  return Object.keys(errors).length === 0;
}

function getSelectedCityKey() {
  const city = getCityOptions().find((item) => normalizeText(item.label) === normalizeText(state.form.city));
  return city?.key || "";
}

function buildPayload() {
  const cityKey = getSelectedCityKey();
  return {
    category: state.form.category,
    deal_type: state.form.deal_type,
    city: cityKey,
    rooms: state.form.rooms.includes("any") ? [] : [...state.form.rooms],
    price_from: parseNumber(state.form.price_from),
    price_to: parseNumber(state.form.price_to),
  };
}

async function apiFetch(path, options = {}) {
  // Check if running in Telegram WebApp context
  if (!tg) {
    const error = new Error("Миниапп должен открываться из Telegram. Откройте ссылку на миниапп из Telegram бота.");
    error.status = 401;
    throw error;
  }

  // Check if initData is available
  if (!tg.initData) {
    const error = new Error("Ошибка аутентификации Telegram. Переоткройте миниапп.");
    error.status = 401;
    throw error;
  }

  const headers = new Headers(options.headers || {});
  headers.set("Content-Type", "application/json");
  headers.set("Authorization", `tma ${tg.initData}`);

  const response = await fetch(path, {
    ...options,
    headers,
  });
  const text = await response.text();
  let body = {};
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = { error: text };
    }
  }
  if (!response.ok) {
    const error = new Error(body.error || `HTTP ${response.status}`);
    error.status = response.status;
    error.body = body;
    throw error;
  }
  return body;
}

async function loadData() {
  state.loading = true;
  state.error = null;
  renderHome();
  syncControls();

  try {
    const [metaResponse, filtersResponse] = await Promise.all([
      apiFetch("/api/meta"),
      apiFetch("/api/filters"),
    ]);
    state.meta = metaResponse.meta;
    state.items = filtersResponse.items || [];
    state.loading = false;
    renderMeta();
    renderHome();
    syncControls();
  } catch (error) {
    state.loading = false;
    state.error = error;
    renderHome();
    syncControls();
    
    // Log error for debugging
    console.error("Failed to load data:", {
      message: error.message,
      status: error.status,
      tgAvailable: !!tg,
      initDataAvailable: tg?.initData ? "yes" : "no",
    });
    
    let userMessage = error.message || "Не удалось загрузить данные";
    if (error.status === 401) {
      userMessage = "Ошибка аутентификации. Переоткройте миниапп из Telegram.";
    }
    showBanner(error.body?.error || userMessage, "error");
  }
}

function renderMeta() {
  const meta = getMeta();
  refs.categoryChips.innerHTML = "";
  refs.dealTypeChips.innerHTML = "";
  refs.roomChips.innerHTML = "";
  refs.cityOptions.innerHTML = "";

  meta.cities.forEach((city) => {
    const option = document.createElement("option");
    option.value = city.label;
    refs.cityOptions.appendChild(option);
  });

  meta.categories.forEach((category) => {
    const chip = createChip(category.label, state.form.category === category.key, () => {
      state.form.category = category.key;
      const options = getDealTypeOptions(category.key);
      if (!options.some((item) => item.key === state.form.deal_type)) {
        state.form.deal_type = options[0]?.key || "";
      }
      setDirty(true);
      state.formErrors = {};
      state.formError = "";
      renderMeta();
      renderForm();
      syncControls();
      haptic("impact", "light");
    });
    refs.categoryChips.appendChild(chip);
  });

  getDealTypeOptions(getSelectedCategory()).forEach((dealType) => {
    const chip = createChip(dealType.label, state.form.deal_type === dealType.key, () => {
      state.form.deal_type = dealType.key;
      setDirty(true);
      state.formErrors = {};
      state.formError = "";
      renderMeta();
      renderForm();
      syncControls();
      haptic("impact", "light");
    });
    refs.dealTypeChips.appendChild(chip);
  });

  getRoomOptions()
    .filter((option) => option.key !== "any")
    .forEach((room) => {
      const chip = createChip(room.label, state.form.rooms.includes(room.key), () => {
        toggleRoom(room.key);
        haptic("impact", "light");
      }, false);
      refs.roomChips.appendChild(chip);
    });

  const anyChip = createChip("Любые", state.form.rooms.length === 0, () => {
    state.form.rooms = [];
      setDirty(true);
      state.formErrors = {};
      state.formError = "";
      renderMeta();
    renderForm();
    syncControls();
    haptic("impact", "light");
  }, true);
  refs.roomChips.prepend(anyChip);
}

function toggleRoom(roomKey) {
  const rooms = new Set(state.form.rooms.filter((room) => room !== "any"));
  if (rooms.has(roomKey)) {
    rooms.delete(roomKey);
  } else {
    rooms.add(roomKey);
  }
  state.form.rooms = Array.from(rooms);
      setDirty(true);
      state.formErrors = {};
      state.formError = "";
      renderMeta();
  renderForm();
  syncControls();
}

function createChip(label, active, onClick, muted = false) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = `chip${active ? " is-active" : ""}${muted ? " is-muted" : ""}`;
  button.textContent = label;
  button.addEventListener("click", onClick);
  return button;
}

function renderHome() {
  refs.loadingState.hidden = !state.loading;
  refs.errorState.hidden = !state.error;
  refs.emptyState.hidden = state.loading || state.error || state.items.length > 0;
  refs.filtersList.hidden = state.loading || state.error || state.items.length === 0;
  refs.errorText.textContent = state.error?.body?.error || state.error?.message || "Проверьте сеть или попробуйте еще раз.";

  if (state.loading) {
    refs.skeletonList.innerHTML = [
      "wide",
      "medium",
      "small",
    ].map((width) => `<div class=\"skeleton-card\"><div class=\"skeleton-line wide\"></div><div class=\"skeleton-line ${width}\"></div><div class=\"skeleton-line small\"></div></div>`).join("");
    return;
  }

  if (!state.error && state.items.length > 0) {
    refs.filtersList.innerHTML = state.items.map(renderFilterCard).join("");
    attachCardHandlers();
  }
}

function renderFilterCard(item) {
  const statusLabel = item.is_active ? "Активен" : "Приостановлен";
  const statusClass = item.is_active ? "is-active" : "is-paused";
  const created = item.created_at ? new Date(item.created_at).toLocaleString("ru-RU", { dateStyle: "medium", timeStyle: "short" }) : "Дата неизвестна";
  const details = [
    item.category_label,
    item.deal_type_label,
    item.city_label,
    item.rooms_label,
  ].filter(Boolean).join(" · ");

  return `
    <article class="filter-card" data-filter-id="${item.id}">
      <div class="filter-card-header">
        <div>
          <h3 class="filter-title">${escapeHtml(item.title)}</h3>
          <p class="filter-summary">${escapeHtml(item.summary || details)}</p>
        </div>
        <span class="status-pill ${statusClass}">${statusLabel}</span>
      </div>
      <div class="filter-meta">
        <span>${escapeHtml(created)}</span>
      </div>
      <div class="filter-actions">
        <button class="card-action" data-action="edit" type="button">Редактировать</button>
        <button class="card-action" data-action="toggle" type="button">${item.is_active ? "Пауза" : "Включить"}</button>
        <button class="card-action danger" data-action="delete" type="button">Удалить</button>
      </div>
    </article>
  `;
}

function attachCardHandlers() {
  refs.filtersList.querySelectorAll(".filter-card").forEach((card) => {
    const id = Number.parseInt(card.dataset.filterId, 10);
    const item = state.items.find((entry) => entry.id === id);
    if (!item) {
      return;
    }
    card.querySelector('[data-action="edit"]')?.addEventListener("click", (event) => {
      event.stopPropagation();
      openEditForm(item);
    });
    card.querySelector('[data-action="toggle"]')?.addEventListener("click", async (event) => {
      event.stopPropagation();
      await toggleFilter(item.id);
    });
    card.querySelector('[data-action="delete"]')?.addEventListener("click", async (event) => {
      event.stopPropagation();
      await deleteFilter(item.id);
    });
  });
}

function renderForm() {
  if (!state.meta) {
    return;
  }

  refs.cityInput.value = getCityLabel(state.form.city);
  refs.priceFromInput.value = state.form.price_from ? formatNumber(state.form.price_from) : "";
  refs.priceToInput.value = state.form.price_to ? formatNumber(state.form.price_to) : "";
  refs.formSummary.textContent = buildSummary(state.form);
  refs.formError.hidden = !state.formError;
  refs.formError.textContent = state.formError || "";

  const fieldMap = {
    category: refs.filterForm.querySelector('[data-error-for="category"]'),
    deal_type: refs.filterForm.querySelector('[data-error-for="deal_type"]'),
    city: refs.filterForm.querySelector('[data-error-for="city"]'),
    rooms: refs.filterForm.querySelector('[data-error-for="rooms"]'),
    price_from: refs.filterForm.querySelector('[data-error-for="price_from"]'),
    price_to: refs.filterForm.querySelector('[data-error-for="price_to"]'),
  };

  Object.entries(fieldMap).forEach(([name, node]) => {
    if (!node) {
      return;
    }
    const error = state.formErrors[name] || "";
    node.textContent = error;
  });

  refs.priceFromInput.classList.toggle("is-invalid", Boolean(state.formErrors.price_from));
  refs.priceToInput.classList.toggle("is-invalid", Boolean(state.formErrors.price_to));
  refs.cityInput.classList.toggle("is-invalid", Boolean(state.formErrors.city));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

async function submitForm() {
  if (state.submitting) {
    return;
  }

  const valid = isFormValid(true);
  if (!valid) {
    haptic("error");
    showToast("Исправьте ошибки в форме");
    syncControls();
    return;
  }

  state.submitting = true;
  syncControls();
  showBanner(state.formMode === "edit" ? "Сохраняю изменения..." : "Сохраняю фильтр...");

  try {
    const body = JSON.stringify({ form: buildPayload() });
    const method = state.formMode === "edit" ? "PATCH" : "POST";
    const path = state.formMode === "edit" ? `/api/filters/${state.editingId}` : "/api/filters";
    const response = await apiFetch(path, { method, body });
    state.submitting = false;
    setDirty(false);
    hideBanner();
    haptic("success");
    showToast(state.formMode === "edit" ? "Фильтр сохранён" : "Фильтр создан");
    await loadData();
    if (response?.item) {
      state.items = state.items.map((item) => (item.id === response.item.id ? response.item : item));
    }
    setScreen("home");
  } catch (error) {
    state.submitting = false;
    const fields = error.body?.fields || {};
    state.formErrors = fields;
    if (!Object.keys(fields).length) {
      state.formError.hidden = false;
      state.formError.textContent = error.body?.error || error.message || "Не удалось сохранить фильтр";
    } else {
      state.formError.hidden = true;
    }
    renderForm();
    syncControls();
    haptic("error");
    showBanner(error.body?.error || "Не удалось сохранить фильтр", "error");
  }
}

async function toggleFilter(id) {
  try {
    await apiFetch(`/api/filters/${id}/toggle`, { method: "PATCH", body: "{}" });
    haptic("success");
    showToast("Статус фильтра изменён");
    await loadData();
  } catch (error) {
    haptic("error");
    showBanner(error.body?.error || "Не удалось изменить статус фильтра", "error");
  }
}

function confirmDelete() {
  if (tg?.showConfirm) {
    return new Promise((resolve) => {
      tg.showConfirm("Удалить фильтр?", (confirmed) => resolve(Boolean(confirmed)));
    });
  }
  return Promise.resolve(window.confirm("Удалить фильтр?"));
}

async function deleteFilter(id) {
  const confirmed = await confirmDelete();
  if (!confirmed) {
    return;
  }

  try {
    await apiFetch(`/api/filters/${id}`, { method: "DELETE", body: "{}" });
    haptic("impact", "medium");
    showToast("Фильтр удалён");
    await loadData();
  } catch (error) {
    haptic("error");
    showBanner(error.body?.error || "Не удалось удалить фильтр", "error");
  }
}

function handleBack() {
  if (state.screen !== "form") {
    return;
  }
  if (state.dirty) {
    const confirmed = tg?.showConfirm
      ? null
      : window.confirm("Есть несохранённые изменения. Закрыть форму?");
    if (confirmed === false) {
      return;
    }
    if (confirmed === null && tg?.showConfirm) {
      tg.showConfirm("Есть несохранённые изменения. Закрыть форму?", (result) => {
        if (result) {
          setScreen("home");
          setDirty(false);
        }
      });
      return;
    }
  }
  setScreen("home");
  setDirty(false);
}

function onFormInput(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  if (target === refs.cityInput) {
    state.form.city = target.value;
  } else if (target === refs.priceFromInput) {
    state.form.price_from = target.value.replace(/[^\d]/g, "");
  } else if (target === refs.priceToInput) {
    state.form.price_to = target.value.replace(/[^\d]/g, "");
  }
  setDirty(true);
  state.formErrors = {};
  renderForm();
  syncControls();
}

function onFormBlur(event) {
  const target = event.target;
  if (!(target instanceof HTMLInputElement)) {
    return;
  }
  if (target === refs.priceFromInput) {
    state.form.price_from = target.value.replace(/[^\d]/g, "");
  } else if (target === refs.priceToInput) {
    state.form.price_to = target.value.replace(/[^\d]/g, "");
  } else if (target === refs.cityInput) {
    const matched = getCityOptions().find((item) => normalizeText(item.label) === normalizeText(target.value));
    if (matched) {
      state.form.city = matched.label;
    }
  }
  renderForm();
}

function initTelegram() {
  if (!tg) {
    return;
  }
  tg.ready?.();
  tg.expand?.();
  tg.enableClosingConfirmation?.(false);
  tg.onEvent?.("themeChanged", setTheme);
  tg.onEvent?.("viewportChanged", syncViewport);
}

function initFallbackControls() {
  refs.fallbackAction.addEventListener("click", () => {
    if (state.screen === "form") {
      submitForm();
      return;
    }
    openCreateForm();
  });
}

function initFormEvents() {
  refs.filterForm.addEventListener("input", onFormInput);
  refs.filterForm.addEventListener("blur", onFormBlur, true);
  refs.cityInput.addEventListener("change", () => {
    setDirty(true);
    renderForm();
    syncControls();
  });
}

function initButtons() {
  refs.retryButton.addEventListener("click", loadData);
  refs.emptyCreateButton.addEventListener("click", openCreateForm);
  refs.refreshButton.addEventListener("click", loadData);

  if (tg?.MainButton?.onClick) {
    if (!ui.mainButtonReady) {
      ui.mainButtonHandler = createMainButtonAction;
      tg.MainButton.onClick(() => {
        const action = ui.mainButtonHandler?.();
        if (typeof action === "function") {
          action();
        }
      });
      ui.mainButtonReady = true;
    }
  }

  if (tg?.BackButton?.onClick && !ui.backButtonHandler) {
    ui.backButtonHandler = handleBack;
    tg.BackButton.onClick(handleBack);
  }
}

function init() {
  setTheme();
  syncViewport();
  initTelegram();
  initFallbackControls();
  initFormEvents();
  initButtons();
  window.addEventListener("resize", syncViewport);
  window.addEventListener("orientationchange", syncViewport);
  state.form = createEmptyForm();
  setScreen("home");
  
  // Wait for Telegram to be ready before loading data
  if (tg && tg.initData) {
    loadData();
  } else if (tg) {
    // Telegram is available but initData not ready yet, wait a bit
    setTimeout(() => {
      if (tg.initData) {
        loadData();
      } else {
        showBanner("Ошибка аутентификации. Переоткройте миниапп из Telegram.", "error");
        state.error = { message: "initData не установлен" };
        renderHome();
        syncControls();
      }
    }, 500);
  } else {
    // Not in Telegram environment
    showBanner("Миниапп должен открываться из Telegram.", "error");
    state.error = { message: "Не в контексте Telegram" };
    renderHome();
    syncControls();
  }
}

init();
