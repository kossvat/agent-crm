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
let categoryFilter = 'all'; // category filter
let jwtToken = localStorage.getItem('crm_jwt') || null;
let currentUser = null;
let currentWorkspace = null;

const CATEGORIES = [
    { id: 'business', label: 'Business', color: '#4CAF50', icon: '💼' },
    { id: 'content', label: 'Content', color: '#2196F3', icon: '📝' },
    { id: 'projects', label: 'Projects', color: '#9C27B0', icon: '🚀' },
    { id: 'system', label: 'System', color: '#FF5722', icon: '⚙️' },
    { id: 'education', label: 'Education', color: '#FF9800', icon: '📚' },
    { id: 'personal', label: 'Personal', color: '#607D8B', icon: '👤' },
];
let periodFilter = localStorage.getItem('crm_period') || 'all';
let refreshTimer = null;

// --- API Client ---
async function api(path, options = {}) {
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (jwtToken) headers['Authorization'] = `Bearer ${jwtToken}`;
    if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;

    const resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `API Error ${resp.status}`);
    }
    if (resp.status === 204) return null;
    return resp.json();
}

// --- JWT Auth Flow ---
async function authenticateUser() {
    // Try JWT auth via Telegram initData
    if (tg?.initData) {
        try {
            const authResp = await api('/auth/telegram', {
                method: 'POST',
                body: JSON.stringify({ init_data: tg.initData }),
            });
            jwtToken = authResp.access_token;
            localStorage.setItem('crm_jwt', jwtToken);
            currentUser = authResp.user;
            return authResp.user;
        } catch (e) {
            console.warn('Telegram auth failed:', e.message);
        }
    }

    // Fallback: try existing JWT token with /me
    if (jwtToken) {
        try {
            const meResp = await api('/auth/me');
            currentUser = meResp.user;
            currentWorkspace = meResp.workspace;
            return currentUser;
        } catch (e) {
            console.warn('JWT /me failed:', e.message);
            jwtToken = null;
            localStorage.removeItem('crm_jwt');
        }
    }

    return null;
}

// --- Onboarding Wizard ---
let onboardingStep = 1;
let onboardingAgents = [];

function showOnboarding() {
    const overlay = document.getElementById('onboarding-overlay');
    const nav = document.getElementById('bottom-nav');
    overlay.classList.remove('hidden');
    nav.style.display = 'none';
    renderOnboardingStep();
}

function hideOnboarding() {
    const overlay = document.getElementById('onboarding-overlay');
    const nav = document.getElementById('bottom-nav');
    overlay.classList.add('hidden');
    nav.style.display = '';
}

function stepsIndicatorHTML(current, total = 4) {
    return `<div class="onboarding-steps-indicator">
        ${Array.from({ length: total }, (_, i) => {
            const step = i + 1;
            const cls = step < current ? 'done' : step === current ? 'active' : '';
            return `<div class="step-dot ${cls}"></div>`;
        }).join('')}
    </div>`;
}

