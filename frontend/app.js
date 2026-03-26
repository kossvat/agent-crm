/**
 * Agent CRM — Telegram Mini App Frontend
 * SPA with hash-based routing, Kanban board with SortableJS drag & drop.
 */

// --- Telegram WebApp Init ---
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready();
    tg.expand();
    try { tg.setHeaderColor('secondary_bg_color'); } catch(e) {}
}

// --- Config ---
const API_BASE = '/api';
const REFRESH_INTERVAL = 30000;

// --- State ---
let currentRoute = 'dashboard';
let agents = [];
let allTasks = [];
let kanbanFilter = 'all'; // agent filter
let periodFilter = localStorage.getItem('crm_period') || 'all';
let refreshTimer = null;

// --- API Client ---
async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;

    const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `API Error ${resp.status}`);
    }
    if (resp.status === 204) return null;
    return resp.json();
}

// --- Router ---
function navigate(route) {
    currentRoute = route;
    window.location.hash = route;
    updateNav();
    render();
}

function updateNav() {
    document.querySelectorAll('.nav-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.route === currentRoute);
    });
    const titles = { dashboard: 'Dashboard', kanban: 'Task Board', agents: 'Agents', alerts: 'Alerts' };
    document.getElementById('page-title').textContent = titles[currentRoute] || 'Agent CRM';
}

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.route));
});
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.slice(1) || 'dashboard';
    if (hash !== currentRoute) { currentRoute = hash; updateNav(); render(); }
});

