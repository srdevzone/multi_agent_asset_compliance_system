/* Login Page Controller - Asset Compliance AI */

(function () {
  window.PageControllers = window.PageControllers || {};

  window.PageControllers.login = {
    init() {
      console.log('Login controller initialized');
      this.loginForm = document.getElementById('login-form');
      this.apiKeyInput = document.getElementById('login-api-key');
      this.submitBtn = document.getElementById('login-submit-btn');
      this.alertContainer = document.getElementById('login-alert-container');
      
      this._boundHandleLogin = this.handleLogin.bind(this);
      if (this.loginForm) {
        this.loginForm.addEventListener('submit', this._boundHandleLogin);
      }

      this.checkDevMode();
    },

    async handleLogin(e) {
      e.preventDefault();
      
      const apiKey = this.apiKeyInput.value.trim();
      if (!apiKey) return;

      this.setLoading(true);
      this.showAlert('', 'clear');

      try {
        // Perform auth verification. We supply the api_key in both body and header to satisfy diverse backends.
        const response = await window.ApiClient.post(
          '/api/v1/auth/verify', 
          { api_key: apiKey }, 
          { headers: { 'X-API-Key': apiKey } }
        );

        console.log('Authentication verification response:', response);

        // Save key to config
        if (window.Config) {
          window.Config.set('apiKey', apiKey);
          window.Config.addActivity('Authentication', 'Successfully signed in using API Key', 'success');
        }

        if (window.Toast) {
          window.Toast.success('Session verified. Redirecting...');
        }

        // Redirect to dashboard
        setTimeout(() => {
          window.location.hash = '#/dashboard';
        }, 800);

      } catch (error) {
        console.error('Authentication verification failed:', error);
        
        let errorMsg = 'Failed to verify API Key. Please check the key and backend connection.';
        if (error.status === 401) {
          errorMsg = 'Invalid API Key. Please check your credentials and try again.';
        } else if (error.message) {
          errorMsg = error.message;
        }

        this.showAlert(errorMsg, 'error');
        
        if (window.Config) {
          window.Config.addActivity('Authentication', `Failed login attempt: ${errorMsg}`, 'error');
        }
        
        if (window.Toast) {
          window.Toast.error(errorMsg);
        }
      } finally {
        this.setLoading(false);
      }
    },

    async checkDevMode() {
      try {
        // Query dev mode configuration helper endpoint
        const config = await window.ApiClient.get('/api/v1/auth/config');
        if (config && (config.dev_mode || config.devMode || config.api_key || config.apiKey)) {
          const devKey = config.api_key || config.apiKey || '';
          
          const devHelper = document.getElementById('dev-helper-container');
          const autoBtn = document.getElementById('dev-autopopulate-btn');
          
          if (devHelper && autoBtn && devKey) {
            devHelper.style.display = 'block';
            autoBtn.addEventListener('click', (e) => {
              e.preventDefault();
              this.apiKeyInput.value = devKey;
              if (window.Toast) {
                window.Toast.info('Development key auto-populated.');
              }
            });
          }
        }
      } catch (e) {
        // Silence errors in production since /auth/config might not exist or be disabled
        console.log('Authentication config helper not active (likely non-dev mode or production).');
      }
    },

    setLoading(isLoading) {
      if (!this.submitBtn) return;
      if (isLoading) {
        this.submitBtn.disabled = true;
        this.submitBtn.innerText = 'Verifying...';
      } else {
        this.submitBtn.disabled = false;
        this.submitBtn.innerText = 'Verify Credentials';
      }
    },

    showAlert(message, type = 'error') {
      if (!this.alertContainer) return;
      if (type === 'clear') {
        this.alertContainer.innerHTML = '';
        return;
      }

      this.alertContainer.innerHTML = `
        <div class="alert alert-${type}">
          <strong style="text-transform: capitalize;">${type}:</strong> ${message}
        </div>
      `;
    },

    destroy() {
      console.log('Login controller destroyed');
      if (this.loginForm && this._boundHandleLogin) {
        this.loginForm.removeEventListener('submit', this._boundHandleLogin);
      }
    }
  };
})();
