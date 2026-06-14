import './index.css';
import { api } from './utils/api.js';
import { PipelineWebSocket } from './utils/websocket.js';

// Global variables
let selectedAccountId = 'd3b07384-d113-4956-a5cc-9c0211a766bb';
let activeWebSocket = null;
let currentGoldPricePerGram = 4220.30; // default fallback

// Cache for holding the list of all fetched transactions (for modal lookup)
let currentTransactionsList = [];

// DOM Elements
const accountSelect = document.getElementById('account-select');
const triggerPipelineBtn = document.getElementById('trigger-pipeline-btn');
const wsStatusDot = document.getElementById('ws-status-dot');
const wsStatusText = document.getElementById('ws-status-text');

// Pipeline Tracker Elements
const pipelineStatusLabel = document.getElementById('pipeline-status-label');
const pipelineProgressBar = document.getElementById('pipeline-progress-bar');
const pipelineNodes = {
    ingest: document.getElementById('node-ingest'),
    normalize: document.getElementById('node-normalize'),
    categorize: document.getElementById('node-categorize'),
    shariah_screen: document.getElementById('node-shariah_screen'),
    detect_recurrence: document.getElementById('node-detect_recurrence'),
    generate_insights: document.getElementById('node-generate_insights'),
    zakat_calculation: document.getElementById('node-zakat_calculation'),
};
const pipelineNodeTimes = {
    ingest: document.getElementById('time-ingest'),
    normalize: document.getElementById('time-normalize'),
    categorize: document.getElementById('time-categorize'),
    shariah_screen: document.getElementById('time-shariah_screen'),
    detect_recurrence: document.getElementById('time-detect_recurrence'),
    generate_insights: document.getElementById('time-generate_insights'),
    zakat_calculation: document.getElementById('time-zakat_calculation'),
};

// Profile Elements
const complianceRadialBar = document.getElementById('compliance-radial-bar');
const complianceScoreVal = document.getElementById('compliance-score-val');
const avgIncomeVal = document.getElementById('avg-income-val');
const avgSpendVal = document.getElementById('avg-spend-val');
const categoryDistributionContainer = document.getElementById('category-distribution-container');

// Zakat Calculator Elements
const zakatDueVal = document.getElementById('zakat-due-val');
const zakatCashInput = document.getElementById('zakat-cash');
const zakatSavingsInput = document.getElementById('zakat-savings');
const zakatInvestmentsInput = document.getElementById('zakat-investments');
const zakatDebtsInput = document.getElementById('zakat-debts');
const goldPriceInput = document.getElementById('gold-price-per-gram');

// Shariah Audit Elements
const shariahCompliantCount = document.getElementById('shariah-compliant-count');
const shariahNonCompliantCount = document.getElementById('shariah-non-compliant-count');
const shariahReviewCount = document.getElementById('shariah-review-count');
const flaggedTransactionsList = document.getElementById('flagged-transactions-list');

// Insights & Feed Elements
const insightsFeedContainer = document.getElementById('insights-feed-container');
const filterCategory = document.getElementById('filter-category');
const filterShariah = document.getElementById('filter-shariah');
const transactionTableBody = document.getElementById('transaction-table-body');

// Modal Elements
const detailModalOverlay = document.getElementById('detail-modal-overlay');
const detailCloseBtn = document.getElementById('detail-close-btn');
const detailId = document.getElementById('detail-id');
const detailMethod = document.getElementById('detail-method');
const detailCatConfidence = document.getElementById('detail-cat-confidence');
const detailShariahConfidence = document.getElementById('detail-shariah-confidence');
const detailShariahFlags = document.getElementById('detail-shariah-flags');
const detailRawPayload = document.getElementById('detail-raw-payload');