function renderOnboardingStep() {
    const container = document.getElementById('onboarding-content');

    switch (onboardingStep) {
        case 1:
            container.innerHTML = `
                <div class="onboarding-step">
                    ${stepsIndicatorHTML(1)}
                    <div class="onboarding-emoji">🤖</div>
                    <div class="onboarding-title">Welcome to Agent CRM</div>
                    <div class="onboarding-subtitle">Manage your AI agent team in one place</div>
                    <button class="onboarding-btn" onclick="onboardingNext()">Get Started</button>
                </div>
            `;
            break;

        case 2:
            const agentListHTML = onboardingAgents.length
                ? `<div class="onboarding-agents-list">${onboardingAgents.map(a =>
                    `<div class="onboarding-agent-item">
                        <div class="agent-emoji">${a.emoji}</div>
                        <div class="agent-info">
                            <div class="agent-name">${a.name}</div>
                            <div class="agent-meta">${a.model || ''} · ${a.role || ''}</div>
                        </div>
                    </div>`
                ).join('')}</div>`
                : '';

            container.innerHTML = `
                <div class="onboarding-step">
                    ${stepsIndicatorHTML(2)}
                    <div class="onboarding-title">Connect Agents</div>
                    <div class="onboarding-subtitle">How do you want to add agents?</div>
                    <div class="onboarding-cards">
                        <div class="onboarding-card" id="ob-card-import" onclick="showImportForm()">
                            <div class="onboarding-card-icon">🔗</div>
                            <div class="onboarding-card-title">OpenClaw Auto-Import</div>
                            <div class="onboarding-card-desc">Connect your OpenClaw instance</div>
                        </div>
                        <div class="onboarding-card" id="ob-card-manual" onclick="showManualForm()">
                            <div class="onboarding-card-icon">✋</div>
                            <div class="onboarding-card-title">Add Manually</div>
                            <div class="onboarding-card-desc">Create agents one by one</div>
                        </div>
                    </div>
                    <div id="ob-form-area"></div>
                    ${agentListHTML}
                    <button class="onboarding-btn" onclick="onboardingNext()" ${onboardingAgents.length === 0 ? 'disabled' : ''}>Next</button>
                </div>
            `;
            break;

        case 3:
            const agentOpts = onboardingAgents.map(a =>
                `<option value="${a.id}">${a.emoji} ${a.name}</option>`
            ).join('');
            container.innerHTML = `
                <div class="onboarding-step">
                    ${stepsIndicatorHTML(3)}
                    <div class="onboarding-title">Create Your First Task</div>
                    <div class="onboarding-subtitle">Give your agents something to work on</div>
                    <div class="onboarding-form">
                        <div class="field">
                            <label>Task Title</label>
                            <input type="text" id="ob-task-title" placeholder="e.g. Write welcome post">
                        </div>
                        <div class="field">
                            <label>Assign to Agent</label>
                            <select id="ob-task-agent">
                                <option value="">Unassigned</option>
                                ${agentOpts}
                            </select>
                        </div>
                    </div>
                    <button class="onboarding-btn" onclick="onboardingCreateTask()">Create</button>
                    <button class="onboarding-btn onboarding-btn-secondary" onclick="onboardingNext()">Skip</button>
                </div>
            `;
            break;

        case 4:
            const tier = currentUser?.tier || currentWorkspace?.tier || 'hobby';
            container.innerHTML = `
                <div class="onboarding-step">
                    ${stepsIndicatorHTML(4)}
                    <div class="onboarding-emoji">🎉</div>
                    <div class="onboarding-title">You're All Set!</div>
                    <div class="onboarding-subtitle">Your workspace is ready</div>
                    <div class="onboarding-summary">
                        <div class="onboarding-summary-item">
                            <span>Agents</span>
                            <span class="onboarding-summary-value">${onboardingAgents.length}</span>
                        </div>
                        <div class="onboarding-summary-item">
                            <span>Tier</span>
                            <span class="onboarding-summary-value">${tier.charAt(0).toUpperCase() + tier.slice(1)}</span>
                        </div>
                    </div>
                    <button class="onboarding-btn" onclick="finishOnboarding()">Open Dashboard</button>
                </div>
            `;
            break;
    }
}

window.onboardingNext = function() {
    onboardingStep++;
    renderOnboardingStep();
};

window.showImportForm = function() {
    document.getElementById('ob-card-import').classList.add('active');
    document.getElementById('ob-card-manual').classList.remove('active');
    document.getElementById('ob-form-area').innerHTML = `
        <div class="onboarding-form">
            <div class="field">
                <label>OpenClaw URL</label>
                <input type="text" id="ob-openclaw-url" placeholder="http://localhost:3335">
            </div>
            <button class="onboarding-btn" onclick="importFromOpenClaw()" style="margin-top:0">Connect</button>
        </div>
    `;
};

window.showManualForm = function() {
    document.getElementById('ob-card-manual').classList.add('active');
    document.getElementById('ob-card-import').classList.remove('active');
    document.getElementById('ob-form-area').innerHTML = `
        <div class="onboarding-form">
            <div class="field">
                <label>Name</label>
                <input type="text" id="ob-agent-name" placeholder="Agent name">
            </div>
            <div class="field">
                <label>Emoji</label>
                <input type="text" id="ob-agent-emoji" placeholder="🤖" maxlength="4">
            </div>
            <div class="field">
                <label>Model</label>
                <input type="text" id="ob-agent-model" placeholder="claude-sonnet-4-6">
            </div>
            <div class="field">
                <label>Role</label>
                <input type="text" id="ob-agent-role" placeholder="e.g. Developer, Writer">
            </div>
            <button class="onboarding-btn" onclick="addManualAgent()" style="margin-top:0">Add Agent</button>
        </div>
    `;
};

window.importFromOpenClaw = async function() {
    const url = document.getElementById('ob-openclaw-url')?.value?.trim();
    if (!url) return;
    try {
        // Try to fetch agents from OpenClaw instance
        const resp = await fetch(`${url}/api/agents`);
        if (!resp.ok) throw new Error('Failed to connect');
        const clawAgents = await resp.json();

        // Create each agent in our backend
        for (const ca of clawAgents) {
            try {
                const created = await api('/agents', {
                    method: 'POST',
                    body: JSON.stringify({
                        name: ca.name || ca.id,
                        emoji: ca.emoji || '🤖',
                        model: ca.model || '',
                        role: ca.role || '',
                    }),
                });
                onboardingAgents.push(created);
            } catch (e) {
                console.warn('Failed to create agent:', e.message);
            }
        }

        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        renderOnboardingStep();
    } catch (e) {
        alert('Failed to connect: ' + e.message);
    }
};

