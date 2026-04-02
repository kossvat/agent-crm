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
    // Prevent pull-to-close when scrolling content
    try { tg.disableVerticalSwipes(); } catch(e) {}
    try { tg.isVerticalSwipesEnabled = false; } catch(e) {}
}

// --- Config ---
const API_BASE = '/api';
const REFRESH_INTERVAL = 30000;

// --- Toast Notification System ---
function showToast(message, type = 'info', options = {}) {
    const { title, duration = 4000 } = options;
    const container = document.getElementById('toast-container');
    if (!container) return;

    const icons = { error: '❌', warning: '⚠️', success: '✅', info: 'ℹ️' };
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.style.position = 'relative';
    toast.innerHTML = `
        <span class="toast-icon">${icons[type] || icons.info}</span>
        <div class="toast-body">
            ${title ? `<div class="toast-title">${title}</div>` : ''}
            <div class="toast-message">${message}</div>
        </div>
        <button class="toast-close">&times;</button>
        <div class="toast-progress" style="animation-duration:${duration}ms"></div>
    `;

    // Haptic feedback
    if (tg?.HapticFeedback) {
        if (type === 'error') tg.HapticFeedback.notificationOccurred('error');
        else if (type === 'success') tg.HapticFeedback.notificationOccurred('success');
        else tg.HapticFeedback.impactOccurred('light');
    }

    // Close handlers
    const dismiss = () => {
        toast.classList.add('toast-exit');
        setTimeout(() => toast.remove(), 250);
    };
    toast.querySelector('.toast-close').addEventListener('click', dismiss);
    toast.addEventListener('click', (e) => {
        if (!e.target.closest('.toast-close')) dismiss();
    });

    container.appendChild(toast);

    // Auto-dismiss
    setTimeout(dismiss, duration);

    // Max 3 toasts
    while (container.children.length > 3) {
        container.firstChild.remove();
    }
}

// --- Network Status ---
let isOffline = false;
window.addEventListener('online', () => {
    isOffline = false;
    document.getElementById('offline-banner')?.classList.add('hidden');
    showToast('Back online', 'success', { duration: 2000 });
});
window.addEventListener('offline', () => {
    isOffline = true;
    document.getElementById('offline-banner')?.classList.remove('hidden');
});

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
let isDemoMode = false;

// --- Demo Mode Data ---
const DEMO_AGENTS = [
    { id: 101, name: 'Content Writer', emoji: '✍️', model: 'claude-sonnet-4-6', status: 'active', role: 'Content', bio: 'Writes blog posts and social media content', daily_cost: 2.5, last_active: new Date().toISOString() },
    { id: 102, name: 'Code Reviewer', emoji: '🔍', model: 'claude-opus-4-6', status: 'idle', role: 'Engineering', bio: 'Reviews PRs and suggests improvements', daily_cost: 4.0, last_active: new Date(Date.now() - 3600000).toISOString() },
    { id: 103, name: 'Data Analyst', emoji: '📊', model: 'claude-sonnet-4-6', status: 'active', role: 'Analytics', bio: 'Analyzes data and generates reports', daily_cost: 3.2, last_active: new Date().toISOString() },
];
const DEMO_TASKS = [
    { id: 201, title: 'Write Q1 blog post', description: 'Quarterly review blog post for the company blog', status: 'todo', priority: 'high', agent_id: 101, agent_name: 'Content Writer', agent_emoji: '✍️', category: 'content', created: new Date(Date.now() - 86400000).toISOString() },
    { id: 202, title: 'Review auth PR #42', description: 'Security review of the new auth flow', status: 'in_progress', priority: 'high', agent_id: 102, agent_name: 'Code Reviewer', agent_emoji: '🔍', category: 'projects', created: new Date(Date.now() - 43200000).toISOString() },
    { id: 203, title: 'Analyze user retention', description: 'Monthly retention cohort analysis', status: 'in_progress', priority: 'medium', agent_id: 103, agent_name: 'Data Analyst', agent_emoji: '📊', category: 'business', created: new Date(Date.now() - 172800000).toISOString() },
    { id: 204, title: 'Draft social media plan', description: 'Plan content for next 2 weeks', status: 'todo', priority: 'medium', agent_id: 101, agent_name: 'Content Writer', agent_emoji: '✍️', category: 'content', created: new Date().toISOString() },
    { id: 205, title: 'Deploy monitoring dashboard', description: 'Set up Grafana dashboards for prod', status: 'done', priority: 'low', agent_id: 102, agent_name: 'Code Reviewer', agent_emoji: '🔍', category: 'system', created: new Date(Date.now() - 259200000).toISOString() },
];
const DEMO_JOURNAL = [
    { id: 301, date: new Date().toISOString().slice(0, 10), agent_id: 101, content: 'Drafted 2 blog post outlines and published the weekly newsletter. Engagement up 15%.', source: 'auto' },
    { id: 302, date: new Date().toISOString().slice(0, 10), agent_id: 103, content: 'Completed user funnel analysis — found 23% drop-off at onboarding step 3. Recommended simplification.', source: 'auto' },
    { id: 303, date: new Date(Date.now() - 86400000).toISOString().slice(0, 10), agent_id: 102, content: 'Reviewed 4 PRs, found 2 critical SQL injection vulnerabilities. Both patched.', source: 'auto' },
];

async function demoApi(path, options = {}) {
    // Read-only endpoints — fetch from backend demo API
    if (path.startsWith('/dashboard')) {
        try { return await fetch('/api/demo/dashboard').then(r => r.json()); } catch(_) {}
        return { agent_count: 3, active_tasks: 4, today_cost: 12.50, unread_alerts: 0, agents: DEMO_AGENTS, recent_alerts: [] };
    }
    if (path.startsWith('/agents')) {
        try { return await fetch('/api/demo/agents').then(r => r.json()); } catch(_) {}
        return DEMO_AGENTS;
    }
    if (path === '/tasks' || path.startsWith('/tasks?')) {
        try { return await fetch('/api/demo/tasks').then(r => r.json()); } catch(_) {}
        return DEMO_TASKS;
    }
    if (path.startsWith('/system/status')) return { status: 'ok', gateway: true };
    if (path.startsWith('/spending/current')) return { today: 12.50, month: 87.30, plan: 'Pro', window_hours: 5, usage: { all: { used: 0, limit: 44000, pct: 0 }, models: [] }, agents: DEMO_AGENTS.map(a => ({ agent_id: a.id, agent_name: a.name, cost: a.daily_cost })) };
    if (path.startsWith('/spending/timeline')) return { labels: [], data: [] };
    if (path.startsWith('/spending/sessions')) return [];
    if (path.startsWith('/journal')) return DEMO_JOURNAL;
    if (path.startsWith('/alerts')) return [];
    if (path.startsWith('/crons')) return [];
    if (path.startsWith('/files')) return [];
    // Write operations — block in demo mode
    showToast('Demo mode \u2014 open in Telegram to manage your agents', 'info', { duration: 2500 });
    return { ok: true };
}