// Sample transactions list to post for pipeline ingestion trigger demo
const getSampleTransactions = () => [
    {
        external_id: `tx_${Date.now()}_dewa`,
        amount: 320.50,
        currency: "AED",
        direction: "debit",
        transaction_date: new Date().toISOString().split('T')[0],
        merchant_name: "DEWA Dubai Electricity & Water Authority",
        merchant_mcc: "4900",
        description: "Monthly apartment utilities payment",
        source: "manual"
    },
    {
        external_id: `tx_${Date.now()}_pub`,
        amount: 120.00,
        currency: "AED",
        direction: "debit",
        transaction_date: new Date().toISOString().split('T')[0],
        merchant_name: "The Irish Pub House Mall",
        merchant_mcc: "5813",
        description: "Overdraft drinks pub fee charges",
        source: "manual"
    },
    {
        external_id: `tx_${Date.now()}_carrefour`,
        amount: 245.10,
        currency: "AED",
        direction: "debit",
        transaction_date: new Date().toISOString().split('T')[0],
        merchant_name: "Carrefour Hypermarket Emirates",
        merchant_mcc: "5411",
        description: "Family household groceries",
        source: "manual"
    },
    {
        external_id: `tx_${Date.now()}_interest`,
        amount: 45.00,
        currency: "AED",
        direction: "debit",
        transaction_date: new Date().toISOString().split('T')[0],
        merchant_name: "Conventional overdraft interest payment charges",
        merchant_mcc: "6011",
        description: "Bank overdraft charges fee",
        source: "manual"
    },
    {
        external_id: `tx_${Date.now()}_salary`,
        amount: 25000.00,
        currency: "AED",
        direction: "credit",
        transaction_date: new Date().toISOString().split('T')[0],
        merchant_name: "ACME Corp Payroll",
        merchant_mcc: "6012",
        description: "Monthly salary direct credit payout",
        source: "manual"
    }
];