window.addManualAgent = async function() {
    const name = document.getElementById('ob-agent-name')?.value?.trim();
    const emoji = document.getElementById('ob-agent-emoji')?.value?.trim() || '🤖';
    const model = document.getElementById('ob-agent-model')?.value?.trim() || '';
    const role = document.getElementById('ob-agent-role')?.value?.trim() || '';

    if (!name) { alert('Name is required'); return; }

    try {
        const created = await api('/agents', {
            method: 'POST',
            body: JSON.stringify({ name, emoji, model, role }),
        });
        onboardingAgents.push(created);
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        renderOnboardingStep();
    } catch (e) {
        alert('Failed to add agent: ' + e.message);
    }
};

window.onboardingCreateTask = async function() {
    const title = document.getElementById('ob-task-title')?.value?.trim();
    if (!title) { alert('Title is required'); return; }

    const agentId = document.getElementById('ob-task-agent')?.value || null;
    try {
        await api('/tasks', {
            method: 'POST',
            body: JSON.stringify({
                title,
                agent_id: agentId ? parseInt(agentId) : null,
                status: 'todo',
                priority: 'medium',
            }),
        });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        onboardingNext();
    } catch (e) {
        alert('Failed to create task: ' + e.message);
    }
};

window.finishOnboarding = async function() {
    try {
        await api('/auth/onboarding-complete', { method: 'PATCH' });
    } catch (e) {
        console.warn('Failed to mark onboarding complete:', e.message);
    }
    hideOnboarding();
    navigate('dashboard');
};

// --- Tier Badge ---
function getTierBadgeHTML() {
    const tier = currentUser?.tier || currentWorkspace?.tier || null;
    if (!tier) return '';
    return `<span class="tier-badge tier-${tier}">${tier}</span>`;
}