// --- Render ---
async function render() {
    const content = document.getElementById('content');
    content.innerHTML = '<div class="loading">Loading...</div>';
    document.querySelector('.btn-fab')?.remove();

    try {
        switch (currentRoute) {
            case 'dashboard': await renderDashboard(content); break;
            case 'kanban': await renderKanban(content); break;
            case 'agents': await renderAgents(content); break;
            case 'alerts': await renderAlerts(content); break;
            default: content.innerHTML = '<div class="empty-state"><p>Not found</p></div>';
        }
    } catch (err) {
        content.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${err.message}</p></div>`;
    }
}

// --- Period Filter HTML ---
function periodFilterHTML() {
    const periods = [
        { id: 'today', label: 'Today' },
        { id: 'week', label: 'Week' },
        { id: 'month', label: 'Month' },
        { id: 'all', label: 'All' },
    ];
    return `<div class="period-filter">
        ${periods.map(p => `<button class="period-chip ${periodFilter === p.id ? 'active' : ''}" data-period="${p.id}">${p.label}</button>`).join('')}
    </div>`;
}

function bindPeriodFilter(el) {
    el.querySelectorAll('.period-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            periodFilter = chip.dataset.period;
            localStorage.setItem('crm_period', periodFilter);
            render();
        });
    });
}

// --- Dashboard ---
async function renderDashboard(el) {
    const params = periodFilter !== 'all' ? `?period=${periodFilter}` : '';
    const data = await api(`/dashboard${params}`);
    agents = data.agents;

    const costLabel = periodFilter === 'today' ? 'Today' : periodFilter === 'week' ? 'This Week' : periodFilter === 'month' ? 'This Month' : 'Total';
    const taskLabel = periodFilter === 'all' ? 'Active Tasks' : `Tasks (${periodFilter})`;

    el.innerHTML = `
        ${periodFilterHTML()}
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-value">${data.agent_count}</div>
                <div class="summary-label">Agents</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">${data.active_tasks}</div>
                <div class="summary-label">${taskLabel}</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">$${data.today_cost.toFixed(2)}</div>
                <div class="summary-label">${costLabel}</div>
            </div>
            <div class="summary-card">
                <div class="summary-value">${data.unread_alerts}</div>
                <div class="summary-label">Alerts</div>
            </div>
        </div>
        <div class="section-header">Agents</div>
        ${data.agents.map(a => `<div class="card agent-card">
            <div class="agent-emoji">${a.emoji}</div>
            <div class="agent-info">
                <div class="agent-name">${a.name}</div>
                <div class="agent-meta">${a.model ? a.model.split('/').pop() : '—'}</div>
            </div>
            <span class="status-badge status-${a.status}">
                <span class="status-dot"></span> ${a.status}
            </span>
        </div>`).join('') || '<div class="empty-state"><p>No agents</p></div>'}
        ${data.recent_alerts.length ? `
            <div class="section-header">Recent Alerts</div>
            ${data.recent_alerts.slice(0, 5).map(a => alertCardHTML(a)).join('')}
        ` : ''}
    `;
    bindPeriodFilter(el);
}

// ============================================
//  KANBAN BOARD
// ============================================

const COLUMNS = [
    { id: 'todo', label: 'Todo', icon: '📝' },
    { id: 'in_progress', label: 'In Progress', icon: '🔄' },
    { id: 'done', label: 'Done', icon: '✅' },
];

async function renderKanban(el) {
    // Load data with period filter
    if (!agents.length) try { agents = await api('/agents'); } catch(e) {}
    const periodParam = periodFilter !== 'all' ? `?period=${periodFilter}` : '';
    allTasks = await api(`/tasks${periodParam}`);

    // Filter by agent (client-side on top of server period filter)
    const filtered = kanbanFilter === 'all'
        ? allTasks
        : allTasks.filter(t => t.agent_id == kanbanFilter);

    // Build HTML
    el.innerHTML = `
        ${periodFilterHTML()}
        <div class="kanban-filter">
            <button class="filter-chip ${kanbanFilter === 'all' ? 'active' : ''}" data-filter="all">All</button>
            ${agents.map(a => `
                <button class="filter-chip ${kanbanFilter == a.id ? 'active' : ''}" data-filter="${a.id}">
                    ${a.emoji} ${a.name}
                </button>
            `).join('')}
        </div>
        <div class="kanban-container" id="kanban-container">
            ${COLUMNS.map(col => {
                const colTasks = filtered.filter(t => t.status === col.id);
                return `
                    <div class="kanban-column">
                        <div class="column-header col-${col.id}">
                            ${col.icon} ${col.label}
                            <span class="col-count">${colTasks.length}</span>
                        </div>
                        <div class="column-body" id="col-${col.id}" data-status="${col.id}">
                            ${colTasks.map(t => kanbanCardHTML(t)).join('')}
                        </div>
                    </div>
                `;
            }).join('')}
        </div>
        <div class="kanban-dots" id="kanban-dots">
            ${COLUMNS.map((_, i) => `<div class="kanban-dot ${i === 0 ? 'active' : ''}"></div>`).join('')}
        </div>
    `;

    // Setup period filter
    bindPeriodFilter(el);

    // Setup agent filter clicks
    el.querySelectorAll('.filter-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            kanbanFilter = chip.dataset.filter;
            renderKanban(el);
        });
    });

    // Setup card clicks
    el.querySelectorAll('.kanban-card').forEach(card => {
        card.addEventListener('click', (e) => {
            // Don't trigger on drag
            if (card.classList.contains('sortable-chosen')) return;
            openTaskModal(parseInt(card.dataset.id));
        });
    });

    // Setup SortableJS on each column
    initKanbanDragDrop();

    // Setup scroll dots
    initScrollDots();

    // FAB
    const fab = document.createElement('button');
    fab.className = 'btn-fab';
    fab.textContent = '+';
    fab.onclick = () => openTaskModal();
    document.body.appendChild(fab);
}

function kanbanCardHTML(t) {
    const agentStr = t.agent ? `${t.agent.emoji} ${t.agent.name}` : '—';
    const dlClass = t.deadline_status === 'overdue' ? 'deadline-overdue-card'
        : t.deadline_status === 'soon' ? 'deadline-soon-card' : '';
    const dlBadge = t.deadline ? deadlineBadgeHTML(t) : '';

    return `
        <div class="kanban-card priority-${t.priority} ${dlClass}" data-id="${t.id}">
            <div class="kanban-title">${escapeHtml(t.title)}</div>
            <div class="kanban-meta">
                <span class="kanban-agent">${agentStr}</span>
                <span class="priority-dot"></span>
                ${dlBadge}
                <span>${timeAgo(t.created)}</span>
            </div>
        </div>
    `;
}

function deadlineBadgeHTML(t) {
    if (!t.deadline) return '';
    const dl = new Date(t.deadline);
    const cls = `deadline-${t.deadline_status || 'ok'}`;
    const icon = t.deadline_status === 'overdue' ? '🔴'
        : t.deadline_status === 'soon' ? '🟡' : '⏰';
    const label = t.deadline_status === 'overdue' ? 'overdue'
        : t.deadline_status === 'soon' ? 'due soon'
        : formatDeadline(dl);
    return `<span class="deadline-badge ${cls}">${icon} ${label}</span>`;
}

function formatDeadline(dt) {
    const now = new Date();
    const diffH = (dt - now) / 3600000;
    if (diffH < 24) return `${Math.round(diffH)}h`;
    return `${Math.round(diffH / 24)}d`;
}

function initKanbanDragDrop() {
    COLUMNS.forEach(col => {
        const el = document.getElementById(`col-${col.id}`);
        if (!el) return;

        new Sortable(el, {
            group: 'kanban',
            animation: 150,
            ghostClass: 'sortable-ghost',
            chosenClass: 'sortable-chosen',
            dragClass: 'sortable-drag',
            delay: 100, // prevent accidental drags
            delayOnTouchOnly: true,
            touchStartThreshold: 5,

            onEnd: async function(evt) {
                const taskId = parseInt(evt.item.dataset.id);
                const newStatus = evt.to.dataset.status;
                const oldStatus = evt.from.dataset.status;

                if (newStatus === oldStatus) return;

                try {
                    await api(`/tasks/${taskId}`, {
                        method: 'PATCH',
                        body: JSON.stringify({ status: newStatus }),
                    });

                    // Update local state
                    const task = allTasks.find(t => t.id === taskId);
                    if (task) task.status = newStatus;

                    // Update column counts
                    updateColumnCounts();

                    // Haptic feedback
                    if (tg) tg.HapticFeedback?.impactOccurred('light');
                } catch (err) {
                    console.error('Failed to update task:', err);
                    // Revert by re-rendering
                    renderKanban(document.getElementById('content'));
                }
            },
        });
    });
}

function updateColumnCounts() {
    COLUMNS.forEach(col => {
        const body = document.getElementById(`col-${col.id}`);
        if (!body) return;
        const count = body.querySelectorAll('.kanban-card').length;
        const header = body.previousElementSibling;
        const countEl = header?.querySelector('.col-count');
        if (countEl) countEl.textContent = count;
    });
}

function initScrollDots() {
    const container = document.getElementById('kanban-container');
    const dots = document.querySelectorAll('.kanban-dot');
    if (!container || !dots.length) return;

    container.addEventListener('scroll', () => {
        const scrollLeft = container.scrollLeft;
        const colWidth = container.scrollWidth / COLUMNS.length;
        const activeIndex = Math.round(scrollLeft / colWidth);
        dots.forEach((dot, i) => dot.classList.toggle('active', i === activeIndex));
    });
}

// --- Agents ---
async function renderAgents(el) {
    agents = await api('/agents');
    el.innerHTML = agents.length
        ? agents.map(a => `<div class="card agent-card">
            <div class="agent-emoji">${a.emoji}</div>
            <div class="agent-info">
                <div class="agent-name">${a.name}</div>
                <div class="agent-meta">
                    ${a.model ? a.model.split('/').pop() : '—'}
                    · $${a.daily_cost.toFixed(2)}/day
                </div>
                <div class="agent-meta">Last active: ${a.last_active ? timeAgo(a.last_active) : 'never'}</div>
            </div>
            <span class="status-badge status-${a.status}">
                <span class="status-dot"></span> ${a.status}
            </span>
        </div>`).join('')
        : '<div class="empty-state"><div class="empty-icon">🤖</div><p>No agents</p></div>';
}

// --- Alerts ---
async function renderAlerts(el) {
    const alerts = await api('/alerts');
    el.innerHTML = alerts.length
        ? alerts.map(a => alertCardHTML(a)).join('')
        : '<div class="empty-state"><div class="empty-icon">🔔</div><p>No alerts</p></div>';
}

function alertCardHTML(a) {
    const icons = { error: '🚨', warning: '⚠️', info: 'ℹ️' };
    return `
        <div class="card alert-card ${a.is_read ? '' : 'alert-unread'}" onclick="markAlertRead(${a.id})">
            <div class="alert-icon">${icons[a.type] || 'ℹ️'}</div>
            <div class="alert-body">
                <div class="alert-message">${escapeHtml(a.message)}</div>
                <div class="alert-time">${timeAgo(a.created)}</div>
            </div>
        </div>
    `;
}

window.markAlertRead = async function(id) {
    try { await api(`/alerts/${id}/read`, { method: 'PATCH' }); render(); } catch(e) {}
};

// --- Task Modal ---
window.openTaskModal = async function(taskId = null) {
    const overlay = document.getElementById('modal-overlay');
    const form = document.getElementById('task-form');
    const title = document.getElementById('modal-title');
    const deleteBtn = document.getElementById('btn-delete-task');

    // Populate agent dropdown
    const agentSelect = document.getElementById('task-agent');
    agentSelect.innerHTML = '<option value="">Unassigned</option>' +
        agents.map(a => `<option value="${a.id}">${a.emoji} ${a.name}</option>`).join('');

    if (taskId) {
        title.textContent = 'Edit Task';
        deleteBtn.style.display = 'block';
        try {
            const task = await api(`/tasks/${taskId}`);
            document.getElementById('task-id').value = task.id;
            document.getElementById('task-title').value = task.title;
            document.getElementById('task-desc').value = task.description;
            document.getElementById('task-status').value = task.status;
            document.getElementById('task-priority').value = task.priority;
            document.getElementById('task-agent').value = task.agent_id || '';
            document.getElementById('task-deadline').value = task.deadline
                ? new Date(task.deadline).toISOString().slice(0, 16) : '';
        } catch(e) { console.error(e); }
    } else {
        title.textContent = 'New Task';
        deleteBtn.style.display = 'none';
        form.reset();
        document.getElementById('task-id').value = '';
        document.getElementById('task-deadline').value = '';
    }

    overlay.classList.remove('hidden');
};

window.closeModal = function() {
    document.getElementById('modal-overlay').classList.add('hidden');
};

document.getElementById('modal-overlay').addEventListener('click', (e) => {
    if (e.target === e.currentTarget) closeModal();
});

document.getElementById('task-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('task-id').value;
    const deadlineVal = document.getElementById('task-deadline').value;
    const data = {
        title: document.getElementById('task-title').value,
        description: document.getElementById('task-desc').value,
        status: document.getElementById('task-status').value,
        priority: document.getElementById('task-priority').value,
        agent_id: document.getElementById('task-agent').value || null,
        deadline: deadlineVal ? new Date(deadlineVal).toISOString() : null,
    };
    if (data.agent_id) data.agent_id = parseInt(data.agent_id);

    try {
        if (id) {
            await api(`/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) });
        } else {
            await api('/tasks', { method: 'POST', body: JSON.stringify(data) });
        }
        closeModal();
        render();
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
    } catch (err) { alert(err.message); }
});

window.deleteCurrentTask = async function() {
    const id = document.getElementById('task-id').value;
    if (!id) return;
    if (!confirm('Delete this task?')) return;
    try {
        await api(`/tasks/${id}`, { method: 'DELETE' });
        closeModal();
        render();
        if (tg) tg.HapticFeedback?.notificationOccurred('warning');
    } catch (err) { alert(err.message); }
};

// --- Utilities ---
function escapeHtml(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}

function timeAgo(dateStr) {
    const diff = (Date.now() - new Date(dateStr).getTime()) / 1000;
    if (diff < 60) return 'just now';
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
}

// --- Init ---
navigate(window.location.hash.slice(1) || 'dashboard');
refreshTimer = setInterval(() => { if (currentRoute === 'dashboard') render(); }, REFRESH_INTERVAL);
