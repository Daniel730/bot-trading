lucide.createIcons();

const arbiMesh = document.getElementById('arbi-mesh');
const arbiBubble = document.getElementById('arbi-bubble');
const journalLog = document.getElementById('journal-log');
const valState = document.getElementById('val-state');
const uptimeEl = document.getElementById('uptime');

// --- CHARTS ---
const revCtx = document.getElementById('revenue-chart').getContext('2d');
const revenueChart = new Chart(revCtx, {
    type: 'line',
    data: {
        labels: [],
        datasets: [{
            label: 'Revenue',
            data: [],
            borderColor: '#00f2ff',
            backgroundColor: 'rgba(0, 242, 255, 0.1)',
            borderWidth: 2,
            tension: 0.4,
            pointRadius: 0,
            fill: true
        }]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
            x: { display: false },
            y: {
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: '#8892b0', font: { size: 8 } }
            }
        }
    }
});

// Timer
let startTime = Date.now();
setInterval(() => {
    let diff = Math.floor((Date.now() - startTime) / 1000);
    let h = Math.floor(diff / 3600).toString().padStart(2, '0');
    let m = Math.floor((diff % 3600) / 60).toString().padStart(2, '0');
    let s = (diff % 60).toString().padStart(2, '0');
    uptimeEl.textContent = `${h}:${m}:${s}`;
}, 1000);

const thoughts = {
    idle: ["Scanning for alpha...", "Markets are quiet...", "Optimizing filters.", "Waiting for signal cross."],
    analyzing: ["SEC 10-K analysis in progress.", "Kalman convergence check.", "Calculating hedge ratios.", "Risk cluster audit..."],
    executing: ["TRADE AUTHORIZED!", "Capturing delta.", "Spread locked.", "Transaction confirmed."]
};

function addLog(text, agent = null, verdict = null) {
    const line = document.createElement('div');
    line.className = 'log-line';
    if (agent) line.classList.add(`agent-${agent.toLowerCase()}`);
    
    const time = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
    
    let agentTag = '';
    if (agent) {
        let color = 'var(--neon-cyan)';
        if (verdict === 'BULLISH' || verdict === 'EXECUTE') color = 'var(--neon-lime)';
        if (verdict === 'BEARISH' || verdict === 'REJECT') color = '#ff4d4d';
        agentTag = `<span class="agent-tag" style="color:${color}">[${agent}]</span> `;
    }

    line.innerHTML = `<span style="color:rgba(0,242,255,0.4)">[${time}]</span> > ${agentTag}${text}`;
    journalLog.prepend(line);
    // Keep only last 50 lines
    if (journalLog.children.length > 50) journalLog.removeChild(journalLog.lastChild);
}

function speak(text) {
    arbiBubble.textContent = text;
    arbiBubble.classList.add('visible');
    setTimeout(() => arbiBubble.classList.remove('visible'), 5000);
}

function setMood(mood) {
    arbiMesh.parentElement.className = 'arbi-model state-' + mood;
    const list = thoughts[mood] || thoughts.idle;
    if (Math.random() > 0.7) speak(list[Math.floor(Math.random() * list.length)]);
}

function formatCurrency(val) {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
}

function getSignalColor(status) {
    if (status.includes('EXECUTING')) return 'var(--neon-magenta)';
    if (status.includes('VETO')) return '#ff4d4d';
    if (status.includes('Approval')) return 'var(--neon-lime)';
    return 'var(--neon-cyan)';
}

// --- TERMINAL LOGIC ---
const terminalModal = document.getElementById('terminal-modal');
const openTerminalBtn = document.getElementById('open-terminal');
const closeTerminalBtn = document.getElementById('close-terminal');
const terminalMessages = document.getElementById('terminal-messages');
const terminalInput = document.getElementById('terminal-input');

function openTerminal() {
    terminalModal.classList.add('active');
    terminalInput.focus();
    // Scroll to bottom
    terminalMessages.scrollTop = terminalMessages.scrollHeight;
}

function closeTerminal() {
    terminalModal.classList.remove('active');
}

openTerminalBtn.addEventListener('click', openTerminal);
closeTerminalBtn.addEventListener('click', closeTerminal);

