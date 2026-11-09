/* =========================================================
   Painel de Mesas — dados mockados (apenas visual)
    sem backend, sem atualização em tempo real.
    Cada mesa tem "minutesAgo": há quantos minutos o status começou.
    Cronômetros rodam no navegador, sem backend. Depois muda para o backend real.
   ========================================================= */

const STATUS = {
  available: { label: "Disponível", timeLabel: "Livre há" },
  occupied: { label: "Ocupada", timeLabel: "Ocupada há" },
};

const TABLES = [
  { number: 1, status: "occupied", minutesAgo: 52, seats: 4, note: "Ocupada" },
  { number: 2, status: "occupied", minutesAgo: 95, seats: 2, note: "Ocupada" },
  { number: 3, status: "occupied", minutesAgo: 168, seats: 4, note: "Ocupada" },
  { number: 4, status: "available", minutesAgo: 0, seats: 4, note: "Pronta para uso" },
  { number: 5, status: "available", minutesAgo: 0, seats: 4, note: "Pronta para uso" },
  { number: 6, status: "occupied", minutesAgo: 12, seats: 2, note: "Ocupada" },
  { number: 7, status: "available", minutesAgo: 0, seats: 2, note: "Pronta para uso" },
  { number: 8, status: "occupied", minutesAgo: 34, seats: 2, note: "Ocupada" },
  { number: 9, status: "occupied", minutesAgo: 76, seats: 4, note: "Ocupada" },
  { number: 10, status: "available", minutesAgo: 0, seats: 4, note: "Pronta para uso" },
  { number: 11, status: "occupied", minutesAgo: 5, seats: 2, note: "Ocupada" },
  { number: 12, status: "available", minutesAgo: 0, seats: 2, note: "Pronta para uso" },
  { number: 13, status: "available", minutesAgo: 0, seats: 2, note: "Pronta para uso" },
];

const ICON_TABLE = `
  <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor"
       stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <ellipse cx="12" cy="9" rx="8" ry="2.5"/>
    <path d="M12 11.5V20M8 20h8"/>
    <path d="M2.5 11v4M21.5 11v4M2.5 15h2M19.5 15h2"/>
  </svg>`;

const pad = (n) => String(n).padStart(2, "0");

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return `${pad(h)}:${pad(m)}:${pad(s)}`;
}

function renderKpis(tables) {
  const count = (s) => tables.filter((t) => t.status === s).length;
  const items = [
    { cls: "total", label: "Total de mesas", value: tables.length },
    { cls: "available", label: "Disponíveis", value: count("available") },
    { cls: "occupied", label: "Ocupadas", value: count("occupied") },
  ];

  document.getElementById("kpis").innerHTML = items
    .map(
      (i) => `
      <article class="kpi kpi--${i.cls}">
        <p class="kpi__label">${i.label}</p>
        <p class="kpi__value">${pad(i.value)}</p>
      </article>`
    )
    .join("");
}

function renderTables(tables) {
  document.getElementById("tables").innerHTML = tables
    .map((t) => {
      const s = STATUS[t.status];
      return `
      <article class="card card--${t.status}" role="listitem">
        <div class="card__top">
          <div class="card__id">
            <div class="card__icon">${ICON_TABLE}</div>
            <div>
              <h3 class="card__name">Mesa ${pad(t.number)}</h3>
              <p class="card__seats">${t.seats} lugares</p>
            </div>
          </div>
          <span class="badge">${s.label}</span>
        </div>

        <div class="card__bottom">
          <div>
            <span class="card__time-label">${s.timeLabel}</span>
            <span class="card__time" data-start="${Date.now() - t.minutesAgo * 60 * 1000}">${formatElapsed(t.minutesAgo * 60 * 1000)}</span>
          </div>
          <p class="card__note">${t.note}</p>
        </div>
      </article>`;
    })
    .join("");
}

function tick() {
  const now = Date.now();
  document.querySelectorAll(".card__time").forEach((el) => {
    el.textContent = formatElapsed(now - Number(el.dataset.start));
  });
}

renderKpis(TABLES);
renderTables(TABLES);
setInterval(tick, 1000);

/* Relógio e data reais (usa o horário do computador) */
function updateClock() {
  const now = new Date();

  document.getElementById("clock-time").textContent =
    now.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });

  const date = now.toLocaleDateString("pt-BR", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  });
  document.getElementById("clock-date").textContent =
    date.charAt(0).toUpperCase() + date.slice(1);
}

updateClock();
setInterval(updateClock, 1000);