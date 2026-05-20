/**
 * Utility functions for the js_sample fixture.
 */

export function clamp(value, min, max) {
    if (value < min) return min;
    if (value > max) return max;
    return value;
}

export function range(start, end, step = 1) {
    const result = [];
    for (let i = start; i < end; i += step) {
        result.push(i);
    }
    return result;
}

export function groupBy(array, keyFn) {
    const groups = {};
    for (const item of array) {
        const key = keyFn(item);
        if (!groups[key]) {
            groups[key] = [];
        }
        groups[key].push(item);
    }
    return groups;
}

export function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}