function updateHeaderTier() {
    const h1 = document.getElementById('page-title');
    // Remove old badge if any
    const oldBadge = h1.querySelector('.tier-badge');
    if (oldBadge) oldBadge.remove();
    const badge = getTierBadgeHTML();
    if (badge) h1.insertAdjacentHTML('beforeend', badge);
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
    const titles = { dashboard: 'Dashboard', kanban: 'Task Board', agents: 'Agents', crons: 'Crons', files: 'Files', journal: 'Journal', alerts: 'Alerts' };
    document.getElementById('page-title').textContent = titles[currentRoute] || 'Agent CRM';
    updateHeaderTier();
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
            case 'crons': await renderCrons(content); break;
            case 'files': await renderFiles(content); break;
            case 'journal': await renderJournal(content); break;
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
    const [data, sysStatus, spending, dailyTimeline, weeklyTimeline, sessions] = await Promise.all([
        api(`/dashboard${params}`),
        api('/system/status').catch(() => ({ status: 'unknown', gateway: false })),
        api('/spending/current').catch(() => ({ today: 0, week: 0, month: 0, budget: 200, agents: [] })),
        api('/spending/timeline?range=day').catch(() => ({ labels: [], data: [] })),
        api('/spending/timeline?range=week').catch(() => ({ labels: [], data: [] })),
        api('/spending/sessions').catch(() => []),
    ]);
    agents = data.agents;

    const costLabel = periodFilter === 'today' ? 'Today' : periodFilter === 'week' ? 'This Week' : periodFilter === 'month' ? 'This Month' : 'Total';
    const taskLabel = periodFilter === 'all' ? 'Active Tasks' : `Tasks (${periodFilter})`;
    const statusIcon = sysStatus.gateway ? '🟢' : '🔴';
    const statusText = sysStatus.gateway ? 'Running' : 'Stopped';
    const budgetPct = Math.min(100, (spending.month / spending.budget * 100)).toFixed(0);

    el.innerHTML = `
        <div class="system-bar">
            <span class="sys-status">${statusIcon} ${statusText}</span>
            <div class="sys-actions">
                <button class="btn-sm btn-danger-sm" onclick="systemAction('stop')">⏹ Stop</button>
                <button class="btn-sm btn-success-sm" onclick="systemAction('resume')">▶ Resume</button>
            </div>
        </div>
        <div class="budget-bar">
            <div class="budget-label">Monthly Budget: $${spending.month.toFixed(2)} / $${spending.budget}</div>
            <div class="progress-track"><div class="progress-fill ${budgetPct > 90 ? 'progress-danger' : budgetPct > 80 ? 'progress-warn' : ''}" style="width:${budgetPct}%"></div></div>
            <div class="budget-meta">
                <span class="budget-tag">📅 Today: $${spending.today.toFixed(2)}</span>
                <span class="budget-tag">📆 Week: $${spending.week.toFixed(2)}</span>
            </div>
        </div>
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
        <div class="section-header">Today (hourly)</div>
        <div class="chart-container"><canvas id="dash-daily-chart"></canvas></div>
        <div class="section-header">This Week (daily)</div>
        <div class="chart-container"><canvas id="dash-weekly-chart"></canvas></div>
        ${sessions.length ? `
        <div class="section-header">Sessions</div>
        <div class="sessions-list">
            ${sessions.map(s => {
                const agentEmoji = agents.find(a => a.name?.toLowerCase() === s.agent?.toLowerCase())?.emoji || '🤖';
                return `<div class="card session-card">
                    <div class="session-agent">${agentEmoji} ${s.agent}</div>
                    <div class="session-meta">
                        <span class="session-id">${(s.session_id || '').slice(0, 8)}</span>
                        <span class="session-cost">$${s.cost.toFixed(2)}</span>
                        <span class="session-msgs">${s.messages} msgs</span>
                    </div>
                </div>`;
            }).join('')}
        </div>
        ` : ''}
        <div class="section-header">Agents</div>
        ${data.agents.map(a => `<div class="card agent-card">
            <div class="agent-emoji">${a.emoji}</div>
            <div class="agent-info">
                <div class="agent-name">${a.name}</div>
                <div class="agent-meta">${a.role || (a.model ? a.model.split('/').pop() : '—')}</div>
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

    // Render dashboard daily chart (green)
    if (dailyTimeline.labels.length && typeof Chart !== 'undefined') {
        const ctx = document.getElementById('dash-daily-chart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dailyTimeline.labels,
                    datasets: [{
                        label: 'Hourly $',
                        data: dailyTimeline.data,
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: v => '$' + v, color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        x: { ticks: { color: '#888' }, grid: { display: false } },
                    },
                },
            });
        }
    }

    // Render dashboard weekly chart (purple)
    if (weeklyTimeline.labels.length && typeof Chart !== 'undefined') {
        const ctx = document.getElementById('dash-weekly-chart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: weeklyTimeline.labels.map(l => l.slice(5)),
                    datasets: [{
                        label: 'Daily $',
                        data: weeklyTimeline.data,
                        borderColor: '#6c63ff',
                        backgroundColor: 'rgba(108, 99, 255, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: v => '$' + v, color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        x: { ticks: { color: '#888' }, grid: { display: false } },
                    },
                },
            });
        }
    }
}

window.systemAction = async function(action) {
    if (action === 'stop' && !confirm('Stop gateway and disable all crons?')) return;
    try {
        await api(`/system/${action}`, { method: 'POST' });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        render();
    } catch (err) { alert(err.message); }
};

// ============================================
//  KANBAN BOARD
// ============================================

const COLUMNS = [
    { id: 'todo', label: 'Todo', icon: '📝' },
    { id: 'in_progress', label: 'In Progress', icon: '🔄' },
    { id: 'done', label: 'Done', icon: '✅' },
];

