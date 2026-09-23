/* Ingest Assets Page Controller - Asset Compliance AI */

(function () {
  window.PageControllers = window.PageControllers || {};

  window.PageControllers.ingest = {
    selectedFiles: [],
    activeTab: 'tab-direct',
    jsonValid: false,

    init() {
      console.log('Ingest controller initialized');
      this.selectedFiles = [];
      this.activeTab = 'tab-direct';
      this.jsonValid = false;

      // Dom cache
      this.form = document.getElementById('doc-ingest-form');
      this.assetIdInput = document.getElementById('ingest-asset-id');
      this.assetIdError = document.getElementById('asset-id-validation-error');
      
      this.tabHeaders = document.querySelectorAll('.ingest-tab-header');
      this.tabContents = document.querySelectorAll('.ingest-tab-content');

      // Tab 1 Elements
      this.directDropzone = document.getElementById('direct-upload-dropzone');
      this.directFileInput = document.getElementById('direct-file-input');
      this.directFileList = document.getElementById('direct-file-list');
      this.directProgressContainer = document.getElementById('direct-upload-progress-container');
      this.directProgressBar = document.getElementById('direct-upload-progress-bar');
      this.directError = document.getElementById('direct-validation-error');

      // Tab 2 Elements
      this.jsonTextarea = document.getElementById('json-payload-textarea');
      this.jsonBadge = document.getElementById('json-validation-badge');
      this.jsonError = document.getElementById('json-validation-error');

      // Tab 3 Elements
      this.jsonFileDropzone = document.getElementById('json-file-dropzone');
      this.jsonFileInput = document.getElementById('json-file-input');
      this.jsonFileError = document.getElementById('json-file-validation-error');

      // Result Panel Elements
      this.resultPanel = document.getElementById('ingest-result-panel');
      this.resultStatusBadge = document.getElementById('result-status-badge');
      this.resultNamespace = document.getElementById('result-namespace');
      this.resultAssetId = document.getElementById('result-asset-id');
      this.resultDocsProcessed = document.getElementById('result-docs-processed');
      this.resultVectorsUpserted = document.getElementById('result-vectors-upserted');
      this.resultVectorsDeleted = document.getElementById('result-vectors-deleted');
      this.resultCompletedAt = document.getElementById('result-completed-at');

      this.submitBtn = document.getElementById('submit-ingest-btn');
      this.eventValidationError = document.getElementById('event-validation-error');

      // Setup default Asset ID if available
      if (window.Config && typeof window.Config.getCurrentAssetId === 'function') {
        this.assetIdInput.value = window.Config.getCurrentAssetId();
      }

      // Bind Listeners
      this.bindEvents();
      
      // Initial validation on load
      this.validateJsonRealtime();
      this.checkEventAndTabConstraints();
    },

    bindEvents() {
      // Form submit
      this.onSubmitBound = this.handleSubmit.bind(this);
      this.form.addEventListener('submit', this.onSubmitBound);

      // Tab switching
      this.tabHeaders.forEach(header => {
        header.addEventListener('click', () => {
          const tabId = header.getAttribute('data-tab');
          this.switchTab(tabId);
        });
      });

      // Asset ID input validation
      this.onAssetIdInputBound = () => {
        this.validateAssetIdField();
        this.checkEventAndTabConstraints();
      };
      this.assetIdInput.addEventListener('input', this.onAssetIdInputBound);

      // Ingest Lifecycle Event radios validation
      this.onEventRadioChangeBound = () => {
        this.checkEventAndTabConstraints();
      };
      const eventRadios = this.form.querySelectorAll('input[name="ingest-event"]');
      eventRadios.forEach(radio => {
        radio.addEventListener('change', this.onEventRadioChangeBound);
      });

      // Tab 1 Dropzone & File Input
      this.directDropzoneClickBound = () => this.directFileInput.click();
      this.directDropzone.addEventListener('click', this.directDropzoneClickBound);
      this.onDirectFileChangeBound = (e) => this.handleDirectFileSelect(e);
      this.directFileInput.addEventListener('change', this.onDirectFileChangeBound);
      
      this._directDropzoneHandlers = this.setupDropzoneEvents(this.directDropzone, (files) => this.addDirectFiles(files));

      // Tab 2 Textarea
      this.onJsonInputBound = () => this.validateJsonRealtime();
      this.jsonTextarea.addEventListener('input', this.onJsonInputBound);

      // Tab 3 Dropzone & File Input
      this.jsonFileDropzoneClickBound = () => this.jsonFileInput.click();
      this.jsonFileDropzone.addEventListener('click', this.jsonFileDropzoneClickBound);
      this.onJsonFileChangeBound = (e) => this.handleJsonFileSelect(e);
      this.jsonFileInput.addEventListener('change', this.onJsonFileChangeBound);
      
      this._jsonFileDropzoneHandlers = this.setupDropzoneEvents(this.jsonFileDropzone, (files) => this.handleJsonFileDrop(files));
    },

    setupDropzoneEvents(dropzone, onFilesDropped) {
      const handlers = {};

      handlers.dragenter = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
      };
      handlers.dragover = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.add('dragover');
      };
      handlers.dragleave = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
      };
      handlers.drop = (e) => {
        e.preventDefault();
        e.stopPropagation();
        dropzone.classList.remove('dragover');
        const dt = e.dataTransfer;
        const files = dt.files;
        if (files && files.length > 0) {
          onFilesDropped(files);
        }
      };

      dropzone.addEventListener('dragenter', handlers.dragenter, false);
      dropzone.addEventListener('dragover', handlers.dragover, false);
      dropzone.addEventListener('dragleave', handlers.dragleave, false);
      dropzone.addEventListener('drop', handlers.drop, false);

      return handlers;
    },

    switchTab(tabId) {
      this.activeTab = tabId;
      
      // Update Tab Headers active state
      this.tabHeaders.forEach(header => {
        if (header.getAttribute('data-tab') === tabId) {
          header.classList.add('active');
        } else {
          header.classList.remove('active');
        }
      });

      // Update Tab Contents active state
      this.tabContents.forEach(content => {
        if (content.id === tabId) {
          content.classList.add('active');
        } else {
          content.classList.remove('active');
        }
      });

      // Clear general errors when switching
      if (this.directError) this.directError.style.display = 'none';
      if (this.jsonError) this.jsonError.style.display = 'none';
      if (this.jsonFileError) this.jsonFileError.style.display = 'none';

      this.checkEventAndTabConstraints();
    },

    validateAssetId(val) {
      if (!val || val.trim().length === 0) {
        return { valid: false, error: 'Asset ID is required.' };
      }
      const pattern = /^[a-zA-Z0-9\-_]+$/;
      if (!pattern.test(val)) {
        return { valid: false, error: 'Asset ID must contain only alphanumeric characters, hyphens, and underscores.' };
      }
      return { valid: true };
    },

    validateAssetIdField() {
      const val = this.assetIdInput.value.trim();
      const check = this.validateAssetId(val);
      if (!check.valid) {
        this.assetIdError.textContent = check.error;
        this.assetIdError.style.display = 'block';
        return false;
      } else {
        this.assetIdError.style.display = 'none';
        return true;
      }
    },

    checkEventAndTabConstraints() {
      // Clear errors
      this.eventValidationError.style.display = 'none';
      this.eventValidationError.textContent = '';
      
      const assetIdVal = this.assetIdInput.value.trim();
      const assetIdCheck = this.validateAssetId(assetIdVal);
      
      if (assetIdVal.length > 0 && !assetIdCheck.valid) {
        this.assetIdError.textContent = assetIdCheck.error;
        this.assetIdError.style.display = 'block';
      } else {
        this.assetIdError.style.display = 'none';
      }

      const eventVal = this.form.querySelector('input[name="ingest-event"]:checked')?.value;

      if (this.activeTab === 'tab-direct') {
        if (eventVal === 'update') {
          this.eventValidationError.textContent = "Direct file upload does not support the 'Update' event. Please use 'Create' or 'Add', or paste/upload a JSON payload with an 'update' event.";
          this.eventValidationError.style.display = 'block';
          this.submitBtn.disabled = true;
          return false;
        }

        const hasFiles = this.selectedFiles.length > 0;
        const isAssetIdValid = assetIdCheck.valid;

        this.submitBtn.disabled = !hasFiles || !isAssetIdValid;
      } else if (this.activeTab === 'tab-paste') {
        this.submitBtn.disabled = !this.jsonValid;
      } else {
        // Tab 3 JSON File upload (user must upload a file first, which auto-switches to Tab 2)
        this.submitBtn.disabled = true;
      }
    },

    addDirectFiles(files) {
      this.directError.style.display = 'none';

      Array.from(files).forEach(file => {
        // Size validation: 50MB limit
        if (file.size > 50 * 1024 * 1024) {
          if (window.Toast) {
            window.Toast.error(`File "${file.name}" exceeds the 50MB size limit.`);
          }
          return;
        }

        // Type validation
        const ext = file.name.split('.').pop().toLowerCase();
        const isPdf = ext === 'pdf';
        const isImage = ['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext);

        if (!isPdf && !isImage) {
          if (window.Toast) {
            window.Toast.error(`File "${file.name}" has an unsupported format. Select PDF or image files.`);
          }
          return;
        }

        // Duplicate check
        const isDuplicate = this.selectedFiles.some(f => f.name === file.name && f.size === file.size);
        if (!isDuplicate) {
          this.selectedFiles.push(file);
        }
      });

      this.renderFileList();
      this.checkEventAndTabConstraints();
    },

    handleDirectFileSelect(e) {
      if (e.target.files) {
        this.addDirectFiles(e.target.files);
        this.directFileInput.value = '';
      }
    },

    removeFile(index) {
      this.selectedFiles.splice(index, 1);
      this.renderFileList();
      this.checkEventAndTabConstraints();
    },

    renderFileList() {
      this.directFileList.innerHTML = '';
      if (this.selectedFiles.length === 0) {
        return;
      }

      this.selectedFiles.forEach((file, index) => {
        const item = document.createElement('div');
        item.className = 'ingest-file-item';
        
        const sizeStr = window.Utils.formatBytes(file.size);
        
        // Auto-infer type for display
        const ext = file.name.split('.').pop().toLowerCase();
        let inferredType = 'other';
        if (['png', 'jpg', 'jpeg', 'webp', 'gif'].includes(ext)) {
          inferredType = 'installation_image';
        } else if (ext === 'pdf') {
          inferredType = 'compliance_spec';
          if (file.name.toLowerCase().includes('manual') || file.name.toLowerCase().includes('user')) {
            inferredType = 'user_manual';
          } else if (file.name.toLowerCase().includes('safety') || file.name.toLowerCase().includes('msds')) {
            inferredType = 'safety_sheet';
          }
        }

        item.innerHTML = `
          <div class="file-item-header">
            <div class="file-item-info">
              <span class="file-item-name">${window.Utils.escapeHtml(file.name)}</span>
              <span class="file-item-meta">${sizeStr} | Inferred: <strong>${inferredType}</strong></span>
            </div>
            <div class="file-item-controls">
              <button type="button" class="btn-remove-file" data-index="${index}">🗑️</button>
            </div>
          </div>
        `;
        
        item.querySelector('.btn-remove-file').addEventListener('click', () => {
          this.removeFile(index);
        });

        this.directFileList.appendChild(item);
      });
    },

    handleJsonFileDrop(files) {
      this.jsonFileError.style.display = 'none';
      if (files.length === 0) return;
      const file = files[0];

      if (file.type !== 'application/json' && !file.name.endsWith('.json')) {
        this.showJsonFileError('Only JSON (.json) files are supported.');
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target.result;
        try {
          // Check JSON syntax
          JSON.parse(text);
          
          this.jsonTextarea.value = text;
          this.validateJsonRealtime();
          this.switchTab('tab-paste');
          
          if (window.Toast) {
            window.Toast.success('JSON configuration loaded successfully.');
          }
        } catch (err) {
          this.showJsonFileError(`Failed to parse JSON file: ${err.message}`);
        }
      };
      reader.onerror = () => {
        this.showJsonFileError('Error reading file.');
      };
      reader.readAsText(file);
    },

    handleJsonFileSelect(e) {
      if (e.target.files) {
        this.handleJsonFileDrop(e.target.files);
        this.jsonFileInput.value = '';
      }
    },

    showJsonFileError(msg) {
      this.jsonFileError.textContent = msg;
      this.jsonFileError.style.display = 'block';
      if (window.Toast) {
        window.Toast.error(msg);
      }
    },

    validateJsonPayload(text) {
      try {
        if (!text.trim()) {
          return { valid: false, error: 'JSON payload is empty.' };
        }
        const payload = JSON.parse(text);
        if (typeof payload !== 'object' || payload === null) {
          return { valid: false, error: 'Payload must be a JSON object.' };
        }
        if (!payload.asset_id || typeof payload.asset_id !== 'string' || payload.asset_id.trim().length === 0) {
          return { valid: false, error: 'asset_id is required and must be a non-empty string.' };
        }
        if (!['create', 'update', 'add'].includes(payload.event)) {
          return { valid: false, error: 'event must be one of: "create", "update", "add".' };
        }
        if (!Array.isArray(payload.documents)) {
          return { valid: false, error: 'documents must be an array.' };
        }
        if (payload.documents.length < 1 || payload.documents.length > 50) {
          return { valid: false, error: 'documents array must contain between 1 and 50 documents.' };
        }
        if (payload.event === 'update' && payload.documents.length !== 1) {
          return { valid: false, error: "update event requires exactly one document in the 'documents' list." };
        }
        
        // Validate each document
        const s3KeyPattern = /^[a-zA-Z0-9/_\-\.]+$/;
        const docTypes = ["user_manual", "safety_sheet", "compliance_spec", "installation_image", "other"];
        for (let i = 0; i < payload.documents.length; i++) {
          const doc = payload.documents[i];
          if (typeof doc !== 'object' || doc === null) {
            return { valid: false, error: `documents[${i}] must be an object.` };
          }
          if (!doc.s3_key || typeof doc.s3_key !== 'string' || !s3KeyPattern.test(doc.s3_key)) {
            return { valid: false, error: `documents[${i}].s3_key "${doc.s3_key || ''}" is invalid. Must match pattern ^[a-zA-Z0-9/_\\-\\.]+$ (no spaces or special characters).` };
          }
          if (!doc.doc_id || typeof doc.doc_id !== 'string' || doc.doc_id.trim().length === 0) {
            return { valid: false, error: `documents[${i}].doc_id is required and must be a non-empty string.` };
          }
          if (!doc.doc_type || !docTypes.includes(doc.doc_type)) {
            return { valid: false, error: `documents[${i}].doc_type must be one of: ${docTypes.join(', ')}` };
          }
          if (!doc.filename || typeof doc.filename !== 'string' || doc.filename.trim().length === 0) {
            return { valid: false, error: `documents[${i}].filename is required and must be a non-empty string.` };
          }
        }
        return { valid: true, payload };
      } catch (err) {
        return { valid: false, error: `JSON Syntax Error: ${err.message}` };
      }
    },

    validateJsonRealtime() {
      const text = this.jsonTextarea.value;
      
      if (!text.trim()) {
        this.jsonBadge.textContent = 'JSON Format Pending';
        this.jsonBadge.className = 'badge badge-insufficient textarea-validation-badge';
        this.jsonError.style.display = 'none';
        this.jsonValid = false;
        this.checkEventAndTabConstraints();
        return;
      }

      const res = this.validateJsonPayload(text);
      if (res.valid) {
        this.jsonBadge.textContent = 'JSON Schema Valid';
        this.jsonBadge.className = 'badge badge-compliant textarea-validation-badge';
        this.jsonError.style.display = 'none';
        this.jsonValid = true;
      } else {
        this.jsonBadge.textContent = res.error.startsWith('JSON Syntax Error') ? 'Invalid JSON' : 'Invalid Schema';
        this.jsonBadge.className = 'badge badge-non-compliant textarea-validation-badge';
        this.jsonError.textContent = res.error;
        this.jsonError.style.display = 'block';
        this.jsonValid = false;
      }
      this.checkEventAndTabConstraints();
    },

    async handleSubmit(e) {
      e.preventDefault();

      const assetIdVal = this.assetIdInput.value.trim();
      const eventVal = this.form.querySelector('input[name="ingest-event"]:checked')?.value;

      // Ensure asset id is valid
      if (!this.validateAssetIdField()) {
        if (window.Toast) {
          window.Toast.error('Please fix the validation errors before submitting.');
        }
        return;
      }

      // Hide results prior to processing
      this.resultPanel.style.display = 'none';

      if (this.activeTab === 'tab-direct') {
        if (eventVal === 'update') {
          this.showDirectError("Direct upload does not support the 'Update' event.");
          return;
        }

        if (this.selectedFiles.length === 0) {
          this.showDirectError('Please select or drop at least one file to upload.');
          return;
        }

        this.setLoadingState(true);
        this.directProgressContainer.style.display = 'block';
        this.directProgressBar.style.width = '0%';

        const formData = new FormData();
        formData.append('asset_id', assetIdVal);
        formData.append('event', eventVal);
        
        this.selectedFiles.forEach(file => {
          formData.append('files', file);
        });

        // Use XMLHttpRequest to monitor upload progress
        const xhr = new XMLHttpRequest();
        const apiBaseUrl = window.Config && typeof window.Config.getApiBaseUrl === 'function' 
          ? window.Config.getApiBaseUrl() 
          : window.location.origin;
        
        xhr.open('POST', `${apiBaseUrl.replace(/\/$/, '')}/api/v1/ingest/upload`);
        
        const apiKey = window.Config ? window.Config.getApiKey() : '';
        if (apiKey) {
          xhr.setRequestHeader('X-API-Key', apiKey);
        }

        xhr.upload.addEventListener('progress', (progressEvent) => {
          if (progressEvent.lengthComputable) {
            const percent = Math.round((progressEvent.loaded / progressEvent.total) * 100);
            this.directProgressBar.style.width = `${percent}%`;
          }
        });

        xhr.onload = () => {
          this.setLoadingState(false);
          this.directProgressContainer.style.display = 'none';

          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              const response = JSON.parse(xhr.responseText);
              this.handleIngestSuccess(response);
            } catch (err) {
              this.showDirectError(`Failed to parse response: ${err.message}`);
            }
          } else {
            let errorMsg = `HTTP Error ${xhr.status}`;
            try {
              const errData = JSON.parse(xhr.responseText);
              errorMsg = errData?.detail?.message || errData?.detail || errorMsg;
              if (typeof errorMsg === 'object') {
                errorMsg = JSON.stringify(errorMsg);
              }
            } catch (_) {}
            this.showDirectError(errorMsg);
          }
        };

        xhr.onerror = () => {
          this.setLoadingState(false);
          this.directProgressContainer.style.display = 'none';
          this.showDirectError('Network connection failed. Ensure backend API is online.');
        };

        xhr.send(formData);

      } else if (this.activeTab === 'tab-paste') {
        const text = this.jsonTextarea.value;
        const check = this.validateJsonPayload(text);
        if (!check.valid) {
          this.showJsonError(check.error);
          return;
        }

        this.setLoadingState(true);

        try {
          const response = await window.ApiClient.request('/api/v1/ingest', {
            method: 'POST',
            body: JSON.stringify(check.payload)
          });
          this.handleIngestSuccess(response);
        } catch (err) {
          this.showJsonError(err.message || 'Ingestion request failed.');
        } finally {
          this.setLoadingState(false);
        }
      }
    },

    setLoadingState(isLoading) {
      if (isLoading) {
        this.submitBtn.disabled = true;
        this.submitBtn.innerText = '⚡ Processing Ingestion...';
        this.assetIdInput.disabled = true;
        this.form.querySelectorAll('input[name="ingest-event"]').forEach(r => r.disabled = true);
        this.tabHeaders.forEach(h => h.disabled = true);
        if (this.jsonTextarea) this.jsonTextarea.disabled = true;
        if (this.directFileInput) this.directFileInput.disabled = true;
        if (this.jsonFileInput) this.jsonFileInput.disabled = true;
      } else {
        this.submitBtn.disabled = false;
        this.submitBtn.innerText = '⚡ Submit Document Ingestion';
        this.assetIdInput.disabled = false;
        this.form.querySelectorAll('input[name="ingest-event"]').forEach(r => r.disabled = false);
        this.tabHeaders.forEach(h => h.disabled = false);
        if (this.jsonTextarea) this.jsonTextarea.disabled = false;
        if (this.directFileInput) this.directFileInput.disabled = false;
        if (this.jsonFileInput) this.jsonFileInput.disabled = false;
        this.checkEventAndTabConstraints();
      }
    },

    handleIngestSuccess(data) {
      if (window.Toast) {
        window.Toast.success('Document ingestion completed successfully!');
      }

      if (window.Config && typeof window.Config.addActivity === 'function') {
        window.Config.addActivity(
          'Document Ingestion', 
          `Asset ID: ${data.asset_id} | Namespace: ${data.namespace} | Processed: ${data.documents_processed} docs`, 
          'success'
        );
      }

      // Populate Result Panel
      this.resultNamespace.textContent = data.namespace || '-';
      this.resultAssetId.textContent = data.asset_id || '-';
      this.resultDocsProcessed.textContent = data.documents_processed !== undefined ? data.documents_processed : 0;
      this.resultVectorsUpserted.textContent = data.vectors_upserted !== undefined ? data.vectors_upserted : 0;
      this.resultVectorsDeleted.textContent = data.vectors_deleted !== undefined ? data.vectors_deleted : 0;
      
      const timestamp = data.completed_at ? new Date(data.completed_at).toLocaleString() : new Date().toLocaleString();
      this.resultCompletedAt.textContent = timestamp;

      // Show Result Panel
      this.resultPanel.style.display = 'block';

      // Scroll to Result Panel
      this.resultPanel.scrollIntoView({ behavior: 'smooth', block: 'start' });

      // If Tab 1 was active, clear file list
      if (this.activeTab === 'tab-direct') {
        this.selectedFiles = [];
        this.renderFileList();
      }
      this.checkEventAndTabConstraints();
    },

    showDirectError(msg) {
      this.directError.textContent = msg;
      this.directError.style.display = 'block';
      if (window.Toast) {
        window.Toast.error(msg);
      }
    },

    showJsonError(msg) {
      this.jsonError.textContent = msg;
      this.jsonError.style.display = 'block';
      if (window.Toast) {
        window.Toast.error(msg);
      }
    },

    destroy() {
      console.log('Ingest controller destroyed');
      if (this.form && this.onSubmitBound) {
        this.form.removeEventListener('submit', this.onSubmitBound);
      }
      if (this.assetIdInput && this.onAssetIdInputBound) {
        this.assetIdInput.removeEventListener('input', this.onAssetIdInputBound);
      }
      if (this.jsonTextarea && this.onJsonInputBound) {
        this.jsonTextarea.removeEventListener('input', this.onJsonInputBound);
      }
      if (this.directDropzone && this.directDropzoneClickBound) {
        this.directDropzone.removeEventListener('click', this.directDropzoneClickBound);
      }
      if (this.directFileInput && this.onDirectFileChangeBound) {
        this.directFileInput.removeEventListener('change', this.onDirectFileChangeBound);
      }
      if (this.jsonFileDropzone && this.jsonFileDropzoneClickBound) {
        this.jsonFileDropzone.removeEventListener('click', this.jsonFileDropzoneClickBound);
      }
      if (this.jsonFileInput && this.onJsonFileChangeBound) {
        this.jsonFileInput.removeEventListener('change', this.onJsonFileChangeBound);
      }
      if (this._directDropzoneHandlers && this.directDropzone) {
        const h = this._directDropzoneHandlers;
        this.directDropzone.removeEventListener('dragenter', h.dragenter, false);
        this.directDropzone.removeEventListener('dragover', h.dragover, false);
        this.directDropzone.removeEventListener('dragleave', h.dragleave, false);
        this.directDropzone.removeEventListener('drop', h.drop, false);
      }
      if (this._jsonFileDropzoneHandlers && this.jsonFileDropzone) {
        const h = this._jsonFileDropzoneHandlers;
        this.jsonFileDropzone.removeEventListener('dragenter', h.dragenter, false);
        this.jsonFileDropzone.removeEventListener('dragover', h.dragover, false);
        this.jsonFileDropzone.removeEventListener('dragleave', h.dragleave, false);
        this.jsonFileDropzone.removeEventListener('drop', h.drop, false);
      }
      const eventRadios = this.form ? this.form.querySelectorAll('input[name="ingest-event"]') : [];
      eventRadios.forEach(radio => {
        if (this.onEventRadioChangeBound) {
          radio.removeEventListener('change', this.onEventRadioChangeBound);
        }
      });
    }
  };
})();
