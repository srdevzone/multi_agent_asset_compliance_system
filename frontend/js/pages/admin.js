// js/pages/admin.js

// DOM Elements
const apiStatusBadge = document.getElementById('api-status-badge');
const activeAssetBadge = document.getElementById('active-asset-badge');
const configureApiKeyBtn = document.getElementById('configure-api-key-btn');

const targetAssetIdInput = document.getElementById('target-asset-id');
const fetchStatsBtn = document.getElementById('fetch-stats-btn');
const statsLoading = document.getElementById('stats-loading');
const statsContent = document.getElementById('stats-content');

// Stats Fields
const statsVectorCount = document.getElementById('stats-vector-count');
const statsTotalRuns = document.getElementById('stats-total-runs');
const statsNamespaceName = document.getElementById('stats-namespace-name');
const statsLatestRun = document.getElementById('stats-latest-run');

const countComplete = document.getElementById('count-complete');
const countInProgress = document.getElementById('count-inprogress');
const countFailed = document.getElementById('count-failed');
const countErased = document.getElementById('count-erased');

// Danger Zone Deletion Elements
const deleteAssetBtn = document.getElementById('delete-asset-btn');
const erasureModal = document.getElementById('erasure-modal');
const erasureTargetDisplay = document.getElementById('erasure-target-display');
const expectedAssetIdText = document.getElementById('expected-asset-id-text');
const confirmAssetIdInput = document.getElementById('confirm-asset-id-input');
const confirmationMismatch = document.getElementById('confirmation-mismatch');

const checkVectorDeletion = document.getElementById('check-vector-deletion');
const checkDbErasure = document.getElementById('check-db-erasure');
const checkS3Erasure = document.getElementById('check-s3-erasure');

const executeErasureBtn = document.getElementById('execute-erasure-btn');
const cancelErasureBtn = document.getElementById('cancel-erasure-modal-btn');
const closeErasureBtn = document.getElementById('close-erasure-modal-btn');

// API Key Modal Elements
const apiKeyModal = document.getElementById('api-key-modal');
const apiKeyInput = document.getElementById('api-key-input');
const saveApiKeyBtn = document.getElementById('save-api-modal-btn');
const cancelApiKeyBtn = document.getElementById('cancel-api-modal-btn');
const closeApiKeyBtn = document.getElementById('close-api-modal-btn');

// Page state
let currentActiveAssetId = '';

// Initialize page
async function init() {
  // 1. Setup dev mode / default keys
  await window.Config.fetchAndSetupDevMode();

  // 2. Load API Key status
  updateApiKeyStatus();

  // 3. Load active Asset ID
  currentActiveAssetId = window.Config.getCurrentAssetId();
  targetAssetIdInput.value = currentActiveAssetId;
  activeAssetBadge.textContent = currentActiveAssetId;

  // 4. Fetch initial stats
  if (window.Config.getApiKey()) {
    await fetchStats(currentActiveAssetId);
  } else {
    window.ApiClient.showToast("API Key is not configured. Please set the key first.", "warning");
    apiKeyModal.classList.add('open');
  }

  // 5. Setup event listeners
  setupEventListeners();
}

// Update API status display
function updateApiKeyStatus() {
  window.Utils.renderApiKeyStatus(apiStatusBadge, window.Config.getApiKey());
}

// Fetch Asset Statistics
async function fetchStats(assetId) {
  if (!assetId) {
    window.ApiClient.showToast("Please enter a valid Asset ID.", "warning");
    return;
  }

  statsContent.style.display = 'none';
  statsLoading.style.display = 'flex';

  try {
    const res = await window.ApiClient.getAssetStats(assetId);
    
    // Save as current globally active asset if successful
    window.Config.setCurrentAssetId(assetId);
    currentActiveAssetId = assetId;
    activeAssetBadge.textContent = assetId;
    targetAssetIdInput.value = assetId;

    // Fill metrics
    statsVectorCount.textContent = res.pinecone_vector_count !== undefined ? res.pinecone_vector_count : 0;
    statsTotalRuns.textContent = res.total_audit_runs !== undefined ? res.total_audit_runs : 0;
    statsNamespaceName.textContent = res.pinecone_namespace || `asset_${assetId}`;
    
    if (res.latest_audit_run_at) {
      const date = new Date(res.latest_audit_run_at);
      statsLatestRun.textContent = date.toLocaleDateString() + ' ' + date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } else {
      statsLatestRun.textContent = 'Never';
    }

    // Fill status breakdowns
    const statusCounts = res.audit_run_status_counts || {};
    countComplete.textContent = statusCounts.COMPLETE || 0;
    countInProgress.textContent = statusCounts.IN_PROGRESS || 0;
    countFailed.textContent = statusCounts.FAILED || 0;
    countErased.textContent = statusCounts.ERASED || 0;

  } catch (error) {
    console.error("Failed to load statistics:", error);
    // Reset fields on error
    statsVectorCount.textContent = '0';
    statsTotalRuns.textContent = '0';
    statsNamespaceName.textContent = 'N/A';
    statsLatestRun.textContent = 'N/A';
    countComplete.textContent = '0';
    countInProgress.textContent = '0';
    countFailed.textContent = '0';
    countErased.textContent = '0';
  } finally {
    statsLoading.style.display = 'none';
    statsContent.style.display = 'block';
  }
}