async function renderKanban(el) {
    // Load data with period + category filter
    if (!agents.length) try { agents = await api('/agents'); } catch(e) {}
    const params = new URLSearchParams();
    if (periodFilter !== 'all') params.set('period', periodFilter);
    if (categoryFilter !== 'all') params.set('category', categoryFilter);
    const qs = params.toString() ? `?${params}` : '';
    allTasks = await api(`/tasks${qs}`);

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
        <div class="kanban-filter category-filter">
            <button class="filter-chip cat-chip ${categoryFilter === 'all' ? 'active' : ''}" data-cat="all">All</button>
            ${CATEGORIES.map(c => `
                <button class="filter-chip cat-chip ${categoryFilter === c.id ? 'active' : ''}" data-cat="${c.id}" style="--cat-color: ${c.color}">
                    ${c.icon} ${c.label}
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
    el.querySelectorAll('.filter-chip:not(.cat-chip)').forEach(chip => {
        chip.addEventListener('click', () => {
            kanbanFilter = chip.dataset.filter;
            renderKanban(el);
        });
    });

    // Setup category filter clicks
    el.querySelectorAll('.cat-chip').forEach(chip => {
        chip.addEventListener('click', () => {
            categoryFilter = chip.dataset.cat;
            renderKanban(el);
        });
    });

    // Setup card clicks
    el.querySelectorAll('.kanban-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (card.classList.contains('sortable-chosen')) return;
            // Edit button opens modal
            if (e.target.closest('.kanban-edit-btn')) {
                openTaskModal(parseInt(card.dataset.id));
                return;
            }
            // Everything else toggles expand
            card.classList.toggle('expanded');
            if (tg) tg.HapticFeedback?.impactOccurred('light');
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

function categoryBadgeHTML(cat) {
    if (!cat) return '';
    const c = CATEGORIES.find(x => x.id === cat);
    if (!c) return `<span class="cat-badge">${cat}</span>`;
    return `<span class="cat-badge" style="background:${c.color}20;color:${c.color};border:1px solid ${c.color}40">${c.icon} ${c.label}</span>`;
}

function kanbanCardHTML(t) {
    const agentStr = t.agent ? `${t.agent.emoji} ${t.agent.name}` : '—';
    const dlClass = t.deadline_status === 'overdue' ? 'deadline-overdue-card'
        : t.deadline_status === 'soon' ? 'deadline-soon-card' : '';
    const dlBadge = t.deadline ? deadlineBadgeHTML(t) : '';
    const catBadge = categoryBadgeHTML(t.category);

    const descPreview = t.description ? `<div class="kanban-desc">${escapeHtml(t.description)}</div>` : '';

    return `
        <div class="kanban-card priority-${t.priority} ${dlClass}" data-id="${t.id}">
            <div class="kanban-title">${escapeHtml(t.title)}</div>
            ${descPreview}
            <div class="kanban-meta">
                <span class="kanban-agent">${agentStr}</span>
                ${catBadge}
                <span class="priority-dot"></span>
                ${dlBadge}
                <span>${timeAgo(t.created)}</span>
            </div>
            <button class="kanban-edit-btn">✏️ Edit</button>
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
let availableModels = [];

async function renderAgents(el) {
    [agents, availableModels] = await Promise.all([
        api('/agents'),
        api('/agents/models').catch(() => ['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-35-20241022']),
    ]);

    // Check restart status
    const restartStatus = await api('/agents/restart-status').catch(() => ({ restart_pending: false }));
    const restartBanner = restartStatus.restart_pending
        ? `<div class="card restart-banner" onclick="restartGateway()">
            <span>⚠️ Config changed — tap to restart gateway</span>
        </div>`
        : '';

    const tier = currentUser?.tier || currentWorkspace?.tier || 'hobby';
    const agentLimit = currentWorkspace?.agent_limit || 3;
    const limitInfo = `<div class="agent-limit-info">🤖 ${agents.length}/${agentLimit} agents (${tier.charAt(0).toUpperCase() + tier.slice(1)})</div>`;

    el.innerHTML = restartBanner + limitInfo + (agents.length
        ? agents.map(a => `<div class="card agent-card-full">
            <div class="agent-header">
                <div class="agent-emoji">${a.emoji}</div>
                <div class="agent-info">
                    <div class="agent-name">${a.name}</div>
                    <div class="agent-role">${a.role || '—'}</div>
                    <div class="agent-bio">${a.bio || ''}</div>
                </div>
                <span class="status-badge status-${a.status}">
                    <span class="status-dot"></span> ${a.status}
                </span>
            </div>
            <div class="agent-details">
                <div class="agent-detail">
                    <label>Model</label>
                    <select class="agent-model-select" data-agent-id="${a.id}" onchange="changeAgentModel(${a.id}, this.value)">
                        ${availableModels.map(m => `<option value="${m}" ${a.model === m ? 'selected' : ''}>${m.split('/').pop()}</option>`).join('')}
                        ${a.model && !availableModels.includes(a.model) ? `<option value="${a.model}" selected>${a.model.split('/').pop()}</option>` : ''}
                    </select>
                </div>
                <div class="agent-meta-row">
                    <span>Last active: ${a.last_active ? timeAgo(a.last_active) : 'never'}</span>
                    <span>Cost: <strong style="color:var(--text);font-size:13px">$${a.daily_cost.toFixed(2)}</strong>/day</span>
                </div>
            </div>
        </div>`).join('')
        : '<div class="empty-state"><div class="empty-icon">🤖</div><p>No agents</p></div>');
}

window.changeAgentModel = async function(agentId, model) {
    try {
        await api(`/agents/${agentId}`, {
            method: 'PATCH',
            body: JSON.stringify({ model }),
        });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        render(); // Re-render to show restart banner
    } catch (err) {
        alert(err.message);
        render();
    }
};

window.restartGateway = async function() {
    if (!confirm('Restart OpenClaw gateway? Agents will be briefly unavailable (~3 sec).')) return;
    try {
        await api('/agents/restart', { method: 'POST' });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        render();
    } catch (err) {
        alert('Restart failed: ' + err.message);
    }
};

// --- Alerts ---
async function renderAlerts(el) {
    const [alerts, sysStatus, spending, timeline, dailyTimeline] = await Promise.all([
        api('/alerts'),
        api('/system/status').catch(() => ({ status: 'unknown', gateway: false })),
        api('/spending/current').catch(() => ({ today: 0, week: 0, month: 0, budget: 200 })),
        api('/spending/timeline?range=week').catch(() => ({ labels: [], data: [] })),
        api('/spending/timeline?range=day').catch(() => ({ labels: [], data: [] })),
    ]);

    const statusIcon = sysStatus.gateway ? '🟢' : '🔴';
    const budgetPct = Math.min(100, (spending.month / spending.budget * 100)).toFixed(0);

    el.innerHTML = `
        <div class="system-bar">
            <span class="sys-status">${statusIcon} ${sysStatus.gateway ? 'Running' : 'Stopped'}</span>
            <div class="sys-actions">
                <button class="btn-sm btn-danger-sm" onclick="systemAction('stop')">⏹ Stop</button>
                <button class="btn-sm btn-success-sm" onclick="systemAction('resume')">▶ Resume</button>
                <button class="btn-sm btn-fix-sm" onclick="systemFix()">🔧 Fix</button>
            </div>
        </div>
        <div class="budget-bar">
            <div class="budget-label">Budget: $${spending.month.toFixed(2)} / $${spending.budget} (${budgetPct}%)</div>
            <div class="progress-track"><div class="progress-fill ${budgetPct > 90 ? 'progress-danger' : budgetPct > 80 ? 'progress-warn' : ''}" style="width:${budgetPct}%"></div></div>
            <div class="budget-meta">
                <span class="budget-tag">📅 Today: $${spending.today.toFixed(2)}</span>
                <span class="budget-tag">📆 Week: $${spending.week.toFixed(2)}</span>
            </div>
        </div>
        <div class="section-header">Today (hourly)</div>
        <div class="chart-container"><canvas id="alerts-daily-chart"></canvas></div>
        <div class="section-header">Spending (7 days)</div>
        <div class="chart-container"><canvas id="spending-chart"></canvas></div>
        <div class="section-header">Alerts</div>
        ${alerts.length
            ? alerts.map(a => alertCardHTML(a)).join('')
            : '<div class="empty-state"><div class="empty-icon">🔔</div><p>No alerts</p></div>'}
    `;

    // Render daily chart (green)
    if (dailyTimeline.labels.length && typeof Chart !== 'undefined') {
        const ctx = document.getElementById('alerts-daily-chart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: dailyTimeline.labels,
                    datasets: [{
                        label: 'Hourly $',
                        data: dailyTimeline.data,
                        borderColor: '#4CAF50',
                        backgroundColor: 'rgba(76, 175, 80, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: v => '$' + v, color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        x: { ticks: { color: '#888' }, grid: { display: false } },
                    },
                },
            });
        }
    }

    // Render weekly chart (purple)
    if (timeline.labels.length && typeof Chart !== 'undefined') {
        const ctx = document.getElementById('spending-chart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: timeline.labels.map(l => l.slice(5)),
                    datasets: [{
                        label: 'Daily $',
                        data: timeline.data,
                        borderColor: '#6c63ff',
                        backgroundColor: 'rgba(108, 99, 255, 0.1)',
                        fill: true,
                        tension: 0.3,
                        pointRadius: 4,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { beginAtZero: true, ticks: { callback: v => '$' + v, color: '#888' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                        x: { ticks: { color: '#888' }, grid: { display: false } },
                    },
                },
            });
        }
    }
}

window.systemFix = async function() {
    if (!confirm('This will reset agent sessions and pause all crons. Continue?')) return;
    try {
        const result = await api('/system/fix', { method: 'POST' });
        let msg = '🔧 Fix applied:\n';
        msg += `Sessions cleared: ${result.cleared_sessions.length}\n`;
        msg += `Crons paused: ${result.paused_crons.length}\n`;
        if (Object.keys(result.spending_last_hour).length) {
            msg += '\nSpending (last hour):\n';
            for (const [agent, data] of Object.entries(result.spending_last_hour)) {
                msg += `  ${agent}: $${data.cost} (${data.messages} msgs)\n`;
            }
        }
        alert(msg);
        if (tg) tg.HapticFeedback?.notificationOccurred('warning');
        render();
    } catch (err) { alert(err.message); }
};

function alertCardHTML(a) {
    const icons = { error: '🚨', warning: '⚠️', info: 'ℹ️' };
    const typeClass = `alert-${a.type || 'info'}`;
    return `
        <div class="card alert-card ${typeClass} ${a.is_read ? '' : 'alert-unread'}" onclick="markAlertRead(${a.id})">
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
            document.getElementById('task-category').value = task.category || '';
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
        category: document.getElementById('task-category').value || '',
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

// ============================================
//  JOURNAL PAGE
// ============================================

async function renderJournal(el) {
    let days = [];
    try {
        days = await api('/journal?limit=30');
    } catch (err) {
        el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>${err.message}</p></div>`;
        return;
    }

    if (!agents.length) try { agents = await api('/agents'); } catch(e) {}

    el.innerHTML = `
        <div class="journal-actions">
            <button class="btn btn-primary btn-sm" onclick="importMemory()">📥 Import from Memory</button>
            <button class="btn btn-primary btn-sm" onclick="openJournalEditor()">✏️ New Entry</button>
        </div>
        ${days.length ? days.map(day => `
            <div class="card journal-day">
                <div class="journal-day-header">
                    <span class="journal-date">${formatJournalDate(day.date)}</span>
                    <span class="journal-cost">${day.total_cost > 0 ? '$' + day.total_cost.toFixed(2) : ''}</span>
                </div>
                ${day.entries.map(e => `
                    <div class="journal-entry" data-id="${e.id}">
                        <div class="journal-entry-header">
                            <span class="journal-agent">${e.agent ? e.agent.emoji + ' ' + e.agent.name : '📝'}</span>
                            <span class="journal-source ${e.source}">${e.source}</span>
                        </div>
                        <div class="journal-content markdown-body">${marked.parse(e.content)}</div>
                    </div>
                `).join('')}
            </div>
        `).join('') : '<div class="empty-state"><div class="empty-icon">📔</div><p>No journal entries yet</p></div>'}
    `;
}