// Helper: Format currency to AED
const formatAED = (value) => {
    if (value === null || value === undefined) return 'AED 0.00';
    return `AED ${parseFloat(value).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
};

// Initialize Dashboard Data
async function loadDashboardData() {
    try {
        selectedAccountId = accountSelect.value;
        console.log(`Loading dashboard metrics for account: ${selectedAccountId}`);

        // Fetch parallel stats from backend
        const [profile, zakat, insights, transactions] = await Promise.all([
            api.getProfile(selectedAccountId).catch(() => null),
            api.getZakat(selectedAccountId).catch(() => null),
            api.getInsights(selectedAccountId).catch(() => []),
            api.getTransactions(selectedAccountId, {
                category: filterCategory.value,
                shariah_status: filterShariah.value,
                limit: 50
            }).catch(() => ({ items: [], total: 0 }))
        ]);

        renderProfile(profile);
        renderZakat(zakat);
        renderInsights(insights);
        renderTransactions(transactions.items);

    } catch (err) {
        console.error('Failed to load dashboard data:', err);
    }
}

// Render Profile Card
function renderProfile(profile) {
    if (!profile) return;

    // 1. Shariah Compliance circular progress
    const score = parseFloat(profile.shariah_compliance_score || 0);
    const percentage = Math.round(score * 100);
    complianceScoreVal.textContent = `${percentage}%`;
    
    // Circumference of radial circle = 2 * PI * r = 2 * 3.14159 * 70 = 439.8 -> round to 440
    const offset = 440 - (440 * score);
    complianceRadialBar.style.strokeDashoffset = offset;

    // 2. Averages Inflow/Outflow
    avgIncomeVal.textContent = formatAED(profile.avg_monthly_income);
    avgSpendVal.textContent = formatAED(profile.avg_monthly_spend);

    // 3. Top category bars
    categoryDistributionContainer.innerHTML = '';
    const categories = profile.top_categories || [];

    if (categories.length === 0) {
        categoryDistributionContainer.innerHTML = `<div style="font-size: 0.8rem; color: var(--color-text-muted); text-align: center;">No category data.</div>`;
        return;
    }

    categories.forEach(item => {
        const pct = parseFloat(item.pct || 0);
        const name = item.category.replace('_', ' ');
        const bar = document.createElement('div');
        bar.className = 'category-bar-item';
        bar.innerHTML = `
            <div class="category-bar-header">
                <span class="category-bar-label">${name}</span>
                <span class="category-bar-amount">${pct.toFixed(1)}% (${formatAED(item.amount)})</span>
            </div>
            <div class="category-bar-track">
                <div class="category-bar-fill" style="width: ${pct}%"></div>
            </div>
        `;
        categoryDistributionContainer.appendChild(bar);
    });
}

// Render Zakat Card
function renderZakat(zakat) {
    if (!zakat) return;

    // 1. Set Zakat Obligation Display
    zakatDueVal.textContent = formatAED(zakat.zakat_due);

    // 2. Set input values from backend calculations
    const eligibleAssets = parseFloat(zakat.eligible_assets || 0);
    zakatCashInput.value = Math.round(eligibleAssets * 0.4); // split assets across fields for show
    zakatSavingsInput.value = Math.round(eligibleAssets * 0.3);
    zakatInvestmentsInput.value = Math.round(eligibleAssets * 0.3);
    zakatDebtsInput.value = 0;

    const nisab = parseFloat(zakat.nisab_threshold || 358725.48);
    currentGoldPricePerGram = nisab / 85;
    goldPriceInput.value = currentGoldPricePerGram.toFixed(2);
}

// Interactive Client-Side Zakat Recalculator
function recalculateZakat() {
    const cash = parseFloat(zakatCashInput.value) || 0;
    const savings = parseFloat(zakatSavingsInput.value) || 0;
    const investments = parseFloat(zakatInvestmentsInput.value) || 0;
    const debts = parseFloat(zakatDebtsInput.value) || 0;
    const goldPrice = parseFloat(goldPriceInput.value) || currentGoldPricePerGram;

    const assets = cash + savings + investments - debts;
    const nisabThreshold = goldPrice * 85;
    const isEligible = assets >= nisabThreshold;
    const zakatDue = isEligible ? assets * 0.025 : 0;

    zakatDueVal.textContent = formatAED(zakatDue);

    // Highlight gold color depending on eligibility
    const dueValEl = document.getElementById('zakat-due-val');
    if (zakatDue > 0) {
        dueValEl.style.textShadow = '0 0 15px rgba(212, 168, 83, 0.6)';
        dueValEl.style.color = 'var(--color-accent-light)';
    } else {
        dueValEl.style.textShadow = 'none';
        dueValEl.style.color = 'var(--color-text-secondary)';
    }
}

// Render Insights
function renderInsights(insights) {
    insightsFeedContainer.innerHTML = '';
    
    if (insights.length === 0) {
        insightsFeedContainer.innerHTML = `<div style="color: var(--color-text-muted); font-size: 0.9rem; text-align: center; padding: var(--space-md);">No financial insights available. Please run the pipeline.</div>`;
        return;
    }

    insights.forEach(ins => {
        const severity = ins.severity || 'info';
        const card = document.createElement('div');
        card.className = `insight-card ${severity}`;
        card.innerHTML = `
            <div class="insight-header">
                <span>${ins.title}</span>
                <span class="badge badge-category" style="font-size: 0.7rem;">${severity}</span>
            </div>
            <div class="insight-body">${ins.body}</div>
        `;
        insightsFeedContainer.appendChild(card);
    });
}

// Render Enriched Transactions Ledger and Shariah audit statistics
function renderTransactions(transactions) {
    currentTransactionsList = transactions;
    transactionTableBody.innerHTML = '';

    // Track compliant, non-compliant, and review counts
    let compliantCount = 0;
    let nonCompliantCount = 0;
    let reviewCount = 0;
    const flaggedList = [];

    if (transactions.length === 0) {
        transactionTableBody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--color-text-muted); padding: var(--space-xl);">No transactions match the filter parameters.</td></tr>`;
        shariahCompliantCount.textContent = '0';
        shariahNonCompliantCount.textContent = '0';
        shariahReviewCount.textContent = '0';
        flaggedTransactionsList.innerHTML = `<div style="color: var(--color-text-muted); font-size: 0.85rem; text-align: center; padding: var(--space-md);">No flagged transactions.</div>`;
        return;
    }

    transactions.forEach(tx => {
        const mapped = tx.mapped_transaction || {};
        
        // Count compliance stats
        const status = tx.shariah_status;
        if (status === 'compliant') compliantCount++;
        else if (status === 'non_compliant') {
            nonCompliantCount++;
            flaggedList.push(tx);
        }
        else if (status === 'review') reviewCount++;

        // Render Table Row
        const row = document.createElement('tr');
        row.dataset.txId = tx.id;
        row.addEventListener('click', () => showTransactionDetails(tx.id));

        const amountClass = mapped.direction === 'credit' ? 'credit' : 'debit';
        const amountSign = mapped.direction === 'credit' ? '+' : '-';
        const formattedAmount = `${amountSign} AED ${parseFloat(mapped.amount || 0).toFixed(2)}`;

        const dateStr = mapped.transaction_date || '-';
        const merchant = mapped.merchant_name || mapped.description || 'Unknown Merchant';
        const category = tx.category || 'other';
        const subcategory = tx.subcategory ? ` (${tx.subcategory.replace('_', ' ')})` : '';
        const recurTag = tx.is_recurring ? `<span class="recur-tag">🔄 Recur</span>` : '';

        row.innerHTML = `
            <td>${dateStr}</td>
            <td>
                <div style="font-weight: 500;">${merchant}</div>
                <div style="font-size: 0.75rem; color: var(--color-text-secondary);">${mapped.description || ''} ${recurTag}</div>
            </td>
            <td><span class="badge badge-category">${category}${subcategory}</span></td>
            <td><span class="badge badge-shariah ${status}">${status.replace('_', ' ')}</span></td>
            <td class="transaction-amount ${amountClass}">${formattedAmount}</td>
        `;

        transactionTableBody.appendChild(row);
    });

    // Update Shariah Screen count statistics
    shariahCompliantCount.textContent = compliantCount;
    shariahNonCompliantCount.textContent = nonCompliantCount;
    shariahReviewCount.textContent = reviewCount;

    // Render Flagged/Haram log cards
    flaggedTransactionsList.innerHTML = '';
    if (flaggedList.length === 0) {
        flaggedTransactionsList.innerHTML = `<div style="color: var(--color-text-muted); font-size: 0.85rem; text-align: center; padding: var(--space-md);">No non-compliant transactions flagged.</div>`;
        return;
    }

    flaggedList.forEach(tx => {
        const mapped = tx.mapped_transaction || {};
        const card = document.createElement('div');
        card.className = 'flagged-item';
        
        // Combine all reasons
        const reasons = (tx.shariah_flags || []).map(f => f.reason).join('; ') || 'Flagged by Shariah rules blocklist.';

        card.innerHTML = `
            <div class="flagged-item-header">
                <span>${mapped.merchant_name || 'Haram Merchant'}</span>
                <span class="spend">- AED ${parseFloat(mapped.amount || 0).toFixed(2)}</span>
            </div>
            <div class="flagged-item-desc">Category: ${tx.category} | MCC: ${mapped.merchant_mcc || 'N/A'}</div>
            <div class="flagged-item-reason">⚠️ ${reasons}</div>
        `;
        flaggedTransactionsList.appendChild(card);
    });
}