function enterDemoMode() {
    isDemoMode = true;
    jwtToken = null;
    localStorage.removeItem('crm_jwt');
    currentUser = { id: 0, name: 'Demo User', onboarding_complete: true, is_superadmin: false };
    currentWorkspace = { id: 0, name: 'Demo Workspace', tier: 'pro', agent_limit: 10 };
    agents = [...DEMO_AGENTS];
    allTasks = [...DEMO_TASKS];

    hideOnboarding();

    // Inject demo banner
    let banner = document.getElementById('demo-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'demo-banner';
        banner.innerHTML = `
            <span>🎮 Demo Mode — <a href="https://t.me/Ai_Agent_CRM_bot" style="color:var(--link);text-decoration:underline;">Open in Telegram</a> for the real thing</span>
            <button onclick="exitDemoMode()">Exit Demo</button>
        `;
        document.getElementById('app').prepend(banner);
    }
    banner.style.display = '';

    // Hide irrelevant nav items in demo
    document.getElementById('nav-admin')?.style && (document.getElementById('nav-admin').style.display = 'none');

    const validRoutes = ['dashboard', 'kanban', 'agents', 'journal'];
    // Hide files/crons/alerts in demo — less relevant
    document.querySelectorAll('.nav-btn').forEach(btn => {
        const r = btn.dataset.route;
        if (['files', 'crons', 'alerts'].includes(r)) btn.style.display = 'none';
        else btn.style.display = '';
    });

    navigate('dashboard');
}

function exitDemoMode() {
    isDemoMode = false;
    currentUser = null;
    currentWorkspace = null;
    agents = [];
    allTasks = [];
    jwtToken = null;
    localStorage.removeItem('crm_jwt');

    const banner = document.getElementById('demo-banner');
    if (banner) banner.style.display = 'none';

    // Restore all nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => btn.style.display = '');

    showInviteScreen();
}

// --- API Client ---
async function api(path, options = {}) {
    if (isDemoMode) return demoApi(path, options);
    const headers = { 'Content-Type': 'application/json', ...options.headers };
    if (jwtToken) headers['Authorization'] = `Bearer ${jwtToken}`;
    if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;

    let resp;
    try {
        resp = await fetch(`${API_BASE}${path}`, { ...options, headers });
    } catch (networkErr) {
        throw new ApiError('Network error — check your connection', 0, path);
    }

    if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        if (resp.status === 429) {
            const retry = resp.headers.get('Retry-After') || '30';
            throw new ApiError(`Too many requests. Try again in ${retry}s`, 429, path);
        }
        if (resp.status === 401) {
            throw new ApiError('Session expired — reopen the app', 401, path);
        }
        throw new ApiError(err.detail || `Server error (${resp.status})`, resp.status, path);
    }
    if (resp.status === 204) return null;
    return resp.json();
}

class ApiError extends Error {
    constructor(message, status, path) {
        super(message);
        this.status = status;
        this.path = path;
    }
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
            if (e.status === 403 && (e.message === 'invite_required' || e.message === 'invalid_invite')) {
                // New user needs invite code
                return { needs_invite: true };
            }
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
            // JWT expired/invalid — retry with initData
            if (tg?.initData) {
                try {
                    const retryResp = await api('/auth/telegram', {
                        method: 'POST',
                        body: JSON.stringify({ init_data: tg.initData }),
                    });
                    jwtToken = retryResp.access_token;
                    localStorage.setItem('crm_jwt', jwtToken);
                    currentUser = retryResp.user;
                    return retryResp.user;
                } catch (e2) {
                    if (e2.status === 403) return { needs_invite: true };
                }
            }
        }
    }

    // No auth at all — if we have initData, user needs invite
    if (tg?.initData) return { needs_invite: true };

    return null;
}

// --- Invite Code Screen ---
function showInviteScreen(errorMsg = '') {
    const overlay = document.getElementById('onboarding-overlay');
    const content = document.getElementById('onboarding-content');
    const nav = document.getElementById('bottom-nav');
    overlay.classList.remove('hidden');
    nav.style.display = 'none';

    content.innerHTML = `
        <div class="onboarding-step">
            <div class="onboarding-emoji">🔑</div>
            <div class="onboarding-title">Invite Only</div>
            <div class="onboarding-subtitle">
                AgentCRM is in closed beta.<br>
                Enter your invite code to get started.
            </div>
            <div class="onboarding-form">
                <div class="field">
                    <input type="text" id="invite-code-input"
                        placeholder="Enter invite code"
                        maxlength="16"
                        autocomplete="off"
                        autocapitalize="characters"
                        style="text-align:center; font-size:20px; letter-spacing:3px; text-transform:uppercase; font-weight:700;">
                </div>
                ${errorMsg ? `<div style="color:var(--error); font-size:13px; text-align:center; margin-bottom:12px;">${errorMsg}</div>` : ''}
            </div>
            <button class="onboarding-btn" id="invite-submit-btn" onclick="submitInviteCode()">Continue</button>
            <div style="margin-top:16px;">
                <button class="onboarding-btn demo-btn" onclick="enterDemoMode()" style="background:transparent; border:1px solid var(--border); color:var(--text-secondary); font-size:15px;">
                    🎮 Try Demo
                </button>
            </div>
            <div style="margin-top:16px; font-size:12px; color:var(--text-hint);">
                Don't have a code? Join our <a href="https://t.me/agentforgeai" style="color:var(--link);">Telegram</a> for updates.
            </div>
        </div>
    `;

    // Focus input
    setTimeout(() => {
        const input = document.getElementById('invite-code-input');
        if (input) input.focus();
    }, 300);

    // Enter key submit
    document.getElementById('invite-code-input')?.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') submitInviteCode();
    });
}

async function submitInviteCode() {
    const input = document.getElementById('invite-code-input');
    const btn = document.getElementById('invite-submit-btn');
    const code = input?.value?.trim();

    if (!code) {
        showInviteScreen('Please enter an invite code');
        return;
    }

    btn.disabled = true;
    btn.textContent = 'Checking...';

    try {
        // First validate
        const check = await api(`/auth/invites/check/${encodeURIComponent(code)}`);
        if (!check.valid) {
            showInviteScreen('Invalid or expired invite code');
            return;
        }

        // Now auth with invite code
        const authResp = await api('/auth/telegram', {
            method: 'POST',
            body: JSON.stringify({
                init_data: tg?.initData || '',
                invite_code: code,
            }),
        });

        jwtToken = authResp.access_token;
        localStorage.setItem('crm_jwt', jwtToken);
        currentUser = authResp.user;

        if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        showToast('Welcome to AgentCRM! 🎉', 'success', { duration: 3000 });

        // Continue to onboarding or dashboard
        hideOnboarding();
        if (!currentUser.onboarding_complete) {
            showOnboarding();
        } else {
            render();
        }
    } catch (e) {
        showInviteScreen(e.message || 'Something went wrong');
    }
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
                    <div class="onboarding-title">Connect Your Agents</div>
                    <div class="onboarding-subtitle">Link your AI agents to this dashboard</div>
                    <div class="onboarding-cards">
                        <div class="onboarding-card" id="ob-card-link" onclick="obGenerateLink()">
                            <div class="onboarding-card-icon">🔗</div>
                            <div class="onboarding-card-title">Generate Connect Link</div>
                            <div class="onboarding-card-desc">Copy link → paste in your agent config</div>
                        </div>
                        <div class="onboarding-card" id="ob-card-manual" onclick="showManualForm()">
                            <div class="onboarding-card-icon">✋</div>
                            <div class="onboarding-card-title">Add Manually</div>
                            <div class="onboarding-card-desc">Create agent cards by hand</div>
                        </div>
                    </div>
                    <div id="ob-form-area"></div>
                    ${agentListHTML}
                    <button class="onboarding-btn" onclick="onboardingNext()">Next</button>
                    ${onboardingAgents.length === 0 ? '<button class="onboarding-btn onboarding-btn-secondary" onclick="onboardingNext()">Skip for now</button>' : ''}
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
    // Legacy — redirect to generate link
    obGenerateLink();
};