// Validation logic for GDPR Delete Confirmation
function validateErasureConfirmation() {
  const checkbox1 = checkVectorDeletion.checked;
  const checkbox2 = checkDbErasure.checked;
  const checkbox3 = checkS3Erasure.checked;
  const textInputVal = confirmAssetIdInput.value.trim();

  const textMatches = textInputVal === currentActiveAssetId;

  // Show/hide mismatch error text only when input is not empty and doesn't match
  if (textInputVal.length > 0 && !textMatches) {
    confirmationMismatch.style.display = 'block';
  } else {
    confirmationMismatch.style.display = 'none';
  }

  // Button should be active only when all 3 checks are checked and typed ID matches active Asset ID exactly
  if (checkbox1 && checkbox2 && checkbox3 && textMatches) {
    executeErasureBtn.disabled = false;
  } else {
    executeErasureBtn.disabled = true;
  }
}

// Reset the erasure modal fields
function resetErasureModal() {
  checkVectorDeletion.checked = false;
  checkDbErasure.checked = false;
  checkS3Erasure.checked = false;
  confirmAssetIdInput.value = '';
  confirmationMismatch.style.display = 'none';
  executeErasureBtn.disabled = true;
}

// Setup Event Listeners
function setupEventListeners() {

  // Fetch stats click
  fetchStatsBtn.addEventListener('click', () => {
    const val = targetAssetIdInput.value.trim();
    fetchStats(val);
  });

  // Fetch stats on pressing Enter in input
  targetAssetIdInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const val = targetAssetIdInput.value.trim();
      fetchStats(val);
    }
  });

  // API Key modal open/close
  configureApiKeyBtn.addEventListener('click', () => {
    apiKeyInput.value = window.Config.getApiKey();
  });
  const { closeModal: closeApiKeyModal } = window.Modal.bindStandardModal(
    'api-key-modal',
    [configureApiKeyBtn],
    [closeApiKeyBtn, cancelApiKeyBtn]
  );

  // Save API Key
  saveApiKeyBtn.addEventListener('click', async () => {
    const key = apiKeyInput.value.trim();
    if (!key) {
      window.ApiClient.showToast("Please enter an API Key", "warning");
      return;
    }

    saveApiKeyBtn.disabled = true;
    saveApiKeyBtn.textContent = "Verifying...";

    try {
      const res = await window.ApiClient.verifyApiKey(key);
      if (res.valid) {
        window.Config.setApiKey(key);
        updateApiKeyStatus();
        window.ApiClient.showToast("API Key verified and updated successfully!", "success");
        closeApiKeyModal();
        // Trigger statistics reload if successful
        fetchStats(currentActiveAssetId);
      } else {
        window.ApiClient.showToast("Invalid API Key. Please verify and try again.", "error");
      }
    } catch (e) {
      console.error(e);
    } finally {
      saveApiKeyBtn.disabled = false;
      saveApiKeyBtn.textContent = "Verify & Save";
    }
  });

  // GDPR Delete open modal
  deleteAssetBtn.addEventListener('click', () => {
    if (!window.Config.getApiKey()) {
      window.ApiClient.showToast("API Key is missing. Configure it first.", "warning");
      apiKeyModal.classList.add('open');
      return;
    }
    
    resetErasureModal();
    erasureTargetDisplay.textContent = currentActiveAssetId;
    expectedAssetIdText.textContent = currentActiveAssetId;
    erasureModal.classList.add('open');
  });

  const { closeModal: closeErasureModal } = window.Modal.bindStandardModal(
    'erasure-modal',
    [],
    [closeErasureBtn, cancelErasureBtn]
  );

  // Add validation listeners for GDPR deletion steps
  checkVectorDeletion.addEventListener('change', validateErasureConfirmation);
  checkDbErasure.addEventListener('change', validateErasureConfirmation);
  checkS3Erasure.addEventListener('change', validateErasureConfirmation);
  confirmAssetIdInput.addEventListener('input', validateErasureConfirmation);

  // Execute GDPR Erasure
  executeErasureBtn.addEventListener('click', async () => {
    executeErasureBtn.disabled = true;
    executeErasureBtn.textContent = "Erasing data...";
    cancelErasureBtn.disabled = true;
    closeErasureBtn.disabled = true;

    try {
      const res = await window.ApiClient.deleteAsset(currentActiveAssetId);
      window.ApiClient.showToast(res.message || `Asset '${currentActiveAssetId}' records erased successfully.`, "success");
      closeErasureModal();
      // Reload stats for the current asset to see the changes (e.g. 0 vectors, status counts reset/updated)
      await fetchStats(currentActiveAssetId);
    } catch (error) {
      console.error("Erasure failed:", error);
      executeErasureBtn.disabled = false;
      executeErasureBtn.textContent = "Permanently Erase All Data";
      cancelErasureBtn.disabled = false;
      closeErasureBtn.disabled = false;
    }
  });
}

// Start execution
document.addEventListener('DOMContentLoaded', init);