// Show Transaction Audit details in slide-out Modal Overlay
function showTransactionDetails(id) {
    const tx = currentTransactionsList.find(t => t.id === id);
    if (!tx) return;

    const mapped = tx.mapped_transaction || {};

    detailId.textContent = tx.id;
    detailMethod.textContent = tx.categorization_method || 'N/A';
    detailCatConfidence.textContent = tx.category_confidence ? `${(parseFloat(tx.category_confidence)*100).toFixed(0)}%` : 'N/A';
    detailShariahConfidence.textContent = tx.shariah_confidence ? `${(parseFloat(tx.shariah_confidence)*100).toFixed(0)}%` : 'N/A';
    
    // shariah flags
    const flags = tx.shariah_flags || [];
    if (flags.length === 0) {
        detailShariahFlags.textContent = 'None';
    } else {
        detailShariahFlags.innerHTML = flags.map(f => `
            <div style="margin-bottom: 6px; padding: var(--space-xs); background: rgba(255,255,255,0.02); border-radius: var(--radius-sm); border-left: 2px solid var(--color-accent);">
                <strong>Rule:</strong> ${f.rule} (Source: ${f.source})<br>
                <strong>Reason:</strong> ${f.reason}
            </div>
        `).join('');
    }

    // raw JSON payload formatting
    const rawPayload = mapped.raw_payload || tx;
    detailRawPayload.textContent = JSON.stringify(rawPayload, null, 2);

    detailModalOverlay.classList.add('active');
}

