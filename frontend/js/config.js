// js/config.js

const CONFIG_KEYS = {
  API_KEY: 'asset_compliance_api_key',
  CURRENT_ASSET_ID: 'asset_compliance_current_asset_id',
  CURRENT_ASSET_SPEC: 'asset_compliance_current_asset_spec',
  CURRENT_PREVIOUS_VERDICTS: 'asset_compliance_current_previous_verdicts'
};

export const Config = {
  getApiKey() {
    return localStorage.getItem(CONFIG_KEYS.API_KEY) || '';
  },

  setApiKey(key) {
    localStorage.setItem(CONFIG_KEYS.API_KEY, key);
  },

  getCurrentAssetId() {
    return localStorage.getItem(CONFIG_KEYS.CURRENT_ASSET_ID) || 'sample-pump-001';
  },

  setCurrentAssetId(assetId) {
    localStorage.setItem(CONFIG_KEYS.CURRENT_ASSET_ID, assetId);
  },

  getApiBaseUrl() {
    return localStorage.getItem('asset_compliance_api_base_url') || window.location.origin;
  },

  setApiBaseUrl(url) {
    localStorage.setItem('asset_compliance_api_base_url', url);
    if (window.ApiClient) {
      window.ApiClient.updateBaseUrl(url);
    }
  },

  save({ apiBaseUrl, apiKey }) {
    if (apiBaseUrl !== undefined) {
      this.setApiBaseUrl(apiBaseUrl);
    }
    if (apiKey !== undefined) {
      this.setApiKey(apiKey);
    }
  },

  reset() {
    Object.values(CONFIG_KEYS).forEach(key => localStorage.removeItem(key));
    localStorage.removeItem('asset_compliance_api_base_url');
  },

  set(key, value) {
    if (key === 'apiKey') {
      this.setApiKey(value);
    } else if (key === 'currentAssetId') {
      this.setCurrentAssetId(value);
    } else {
      localStorage.setItem(`asset_compliance_${key}`, value);
    }
  },

  getActivityLog() {
    try {
      const logs = localStorage.getItem('asset_compliance_activity_log');
      return logs ? JSON.parse(logs) : [];
    } catch (e) {
      console.error("Error parsing activity log:", e);
      return [];
    }
  },

  clearActivityLog() {
    localStorage.removeItem('asset_compliance_activity_log');
  },

  addActivity(type, message, status = 'info') {
    try {
      const logs = this.getActivityLog();
      logs.push({
        id: 'act-' + Date.now() + '-' + Math.random().toString(36).substring(2, 11),
        type,
        message,
        status,
        timestamp: new Date().toISOString()
      });
      const trimmedLogs = logs.slice(-100);
      localStorage.setItem('asset_compliance_activity_log', JSON.stringify(trimmedLogs));
    } catch (e) {
      console.error("Error saving activity log:", e);
    }
  },

  getCurrentAssetSpec() {
    try {
      const spec = localStorage.getItem(CONFIG_KEYS.CURRENT_ASSET_SPEC);
      if (spec) return JSON.parse(spec);
    } catch (e) {
      console.error("Error parsing asset spec:", e);
    }
    // Return a default spec if none is saved
    return {
      name: "High-Pressure Water Pump XP-900",
      category: "pump",
      manufacturer: "PumpCorp Industries",
      model: "XP-900",
      serial_number: "PC-900-8849-X",
      flow_rate: "150 GPM",
      pressure_max: "600 PSI"
    };
  },

  setCurrentAssetSpec(spec) {
    localStorage.setItem(CONFIG_KEYS.CURRENT_ASSET_SPEC, JSON.stringify(spec));
  },

  getCurrentPreviousVerdicts() {
    try {
      const verdicts = localStorage.getItem(CONFIG_KEYS.CURRENT_PREVIOUS_VERDICTS);
      if (verdicts) return JSON.parse(verdicts);
    } catch (e) {
      console.error("Error parsing previous verdicts:", e);
    }
    // Return a default array of previous verdicts if none are saved
    return [
      {
        asset_id: this.getCurrentAssetId(),
        run_id: "run-98234-abc",
        compliance_status: "COMPLIANT",
        confidence: 0.92,
        triggered_rules: [],
        evidence: [
          {
            source_type: "document",
            filename: "xp900_installation_guide.pdf",
            doc_id: "doc_xp900_install",
            doc_type: "compliance_spec",
            page: 4,
            finding: "Minimum wall clearance of 12 inches is maintained.",
            relevance_score: 0.88
          }
        ],
        recommendations: ["Perform regular gasket checks every 6 months."],
        verdict_reasoning: "The asset satisfies all structural and clearance rules described in the installation guidelines.",
        generated_at: new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString() // 30 days ago
      }
    ];
  },

  setCurrentPreviousVerdicts(verdicts) {
    localStorage.setItem(CONFIG_KEYS.CURRENT_PREVIOUS_VERDICTS, JSON.stringify(verdicts));
  },

  // Caching up to 50 turns per asset
  getChatHistory(assetId) {
    try {
      const history = localStorage.getItem(`chat_history_${assetId}`);
      return history ? JSON.parse(history) : [];
    } catch (e) {
      console.error("Error parsing chat history:", e);
      return [];
    }
  },

  saveChatHistory(assetId, history) {
    try {
      // Keep up to 50 turns (1 turn = 1 user + 1 assistant message, so 100 items maximum)
      const trimmedHistory = history.slice(-100);
      localStorage.setItem(`chat_history_${assetId}`, JSON.stringify(trimmedHistory));
    } catch (e) {
      console.error("Error saving chat history:", e);
    }
  },

  clearChatHistory(assetId) {
    localStorage.removeItem(`chat_history_${assetId}`);
  },

  async fetchAndSetupDevMode() {
    try {
      const response = await fetch('/api/v1/auth/config');
      if (response.ok) {
        const data = await response.json();
        if (data.dev_mode) {
          console.log("Dev mode detected.");
        }
        return data;
      }
    } catch (e) {
      console.error("Failed to fetch auth config", e);
    }
  }
};

if (typeof window !== 'undefined') {
  window.Config = Config;
}
