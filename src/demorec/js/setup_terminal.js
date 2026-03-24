/**
 * Set up xterm.js terminal with full viewport and optional row targeting.
 * 
 * @param {Object} config - Terminal configuration
 * @param {number} config.fontSize - Base font size
 * @param {string} config.fontFamily - Font family string
 * @param {number} config.lineHeight - Line height multiplier
 * @param {Object} [config.theme] - xterm.js theme object
 * @param {number} [config.desiredRows] - Target number of rows
 * @returns {{rows: number, cols: number, fontSize: number, baselineRows: number} | null}
 */
(config) => {
    if (!window.term) return null;

    // Make container fill viewport
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

    const term = window.term;
    term.options.fontFamily = config.fontFamily;
    term.options.lineHeight = config.lineHeight;
    term.options.cursorBlink = false;

    if (config.theme) {
        term.options.theme = config.theme;
    }

    term.fit();
    const baselineRows = term.rows;
    let finalFontSize = config.fontSize;

    // Adjust font size to achieve desired rows
    if (config.desiredRows && config.desiredRows !== baselineRows) {
        finalFontSize = Math.round(config.fontSize * (baselineRows / config.desiredRows));
        term.options.fontSize = finalFontSize;
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