// Close transaction detail modal
detailCloseBtn.addEventListener('click', () => {
    detailModalOverlay.classList.remove('active');
});
detailModalOverlay.addEventListener('click', (e) => {
    if (e.target === detailModalOverlay) {
        detailModalOverlay.classList.remove('active');
    }
});

// Real-Time Ingestion Pipeline Trigger Flow
async function triggerPipelineRun() {
    try {
        console.log('Initiating pipeline run trigger...');
        triggerPipelineBtn.disabled = true;
        triggerPipelineBtn.textContent = '⏳ Submitting...';

        // 1. Send Ingestion request
        const transactionsBatch = getSampleTransactions();
        const requestPayload = {
            account_id: selectedAccountId,
            transactions: transactionsBatch
        };

        const response = await api.ingestTransactions(requestPayload);
        const { pipeline_id, ws_channel } = response;
        console.log(`Pipeline accepted! Ingestion ID: ${pipeline_id}, WS Channel: ${ws_channel}`);

        // 2. Connect to real-time WebSocket channel
        initializeWebSocketTracker(pipeline_id);

    } catch (err) {
        console.error('Trigger Ingestion flow failed:', err);
        alert(`Ingestion failed: ${err.message}`);
        triggerPipelineBtn.disabled = false;
        triggerPipelineBtn.textContent = '🚀 Trigger Ingestion Pipeline';
    }
}

// Connect and Animate Pipeline Visualizer via WebSockets
function initializeWebSocketTracker(pipelineId) {
    if (activeWebSocket) {
        activeWebSocket.disconnect();
    }

    resetPipelineNodes();
    pipelineStatusLabel.textContent = 'RUNNING';
    pipelineStatusLabel.style.background = 'rgba(245, 158, 11, 0.15)';
    pipelineStatusLabel.style.color = 'var(--color-warning)';
    wsStatusDot.className = 'ws-status-dot connecting';
    wsStatusText.textContent = 'WS Connecting';

    activeWebSocket = new PipelineWebSocket(pipelineId, {
        onOpen: () => {
            console.log(`WebSocket connected to pipeline channel: ${pipelineId}`);
            wsStatusDot.className = 'ws-status-dot connected';
            wsStatusText.textContent = 'WS Connected';
        },
        onMessage: (event) => {
            handlePipelineEvent(event);
        },
        onClose: () => {
            console.log('WebSocket connection closed.');
            wsStatusDot.className = 'ws-status-dot';
            wsStatusText.textContent = 'WS Offline';
        },
        onError: (err) => {
            console.error('WebSocket connection error:', err);
        }
    });

    activeWebSocket.connect();
}

