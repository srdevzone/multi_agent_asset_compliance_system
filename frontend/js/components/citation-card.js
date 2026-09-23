// js/components/citation-card.js

(function () {
  const CitationCard = {
    /**
     * Render a single citation card into a container.
     * @param {HTMLElement} container - element to append the card to
     * @param {Object} citation
     * @param {string} [citation.title] - document title / filename
     * @param {string} [citation.filename] - alias for title
     * @param {string} [citation.text] - citation text body
     * @param {string} [citation.excerpt] - alias for text
     * @param {number} [citation.score] - match score (0-1)
     * @param {string} [citation.url] - external link URL
     * @param {string} [citation.docType] - document type label
     * @param {number|null} [citation.page] - page number
     * @param {Function} [citation.onView] - callback when "View Reference" is clicked
     * @returns {HTMLElement} the rendered card
     */
    render(container, citation) {
      const {
        title,
        filename,
        text,
        excerpt,
        score,
        url,
        docType,
        page,
        onView
      } = citation;

      const displayTitle = title || filename || 'Unknown Document';
      const displayText = text || excerpt || '';

      const card = document.createElement('div');
      card.className = 'citation-card';

      const metaParts = [];
      if (docType) metaParts.push(`Type: ${window.Utils.escapeHtml(docType)}`);
      if (page !== null && page !== undefined) metaParts.push(`Page ${page}`);
      const metaText = metaParts.length > 0 ? metaParts.join(' | ') : 'Page N/A';

      card.innerHTML = `
        <div class="citation-header">
          <span>📄</span>
          <span class="citation-filename">${window.Utils.escapeHtml(displayTitle)}</span>
          <span class="citation-meta">${metaText}</span>
        </div>
        <div class="citation-body">
          "${window.Utils.escapeHtml(displayText)}"
        </div>
        <div class="citation-footer">
          <span class="citation-score">Match: ${score !== undefined && score !== null ? (score * 100).toFixed(0) : 0}%</span>
          <a href="${url || '#'}" target="_blank" class="citation-link">View Section</a>
        </div>
      `;

      const link = card.querySelector('.citation-link');
      if (onView) {
        link.addEventListener('click', (e) => {
          e.preventDefault();
          onView(citation);
        });
      }

      container.appendChild(card);
      return card;
    }
  };

  window.CitationCard = CitationCard;
})();