window.obGenerateLink = async function() {
    const linkCard = document.getElementById('ob-card-link');
    const manualCard = document.getElementById('ob-card-manual');
    if (linkCard) linkCard.classList.add('active');
    if (manualCard) manualCard.classList.remove('active');
    const area = document.getElementById('ob-form-area');
    area.innerHTML = '<div style="text-align:center;padding:12px;color:var(--text-hint);">Generating link...</div>';
    try {
        const resp = await api('/connect/generate', { method: 'POST' });
        const promptText = `Connect to my AgentCRM dashboard using this link: ${resp.connect_url}`;
        area.innerHTML = `
            <div class="onboarding-form">
                <div style="text-align:center;margin-bottom:16px;">
                    <div style="font-size:15px;font-weight:600;margin-bottom:8px;">✅ Link Generated!</div>
                    <div style="font-size:13px;color:var(--text-hint);">Send this to your AI agent</div>
                </div>

                <div style="background:var(--card-bg);border:1px solid var(--border);border-radius:10px;padding:14px;margin-bottom:12px;">
                    <div style="font-size:12px;color:var(--text-hint);margin-bottom:6px;">📋 Copy and send to your agent:</div>
                    <div style="font-size:14px;line-height:1.5;color:var(--text);">${promptText}</div>
                </div>
                <button class="onboarding-btn" onclick="navigator.clipboard.writeText(\`${promptText}\`);this.textContent='✅ Copied!';setTimeout(()=>this.textContent='📋 Copy Message',2000)">📋 Copy Message</button>

                <div style="text-align:left;margin-top:20px;font-size:13px;line-height:1.7;color:var(--text-secondary);">
                    <div style="font-weight:600;margin-bottom:8px;color:var(--text);">How it works:</div>
                    <div>1️⃣ Tap <strong>Copy Message</strong> above</div>
                    <div>2️⃣ Paste it in a chat with your AI agent</div>
                    <div>3️⃣ Your agent will connect automatically</div>
                    <div style="margin-top:10px;font-size:12px;color:var(--text-hint);">⏱ Link expires in 24 hours · One-time use</div>
                </div>
            </div>
        `;
    } catch(e) {
        area.innerHTML = '<div style="color:var(--error);text-align:center;padding:12px;">' + e.message + '</div>';
    }
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
        showToast(e.message, 'error', { title: 'Connection failed' });
    }
};

window.addManualAgent = async function() {
    const name = document.getElementById('ob-agent-name')?.value?.trim();
    const emoji = document.getElementById('ob-agent-emoji')?.value?.trim() || '🤖';
    const model = document.getElementById('ob-agent-model')?.value?.trim() || '';
    const role = document.getElementById('ob-agent-role')?.value?.trim() || '';

    if (!name) { showToast('Agent name is required', 'warning');  return; }

    try {
        const created = await api('/agents', {
            method: 'POST',
            body: JSON.stringify({ name, emoji, model, role }),
        });
        onboardingAgents.push(created);
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        renderOnboardingStep();
    } catch (e) {
        showToast(e.message, 'error', { title: 'Failed to add agent' });
    }
};

window.onboardingCreateTask = async function() {
    const title = document.getElementById('ob-task-title')?.value?.trim();
    if (!title) { showToast('Task title is required', 'warning');  return; }

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
        showToast(e.message, 'error', { title: 'Failed to save task' });
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
    const titles = { dashboard: 'Dashboard', kanban: 'Task Board', agents: 'Agents', crons: 'Crons', files: 'Files', journal: 'Journal', alerts: 'Alerts', admin: 'Admin Panel' };
    document.getElementById('page-title').textContent = titles[currentRoute] || 'Agent CRM';
    updateHeaderTier();
    // Show/hide admin tab
    const adminBtn = document.getElementById('nav-admin');
    if (adminBtn) {
        adminBtn.style.display = (currentUser?.is_superadmin && !isDemoMode) ? '' : 'none';
    }
}

document.querySelectorAll('.nav-btn').forEach(btn => {
    btn.addEventListener('click', () => navigate(btn.dataset.route));
});
window.addEventListener('hashchange', () => {
    const hash = window.location.hash.slice(1) || 'dashboard';
    if (hash !== currentRoute) { currentRoute = hash; updateNav(); render(); }
});

