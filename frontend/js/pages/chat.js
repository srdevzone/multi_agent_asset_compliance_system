// js/pages/chat.js

// DOM Elements
const apiStatusBadge = document.getElementById('api-status-badge');
const activeAssetBadge = document.getElementById('active-asset-badge');
const configureApiKeyBtn = document.getElementById('configure-api-key-btn');
const clearHistoryBtn = document.getElementById('clear-history-btn');

const assetIdInput = document.getElementById('asset-id-input');
const docTypeFilter = document.getElementById('doc-type-filter');

const editSpecBtn = document.getElementById('edit-spec-btn');
const editVerdictsBtn = document.getElementById('edit-verdicts-btn');

const chatMessagesContainer = document.getElementById('chat-messages-container');
const chatEmptyState = document.getElementById('chat-empty-state');
const chatQuestionInput = document.getElementById('chat-question-input');
const chatSendBtn = document.getElementById('chat-send-btn');
const charCounter = document.getElementById('char-counter');
const loadingIndicator = document.getElementById('loading-indicator');

const citationsContainer = document.getElementById('citations-container');
const citationsEmpty = document.getElementById('citations-empty');

// Modals
const apiKeyModal = document.getElementById('api-key-modal');
const apiKeyInput = document.getElementById('api-key-input');
const saveApiKeyBtn = document.getElementById('save-api-modal-btn');
const cancelApiKeyBtn = document.getElementById('cancel-api-modal-btn');
const closeApiKeyBtn = document.getElementById('close-api-modal-btn');

const assetSpecModal = document.getElementById('asset-spec-modal');
const specJsonTextarea = document.getElementById('spec-json-textarea');
const specJsonError = document.getElementById('spec-json-error');
const saveSpecBtn = document.getElementById('save-spec-modal-btn');
const cancelSpecBtn = document.getElementById('cancel-spec-modal-btn');
const closeSpecBtn = document.getElementById('close-spec-modal-btn');

const verdictsModal = document.getElementById('verdicts-modal');
const verdictsJsonTextarea = document.getElementById('verdicts-json-textarea');
const verdictsJsonError = document.getElementById('verdicts-json-error');
const saveVerdictsBtn = document.getElementById('save-verdicts-modal-btn');
const cancelVerdictsBtn = document.getElementById('cancel-verdicts-modal-btn');
const closeVerdictsBtn = document.getElementById('close-verdicts-modal-btn');

// Page State
let chatHistory = [];
let lastCitations = [];

// Initialize Page
async function init() {
  // 1. Setup dev mode / default keys
  await window.Config.fetchAndSetupDevMode();

  // 2. Load API Key status
  updateApiKeyStatus();

  // 3. Load input values from Config
  const assetId = window.Config.getCurrentAssetId();
  assetIdInput.value = assetId;
  activeAssetBadge.textContent = assetId;

  // 4. Load Chat History
  loadHistoryForAsset(assetId);

  // 5. Setup event listeners
  setupEventListeners();
}

// Update API status display
function updateApiKeyStatus() {
  window.Utils.renderApiKeyStatus(apiStatusBadge, window.Config.getApiKey());
}

// Load history from cache for an asset
function loadHistoryForAsset(assetId) {
  chatHistory = window.Config.getChatHistory(assetId);
  renderMessages();
  
  // Clear citations pane on reload unless there's a last citation in the history
  const lastAssistantMsg = [...chatHistory].reverse().find(m => m.role === 'assistant');
  if (lastAssistantMsg && lastAssistantMsg.sources) {
    renderCitations(lastAssistantMsg.sources);
  } else {
    renderCitations([]);
  }
}

// Map search path key to user friendly name
function getPathName(path) {
  switch (path) {
    case 'pinecone_rag':
      return 'Tier 1: Pinecone RAG';
    case 'asset_spec':
      return 'Tier 2: Asset Spec Fallback';
    case 'web_search':
      return 'Tier 3: DuckDuckGo Web Search';
    default:
      return 'Unknown Path';
  }
}