async function sendCommand(command, metadata = null) {
    if (!command) return;
    
    addLog(`Sending terminal command: ${command}`);
    
    try {
        const response = await fetch(`/api/terminal/command?token=${token || ''}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ command, metadata })
        });
        
        const result = await response.json();
        if (!response.ok) {
            console.error("Terminal Command Error:", result.detail);
            addLog(`TERMINAL ERROR: ${result.detail}`);
        }
    } catch (err) {
        console.error("Terminal Fetch Error:", err);
    }
}
window.sendCommand = sendCommand;

terminalInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        const cmd = terminalInput.value.trim();
        if (cmd) {
            sendCommand(cmd);
            terminalInput.value = '';
        }
    }
});

function renderTerminalMessages(messages) {
    if (!messages) return;
    
    terminalMessages.innerHTML = '';
    messages.forEach(msg => {
        const div = document.createElement('div');
        div.className = `terminal-msg ${msg.type.toLowerCase()}`;
        
        let content = `<span class="sender">[${msg.type}]</span> ${msg.text}`;
        
        // Handle approval buttons
        if (msg.metadata && msg.metadata.type === 'approval') {
            const cid = msg.metadata.correlation_id;
            content += `
                <div class="approval-actions">
                    <button class="approve-btn" onclick="sendCommand('/approve ${cid}', {correlation_id: '${cid}'})">
                        APPROVE_${cid}
                    </button>
                </div>
            `;
        }
        
        div.innerHTML = content;
        terminalMessages.appendChild(div);
    });
    
    // Auto scroll
    terminalMessages.scrollTop = terminalMessages.scrollHeight;
}

function updateUI(data) {
    const { stage, details, metrics, active_signals, terminal_messages, timestamp } = data;
    
    // Update State
    if (stage && valState) valState.textContent = stage.toUpperCase();
    if (details) addLog(details);

    // Update Terminal
    if (terminal_messages) renderTerminalMessages(terminal_messages);

    // Update Metrics
    if (metrics) {
        const budget = document.getElementById('val-budget');
        const remaining = document.getElementById('val-remaining');
        const usageText = document.getElementById('val-usage-text');
        const usageBar = document.getElementById('val-usage-bar');
        const inv = document.getElementById('val-investment');
        const dly = document.getElementById('val-daily-profit');
        const roa = document.getElementById('val-roa');
        const projection = document.getElementById('val-projection');

        if (budget && metrics.daily_budget !== undefined) budget.textContent = formatCurrency(metrics.daily_budget);
        if (remaining && metrics.daily_budget !== undefined) remaining.textContent = formatCurrency(metrics.daily_budget - (metrics.total_invested || 0));
        
        if (usageText && metrics.daily_usage_pct !== undefined) usageText.textContent = `${metrics.daily_usage_pct.toFixed(1)}%`;
        if (usageBar && metrics.daily_usage_pct !== undefined) usageBar.style.width = `${Math.min(metrics.daily_usage_pct, 100)}%`;

        if (inv && metrics.total_invested !== undefined) inv.textContent = formatCurrency(metrics.total_invested);
        if (dly && metrics.daily_profit !== undefined) {
            dly.textContent = formatCurrency(metrics.daily_profit);
            dly.style.color = metrics.daily_profit >= 0 ? 'var(--neon-lime)' : '#ff4d4d';
            
            // Daily ROA (Return on Allocation)
            if (roa && metrics.daily_budget > 0) {
                const roaVal = (metrics.daily_profit / metrics.daily_budget) * 100;
                roa.textContent = `${roaVal >= 0 ? '+' : ''}${roaVal.toFixed(2)}%`;
            }

            // Proj. EOD (Simple linear extrapolation or just sum)
            if (projection) {
                const current = metrics.daily_profit;
                projection.textContent = formatCurrency(current);
            }
        }

        // Update Revenue Chart with Daily Profit instead of Lifetime
        if (metrics.daily_profit !== undefined) {
            const label = new Date().toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit' });
            revenueChart.data.labels.push(label);
            revenueChart.data.datasets[0].data.push(metrics.daily_profit);
            
            if (revenueChart.data.labels.length > 30) {
                revenueChart.data.labels.shift();
                revenueChart.data.datasets[0].data.shift();
            }
            revenueChart.update('none');
        }
    }

    // Update Signals Feed
    if (active_signals) {
        const feed = document.getElementById('signals-feed');
        if (active_signals.length === 0) {
            feed.innerHTML = '<div class="empty-state"><i data-lucide="radar" size="32"></i><p>SCANNING_MARKET...</p></div>';
            lucide.createIcons();
        } else {
            feed.innerHTML = ''; 
            active_signals.forEach(sig => {
                const card = document.createElement('div');
                card.className = 'signal-card';
                const color = getSignalColor(sig.status);
                card.style.borderLeft = `2px solid ${color}`;
                card.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                        <div>
                            <div style="font-weight: bold; font-size: 0.85rem; letter-spacing: 1px;">${sig.ticker_a} / ${sig.ticker_b}</div>
                            <div style="font-size: 0.65rem; color: #8892b0; font-family: var(--font-mono); margin-top: 4px;">Z-SCORE: ${sig.z_score.toFixed(2)}</div>
                        </div>
                        <div style="color: ${color}; font-size: 0.6rem; font-weight: bold; text-transform: uppercase; border: 1px solid ${color}; padding: 2px 5px; border-radius: 3px;">${sig.status}</div>
                    </div>
                `;
                feed.appendChild(card);
            });
        }
    }

    const s = (stage || "").toLowerCase();
    if (s.includes('monitor') || s.includes('scan') || s.includes('search')) setMood('idle');
    else if (s.includes('analyz') || s.includes('ai')) setMood('analyzing');
    else if (s.includes('execut') || s.includes('trade')) setMood('executing');
    else setMood('idle');
}

