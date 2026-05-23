/**
 * PriceScope — Frontend Application Logic
 *
 * Handles:
 * - Product search and comparison API calls
 * - Dynamic rendering of results, winner cards, insights
 * - Loading state animations with per-worker steps
 * - Search history management
 * - Error handling with toast notifications
 * - Processing mode display (Celery vs Async)
 */

const API_BASE = window.location.origin;

// --- State ---
let isSearching = false;
let currentResults = null;

// --- DOM Elements ---
const searchInput = document.getElementById('searchInput');
const searchBtn = document.getElementById('searchBtn');
const heroSection = document.getElementById('heroSection');
const resultsSection = document.getElementById('resultsSection');
const loadingSection = document.getElementById('loadingSection');
const winnersGrid = document.getElementById('winnersGrid');
const productsGrid = document.getElementById('productsGrid');
const insightsCard = document.getElementById('insightsCard');
const insightsBody = document.getElementById('insightsBody');
const llmBadge = document.getElementById('llmBadge');
const resultsTitle = document.getElementById('resultsTitle');
const resultsCount = document.getElementById('resultsCount');
const resultsSources = document.getElementById('resultsSources');
const errorToast = document.getElementById('errorToast');
const errorMessage = document.getElementById('errorMessage');
const statusDot = document.getElementById('statusDot');
const statusText = document.getElementById('statusText');
const modeDot = document.getElementById('modeDot');
const modeText = document.getElementById('modeText');


// --- Initialize ---
document.addEventListener('DOMContentLoaded', () => {
    checkHealth();
    loadHistory();

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && !isSearching) {
            performSearch();
        }
    });
});


// --- Search Functions ---

async function performSearch() {
    const query = searchInput.value.trim();
    if (!query || isSearching) return;

    isSearching = true;
    showLoading();
    hideError();

    try {
        animateLoadingSteps();

        const response = await fetch(`${API_BASE}/api/compare`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query }),
        });

        if (!response.ok) {
            const err = await response.json().catch(() => ({}));
            throw new Error(err.detail || `Server error: ${response.status}`);
        }

        const data = await response.json();
        currentResults = data;
        renderResults(data);
        loadHistory();

    } catch (error) {
        console.error('Search failed:', error);
        showError(error.message || 'Failed to compare products. Check that services are running.');
        hideLoading();
    } finally {
        isSearching = false;
    }
}

function quickSearch(query) {
    searchInput.value = query;
    performSearch();
}


// --- Render Functions ---

function renderResults(data) {
    hideLoading();
    resultsSection.style.display = 'block';
    heroSection.querySelector('.hero-content').style.paddingTop = '0';
    heroSection.querySelector('.hero-content h2').style.display = 'none';
    heroSection.querySelector('.hero-content p').style.display = 'none';

    // Results header
    resultsTitle.textContent = `Results for "${data.query}"`;

    const modeLabel = data.processing_mode === 'celery' ? '⚡ Celery' : '🔄 Async';
    resultsCount.textContent = `${data.total_results} products · ${data.processing_time_ms || 0}ms · ${modeLabel}${data.cached ? ' · cached' : ''}`;

    // Source badges
    resultsSources.innerHTML = (data.sources_searched || []).map(source => {
        const cls = source.replace(/\s+/g, '').toLowerCase(); // Removes spaces for class names
        return `<span class="source-badge ${cls}">${source}</span>`;
    }).join('');

    // Winner cards
    renderWinners(data);

    // AI Insights
    if (data.insights) {
        insightsCard.style.display = 'block';
        insightsBody.textContent = data.insights;
        llmBadge.textContent = data.llm_used ? `GPT · ${data.processing_time_ms}ms` : 'Rule-based';
    } else {
        insightsCard.style.display = 'none';
    }

    // Products grid
    renderProducts(data.products, data.best_price, data.best_rating, data.best_value);

    // Smooth scroll to results
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'start' });
}