function formatJournalDate(dateStr) {
    const d = new Date(dateStr + 'T00:00:00');
    const today = new Date();
    today.setHours(0,0,0,0);
    const diff = Math.round((today - d) / 86400000);
    const weekday = d.toLocaleDateString('en', { weekday: 'short' });
    const label = d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
    if (diff === 0) return `📅 Today — ${label}`;
    if (diff === 1) return `📅 Yesterday — ${label}`;
    return `📅 ${weekday}, ${label}`;
}

window.importMemory = async function() {
    try {
        const result = await api('/journal/import-memory', { method: 'POST' });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        alert(`Imported ${result.imported} entries`);
        render();
    } catch (err) {
        alert('Import failed: ' + err.message);
    }
};

window.openJournalEditor = function(entryId = null) {
    const overlay = document.getElementById('modal-overlay');
    const modal = overlay.querySelector('.modal');
    const today = new Date().toISOString().slice(0, 10);

    modal.innerHTML = `
        <div class="modal-header">
            <h2>${entryId ? 'Edit' : 'New'} Journal Entry</h2>
            <button class="modal-close" onclick="closeModal()">&times;</button>
        </div>
        <form class="modal-body" id="journal-form">
            <div class="field-row">
                <div class="field">
                    <label>Date</label>
                    <input type="date" id="journal-date" value="${today}" required>
                </div>
                <div class="field">
                    <label>Agent</label>
                    <select id="journal-agent">
                        <option value="">General</option>
                        ${agents.map(a => `<option value="${a.id}">${a.emoji} ${a.name}</option>`).join('')}
                    </select>
                </div>
            </div>
            <div class="field">
                <label>Content (Markdown)</label>
                <textarea id="journal-content" rows="8" placeholder="What happened today..." required></textarea>
            </div>
            <div class="modal-actions">
                <button type="submit" class="btn btn-primary">Save</button>
            </div>
        </form>
    `;

    document.getElementById('journal-form').addEventListener('submit', async (e) => {
        e.preventDefault();
        const data = {
            date: document.getElementById('journal-date').value,
            agent_id: document.getElementById('journal-agent').value || null,
            content: document.getElementById('journal-content').value,
            source: 'manual',
        };
        if (data.agent_id) data.agent_id = parseInt(data.agent_id);

        try {
            await api('/journal', { method: 'POST', body: JSON.stringify(data) });
            closeModal();
            render();
            if (tg) tg.HapticFeedback?.notificationOccurred('success');
        } catch (err) { alert(err.message); }
    });

    overlay.classList.remove('hidden');
};

