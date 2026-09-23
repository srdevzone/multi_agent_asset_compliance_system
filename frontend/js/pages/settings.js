/* Settings Page Controller - Asset Compliance AI */

(function () {
  window.PageControllers = window.PageControllers || {};

  window.PageControllers.settings = {
    init() {
      console.log('Settings controller initialized');

      this.form = document.getElementById('settings-form');
      this.apiUrlInput = document.getElementById('settings-api-url');
      this.apiKeyInput = document.getElementById('settings-api-key');
      this.toggleKeyBtn = document.getElementById('settings-toggle-key-btn');
      this.saveBtn = document.getElementById('settings-save-btn');
      this.resetBtn = document.getElementById('settings-reset-btn');
      this.testBtn = document.getElementById('settings-test-btn');
      this.consoleEl = document.getElementById('settings-test-console');

      // Populate current config values on mount
      if (window.Config) {
        this.apiUrlInput.value = window.Config.getApiBaseUrl();
        this.apiKeyInput.value = window.Config.getApiKey();
      }

      this._boundHandleSave = this.handleSave.bind(this);
      this._boundHandleToggleKey = this.handleToggleKey.bind(this);
      this._boundHandleReset = this.handleReset.bind(this);
      this._boundHandleTestConnection = this.handleTestConnection.bind(this);

      this.form.addEventListener('submit', this._boundHandleSave);
      this.toggleKeyBtn.addEventListener('click', this._boundHandleToggleKey);
      this.resetBtn.addEventListener('click', this._boundHandleReset);
      this.testBtn.addEventListener('click', this._boundHandleTestConnection);
    },

    handleSave(e) {
      e.preventDefault();
      
      const apiBaseUrl = this.apiUrlInput.value.trim();
      const apiKey = this.apiKeyInput.value.trim();

      if (window.Config) {
        window.Config.save({ apiBaseUrl, apiKey });
        window.Config.addActivity('Settings Configuration', 'API base URL and/or system token updated', 'success');
      }

      if (window.Toast) {
        window.Toast.success('Connection settings saved successfully.');
      }
    },

    handleToggleKey() {
      if (this.apiKeyInput.type === 'password') {
        this.apiKeyInput.type = 'text';
        this.toggleKeyBtn.innerText = 'Hide';
      } else {
        this.apiKeyInput.type = 'password';
        this.toggleKeyBtn.innerText = 'Show';
      }
    },

    handleReset() {
      if (window.Modal) {
        window.Modal.create({
          title: 'Reset to Defaults',
          content: 'Are you sure you want to reset settings? This will restore standard ports and clear your API Key.',
          confirmText: 'Reset',
          cancelText: 'Cancel',
          variant: 'warning',
          onConfirm: (close) => {
            if (window.Config) {
              window.Config.reset();
              this.apiUrlInput.value = window.Config.getApiBaseUrl();
              this.apiKeyInput.value = window.Config.getApiKey();
              window.Config.addActivity('Settings Configuration', 'Settings reset to original defaults', 'warning');
            }
            close();
            if (window.Toast) {
              window.Toast.info('Settings restored to default configurations.');
            }
          }
        });
      }
    },

    async handleTestConnection() {
      if (!this.consoleEl) return;

      this.consoleEl.innerHTML = '';
      this.logToConsole('Diagnosing connection settings...', 'info');

      const testUrl = this.apiUrlInput.value.trim();
      const testKey = this.apiKeyInput.value.trim();

      this.testBtn.disabled = true;
      this.testBtn.innerText = 'Testing...';

      try {
        // Ping GET /health
        const healthUrl = `${testUrl.replace(/\/$/, '')}/health`;
        this.logToConsole(`[PING] GET ${healthUrl}`, 'info');
        
        const startTime = Date.now();
        const response = await fetch(healthUrl, {
          method: 'GET',
          headers: {
            'X-Request-ID': 'diagnose-ping-' + Date.now()
          }
        });
        const latency = Date.now() - startTime;

        if (response.ok) {
          let body;
          try {
            body = await response.json();
          } catch (_) {
            body = { message: 'Text response parsed' };
          }
          this.logToConsole(`[PASS] Ping OK: HTTP ${response.status} (${latency}ms)`, 'success');
          this.logToConsole(`[BODY] ${JSON.stringify(body)}`, 'success');
        } else {
          this.logToConsole(`[FAIL] Ping failed: HTTP ${response.status} - ${response.statusText}`, 'error');
        }

        // Validate Key POST /api/v1/auth/verify (if key supplied)
        if (testKey) {
          const authUrl = `${testUrl.replace(/\/$/, '')}/api/v1/auth/verify`;
          this.logToConsole(`[AUTH] POST ${authUrl}`, 'info');

          const authResponse = await fetch(authUrl, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'X-API-Key': testKey,
              'X-Request-ID': 'diagnose-auth-' + Date.now()
            },
            body: JSON.stringify({ api_key: testKey })
          });

          if (authResponse.ok) {
            this.logToConsole(`[PASS] Key validation successful: HTTP ${authResponse.status}`, 'success');
          } else {
            let errorText = '';
            try {
              errorText = await authResponse.text();
            } catch (_) {}
            this.logToConsole(`[FAIL] Key validation rejected: HTTP ${authResponse.status}. Response: ${errorText}`, 'error');
          }
        } else {
          this.logToConsole('[WARN] Skipping API key verification: No key entered.', 'warning');
        }

      } catch (error) {
        this.logToConsole(`[ERROR] Network error: Failed to fetch. ${error.message}`, 'error');
        this.logToConsole('Please verify the URL is correct, the backend is running, and CORS is configured.', 'error');
      } finally {
        this.testBtn.disabled = false;
        this.testBtn.innerText = '⚡ Run Connectivity Test';
      }
    },

    logToConsole(text, type = 'info') {
      let color = 'var(--on-surface-variant)';
      if (type === 'success') color = 'var(--emerald-success)';
      if (type === 'error') color = 'var(--rose-error)';
      if (type === 'warning') color = 'var(--amber-warning)';

      const line = document.createElement('div');
      line.style.color = color;
      line.style.marginBottom = '4px';
      line.innerText = text;

      this.consoleEl.appendChild(line);
      this.consoleEl.scrollTop = this.consoleEl.scrollHeight;
    },

    destroy() {
      console.log('Settings controller destroyed');
      if (this.form && this._boundHandleSave) {
        this.form.removeEventListener('submit', this._boundHandleSave);
      }
      if (this.toggleKeyBtn && this._boundHandleToggleKey) {
        this.toggleKeyBtn.removeEventListener('click', this._boundHandleToggleKey);
      }
      if (this.resetBtn && this._boundHandleReset) {
        this.resetBtn.removeEventListener('click', this._boundHandleReset);
      }
      if (this.testBtn && this._boundHandleTestConnection) {
        this.testBtn.removeEventListener('click', this._boundHandleTestConnection);
      }
    }
  };
})();