// Markdown parser
function parseMarkdown(text) {
  if (!text) return '';
  
  let escaped = text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
    
  // Code blocks: ```content```
  escaped = escaped.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code class="language-$1">$2</code></pre>');
  
  // Inline code: `content`
  escaped = escaped.replace(/`([^`\n]+)`/g, '<code>$1</code>');
  
  // Bold: **content**
  escaped = escaped.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
  
  // Italic: *content*
  escaped = escaped.replace(/\*([^\*]+)\*/g, '<em>$1</em>');
  
  // Bullet lists
  const lines = escaped.split('\n');
  let inList = false;
  let result = [];
  
  for (let i = 0; i < lines.length; i++) {
    let line = lines[i];
    const match = line.match(/^(\s*)([-*])\s+(.+)$/);
    if (match) {
      if (!inList) {
        inList = true;
        result.push('<ul>');
      }
      result.push(`<li>${match[3]}</li>`);
    } else {
      if (inList) {
        inList = false;
        result.push('</ul>');
      }
      result.push(line);
    }
  }
  if (inList) {
    result.push('</ul>');
  }
  
  escaped = result.join('\n');
  
  // Convert double newlines to paragraphs
  escaped = escaped.split(/\n{2,}/).map(p => {
    if (p.trim().startsWith('<pre>') || p.trim().startsWith('<ul>') || p.trim().startsWith('<li>')) {
      return p;
    }
    return `<p>${p.replace(/\n/g, '<br>')}</p>`;
  }).join('\n');
  
  return escaped;
}

// Render Messages inside the Chat Box
function renderMessages() {
  chatMessagesContainer.innerHTML = '';
  
  if (chatHistory.length === 0) {
    chatMessagesContainer.appendChild(chatEmptyState);
    return;
  }
  
  chatHistory.forEach(msg => {
    const msgElement = document.createElement('div');
    msgElement.className = `message message-${msg.role}`;
    
    if (msg.role === 'assistant') {
      if (msg.search_path) {
        const indicator = document.createElement('span');
        indicator.className = `search-path-indicator path-${msg.search_path}`;
        indicator.textContent = getPathName(msg.search_path);
        msgElement.appendChild(indicator);
      }
      
      const contentDiv = document.createElement('div');
      contentDiv.className = 'markdown-content';
      contentDiv.innerHTML = parseMarkdown(msg.content);
      msgElement.appendChild(contentDiv);
    } else {
      const textNode = document.createElement('div');
      textNode.textContent = msg.content;
      msgElement.appendChild(textNode);
    }
    
    if (msg.timestamp) {
      const timeDiv = document.createElement('div');
      timeDiv.className = 'message-time';
      timeDiv.textContent = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      msgElement.appendChild(timeDiv);
    }
    
    chatMessagesContainer.appendChild(msgElement);
  });
  
  // Scroll to bottom
  chatMessagesContainer.scrollTop = chatMessagesContainer.scrollHeight;
}

// Render Source Citations in the right drawer
function renderCitations(sources) {
  citationsContainer.innerHTML = '';

  if (!sources || sources.length === 0) {
    citationsContainer.appendChild(citationsEmpty);
    return;
  }

  sources.forEach(src => {
    window.CitationCard.render(citationsContainer, {
      filename: src.filename,
      excerpt: src.excerpt,
      score: src.score,
      docType: src.doc_type,
      page: src.page,
      onView: () => {
        window.ApiClient.showToast(`Previewing ${src.filename} is handled by the document manager.`, 'info');
      }
    });
  });
}

// Event Listeners setup
function setupEventListeners() {
  
  // API Key Modal open / close
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
  
  // Clear chat cache
  clearHistoryBtn.addEventListener('click', () => {
    const assetId = window.Config.getCurrentAssetId();
    if (confirm("Are you sure you want to clear the conversation history for this asset?")) {
      window.Config.clearChatHistory(assetId);
      loadHistoryForAsset(assetId);
      window.ApiClient.showToast("Local chat history cleared.", "info");
    }
  });

  // Asset ID change
  assetIdInput.addEventListener('change', () => {
    const val = assetIdInput.value.trim();
    if (val) {
      window.Config.setCurrentAssetId(val);
      activeAssetBadge.textContent = val;
      loadHistoryForAsset(val);
    }
  });

  // Edit Spec Modal
  editSpecBtn.addEventListener('click', () => {
    const spec = window.Config.getCurrentAssetSpec();
    specJsonTextarea.value = JSON.stringify(spec, null, 2);
    specJsonError.style.display = 'none';
  });
  const { closeModal: closeSpecModal } = window.Modal.bindStandardModal(
    'asset-spec-modal',
    [editSpecBtn],
    [closeSpecBtn, cancelSpecBtn]
  );

  saveSpecBtn.addEventListener('click', () => {
    try {
      const parsed = JSON.parse(specJsonTextarea.value);
      if (!parsed.name || !parsed.category) {
        throw new Error("Asset Spec must contain at least 'name' and 'category' properties.");
      }
      window.Config.setCurrentAssetSpec(parsed);
      closeSpecModal();
      window.ApiClient.showToast("Asset specification updated.", "success");
    } catch (e) {
      specJsonError.textContent = e.message || "Invalid JSON syntax.";
      specJsonError.style.display = 'block';
    }
  });

  // Edit Verdicts Modal
  editVerdictsBtn.addEventListener('click', () => {
    const verdicts = window.Config.getCurrentPreviousVerdicts();
    verdictsJsonTextarea.value = JSON.stringify(verdicts, null, 2);
    verdictsJsonError.style.display = 'none';
  });
  const { closeModal: closeVerdictsModal } = window.Modal.bindStandardModal(
    'verdicts-modal',
    [editVerdictsBtn],
    [closeVerdictsBtn, cancelVerdictsBtn]
  );

  saveVerdictsBtn.addEventListener('click', () => {
    try {
      const parsed = JSON.parse(verdictsJsonTextarea.value);
      if (!Array.isArray(parsed)) {
        throw new Error("Previous verdicts must be a JSON array.");
      }
      window.Config.setCurrentPreviousVerdicts(parsed);
      closeVerdictsModal();
      window.ApiClient.showToast("Previous audit verdicts updated.", "success");
    } catch (e) {
      verdictsJsonError.textContent = e.message || "Invalid JSON syntax.";
      verdictsJsonError.style.display = 'block';
    }
  });

  // Question Character counter
  chatQuestionInput.addEventListener('input', () => {
    const len = chatQuestionInput.value.length;
    charCounter.textContent = len;
    
    if (len > 2000) {
      charCounter.style.color = 'var(--rose-error)';
      chatSendBtn.disabled = true;
    } else if (len > 0) {
      charCounter.style.color = '';
      chatSendBtn.disabled = false;
    } else {
      charCounter.style.color = '';
      chatSendBtn.disabled = true;
    }
  });

  // Textarea submit on enter
  chatQuestionInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (!chatSendBtn.disabled) {
        submitQuestion();
      }
    }
  });

  // Click Send button
  chatSendBtn.addEventListener('click', submitQuestion);
}

// Submit Question flow
async function submitQuestion() {
  const question = chatQuestionInput.value.trim();
  const assetId = window.Config.getCurrentAssetId();
  const spec = window.Config.getCurrentAssetSpec();
  const verdicts = window.Config.getCurrentPreviousVerdicts();
  const docFilter = docTypeFilter.value || null;
  const apiKey = window.Config.getApiKey();

  if (!apiKey) {
    window.ApiClient.showToast("API Key is missing. Please click 'Configure API Key' first.", "warning");
    apiKeyModal.classList.add('open');
    return;
  }

  if (!question) return;

  // 1. Add user message locally
  const userMsg = {
    role: 'user',
    content: question,
    timestamp: new Date().toISOString()
  };
  chatHistory.push(userMsg);
  renderMessages();
  
  // Reset input state
  chatQuestionInput.value = '';
  charCounter.textContent = '0';
  chatSendBtn.disabled = true;
  
  // Show Loading state
  loadingIndicator.style.display = 'flex';
  chatQuestionInput.disabled = true;
  docTypeFilter.disabled = true;
  assetIdInput.disabled = true;
  editSpecBtn.disabled = true;
  editVerdictsBtn.disabled = true;
  
  try {
    // 2. Build payload history: API expects { role: "user" | "assistant", content: string }
    const apiHistory = chatHistory.slice(0, -1).map(h => ({
      role: h.role,
      content: h.content
    }));

    const chatRequest = {
      asset_id: assetId,
      asset_spec: spec,
      question: question,
      conversation_history: apiHistory,
      previous_verdicts: verdicts,
      doc_type_filter: docFilter
    };

    const res = await window.ApiClient.queryAsset(chatRequest);
    
    // 3. Add assistant response
    const assistantMsg = {
      role: 'assistant',
      content: res.answer,
      search_path: res.search_path,
      sources: res.sources,
      timestamp: new Date().toISOString()
    };
    chatHistory.push(assistantMsg);
    
    // 4. Update localStorage cache
    window.Config.saveChatHistory(assetId, chatHistory);
    
    // 5. Re-render
    renderMessages();
    renderCitations(res.sources);
    
  } catch (error) {
    console.error("Q&A call failed:", error);
    // Remove the last user message if the request failed to allow retrying
    chatHistory.pop();
    renderMessages();
    chatQuestionInput.value = question;
    charCounter.textContent = question.length;
    chatSendBtn.disabled = false;
  } finally {
    // Hide loading state
    loadingIndicator.style.display = 'none';
    chatQuestionInput.disabled = false;
    docTypeFilter.disabled = false;
    assetIdInput.disabled = false;
    editSpecBtn.disabled = false;
    editVerdictsBtn.disabled = false;
    chatQuestionInput.focus();
  }
}

// Start execution
document.addEventListener('DOMContentLoaded', init);