// ============================================
//  CRONS PAGE
// ============================================

async function renderCrons(el) {
    let crons = [];
    try {
        crons = await api('/crons');
    } catch (err) {
        el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load crons: ${err.message}</p></div>`;
        return;
    }

    el.innerHTML = crons.length
        ? crons.map(c => {
            const nextRun = c.next_run ? new Date(c.next_run).toLocaleString() : '—';
            return `<div class="card cron-card">
                <div class="cron-header">
                    <div class="cron-info">
                        <div class="cron-name">${escapeHtml(c.name)}</div>
                        <div class="cron-schedule">${c.schedule} · ${c.agent_id || 'default'}</div>
                        <div class="cron-meta">${c.model ? c.model.split('/').pop() : ''} · Next: ${nextRun}</div>
                    </div>
                    <label class="toggle">
                        <input type="checkbox" ${c.enabled ? 'checked' : ''} onchange="toggleCron('${c.id}', this.checked)">
                        <span class="toggle-slider"></span>
                    </label>
                </div>
                ${c.description ? `<div class="cron-desc">${escapeHtml(c.description)}</div>` : ''}
            </div>`;
        }).join('')
        : '<div class="empty-state"><div class="empty-icon">⏰</div><p>No cron jobs</p></div>';

    // Inline expand on click
    el.querySelectorAll('.cron-card').forEach(card => {
        card.addEventListener('click', (e) => {
            if (e.target.closest('.toggle')) return;
            const desc = card.querySelector('.cron-desc');
            if (!desc) return;
            card.classList.toggle('expanded');
            if (tg) tg.HapticFeedback?.impactOccurred('light');
        });
    });
}

window.toggleCron = async function(id, enabled) {
    try {
        await api(`/crons/${id}/${enabled ? 'enable' : 'disable'}`, { method: 'POST' });
        if (tg) tg.HapticFeedback?.impactOccurred('light');
    } catch (err) {
        alert(err.message);
        render();
    }
};


// ============================================
//  FILES PAGE
// ============================================

async function renderFiles(el) {
    let files = [];
    try {
        files = await api('/files');
    } catch (err) {
        el.innerHTML = `<div class="empty-state"><p>Failed to load files</p></div>`;
        return;
    }

    // Group by agent
    const grouped = {};
    for (const f of files) {
        if (!grouped[f.agent]) grouped[f.agent] = [];
        grouped[f.agent].push(f);
    }

    el.innerHTML = Object.entries(grouped).map(([agent, agentFiles]) => `
        <div class="section-header">${agent}</div>
        ${agentFiles.map(f => `
            <div class="card file-card ${f.exists ? '' : 'file-missing'}" onclick="${f.exists ? `openFileModal('${agent}', '${f.filename}')` : ''}">
                <div class="file-icon">📄</div>
                <div class="file-info">
                    <div class="file-name">${f.filename}</div>
                    <div class="file-size">${f.exists ? formatBytes(f.size) : 'not found'}</div>
                </div>
            </div>
        `).join('')}
    `).join('');
}

window.openFileModal = async function(agent, filename) {
    try {
        const data = await api(`/files/${agent}/${filename}`);
        const overlay = document.getElementById('modal-overlay');
        const modal = overlay.querySelector('.modal');
        modal.innerHTML = `
            <div class="modal-header">
                <h2>${agent} / ${filename}</h2>
                <button class="modal-close" onclick="closeModal()">&times;</button>
            </div>
            <div class="modal-body markdown-body">${marked.parse(data.content)}</div>
        `;
        overlay.classList.remove('hidden');
    } catch (err) { alert(err.message); }
};

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}


// ============================================
//  ALERTS PAGE (expanded)
// ============================================
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
(async function init() {
    try {
        // Authenticate first
        const user = await authenticateUser();

        // Load workspace info if we have a token
        if (jwtToken && !currentWorkspace) {
            try {
                const meResp = await api('/auth/me');
                currentWorkspace = meResp.workspace;
                if (!currentUser) currentUser = meResp.user;
            } catch (e) {
                console.warn('Failed to load /me:', e.message);
            }
        }

        // Check onboarding
        if (user && user.onboarding_complete === false) {
            // Load existing agents for onboarding state
            try {
                const existingAgents = await api('/agents');
                onboardingAgents = existingAgents || [];
            } catch (e) {}
            showOnboarding();
        }

        const validRoutes = ['dashboard', 'kanban', 'agents', 'crons', 'files', 'journal', 'alerts'];
        let initHash = window.location.hash.slice(1);
        if (initHash.includes('tgWebApp') || initHash.includes('=')) {
            initHash = '';
        }
        navigate(validRoutes.includes(initHash) ? initHash : 'dashboard');
    } catch (e) {
        console.error('Init error:', e);
        navigate('dashboard');
    }

    refreshTimer = setInterval(() => { if (currentRoute === 'dashboard') render(); }, REFRESH_INTERVAL);
})();