// SSE Listener
const urlParams = new URLSearchParams(window.location.search);
const token = urlParams.get('token');
const eventSource = new EventSource(`/stream?token=${token || ''}`);
eventSource.addEventListener('message', (e) => {
    try {
        const data = JSON.parse(e.data);
        updateUI(data);
    } catch (err) {
        console.error("Dashboard Stream Parse Error:", err);
    }
});

// --- TELEMETRY WEBSOCKET (US1 & US2) ---
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const telemetryWS = new WebSocket(`${wsProtocol}//${window.location.host}/ws/telemetry?token=${token || ''}`);

function updateWSStatus(status) {
    const modeEl = document.getElementById('val-mode');
    if (modeEl) {
        const dot = status === 'connected' ? '●' : '○';
        const color = status === 'connected' ? 'var(--neon-lime)' : '#ff4d4d';
        modeEl.innerHTML = `<span style="color:${color}; margin-right:5px;">${dot}</span> ${status.toUpperCase()}`;
    }
}

telemetryWS.onopen = () => {
    console.log("Telemetry WebSocket connected.");
    addLog("TELEMETRY_LINK_ESTABLISHED");
    updateWSStatus('connected');
};

telemetryWS.onmessage = (event) => {
    try {
        const payload = JSON.parse(event.data);
        handleTelemetryUpdate(payload);
    } catch (err) {
        console.error("Telemetry Parse Error:", err);
    }
};

telemetryWS.onclose = () => {
    console.warn("Telemetry WebSocket disconnected.");
    addLog("TELEMETRY_LINK_LOST");
    updateWSStatus('disconnected');
};

// Throttling for high-frequency updates
let lastRiskUpdate = 0;
function handleTelemetryUpdate(payload) {
    const { type, data } = payload;
    
    if (type === 'risk') {
        const now = Date.now();
        if (now - lastRiskUpdate > 100) { // Max 10 updates per second
            updateRiskHUD(data);
            lastRiskUpdate = now;
        }
    } else if (type === 'thought') {
        updateThoughtJournal(data);
    } else if (type === 'status') {
        // Redundant with SSE but kept for future migration
        if (data.stage) valState.textContent = data.stage.toUpperCase();
        if (data.details) addLog(data.details);
    }
}

function updateRiskHUD(data) {
    const { risk_multiplier, max_drawdown_pct, volatility_status, l2_entropy } = data;
    
    const multEl = document.getElementById('risk-multiplier');
    const ddEl = document.getElementById('risk-drawdown');
    const volEl = document.getElementById('risk-vol-status');
    const entropyEl = document.getElementById('risk-entropy');

    if (multEl) {
        multEl.textContent = risk_multiplier.toFixed(2);
        multEl.style.color = risk_multiplier < 0.5 ? 'var(--neon-magenta)' : 'var(--neon-cyan)';
    }
    if (ddEl) {
        ddEl.textContent = `${(max_drawdown_pct * 100).toFixed(1)}%`;
        ddEl.style.color = max_drawdown_pct > 0.05 ? '#ff4d4d' : 'var(--neon-cyan)';
    }
    if (volEl) {
        volEl.textContent = volatility_status;
        volEl.style.color = volatility_status === 'HIGH_VOLATILITY' ? '#ff4d4d' : 'var(--neon-lime)';
    }
    if (entropyEl) {
        entropyEl.textContent = l2_entropy.toFixed(2);
        entropyEl.style.color = l2_entropy > 0.7 ? '#ff4d4d' : 'var(--neon-cyan)';
    }
}

function updateThoughtJournal(data) {
    const { agent_name, thought, verdict, ticker_pair } = data;
    const msg = ticker_pair ? `(${ticker_pair}) ${thought}` : thought;
    addLog(msg, agent_name, verdict);
}

// UI Noise for ambiance (latency only)
setInterval(() => {
    const latEl = document.getElementById('latency');
    if (latEl) latEl.textContent = (Math.random() * 15 + 5).toFixed(0) + 'ms';
}, 4000);