function renderWinners(data) {
    const winners = [
        { key: 'best_price', type: 'price', emoji: '💰', label: 'Cheapest', color: 'green' },
        { key: 'best_rating', type: 'rating', emoji: '⭐', label: 'Best Rated', color: 'amber' },
        { key: 'best_value', type: 'value', emoji: '🏆', label: 'Best Value', color: 'purple' },
    ];

    winnersGrid.innerHTML = winners.map(w => {
        const product = data[w.key];
        if (!product) return '';

        const price = formatPrice(product.normalized_price_inr || product.price, 'INR');
        const stars = renderStarsHTML(product.rating);
        
        // FIX: Look for either 'source' or 'platform'
        const platform = product.source || product.platform || 'Unknown'; 
        const platformClass = platform.replace(/\s+/g, ''); 

        return `
            <div class="winner-card ${w.type}">
                <div class="winner-badge">${w.emoji} ${w.label}</div>
                <div class="winner-title">${escapeHTML(product.title)}</div>
                <div class="winner-price">${price}</div>
                <div class="winner-meta">
                    <span class="winner-stars">${stars} ${product.rating}/5</span>
                    <span>${formatNumber(product.reviews)} reviews</span>
                </div>
                <div class="winner-platform ${platformClass}">${platform}</div>
                <a href="${product.url}" target="_blank" rel="noopener" class="winner-link">
                    View on ${platform} →
                </a>
            </div>
        `;
    }).join('');
}


function renderProducts(products, bestPrice, bestRating, bestValue) {
    if (!products || products.length === 0) {
        productsGrid.innerHTML = '<p style="color:var(--text-tertiary);text-align:center;padding:40px;">No products found.</p>';
        return;
    }

    productsGrid.innerHTML = products.map(product => {
        const price = formatPrice(product.normalized_price_inr || product.price, 'INR');
        const originalPrice = product.currency !== 'INR'
            ? `<span class="product-original-price">(${product.currency} ${formatNumber(product.price)})</span>`
            : '';
            
        // FIX: Look for either 'source' or 'platform'
        const platform = product.source || product.platform || 'Unknown'; 
        const platformClass = platform.replace(/\s+/g, ''); 
        const stars = renderStarsHTML(product.rating);

        // Determine badges
        let badge = '';
        const bestPricePlatform = bestPrice ? (bestPrice.source || bestPrice.platform) : null;
        const bestRatingPlatform = bestRating ? (bestRating.source || bestRating.platform) : null;
        const bestValuePlatform = bestValue ? (bestValue.source || bestValue.platform) : null;

        if (bestPrice && product.title === bestPrice.title && platform === bestPricePlatform) {
            badge = '<span class="value-badge best-price">💰 Cheapest</span>';
        } else if (bestRating && product.title === bestRating.title && platform === bestRatingPlatform) {
            badge = '<span class="value-badge best-rating">⭐ Top Rated</span>';
        } else if (bestValue && product.title === bestValue.title && platform === bestValuePlatform) {
            badge = '<span class="value-badge best-value">🏆 Best Value</span>';
        }

        return `
            <div class="product-card">
                ${badge}
                <div class="product-source-bar ${platformClass}"></div>
                <div class="product-title">${escapeHTML(product.title)}</div>
                <div class="product-price-row">
                    <span class="product-price">${price}</span>
                    ${originalPrice}
                </div>
                <div class="product-rating">
                    <div class="rating-stars">${stars}</div>
                    <span class="rating-text">${product.rating}/5</span>
                    <span class="review-count">(${formatNumber(product.reviews)} reviews)</span>
                </div>
                <div class="product-footer">
                    <span class="product-platform ${platformClass}">${platform}</span>
                    <a href="${product.url}" target="_blank" rel="noopener" class="product-link">
                        View Deal →
                    </a>
                </div>
            </div>
        `;
    }).join('');
}


// --- Loading ---

function showLoading() {
    loadingSection.style.display = 'block';
    resultsSection.style.display = 'none';
    searchBtn.classList.add('loading');
}

function hideLoading() {
    loadingSection.style.display = 'none';
    searchBtn.classList.remove('loading');
}

