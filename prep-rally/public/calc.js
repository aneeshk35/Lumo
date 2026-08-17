/* Lumo calculator — a small self-contained expression engine and grapher.
   No external scripts, so it works offline and inside the SAT-style match view.
   Supports + - * / ^, parentheses, implicit multiplication (2x, 3(x+1)),
   sin cos tan asin acos atan sqrt abs ln log exp, and the constants pi and e. */

(function () {
  const FUNCS = {
    sin: Math.sin, cos: Math.cos, tan: Math.tan,
    asin: Math.asin, acos: Math.acos, atan: Math.atan,
    sqrt: Math.sqrt, abs: Math.abs, exp: Math.exp,
    ln: Math.log, log: (v) => Math.log10(v),
    floor: Math.floor, ceil: Math.ceil, round: Math.round,
  };
  const CONSTS = { pi: Math.PI, e: Math.E };

  function tokenize(src) {
    const s = String(src).replace(/\s+/g, '');
    const out = [];
    let i = 0;
    while (i < s.length) {
      const c = s[i];
      if (/[0-9.]/.test(c)) {
        let j = i;
        while (j < s.length && /[0-9.]/.test(s[j])) j++;
        out.push({ t: 'num', v: parseFloat(s.slice(i, j)) });
        i = j;
      } else if (/[a-z]/i.test(c)) {
        let j = i;
        while (j < s.length && /[a-z]/i.test(s[j])) j++;
        const name = s.slice(i, j).toLowerCase();
        if (FUNCS[name]) out.push({ t: 'func', v: name });
        else if (CONSTS[name] !== undefined) out.push({ t: 'num', v: CONSTS[name] });
        else if (name === 'x') out.push({ t: 'var' });
        else throw new Error(`Unknown name "${name}"`);
        i = j;
      } else if ('+-*/^(),'.includes(c)) {
        out.push({ t: c });
        i++;
      } else {
        throw new Error(`Unexpected character "${c}"`);
      }
    }
    // implicit multiplication: 2x, 2(x), )(, x(, )x, 2sin(x)
    const withMul = [];
    for (let k = 0; k < out.length; k++) {
      const a = out[k], b = out[k + 1];
      withMul.push(a);
      if (!b) continue;
      const aEnd = a.t === 'num' || a.t === 'var' || a.t === ')';
      const bStart = b.t === 'num' || b.t === 'var' || b.t === '(' || b.t === 'func';
      if (aEnd && bStart) withMul.push({ t: '*' });
    }
    return withMul;
  }

  const PREC = { '+': 1, '-': 1, '*': 2, '/': 2, '^': 3 };

  // Shunting-yard to RPN.
  function toRPN(tokens) {
    const out = [], ops = [];
    let prevType = null;
    for (const tok of tokens) {
      if (tok.t === 'num' || tok.t === 'var') {
        out.push(tok);
      } else if (tok.t === 'func') {
        ops.push(tok);
      } else if (tok.t === ',') {
        while (ops.length && ops[ops.length - 1].t !== '(') out.push(ops.pop());
      } else if (PREC[tok.t]) {
        // unary minus / plus
        const unary = (tok.t === '-' || tok.t === '+') &&
          (prevType === null || prevType === '(' || PREC[prevType] !== undefined);
        if (unary) {
          out.push({ t: 'num', v: 0 });
          ops.push({ t: tok.t });
        } else {
          while (ops.length) {
            const top = ops[ops.length - 1];
            if (top.t === 'func' || (PREC[top.t] &&
              (PREC[top.t] > PREC[tok.t] || (PREC[top.t] === PREC[tok.t] && tok.t !== '^')))) {
              out.push(ops.pop());
            } else break;
          }
          ops.push({ t: tok.t });
        }
      } else if (tok.t === '(') {
        ops.push(tok);
      } else if (tok.t === ')') {
        while (ops.length && ops[ops.length - 1].t !== '(') out.push(ops.pop());
        if (!ops.length) throw new Error('Unbalanced parentheses');
        ops.pop();
        if (ops.length && ops[ops.length - 1].t === 'func') out.push(ops.pop());
      }
      prevType = tok.t;
    }
    while (ops.length) {
      const op = ops.pop();
      if (op.t === '(') throw new Error('Unbalanced parentheses');
      out.push(op);
    }
    return out;
  }

  function evalRPN(rpn, x) {
    const st = [];
    for (const tok of rpn) {
      if (tok.t === 'num') st.push(tok.v);
      else if (tok.t === 'var') st.push(x);
      else if (tok.t === 'func') {
        const a = st.pop();
        st.push(FUNCS[tok.v](a));
      } else {
        const b = st.pop(), a = st.pop();
        if (a === undefined || b === undefined) throw new Error('Incomplete expression');
        st.push(tok.t === '+' ? a + b : tok.t === '-' ? a - b :
                tok.t === '*' ? a * b : tok.t === '/' ? a / b : Math.pow(a, b));
      }
    }
    if (st.length !== 1) throw new Error('Incomplete expression');
    return st[0];
  }

  function compile(src) {
    // "y = 2x + 1" and "f(x) = ..." both graph the right-hand side.
    const body = String(src).replace(/^\s*(y|f\s*\(\s*x\s*\))\s*=/i, '');
    const rpn = toRPN(tokenize(body));
    const usesX = rpn.some((t) => t.t === 'var');
    return { fn: (x) => evalRPN(rpn, x), usesX };
  }

  window.LumoCalc = { compile, tokenize, toRPN, evalRPN };
})();