// --- Prevent Telegram pull-to-close on scroll ---
(function() {
    let startY = 0;
    document.addEventListener('touchstart', (e) => {
        startY = e.touches[0].clientY;
    }, { passive: true });

    document.addEventListener('touchmove', (e) => {
        const wrapper = document.querySelector('.app-content-wrapper') || document.getElementById('app');
        const scrollTop = wrapper ? wrapper.scrollTop : 0;
        const dy = e.touches[0].clientY - startY;
        // If at top and pulling down, prevent default (stops TG close)
        if (scrollTop <= 0 && dy > 0) {
            e.preventDefault();
        }
    }, { passive: false });
})();

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
            case 'admin': await renderAdmin(content); break;
            default: content.innerHTML = '<div class="empty-state"><p>Not found</p></div>';
        }
    } catch (err) {
        const isNetwork = err.status === 0 || !navigator.onLine;
        const isAuth = err.status === 401;
        const icon = isNetwork ? '📡' : isAuth ? '🔒' : '⚠️';
        const hint = isNetwork ? 'Check your internet connection'
            : isAuth ? 'Your session expired — reopen the app'
            : 'Something went wrong';
        content.innerHTML = `<div class="empty-state empty-state-error">
            <div class="empty-icon">${icon}</div>
            <p>${hint}</p>
            <button class="btn-retry" onclick="render()">🔄 Retry</button>
        </div>`;
        showToast(err.message, 'error');
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
        api('/spending/current').catch(() => ({ today: 0, month: 0, plan: 'Pro', window_hours: 5, usage: { all: { used: 0, limit: 44000, pct: 0 }, models: [] }, agents: [] })),
        api('/spending/timeline?range=day').catch(() => ({ labels: [], data: [] })),
        api('/spending/timeline?range=week').catch(() => ({ labels: [], data: [] })),
        api('/spending/sessions').catch(() => []),
    ]);
    agents = data.agents;

    const costLabel = periodFilter === 'today' ? 'Today' : periodFilter === 'week' ? 'This Week' : periodFilter === 'month' ? 'This Month' : 'Total';
    const taskLabel = periodFilter === 'all' ? 'Active Tasks' : `Tasks (${periodFilter})`;
    const statusIcon = sysStatus.gateway ? '🟢' : '🔴';
    const statusText = sysStatus.gateway ? 'Running' : 'Stopped';

    // Dual rate limits like Anthropic
    const w = spending.weekly || { pct: 0, resets_in_minutes: 0, models: [] };
    const s = spending.session || { pct: 0, resets_in_minutes: 0, models: [] };
    const wPct = Math.min(100, w.pct || 0).toFixed(1);
    const sPct = Math.min(100, s.pct || 0).toFixed(1);
    const fmtReset = (min, isWeekly) => {
        if (min === null || min === undefined) return '';
        if (min <= 0) return 'Resetting soon';
        const h = Math.floor(min / 60), m = min % 60;
        if (isWeekly && h > 24) {
            // Show as day + time for weekly (e.g. "Resets Sat 7:59 PM")
            const resetDate = new Date(Date.now() + min * 60000);
            const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
            let hrs = resetDate.getHours(), ampm = hrs >= 12 ? 'PM' : 'AM';
            hrs = hrs % 12 || 12;
            const mins = String(resetDate.getMinutes()).padStart(2, '0');
            return `Resets ${days[resetDate.getDay()]} ${hrs}:${mins} ${ampm}`;
        }
        return h > 0 ? `Resets in ${h}hr ${m}min` : `Resets in ${m}min`;
    };
    const modelColors = {'claude-opus-4-6':'#8B5CF6','claude-sonnet-4-6':'#3B82F6','claude-haiku-35-20241022':'#10B981','unknown':'#6B7280'};
    const autoColor = (m, i) => modelColors[m] || ['#F59E0B','#EF4444','#EC4899','#14B8A6'][i % 4];

    const renderModels = (models) => (models || []).map((m, i) => {
        const color = autoColor(m.model, i);
        const barW = Math.min(100, m.pct || 0);
        const shortName = m.model.replace('claude-', '').replace('-20241022', '');
        return `<div class="model-row">
            <div class="model-info">
                <span class="model-dot" style="background:${color}"></span>
                <span class="model-name">${shortName}</span>
                <span class="model-pct">${m.pct.toFixed(1)}%</span>
            </div>
            <div class="progress-track model-track"><div class="progress-fill" style="width:${barW}%;background:${color}"></div></div>
            <div class="model-meta">$${m.cost.toFixed(2)} · ${m.messages} msgs</div>
        </div>`;
    }).join('');

    const hasOpenClaw = sysStatus.gateway === true && sysStatus.status !== 'not_configured';
    const dashStatusIcon = sysStatus.status === 'not_configured' ? '🔗' : statusIcon;
    const dashStatusText = sysStatus.status === 'not_configured' ? 'Remote' : statusText;

    el.innerHTML = `
        <div class="system-bar">
            <span class="sys-status">${dashStatusIcon} ${dashStatusText}</span>
            <div class="sys-actions">
                <button class="btn-sm btn-danger-sm" onclick="systemAction('stop')">⏹ Stop</button>
                <button class="btn-sm btn-success-sm" onclick="systemAction('resume')">▶ Resume</button>
            </div>
        </div>
        ${hasOpenClaw ? `<div class="budget-bar">
            <div class="budget-header">
                <span class="budget-plan">${spending.plan || 'Pro'} Plan</span>
            </div>
            <div class="limit-section">
                <div class="limit-header">
                    <span class="limit-label">Weekly session: ${wPct}%</span>
                    <span class="limit-reset">${fmtReset(w.resets_in_minutes, true)}</span>
                </div>
                <div class="progress-track"><div class="progress-fill ${wPct > 90 ? 'progress-danger' : wPct > 80 ? 'progress-warn' : ''}" style="width:${wPct}%"></div></div>
            </div>
            <div class="limit-section">
                <div class="limit-header">
                    <span class="limit-label">Current session: ${sPct}%</span>
                    <span class="limit-reset">${fmtReset(s.resets_in_minutes)}</span>
                </div>
                <div class="progress-track"><div class="progress-fill progress-session ${sPct > 90 ? 'progress-danger' : sPct > 80 ? 'progress-warn' : ''}" style="width:${sPct}%"></div></div>
            </div>
            <div class="budget-meta">
                <span class="budget-tag">📅 Today: $${spending.today.toFixed(2)}</span>
                <span class="budget-tag">📆 Month: $${(spending.month||0).toFixed(2)}</span>
            </div>` : ''}
            ${hasOpenClaw && w.models?.length ? `<div class="section-label">Weekly by model</div><div class="model-breakdown">${renderModels(w.models)}</div>` : ''}
            ${hasOpenClaw && s.models?.length ? `<div class="section-label">Session by model</div><div class="model-breakdown">${renderModels(s.models)}</div>` : ''}
        ${hasOpenClaw ? '</div>' : ''}
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
        ${dailyTimeline.labels.length ? `
        <div class="section-header">Today (hourly)</div>
        <div class="chart-container"><canvas id="dash-daily-chart"></canvas></div>
        <div class="section-header">This Week (daily)</div>
        <div class="chart-container"><canvas id="dash-weekly-chart"></canvas></div>` : ''}
        ${sessions.length ? `
        <div class="section-header">Sessions</div>
        <div class="sessions-list">
            ${sessions.map(s => {
                const agentEmoji = agents.find(a => a.name?.toLowerCase() === s.agent?.toLowerCase())?.emoji || '🤖';
                const maxCost = Math.max(...sessions.map(x => x.cost), 1);
                const barPct = Math.min(100, (s.cost / maxCost) * 100);
                const barColor = s.cost > 10 ? 'var(--error)' : s.cost > 5 ? 'var(--warning)' : 'var(--success)';
                const lastActive = s.last_active ? timeAgo(s.last_active) : '';
                return `<div class="card session-card">
                    <div class="session-top">
                        <span class="session-agent">${agentEmoji} ${s.agent}</span>
                        <span class="session-cost">$${s.cost.toFixed(2)}</span>
                    </div>
                    <div class="session-bar-track">
                        <div class="session-bar-fill" style="width:${barPct}%;background:${barColor}"></div>
                    </div>
                    <div class="session-bottom">
                        <span class="session-msgs">💬 ${s.messages}</span>
                        ${lastActive ? `<span class="session-time">${lastActive}</span>` : ''}
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
        const result = await api(`/system/${action}`, { method: 'POST' });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        if (result.queued) {
            showToast('Command queued — will apply within ~1 minute', 'success');
        }
        render();
    } catch (err) { showToast(err.message, 'error'); }
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
            // Expand toggle button — don't open modal
            if (e.target.closest('.kanban-expand-btn')) {
                card.classList.toggle('expanded');
                const btn = card.querySelector('.kanban-expand-btn');
                if (btn) btn.textContent = card.classList.contains('expanded') ? 'less ↑' : 'more ↓';
                if (tg) tg.HapticFeedback?.impactOccurred('light');
                return;
            }
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

    const descPreview = t.description
        ? `<div class="kanban-desc">${escapeHtml(t.description)}</div>${t.description.length > 60 ? '<div class="kanban-expand-btn">more ↓</div>' : ''}`
        : '';

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
    let pendingCommands = [];
    [agents, availableModels, pendingCommands] = await Promise.all([
        api('/agents'),
        api('/agents/models').catch(() => ['claude-opus-4-6', 'claude-sonnet-4-6', 'claude-haiku-35-20241022']),
        api('/commands/pending').catch(() => []),
    ]);

    // Build set of agent names with pending model changes
    const pendingAgentNames = new Set();
    for (const cmd of pendingCommands) {
        if (cmd.command_type === 'change_model') {
            try {
                const p = typeof cmd.payload === 'string' ? JSON.parse(cmd.payload) : cmd.payload;
                if (p.agent_name) pendingAgentNames.add(p.agent_name);
            } catch(e) {}
        }
    }

    // Check restart status
    const restartStatus = await api('/agents/restart-status').catch(() => ({ restart_pending: false }));
    const restartBanner = restartStatus.restart_pending
        ? `<div class="card restart-banner" onclick="restartGateway()">
            <span>⚠️ Config changed — tap to restart gateway</span>
        </div>`
        : '';

    const tier = currentUser?.tier || currentWorkspace?.tier || 'hobby';
    const agentLimit = currentWorkspace?.agent_limit || 3;
    const pendingCount = pendingCommands.length;
    const pendingInfo = pendingCount > 0
        ? `<div class="pending-commands-info">⏳ ${pendingCount} pending command${pendingCount > 1 ? 's' : ''} awaiting sync</div>`
        : '';
    const limitInfo = `<div class="agent-limit-info">🤖 ${agents.length}/${agentLimit} agents (${tier.charAt(0).toUpperCase() + tier.slice(1)})</div>`;

    // Connect Remote Agent section (all users)
    let connectSection = '';
    {
        const pendingTokens = await api('/connect/status').catch(() => []);
        const redeemedData = await api('/connect/has-redeemed').catch(() => ({ has_redeemed: false }));
        const hasRedeemed = redeemedData.has_redeemed;
        const pendingHtml = pendingTokens.length
            ? pendingTokens.map(t => {
                const exp = new Date(t.expires);
                const remaining = Math.max(0, Math.round((exp - Date.now()) / 60000));
                const hrs = Math.floor(remaining / 60);
                const mins = remaining % 60;
                return `<div class="connect-token-item">
                    <div class="connect-token-info">
                        <code class="connect-token-preview">${t.token.slice(0, 12)}…</code>
                        <span class="connect-token-expiry">⏳ ${hrs}h ${mins}m left</span>
                    </div>
                    <div class="connect-token-actions">
                        <button class="btn-sm btn-copy" onclick="copyConnectUrl('${t.connect_url}', this)">📋 Copy</button>
                    </div>
                </div>`;
            }).join('')
            : '<div class="connect-empty">No pending connections</div>';

        connectSection = `
            <div class="card connect-section">
                <div class="connect-header">
                    <span class="connect-title">🔗 Remote Agents</span>
                    <button class="btn-sm btn-accent" onclick="generateConnectLink()">+ New Link</button>
                </div>
                <div id="connect-result" class="connect-result hidden"></div>
                <div class="connect-pending">${pendingHtml}</div>
            </div>
            ${!hasRedeemed ? `<div class="card">
                <div class="card-title">🎮 Remote Control</div>
                <p style="color:var(--text-dim);font-size:13px;">Enable model changes and system controls from this dashboard.</p>
                <button class="btn-primary" onclick="copySetupMessage()">📋 Copy Setup Message</button>
                <p style="color:var(--text-dim);font-size:12px;margin-top:8px;">Send the copied message to your AI agent to set up sync.</p>
            </div>` : ''}`;
    }

    el.innerHTML = restartBanner + pendingInfo + limitInfo + connectSection + (agents.length
        ? '<div class="agents-grid">' + agents.map(a => `<div class="card agent-card-full">
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
                    <div style="display:flex;gap:8px;align-items:center;">
                        <select class="agent-model-select" id="model-select-${a.id}" data-agent-id="${a.id}" data-original="${a.model || ''}" onchange="onModelDropdownChange(${a.id})">
                            ${availableModels.map(m => `<option value="${m}" ${a.model === m ? 'selected' : ''}>${m.split('/').pop()}</option>`).join('')}
                            ${a.model && !availableModels.includes(a.model) ? `<option value="${a.model}" selected>${a.model.split('/').pop()}</option>` : ''}
                        </select>
                        <span id="pending-badge-${a.id}" class="pending-badge" style="display:${pendingAgentNames.has(a.name) ? 'inline-block' : 'none'};">⏳ pending</span>
                    </div>
                </div>
                <div class="agent-meta-row">
                    <span>Last active: ${a.last_active ? timeAgo(a.last_active) : 'never'}</span>
                    <span>Cost: <strong style="color:var(--text);font-size:13px">$${a.daily_cost.toFixed(2)}</strong>/day</span>
                </div>
            </div>
        </div>`).join('') + '</div>'
        : `<div class="empty-state">
            <div class="empty-icon">🤖</div>
            <p>No agents yet</p>
            <p style="font-size:13px;color:var(--text-hint);margin-top:4px;">Add agents to start managing your AI team</p>
            <div style="display:flex;flex-direction:column;gap:10px;margin-top:16px;width:100%;max-width:280px;">
                <button class="onboarding-btn" onclick="showAddAgentModal()">+ Add Agent Manually</button>
                <button class="onboarding-btn onboarding-btn-secondary" onclick="rerunOnboarding()">🔄 Re-run Setup Wizard</button>
            </div>
        </div>`);
}

window.onModelDropdownChange = function(agentId) {
    const select = document.getElementById(`model-select-${agentId}`);
    if (!select) return;
    const model = select.value;
    const original = select.dataset.original;
    if (model === original) return;

    const modelShort = model.split('/').pop();
    const agent = agents.find(a => a.id === agentId);
    const agentName = agent?.name || 'Agent';

    showConfirmDialog(
        `Change <strong>${agentName}</strong> model to <strong>${modelShort}</strong>?<br><small style="color:var(--text-dim)">Change will apply automatically within ~1 minute.</small>`,
        async () => {
            try {
                await api(`/agents/${agentId}`, {
                    method: 'PATCH',
                    body: JSON.stringify({ model }),
                });
                if (tg) tg.HapticFeedback?.notificationOccurred('success');
                showToast('Model change queued — will apply within ~1 minute', 'success');
                select.dataset.original = model;
                const badge = document.getElementById(`pending-badge-${agentId}`);
                if (badge) {
                    badge.style.display = 'inline-block';
                    badge.textContent = '⏳ pending';
                    badge.className = 'pending-badge';
                }
                pollCommandStatus(agentId);
            } catch (err) {
                showToast(err.message, 'error');
                select.value = original;
            }
        },
        () => {
            // Cancel — revert dropdown
            select.value = original;
        }
    );
};

// --- Confirmation Dialog ---
function showConfirmDialog(message, onConfirm, onCancel) {
    // Remove existing overlay if any
    document.getElementById('confirm-overlay')?.remove();

    const overlay = document.createElement('div');
    overlay.id = 'confirm-overlay';
    overlay.className = 'confirm-overlay';
    overlay.innerHTML = `
        <div class="confirm-card">
            <div class="confirm-text">${message}</div>
            <div class="confirm-actions">
                <button class="confirm-btn confirm-btn-cancel" id="confirm-cancel">Cancel</button>
                <button class="confirm-btn confirm-btn-primary" id="confirm-ok">Confirm</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);

    const close = () => overlay.remove();

    overlay.querySelector('#confirm-cancel').addEventListener('click', () => { close(); if (onCancel) onCancel(); });
    overlay.querySelector('#confirm-ok').addEventListener('click', () => {
        close();
        onConfirm();
    });
    // Close on overlay click (outside card)
    overlay.addEventListener('click', (e) => {
        if (e.target === overlay) { close(); if (onCancel) onCancel(); }
    });
}

// --- Poll command status after model change ---
function pollCommandStatus(agentId) {
    const agent = agents.find(a => a.id === agentId);
    const agentName = agent?.name;
    if (!agentName) return;

    const POLL_INTERVAL = 5000; // 5 seconds
    const MAX_POLL_TIME = 3 * 60 * 1000; // 3 minutes
    const HINT_TIME = 2 * 60 * 1000; // 2 minutes
    const startTime = Date.now();
    let pollTimer = null;
    let hintShown = false;

    async function checkStatus() {
        if (Date.now() - startTime > MAX_POLL_TIME) {
            // Timeout — stop polling
            clearInterval(pollTimer);
            return;
        }

        // Show hint after 2 minutes of waiting
        if (!hintShown && Date.now() - startTime > HINT_TIME) {
            hintShown = true;
            showToast("Command still pending. If you haven't set up sync yet, copy the setup message from the Agents page → Remote Control section.", 'info', { duration: 10000 });
        }

        try {
            const pending = await api('/commands/pending');
            const hasPending = pending.some(cmd => {
                if (cmd.command_type !== 'change_model') return false;
                try {
                    const p = typeof cmd.payload === 'string' ? JSON.parse(cmd.payload) : cmd.payload;
                    return p.agent_name === agentName;
                } catch { return false; }
            });

            if (!hasPending) {
                // Command resolved — check if applied or failed
                clearInterval(pollTimer);

                // Determine status by fetching all commands (not just pending)
                // If it disappeared from pending, it was either applied or failed
                // We assume applied unless we can check — show success
                const badge = document.getElementById(`pending-badge-${agentId}`);
                if (badge) {
                    badge.textContent = '✅ applied';
                    badge.className = 'cmd-badge-applied';
                    badge.style.display = 'inline-block';
                    setTimeout(() => {
                        badge.style.display = 'none';
                        badge.textContent = '⏳ pending';
                        badge.className = 'pending-badge';
                    }, 5000);
                }
            }
        } catch (err) {
            // Silently ignore poll errors
        }
    }

    pollTimer = setInterval(checkStatus, POLL_INTERVAL);
}

window.showAddAgentModal = function() {
    const modal = document.getElementById('modal-overlay');
    const form = document.getElementById('task-form');
    const title = document.getElementById('modal-title');
    // Repurpose task modal for quick agent add
    title.textContent = 'Add Agent';
    form.innerHTML = `
        <div class="field">
            <label for="new-agent-name">Name</label>
            <input type="text" id="new-agent-name" required placeholder="e.g. Caramel">
        </div>
        <div class="field">
            <label for="new-agent-emoji">Emoji</label>
            <input type="text" id="new-agent-emoji" placeholder="🤖" maxlength="4" style="width:60px;">
        </div>
        <div class="field">
            <label for="new-agent-role">Role</label>
            <input type="text" id="new-agent-role" placeholder="e.g. Lead Coordinator">
        </div>
        <div class="modal-actions">
            <button type="button" class="btn btn-primary" onclick="submitNewAgent()">Create Agent</button>
        </div>
    `;
    modal.classList.remove('hidden');
};

window.submitNewAgent = async function() {
    const name = document.getElementById('new-agent-name')?.value?.trim();
    const emoji = document.getElementById('new-agent-emoji')?.value?.trim() || '🤖';
    const role = document.getElementById('new-agent-role')?.value?.trim() || '';
    if (!name) { showToast('Name is required', 'error'); return; }
    try {
        await api('/agents', { method: 'POST', body: JSON.stringify({ name, emoji, role, model: 'claude-sonnet-4-6', status: 'idle' }) });
        closeModal();
        showToast('Agent created!', 'success');
        render();
    } catch (e) { showToast(e.message, 'error'); }
};

window.rerunOnboarding = async function() {
    try {
        await api('/auth/onboarding-complete', { method: 'POST', body: JSON.stringify({ complete: false }) });
    } catch(e) { /* ignore */ }
    onboardingStep = 1;
    onboardingAgents = [];
    showOnboarding();
};

window.generateConnectLink = async function() {
    const resultEl = document.getElementById('connect-result');
    if (!resultEl) return;
    resultEl.classList.remove('hidden');
    resultEl.innerHTML = '<span class="connect-loading">Generating…</span>';
    try {
        const data = await api('/connect/generate', { method: 'POST' });
        const exp = new Date(data.expires);
        resultEl.innerHTML = `
            <div class="connect-new-link">
                <div class="connect-label">Send this link to your agent:</div>
                <div class="connect-url-row">
                    <input type="text" class="connect-url-input" value="${data.connect_url}" readonly onclick="this.select()">
                    <button class="btn-sm btn-copy" onclick="copyConnectUrl('${data.connect_url}', this)">📋</button>
                </div>
                <div class="connect-meta">Expires: ${exp.toLocaleString()}</div>
            </div>`;
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
    } catch (err) {
        resultEl.innerHTML = `<span class="connect-error">❌ ${err.message}</span>`;
    }
};

window.copySetupMessage = async function() {
    try {
        const data = await api(`/setup/message`);
        // Show modal with selectable text (clipboard blocked in TG WebView)
        const overlay = document.createElement('div');
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:9999;display:flex;align-items:center;justify-content:center;padding:16px';
        overlay.innerHTML = `
            <div style="background:var(--card);border-radius:12px;padding:16px;max-width:90vw;max-height:80vh;overflow-y:auto;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
                    <span style="font-weight:600;font-size:15px;">📋 Setup Message</span>
                    <button onclick="this.closest('div[style*=fixed]').remove()" style="background:none;border:none;color:var(--text);font-size:20px;cursor:pointer;">✕</button>
                </div>
                <p style="color:var(--text-dim);font-size:12px;margin-bottom:8px;">Long-press to select & copy, then send to your AI agent:</p>
                <div style="background:var(--bg);border-radius:8px;padding:12px;font-size:13px;line-height:1.5;user-select:text;-webkit-user-select:text;word-break:break-all;">${data.message}</div>
            </div>
        `;
        overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
        document.body.appendChild(overlay);
        if (tg) tg.HapticFeedback?.impactOccurred('light');
    } catch (err) {
        showToast('Failed to load: ' + err.message, 'error');
    }
};

window.copyConnectUrl = async function(url, btnEl) {
    try {
        await navigator.clipboard.writeText(url);
        const orig = btnEl.textContent;
        btnEl.textContent = '✅';
        if (tg) tg.HapticFeedback?.impactOccurred('light');
        setTimeout(() => { btnEl.textContent = orig; }, 1500);
    } catch {
        // Fallback for Telegram WebApp
        const input = document.createElement('input');
        input.value = url;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        const orig = btnEl.textContent;
        btnEl.textContent = '✅';
        setTimeout(() => { btnEl.textContent = orig; }, 1500);
    }
};

window.restartGateway = async function() {
    if (!confirm('Restart OpenClaw gateway? Agents will be briefly unavailable (~3 sec).')) return;
    try {
        await api('/agents/restart', { method: 'POST' });
        if (tg) tg.HapticFeedback?.notificationOccurred('success');
        render();
    } catch (err) {
        showToast(err.message, 'error', { title: 'Restart failed' });
    }
};

// --- Alerts ---
async function renderAlerts(el) {
    const [alerts, sysStatus, spending, timeline, dailyTimeline] = await Promise.all([
        api('/alerts'),
        api('/system/status').catch(() => ({ status: 'unknown', gateway: false })),
        api('/spending/current').catch(() => ({ today: 0, month: 0, plan: 'Pro', window_hours: 5, usage: { all: { used: 0, limit: 44000, pct: 0 }, models: [] }, agents: [] })),
        api('/spending/timeline?range=week').catch(() => ({ labels: [], data: [] })),
        api('/spending/timeline?range=day').catch(() => ({ labels: [], data: [] })),
    ]);

    const statusIcon = sysStatus.gateway ? '🟢' : '🔴';
    const aw = spending.weekly || { pct: 0 };
    const as2 = spending.session || { pct: 0 };
    const awPct = Math.min(100, aw.pct || 0).toFixed(1);
    const asPct = Math.min(100, as2.pct || 0).toFixed(1);

    const alertHasOpenClaw = sysStatus.gateway === true && sysStatus.status !== 'not_configured';
    const alertStatusIcon = sysStatus.status === 'not_configured' ? '🔗' : statusIcon;
    const alertStatusText = sysStatus.status === 'not_configured' ? 'Remote' : (sysStatus.gateway ? 'Running' : 'Stopped');

    el.innerHTML = `
        <div class="system-bar">
            <span class="sys-status">${alertStatusIcon} ${alertStatusText}</span>
            <div class="sys-actions">
                <button class="btn-sm btn-danger-sm" onclick="systemAction('stop')">⏹ Stop</button>
                <button class="btn-sm btn-success-sm" onclick="systemAction('resume')">▶ Resume</button>
                <button class="btn-sm btn-fix-sm" onclick="systemFix()">🔧 Fix</button>
            </div>
        </div>
        ${alertHasOpenClaw ? `<div class="budget-bar">
            <div class="limit-section">
                <div class="limit-header"><span class="limit-label">Weekly: ${awPct}%</span></div>
                <div class="progress-track"><div class="progress-fill ${awPct > 90 ? 'progress-danger' : awPct > 80 ? 'progress-warn' : ''}" style="width:${awPct}%"></div></div>
            </div>
            <div class="limit-section">
                <div class="limit-header"><span class="limit-label">Session: ${asPct}%</span></div>
                <div class="progress-track"><div class="progress-fill progress-session ${asPct > 90 ? 'progress-danger' : asPct > 80 ? 'progress-warn' : ''}" style="width:${asPct}%"></div></div>
            </div>
            <div class="budget-meta">
                <span class="budget-tag">📅 Today: $${spending.today.toFixed(2)}</span>
                <span class="budget-tag">📆 Month: $${(spending.month||0).toFixed(2)}</span>
            </div>
        </div>` : ''}
        ${dailyTimeline.labels.length ? `
        <div class="section-header">Today (hourly)</div>
        <div class="chart-container"><canvas id="alerts-daily-chart"></canvas></div>
        <div class="section-header">Spending (7 days)</div>
        <div class="chart-container"><canvas id="spending-chart"></canvas></div>` : `
        ${sysStatus.status === 'not_configured' ? '<div class="empty-state" style="margin:16px 0"><div class="empty-icon">⚙️</div><p>Spending charts available when OpenClaw is connected.</p></div>' : ''}
        `}
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
        if (result.queued) {
            showToast('Fix command queued — will apply within ~1 minute', 'success');
        } else {
            let msg = '🔧 Fix applied:\n';
            msg += `Sessions cleared: ${result.cleared_sessions.length}\n`;
            msg += `Crons paused: ${result.paused_crons.length}\n`;
            if (Object.keys(result.spending_last_hour || {}).length) {
                msg += '\nSpending (last hour):\n';
                for (const [agent, data] of Object.entries(result.spending_last_hour)) {
                    msg += `  ${agent}: $${data.cost} (${data.messages} msgs)\n`;
                }
            }
            showToast(msg, 'success', { title: 'System action' });
        }
        render();
    } catch (err) { showToast(err.message, 'error'); }
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
    } catch (err) { showToast(err.message, 'error'); }
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
    } catch (err) { showToast(err.message, 'error'); }
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
        showToast(`Imported ${result.imported} entries`, 'success');
        render();
    } catch (err) {
        showToast(err.message, 'error', { title: 'Import failed' });
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
        } catch (err) { showToast(err.message, 'error'); }
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
        ? '<div class="crons-grid">' + crons.map(c => {
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
        }).join('') + '</div>'
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
        showToast(err.message, 'error');
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

    if (!files || files.length === 0) {
        el.innerHTML = `<div class="empty-state">
            <div class="empty-icon">📁</div>
            <p>No agent files available</p>
            <p style="font-size:13px;color:var(--text-hint);margin-top:4px;">Connect OpenClaw to view agent workspaces.</p>
        </div>`;
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
    } catch (err) { showToast(err.message, 'error'); }
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

// ============================================
//  ADMIN PANEL (superadmin only)
// ============================================

async function renderAdmin(el) {
    if (!currentUser?.is_superadmin) {
        el.innerHTML = '<div class="empty-state"><div class="empty-icon">🔒</div><p>Access denied</p></div>';
        return;
    }

    el.innerHTML = '<div class="loading">Loading admin data...</div>';

    let stats, users, workspaces, invites;
    try {
        [stats, users, workspaces, invites] = await Promise.all([
            api('/admin/stats'),
            api('/admin/users'),
            api('/admin/workspaces'),
            api('/admin/invites'),
        ]);
    } catch (err) {
        el.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><p>Failed to load admin data: ${escapeHtml(err.message)}</p></div>`;
        return;
    }

    el.innerHTML = `
        <!-- Stats Cards -->
        <div class="admin-stats-grid">
            <div class="card admin-stat-card">
                <div class="admin-stat-value">${stats.total_users}</div>
                <div class="admin-stat-label">Users</div>
            </div>
            <div class="card admin-stat-card">
                <div class="admin-stat-value">${stats.total_workspaces}</div>
                <div class="admin-stat-label">Workspaces</div>
            </div>
            <div class="card admin-stat-card">
                <div class="admin-stat-value">${stats.total_agents}</div>
                <div class="admin-stat-label">Agents</div>
            </div>
            <div class="card admin-stat-card">
                <div class="admin-stat-value">${stats.total_tasks}</div>
                <div class="admin-stat-label">Tasks</div>
            </div>
        </div>

        <!-- Invites Summary -->
        <div class="admin-invite-summary" style="margin-bottom:16px;">
            <span class="admin-tag admin-tag-green">🎟️ ${stats.invites_remaining} invites remaining</span>
            <span class="admin-tag admin-tag-dim">${stats.invites_used} used</span>
            <button class="btn btn-sm btn-primary" onclick="adminCreateInvite()" style="margin-left:auto;">+ New Invite</button>
        </div>

        <!-- Users Table -->
        <div class="section-header">Users (${users.length})</div>
        <div class="admin-table-wrap">
            <table class="admin-table">
                <thead><tr>
                    <th>ID</th><th>Name</th><th>TG ID</th><th>Created</th><th>Workspaces</th><th>Onboarding</th><th></th>
                </tr></thead>
                <tbody>
                    ${users.map(u => `<tr>
                        <td>${u.id}</td>
                        <td>${escapeHtml(u.name)} ${u.is_superadmin ? '<span class="admin-badge">👑</span>' : ''}</td>
                        <td class="mono">${u.telegram_id || '—'}</td>
                        <td>${u.created ? new Date(u.created).toLocaleDateString() : '—'}</td>
                        <td>${u.workspaces_count}</td>
                        <td>${u.onboarding_complete ? '✅' : '⏳'}</td>
                        <td>${!u.is_superadmin ? `<button class="btn btn-xs btn-danger" onclick="adminDeleteUser(${u.id}, '${escapeHtml(u.name)}')">Delete</button>` : ''}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>

        <!-- Workspaces Table -->
        <div class="section-header" style="margin-top:20px;">Workspaces (${workspaces.length})</div>
        <div class="admin-table-wrap">
            <table class="admin-table">
                <thead><tr>
                    <th>ID</th><th>Name</th><th>Owner</th><th>Tier</th><th>Agents</th><th>Created</th>
                </tr></thead>
                <tbody>
                    ${workspaces.map(ws => `<tr>
                        <td>${ws.id}</td>
                        <td>${escapeHtml(ws.name)}</td>
                        <td>${escapeHtml(ws.owner_name)}</td>
                        <td><span class="tier-badge tier-${ws.tier}">${ws.tier}</span></td>
                        <td>${ws.agent_count}</td>
                        <td>${ws.created ? new Date(ws.created).toLocaleDateString() : '—'}</td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>

        <!-- Invite Codes Table -->
        <div class="section-header" style="margin-top:20px;">Invite Codes (${invites.length})</div>
        <div class="admin-table-wrap">
            <table class="admin-table">
                <thead><tr>
                    <th>Code</th><th>Uses</th><th>Note</th><th>Created</th><th>Status</th><th></th>
                </tr></thead>
                <tbody>
                    ${invites.map(inv => `<tr>
                        <td class="mono">${inv.code}</td>
                        <td>${inv.use_count}/${inv.max_uses}</td>
                        <td>${escapeHtml(inv.note)}</td>
                        <td>${inv.created ? new Date(inv.created).toLocaleDateString() : '—'}</td>
                        <td><span class="admin-tag ${inv.status === 'active' ? 'admin-tag-green' : 'admin-tag-dim'}">${inv.status}</span></td>
                        <td><button class="btn btn-xs btn-danger" onclick="adminDeleteInvite(${inv.id})">🗑️</button></td>
                    </tr>`).join('')}
                </tbody>
            </table>
        </div>
    `;
}

window.adminDeleteUser = async function(userId, name) {
    if (!confirm(`Delete user "${name}" and all their data? This cannot be undone.`)) return;
    try {
        await api(`/admin/users/${userId}`, { method: 'DELETE' });
        showToast(`User ${name} deleted`, 'success');
        render();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

window.adminDeleteInvite = async function(inviteId) {
    if (!confirm('Delete this invite code?')) return;
    try {
        await api(`/admin/invites/${inviteId}`, { method: 'DELETE' });
        showToast('Invite deleted', 'success');
        render();
    } catch (err) {
        showToast(err.message, 'error');
    }
};

window.adminCreateInvite = async function() {
    const maxUses = prompt('Max uses for this invite code:', '5');
    if (!maxUses) return;
    const note = prompt('Note (optional):', '') || '';
    try {
        const result = await api('/admin/invites', {
            method: 'POST',
            body: JSON.stringify({ max_uses: parseInt(maxUses) || 1, note }),
        });
        showToast(`Invite created: ${result.code}`, 'success', { duration: 8000 });
        render();
    } catch (err) {
        showToast(err.message, 'error');
    }
};


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
        // No Telegram WebApp context — browser visitor → demo mode immediately
        // tg object exists even in browsers (script always loads), so check initData
        if (!tg?.initData && !jwtToken) {
            enterDemoMode();
            return;
        }

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

        // Auth failed and no Telegram — demo mode (e.g. expired JWT was cleared)
        if (!user && !tg?.initData) {
            enterDemoMode();
            return;
        }

        // Check if invite is needed
        if (user && user.needs_invite) {
            // Check for deep link invite code in hash: #invite=CODE
            const hashInvite = window.location.hash.match(/invite=([A-Za-z0-9]+)/);
            if (hashInvite) {
                // Auto-fill and try the code
                window.location.hash = '';
                showInviteScreen();
                const input = document.getElementById('invite-code-input');
                if (input) input.value = hashInvite[1];
            } else {
                showInviteScreen();
            }
            return;
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

        const validRoutes = ['dashboard', 'kanban', 'agents', 'crons', 'files', 'journal', 'alerts', 'admin'];
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