function animateLoadingSteps() {
    const steps = ['step-amazon', 'step-ebay', 'step-google', 'step-walmart', 'step-target', 'step-analyze'];
    steps.forEach(id => {
        const el = document.getElementById(id);
        if (el) el.className = 'loading-step';
    });

    steps.forEach((id, index) => {
        setTimeout(() => {
            const el = document.getElementById(id);
            if (!el) return;
            el.classList.add('active');

            if (index > 0) {
                const prev = document.getElementById(steps[index - 1]);
                if (prev) {
                    prev.classList.remove('active');
                    prev.classList.add('done');
                }
            }
        }, index * 500); 
    });
}


// --- Error Handling ---

function showError(message) {
    errorMessage.textContent = message;
    errorToast.style.display = 'flex';
    setTimeout(hideError, 8000);
}

function hideError() {
    errorToast.style.display = 'none';
}


// --- Health Check ---

async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/api/health`);
        const data = await response.json();

        statusDot.className = `status-dot ${data.status}`;

        const healthyCount = data.services.filter(s => s.status === 'healthy').length;
        const totalCount = data.services.length;
        statusText.textContent = `${healthyCount}/${totalCount} services online`;

        // Show processing mode
        if (data.processing_mode) {
            const mode = data.processing_mode === 'celery' ? '⚡ Celery' : '🔄 Async';
            modeText.textContent = mode;
            modeDot.className = `mode-dot ${data.processing_mode}`;
        }

    } catch (err) {
        statusDot.className = 'status-dot unhealthy';
        statusText.textContent = 'Services offline';
        modeText.textContent = '—';
    }
}


// --- History ---

async function loadHistory() {
    try {
        const response = await fetch(`${API_BASE}/api/history`);
        const data = await response.json();

        const historyList = document.getElementById('historyList');
        historyList.innerHTML = (data.history || []).slice(0, 8).map(item => `
            <div class="history-item" onclick="quickSearch('${escapeHTML(item.query)}')">
                <span>${escapeHTML(item.query)}</span>
                <span class="history-item-count">${item.result_count}</span>
            </div>
        `).join('');

    } catch (err) {
        // Silent fail for history
    }
}


// --- Utility Functions ---

function formatPrice(price, currency = 'INR') {
    if (!price && price !== 0) return '—';

    if (currency === 'INR') {
        return '₹' + Number(price).toLocaleString('en-IN', { maximumFractionDigits: 0 });
    } else if (currency === 'USD') {
        return '$' + Number(price).toLocaleString('en-US', { minimumFractionDigits: 2 });
    }
    return `${currency} ${Number(price).toLocaleString()}`;
}

function formatNumber(num) {
    if (!num && num !== 0) return '0';
    return Number(num).toLocaleString('en-IN');
}

function renderStarsHTML(rating) {
    const fullStars = Math.floor(rating);
    const hasHalf = rating % 1 >= 0.3;
    let html = '';

    for (let i = 0; i < 5; i++) {
        if (i < fullStars) {
            html += '<svg class="star filled" viewBox="0 0 16 16"><path d="M8 1l2.2 4.5L15 6.3l-3.5 3.4.8 4.8L8 12.3 3.7 14.5l.8-4.8L1 6.3l4.8-.8L8 1z" fill="currentColor"/></svg>';
        } else if (i === fullStars && hasHalf) {
            html += '<svg class="star filled" viewBox="0 0 16 16" style="opacity:0.5"><path d="M8 1l2.2 4.5L15 6.3l-3.5 3.4.8 4.8L8 12.3 3.7 14.5l.8-4.8L1 6.3l4.8-.8L8 1z" fill="currentColor"/></svg>';
        } else {
            html += '<svg class="star" viewBox="0 0 16 16"><path d="M8 1l2.2 4.5L15 6.3l-3.5 3.4.8 4.8L8 12.3 3.7 14.5l.8-4.8L1 6.3l4.8-.8L8 1z" fill="currentColor"/></svg>';
        }
    }
    return html;
}

function escapeHTML(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}