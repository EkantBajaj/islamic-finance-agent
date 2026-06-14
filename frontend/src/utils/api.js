const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

/**
 * Handle API responses and throw on HTTP errors
 */
async function handleResponse(response) {
    if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        const message = errorData.detail || `HTTP error! status: ${response.status}`;
        throw new Error(message);
    }
    return response.json();
}

export const api = {
    /**
     * Check backend dependency health
     */
    async getHealth() {
        const res = await fetch(`${API_BASE_URL}/health`);
        return handleResponse(res);
    },

    /**
     * Ingest raw transaction payload
     */
    async ingestTransactions(payload) {
        const res = await fetch(`${API_BASE_URL}/transactions/ingest`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(payload),
        });
        return handleResponse(res);
    },

    /**
     * Get paginated, enriched transaction feed
     */
    async getTransactions(accountId, filters = {}) {
        const queryParams = new URLSearchParams();
        if (filters.category) queryParams.append('category', filters.category);
        if (filters.shariah_status) queryParams.append('shariah_status', filters.shariah_status);
        if (filters.page) queryParams.append('page', filters.page);
        if (filters.limit) queryParams.append('limit', filters.limit);
        
        const url = `${API_BASE_URL}/transactions/${accountId}?${queryParams.toString()}`;
        const res = await fetch(url);
        return handleResponse(res);
    },

    /**
     * Get generated insights
     */
    async getInsights(accountId) {
        const res = await fetch(`${API_BASE_URL}/insights/${accountId}`);
        return handleResponse(res);
    },

    /**
     * Get Zakat obligations breakdown
     */
    async getZakat(accountId) {
        const res = await fetch(`${API_BASE_URL}/zakat/${accountId}`);
        return handleResponse(res);
    },

    /**
     * Get financial profile dashboard indicators
     */
    async getProfile(accountId) {
        const res = await fetch(`${API_BASE_URL}/profile/${accountId}`);
        return handleResponse(res);
    }
};
