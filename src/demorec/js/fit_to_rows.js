/**
 * Iteratively adjust font size to achieve target row count.
 * Call this in a loop until done=true or max iterations reached.
 * 
 * @param {number} desiredRows - Target number of rows
 * @returns {{rows: number, cols: number, fontSize: number, done: boolean} | null}
 */
(desiredRows) => {
    if (!window.term) return null;

    const term = window.term;
    const currentRows = term.rows;
    const currentFontSize = term.options.fontSize || 14;

    if (currentRows === desiredRows) {
        return {
            rows: currentRows,
            cols: term.cols,
            fontSize: currentFontSize,
            done: true
        };
    }

    const newFontSize = Math.round(currentFontSize * (currentRows / desiredRows));
    term.options.fontSize = newFontSize;
    term.fit();

    return {
        rows: term.rows,
        cols: term.cols,
        fontSize: newFontSize,
        done: term.rows === desiredRows
    };
}
