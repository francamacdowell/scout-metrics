import { clamp } from './utils.js';

class Calculator {
    constructor() {
        this.history = [];
        this.result = 0;
    }

    add(n) {
        this.result += n;
        this.history.push({ op: 'add', n });
        return this;
    }

    subtract(n) {
        this.result -= n;
        this.history.push({ op: 'subtract', n });
        return this;
    }

    multiply(n) {
        if (n === 0) {
            this.result = 0;
        } else {
            this.result *= n;
        }
        this.history.push({ op: 'multiply', n });
        return this;
    }

    divide(n) {
        if (n === 0) {
            throw new Error('Division by zero');
        }
        this.result /= n;
        this.history.push({ op: 'divide', n });
        return this;
    }

    clampResult(min, max) {
        this.result = clamp(this.result, min, max);
        return this;
    }

    reset() {
        this.result = 0;
        this.history = [];
        return this;
    }

    getValue() {
        return this.result;
    }
}

export function evaluate(expression) {
    const tokens = expression.trim().split(/\s+/);
    let acc = parseFloat(tokens[0]);
    for (let i = 1; i < tokens.length - 1; i += 2) {
        const op = tokens[i];
        const operand = parseFloat(tokens[i + 1]);
        switch (op) {
            case '+': acc += operand; break;
            case '-': acc -= operand; break;
            case '*': acc *= operand; break;
            case '/':
                if (operand === 0) throw new Error('Division by zero');
                acc /= operand;
                break;
            default:
                throw new Error(`Unknown operator: ${op}`);
        }
    }
    return acc;
}

export default Calculator;
