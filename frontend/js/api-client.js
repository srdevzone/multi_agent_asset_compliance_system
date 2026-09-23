// js/api-client.js

class ApiClient {
  constructor() {
    this.baseUrl = (window.Config && window.Config.getApiBaseUrl()) || window.location.origin;
  }

  updateBaseUrl(url) {
    this.baseUrl = url;
    if (window.Config) {
      window.Config.setApiBaseUrl(url);
    }
  }

  getHeaders() {
    const headers = {
      'Content-Type': 'application/json'
    };
    const apiKey = localStorage.getItem('asset_compliance_api_key');
    if (apiKey) {
      headers['X-API-Key'] = apiKey;
    }
    return headers;
  }

  async request(path, options = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = { ...this.getHeaders(), ...options.headers };
    const config = { ...options, headers };

    try {
      const response = await fetch(url, config);

      if (response.status === 429) {
        const retryAfter = response.headers.get('Retry-After') || '60';
        this.showToast(`Rate limit exceeded. Please retry after ${retryAfter} seconds.`, 'warning');
        throw new Error(`Rate limited: retry after ${retryAfter}s`);
      }

      if (!response.ok) {
        let errorMsg = `HTTP Error ${response.status}`;
        try {
          const errData = await response.json();
          errorMsg = errData?.detail?.message || errData?.detail || errorMsg;
          if (typeof errorMsg === 'object') {
            errorMsg = JSON.stringify(errorMsg);
          }
        } catch (_) {}
        throw new Error(errorMsg);
      }

      return await response.json();
    } catch (error) {
      console.error(`API Request failed for ${path}:`, error);
      if (!error.message.includes('Rate limited')) {
        this.showToast(error.message || 'API request failed', 'error');
      }
      throw error;
    }
  }

  async get(path, options = {}) {
    return this.request(path, { method: 'GET', ...options });
  }

  async post(path, body, options = {}) {
    return this.request(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
      ...options
    });
  }

  async streamRequest(path, body, onChunk, onError, onComplete) {
    const url = `${this.baseUrl}${path}`;
    const headers = { ...this.getHeaders() };

    try {
      const response = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify(body)
      });

      if (!response.ok) {
        let errMsg = `HTTP ${response.status}`;
        try {
          const errData = await response.json();
          errMsg = errData?.detail?.message || errData?.detail || errMsg;
        } catch (_) {}
        throw new Error(errMsg);
      }

      await window.StreamReader.read(response, {
        onNodeComplete: onChunk,
        onVerdict: (verdict) => onChunk({ event: 'verdict', verdict }),
        onError: onError,
        onEnd: onComplete,
      });
    } catch (err) {
      console.error('Streaming request error:', err);
      onError(err);
    }
  }

  showToast(message, type = 'error') {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    // Add specific styled content depending on the type
    let icon = '';
    if (type === 'error') icon = '❌ ';
    else if (type === 'warning') icon = '⚠️ ';
    else if (type === 'success') icon = '✅ ';
    else if (type === 'info') icon = 'ℹ️ ';

    toast.textContent = `${icon}${message}`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      setTimeout(() => {
        toast.remove();
        if (container.children.length === 0) {
          container.remove();
        }
      }, 300);
    }, 5000);
  }

  // Authentication Endpoints
  async getAuthConfig() {
    return this.request('/api/v1/auth/config');
  }

  async verifyApiKey(apiKey) {
    return this.request('/api/v1/auth/verify', {
      method: 'POST',
      body: JSON.stringify({ api_key: apiKey })
    });
  }

  // Auditor Q&A / Chat Endpoint
  async queryAsset(chatRequest) {
    return this.request('/api/v1/chat/query', {
      method: 'POST',
      body: JSON.stringify(chatRequest)
    });
  }

  // Operational Admin Statistics
  async getAssetStats(assetId) {
    return this.request(`/api/v1/admin/assets/${encodeURIComponent(assetId)}/stats`);
  }

  // Permanent Delete Asset Data (GDPR Right-to-Erasure)
  async deleteAsset(assetId) {
    return this.request(`/api/v1/admin/assets/${encodeURIComponent(assetId)}`, {
      method: 'DELETE'
    });
  }
}

window.ApiClient = new ApiClient();