// Handle real-time event updates
function handlePipelineEvent(event) {
    console.log('Real-Time Pipeline Event received:', event);

    const { type, stage, duration_ms, result_count, summary, error } = event;

    if (type === 'stage_started') {
        const node = pipelineNodes[stage];
        if (node) {
            node.classList.add('active');
            pipelineNodeTimes[stage].textContent = 'Processing...';
        }

        // Adjust connector progress bar width percentages
        updateConnectorProgress(stage);
    } 
    else if (type === 'stage_completed') {
        const node = pipelineNodes[stage];
        if (node) {
            node.classList.remove('active');
            node.classList.add('completed');
            const durationSec = ((duration_ms || 0) / 1000).toFixed(2);
            pipelineNodeTimes[stage].textContent = `${durationSec}s (${result_count || 0} items)`;
        }
    } 
    else if (type === 'pipeline_completed') {
        pipelineStatusLabel.textContent = 'COMPLETED';
        pipelineStatusLabel.style.background = 'rgba(16, 185, 129, 0.15)';
        pipelineStatusLabel.style.color = 'var(--color-success)';
        pipelineProgressBar.style.width = '100%';

        console.log(`Pipeline fully completed in ${summary.duration_ms}ms.`);
        
        // Disconnect socket and refresh metrics immediately
        if (activeWebSocket) {
            activeWebSocket.disconnect();
        }
        
        triggerPipelineBtn.disabled = false;
        triggerPipelineBtn.textContent = '🚀 Trigger Ingestion Pipeline';

        // Reload all cards
        loadDashboardData();
    }
    else if (type === 'pipeline_failed') {
        pipelineStatusLabel.textContent = 'FAILED';
        pipelineStatusLabel.style.background = 'rgba(239, 68, 68, 0.15)';
        pipelineStatusLabel.style.color = 'var(--color-danger)';
        
        console.error(`Pipeline failed with error: ${error}`);
        
        if (activeWebSocket) {
            activeWebSocket.disconnect();
        }

        triggerPipelineBtn.disabled = false;
        triggerPipelineBtn.textContent = '🚀 Trigger Ingestion Pipeline';
        alert(`Orchestrator run failed: ${error}`);
    }
}

// Reset node indicators
function resetPipelineNodes() {
    pipelineProgressBar.style.width = '0%';
    Object.keys(pipelineNodes).forEach(stage => {
        const node = pipelineNodes[stage];
        if (node) {
            node.className = 'pipeline-node';
        }
        const timeEl = pipelineNodeTimes[stage];
        if (timeEl) {
            timeEl.textContent = '-';
        }
    });
}

// Move progress connector bar based on stage
function updateConnectorProgress(stage) {
    const stagesOrdered = ['ingest', 'normalize', 'categorize', 'shariah_screen', 'detect_recurrence', 'generate_insights', 'zakat_calculation'];
    const idx = stagesOrdered.indexOf(stage);
    if (idx !== -1) {
        const percentage = (idx / (stagesOrdered.length - 1)) * 100;
        pipelineProgressBar.style.width = `${percentage}%`;
    }
}

// Bind Listeners
accountSelect.addEventListener('change', () => {
    selectedAccountId = accountSelect.value;
    loadDashboardData();
});
triggerPipelineBtn.addEventListener('click', triggerPipelineRun);

// Filters listeners
filterCategory.addEventListener('change', loadDashboardData);
filterShariah.addEventListener('change', loadDashboardData);

// Zakat calculator input event listeners
zakatCashInput.addEventListener('input', recalculateZakat);
zakatSavingsInput.addEventListener('input', recalculateZakat);
zakatInvestmentsInput.addEventListener('input', recalculateZakat);
zakatDebtsInput.addEventListener('input', recalculateZakat);
goldPriceInput.addEventListener('input', recalculateZakat);

// Initial Load
document.addEventListener('DOMContentLoaded', () => {
    // Attempt checking health
    api.getHealth()
        .then(() => console.log('Backend connection is active.'))
        .catch(e => console.warn('Could not reach backend health check:', e));

    loadDashboardData();
});
