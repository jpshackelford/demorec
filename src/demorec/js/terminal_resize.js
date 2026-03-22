/**
 * Terminal resize and font adjustment for xterm.js + ttyd.
 * 
 * This module handles:
 * 1. Making terminal container fill viewport
 * 2. Applying font/theme settings
 * 3. Calculating font size to achieve desired row count
 * 4. Syncing PTY via term.fit()
 */

/**
 * Initialize terminal with desired configuration.
 * Sets up container, applies styling, and fits terminal to viewport.
 * 
 * @param {Object} config - Configuration object
 * @param {number} config.fontSize - Base font size in pixels
 * @param {string} config.fontFamily - Font family string
 * @param {number} config.lineHeight - Line height multiplier
 * @param {Object} [config.theme] - Optional xterm.js theme object
 * @param {number} [config.desiredRows] - Target row count (adjusts font size)
 * @returns {Object|null} Result with rows, cols, fontSize, baselineRows
 */
function initializeTerminal(config) {
    if (!window.term) return null;
    
    // Step 1: Make container fill viewport
    const container = document.querySelector('#terminal-container') || 
                      document.querySelector('.xterm');
    if (container) {
        container.style.width = '100vw';
        container.style.height = '100vh';
        container.style.position = 'fixed';
        container.style.top = '0';
        container.style.left = '0';
        container.style.padding = '0';
        container.style.margin = '0';
    }
    
    // Step 2: Apply terminal options
    const term = window.term;
    term.options.fontFamily = config.fontFamily;
    term.options.lineHeight = config.lineHeight;
    term.options.cursorBlink = false;
    
    // Apply theme if provided
    if (config.theme) {
        term.options.theme = config.theme;
    }
    
    // Step 3: Initial fit to get baseline rows
    term.fit();
    
    let baselineRows = term.rows;
    let finalFontSize = config.fontSize;
    
    // Step 4: If desired rows specified, calculate font size
    // Font size scales inversely with row count:
    // - Fewer rows = larger font
    // - More rows = smaller font
    if (config.desiredRows && config.desiredRows !== baselineRows) {
        finalFontSize = Math.round(config.fontSize * (baselineRows / config.desiredRows));
        term.options.fontSize = finalFontSize;
        
        // Re-fit with new font size
        // term.fit() triggers onResize which sends RESIZE_TERMINAL to ttyd
        term.fit();
    } else {
        term.options.fontSize = finalFontSize;
        term.fit();
    }
    
    return { 
        rows: term.rows, 
        cols: term.cols,
        fontSize: term.options.fontSize,
        baselineRows: baselineRows
    };
}

/**
 * Refine terminal rows by adjusting font size iteratively.
 * Used when initial calculation doesn't achieve exact row count.
 * 
 * @param {number} desiredRows - Target row count
 * @returns {Object|null} Result with rows, cols, fontSize, done
 */
function refineTerminalRows(desiredRows) {
    if (!window.term) return null;
    
    const term = window.term;
    const currentRows = term.rows;
    const currentFontSize = term.options.fontSize || 14;
    
    // Already at desired rows
    if (currentRows === desiredRows) {
        return { 
            rows: currentRows, 
            cols: term.cols, 
            fontSize: currentFontSize, 
            done: true 
        };
    }
    
    // Fine-tune font size based on mismatch
    const newFontSize = Math.round(currentFontSize * (currentRows / desiredRows));
    term.options.fontSize = newFontSize;
    
    // term.fit() handles both xterm resize AND PTY sync
    term.fit();
    
    return { 
        rows: term.rows, 
        cols: term.cols,
        fontSize: newFontSize,
        done: term.rows === desiredRows
    };
}

// Export for use in Python via page.evaluate
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { initializeTerminal, refineTerminalRows };
}
