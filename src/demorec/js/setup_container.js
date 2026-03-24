/**
 * Simple terminal container setup for preview mode.
 * Applies basic styling and font configuration without row targeting.
 * 
 * @param {Object} config - Configuration object
 * @param {number} [config.fontSize] - Font size in pixels
 * @param {string} [config.fontFamily] - Font family string
 * @returns {{rows: number, cols: number} | null}
 */
(config) => {
    if (!window.term) return null;

    const container = document.querySelector('.xterm');
    if (container) {
        container.style.width = '100vw';
        container.style.height = '100vh';
        container.style.position = 'fixed';
        container.style.top = '0';
        container.style.left = '0';
    }

    if (config.fontSize) {
        term.options.fontSize = config.fontSize;
    }
    if (config.fontFamily) {
        term.options.fontFamily = config.fontFamily;
    }

    term.fit();

    return { rows: term.rows, cols: term.cols };
}
