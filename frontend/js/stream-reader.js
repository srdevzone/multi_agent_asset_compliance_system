// js/stream-reader.js

const StreamReader = {
  /**
   * Reads a ReadableStream from a Fetch Response and parses it as NDJSON.
   * @param {Response} response - The fetch Response object containing the body stream.
   * @param {Object} callbacks - Callback functions for stream events.
   * @param {Function} callbacks.onNodeComplete - Called when a LangGraph node finishes.
   * @param {Function} callbacks.onVerdict - Called when the final compliance verdict is received.
   * @param {Function} callbacks.onError - Called when an error occurs during streaming or parsing.
   * @param {Function} callbacks.onEnd - Called when the stream completes successfully.
   */
  async read(response, { onNodeComplete, onVerdict, onError, onEnd } = {}) {
    if (!response.body) {
      const err = new Error("Response body is not readable.");
      if (onError) onError(err);
      if (onEnd) onEnd();
      return;
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    try {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop(); // Keep the last incomplete chunk in the buffer

        for (const line of lines) {
          const trimmedLine = line.trim();
          if (!trimmedLine) continue;

          try {
            const parsed = JSON.parse(trimmedLine);
            
            // Check for errors reported by the stream itself
            if (parsed.error || (parsed.errors && parsed.errors.length > 0)) {
              const errMsg = parsed.error?.message || parsed.error || parsed.errors.join(", ");
              if (onError) onError(new Error(errMsg));
              continue;
            }

            // Route based on event type
            if (parsed.event === "node_complete") {
              if (onNodeComplete) onNodeComplete(parsed);
            } else if (parsed.event === "verdict") {
              if (onVerdict) onVerdict(parsed.verdict);
            } else if (parsed.compliance_status) {
              // Fallback if the final verdict is not wrapped in event: 'verdict'
              if (onVerdict) onVerdict(parsed);
            }
          } catch (err) {
            console.error("Failed to parse stream line:", trimmedLine, err);
            if (onError) onError(new Error(`Parse error: ${err.message}. Line: ${trimmedLine}`));
          }
        }
      }

      // Process any remaining text in the buffer after stream ends
      const remaining = buffer.trim();
      if (remaining) {
        try {
          const parsed = JSON.parse(remaining);
          if (parsed.error || (parsed.errors && parsed.errors.length > 0)) {
            const errMsg = parsed.error?.message || parsed.error || parsed.errors.join(", ");
            if (onError) onError(new Error(errMsg));
          } else if (parsed.event === "node_complete") {
            if (onNodeComplete) onNodeComplete(parsed);
          } else if (parsed.event === "verdict") {
            if (onVerdict) onVerdict(parsed.verdict);
          } else if (parsed.compliance_status) {
            if (onVerdict) onVerdict(parsed);
          }
        } catch (err) {
          console.error("Failed to parse remaining stream buffer:", remaining, err);
          if (onError) onError(new Error(`Parse error: ${err.message}. Line: ${remaining}`));
        }
      }
      
      if (onEnd) onEnd();
    } catch (err) {
      console.error("Stream reading interrupted:", err);
      if (onError) onError(err);
      if (onEnd) onEnd();
    } finally {
      reader.releaseLock();
    }
  }
};

// Expose to window for vanilla JS access
window.StreamReader = StreamReader;
