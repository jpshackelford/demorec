/**
 * Get the current terminal buffer state including visible lines.
 * Used for checkpoint verification to check what's on screen.
 * 
 * @returns {{rows: number, cols: number, viewportY: number, visibleLines: string[]} | null}
 */
() => {
    if (!window.term) return null;

    const term = window.term;
    const buffer = term.buffer.active;

    const visibleLines = [];
    for (let i = 0; i < term.rows; i++) {
        const line = buffer.getLine(buffer.viewportY + i);
        if (line) {
            visibleLines.push(line.translateToString().trimEnd());
        }
    }

    return {
        rows: term.rows,
        cols: term.cols,
        viewportY: buffer.viewportY,
        visibleLines: visibleLines
    };
}
