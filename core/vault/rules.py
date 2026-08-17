"""
QuantOS — Obsidian Vault: the rule DSL
───────────────────────────────────────
Evaluates the expressions in a note's ```quantos-rules``` block against a
`MarketFacts`. This is the component that produces the actual PASS/FAIL — no
language model participates in it, by design.

Why a DSL and not `eval()`
──────────────────────────
The rules come from markdown files. Files are edited casually, sync through
Obsidian, and (once tracked) arrive on the VM through `git pull`. Handing
that text to `eval()` would make "anything that can write to the vault" equal
to "anything that can run code as the user holding the broker keys". Instead
the expression is parsed with `ast.parse(mode="eval")` and walked against a
whitelist: a fixed set of node types, a fixed function vocabulary, and no
attribute access, no subscripting other than the integer bar-lag form, no
names beyond the market facts. Anything outside that raises `RuleSyntaxError`
at PARSE time, which surfaces as UNAVAILABLE — a blocked gate, not a
crash mid-audit and not a silent skip.

The grammar
───────────
    close > sma(50)                      # comparison
    close > sma(50) > sma(150)           # chained, reads like the note does
    sma(200) > sma(200)[20]              # [n] = n bars ago
    volume_sma(5) / volume_sma(50) < 0.40
    close >= high(252) * 0.75
    rs_rating >= 70

Scalars:   close, bar_open, bar_high, bar_low, volume, rs_rating
Windows:   sma(n), ema(n), high(n), low(n), volume_sma(n)
Operators: > >= < <= == !=  and  + - * /  and  unary -  and  `and`/`or`
Lag:       any term may be suffixed [n] for "n bars ago"

Every term that resolves to a number is recorded, so a result can be rendered
with its live values substituted (see `RuleResult.detail`). An unevaluable
term — window not warmed up, fact never supplied — raises `InsufficientData`,
which becomes `passed=None`, which blocks.
"""

from __future__ import annotations

import ast
from typing import Optional

from core.vault.facts import MarketFacts
from core.vault.models import Rule, RuleResult


class RuleSyntaxError(ValueError):
    """The expression is not valid rule-DSL. Raised at parse time."""


class InsufficientData(Exception):
    """A term could not be computed from the data supplied."""

    def __init__(self, term: str) -> None:
        super().__init__(f"{term} could not be computed from the available history")
        self.term = term


# Node types the walker will descend into. Anything else — Attribute, Lambda,
# comprehensions, f-strings, walrus, starred args — is rejected at parse time.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression, ast.Compare, ast.BoolOp, ast.BinOp, ast.UnaryOp,
    ast.Call, ast.Name, ast.Constant, ast.Subscript, ast.Load,
    ast.Gt, ast.GtE, ast.Lt, ast.LtE, ast.Eq, ast.NotEq,
    ast.And, ast.Or, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.USub, ast.UAdd,
)

# name -> MarketFacts method taking (offset)
_SCALARS = {
    "close": "close",
    "bar_open": "bar_open",
    "bar_high": "bar_high",
    "bar_low": "bar_low",
    "volume": "volume",
    "rs_rating": "rs_rating",
}

# name -> MarketFacts method taking (period, offset)
_WINDOWS = {
    "sma": "sma",
    "ema": "ema",
    "high": "high",
    "low": "low",
    "volume_sma": "volume_sma",
}

VOCABULARY = tuple(sorted(_SCALARS)) + tuple(f"{fn}(n)" for fn in sorted(_WINDOWS))


def parse_expression(expression: str) -> ast.Expression:
    """Parse and validate one rule expression. Raises `RuleSyntaxError`.

    Validation happens here, not during evaluation, so a typo in a note is
    caught the moment the vault is loaded rather than on the one morning a
    signal actually fires.
    """
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as e:
        raise RuleSyntaxError(f"{expression!r} is not a valid expression: {e.msg}") from e

    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise RuleSyntaxError(
                f"{expression!r} uses {type(node).__name__}, which is not allowed "
                f"in a rule. Allowed vocabulary: {', '.join(VOCABULARY)}"
            )
        if isinstance(node, ast.Name) and node.id not in _SCALARS and node.id not in _WINDOWS:
            raise RuleSyntaxError(
                f"{expression!r} references unknown term {node.id!r}. "
                f"Allowed vocabulary: {', '.join(VOCABULARY)}"
            )
        if isinstance(node, ast.Call):
            _validate_call(expression, node)
        if isinstance(node, ast.Subscript):
            _lag_of(expression, node)      # validates the [n] form
        if isinstance(node, ast.Constant):
            # Numbers only. Caught here rather than at eval time so a note
            # containing `close > "sma(50)"` is rejected when the vault
            # loads, not on the morning it first matters.
            if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
                raise RuleSyntaxError(
                    f"{expression!r} contains the literal {node.value!r}; rules "
                    f"compare numbers only"
                )

    # A rule must be a question, not a number. `sma(50)` alone is almost
    # certainly a half-written rule, and treating its truthiness as a verdict
    # would quietly pass for any non-zero average.
    if not isinstance(tree.body, (ast.Compare, ast.BoolOp)):
        raise RuleSyntaxError(
            f"{expression!r} is not a comparison — a rule must state a condition "
            f"that can be true or false, e.g. 'close > sma(50)'"
        )
    return tree


def _validate_call(expression: str, node: ast.Call) -> None:
    if not isinstance(node.func, ast.Name) or node.func.id not in _WINDOWS:
        name = getattr(node.func, "id", type(node.func).__name__)
        raise RuleSyntaxError(
            f"{expression!r} calls unknown function {name!r}. "
            f"Allowed: {', '.join(sorted(_WINDOWS))}"
        )
    if node.keywords:
        raise RuleSyntaxError(f"{expression!r}: {node.func.id}() takes no keyword arguments")
    if len(node.args) != 1:
        raise RuleSyntaxError(
            f"{expression!r}: {node.func.id}() takes exactly one argument, "
            f"the lookback period — got {len(node.args)}"
        )
    arg = node.args[0]
    if not isinstance(arg, ast.Constant) or not isinstance(arg.value, int) or arg.value <= 0:
        raise RuleSyntaxError(
            f"{expression!r}: {node.func.id}()'s period must be a positive integer literal"
        )


def _lag_of(expression: str, node: ast.Subscript) -> int:
    """Extract and validate the `[n]` bar-lag on a subscript node."""
    index = node.slice
    if not isinstance(index, ast.Constant) or not isinstance(index.value, int) or index.value < 0:
        raise RuleSyntaxError(
            f"{expression!r}: the [n] suffix means 'n bars ago' and must be a "
            f"non-negative integer literal"
        )
    return index.value


def evaluate_rule(rule: Rule, facts: MarketFacts) -> RuleResult:
    """Evaluate one rule, capturing every term's live value for the report.

    Never raises for data reasons: an unevaluable term yields
    `passed=None`, which the auditor turns into INSUFFICIENT_DATA.
    """
    substitutions: dict[str, float] = {}
    try:
        tree = parse_expression(rule.expression)
    except RuleSyntaxError as e:
        return RuleResult(rule=rule, passed=None, error=str(e))

    try:
        outcome = _eval(tree.body, facts, offset=0, subs=substitutions)
    except InsufficientData as e:
        return RuleResult(rule=rule, passed=None, substitutions=substitutions,
                          error=f"{e.term} unavailable ({facts.bar_count} bars of history)")
    except RuleSyntaxError as e:
        # Defensive: parse_expression should have caught anything malformed.
        # If it did not, the rule is still unevaluable — never silently true.
        return RuleResult(rule=rule, passed=None, substitutions=substitutions, error=str(e))

    return RuleResult(rule=rule, passed=bool(outcome), substitutions=substitutions)


def evaluate_expression(expression: str, facts: MarketFacts, *, offset: int = 0,
                        substitutions: Optional[dict[str, float]] = None) -> bool:
    """Evaluate a bare expression to a boolean, at an optional bar lag.

    The half of `evaluate_rule` that does not assume a `Rule`, exposed for
    core/vault/stages.py — a stage clause is the same DSL evaluated against
    the same facts, and giving it its own copy of the walker would fork the
    grammar the moment either side gained an operator.

    Unlike `evaluate_rule` this PROPAGATES `InsufficientData` and
    `RuleSyntaxError` rather than folding them into a result object, because
    the two callers must react differently: an audit turns an unevaluable
    rule into a blocking INSUFFICIENT_DATA verdict, while a classifier stops
    and reports unclassified. Neither may be silently treated as False.
    """
    tree = parse_expression(expression)
    return bool(_eval(tree.body, facts, offset, substitutions if substitutions is not None else {}))


def _eval(node: ast.AST, facts: MarketFacts, offset: int,
          subs: dict[str, float]) -> float | bool:
    """Recursive evaluator. `offset` is the current bar-lag context, pushed
    down by `[n]` subscripts so `(close > sma(50))[3]`-style nesting resolves
    every inner term at the same historical bar."""

    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise RuleSyntaxError(f"unsupported literal {node.value!r} in a rule")
        return float(node.value)

    if isinstance(node, ast.Subscript):
        lag = _lag_of(ast.unparse(node), node)
        return _eval(node.value, facts, offset + lag, subs)

    if isinstance(node, ast.Name):
        value = getattr(facts, _SCALARS[node.id])(offset)
        return _record(ast.unparse(node), value, offset, subs)

    if isinstance(node, ast.Call):
        period = node.args[0].value                      # validated at parse time
        value = getattr(facts, _WINDOWS[node.func.id])(period, offset)
        return _record(ast.unparse(node), value, offset, subs)

    if isinstance(node, ast.UnaryOp):
        operand = _eval(node.operand, facts, offset, subs)
        return -operand if isinstance(node.op, ast.USub) else +operand

    if isinstance(node, ast.BinOp):
        left = _eval(node.left, facts, offset, subs)
        right = _eval(node.right, facts, offset, subs)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        # Division by zero is a data condition, not a syntax error: a symbol
        # with no traded volume makes volume_sma(50) zero, and the honest
        # answer is "this ratio is unavailable", not a crash or an infinity.
        if right == 0:
            raise InsufficientData(ast.unparse(node.right))
        return left / right

    if isinstance(node, ast.BoolOp):
        values = [_eval(v, facts, offset, subs) for v in node.values]
        return all(values) if isinstance(node.op, ast.And) else any(values)

    if isinstance(node, ast.Compare):
        # Chained comparison, so `close > sma(50) > sma(150)` reads in a note
        # exactly as Minervini writes it. Python semantics: every adjacent
        # pair must hold.
        left = _eval(node.left, facts, offset, subs)
        for op, right_node in zip(node.ops, node.comparators):
            right = _eval(right_node, facts, offset, subs)
            if not _compare(op, left, right):
                return False
            left = right
        return True

    raise RuleSyntaxError(f"unsupported expression element {type(node).__name__}")


def _compare(op: ast.cmpop, left: float, right: float) -> bool:
    if isinstance(op, ast.Gt):
        return left > right
    if isinstance(op, ast.GtE):
        return left >= right
    if isinstance(op, ast.Lt):
        return left < right
    if isinstance(op, ast.LtE):
        return left <= right
    if isinstance(op, ast.Eq):
        return left == right
    if isinstance(op, ast.NotEq):
        return left != right
    raise RuleSyntaxError(f"unsupported comparison {type(op).__name__}")


def _record(term: str, value: Optional[float], offset: int,
            subs: dict[str, float]) -> float:
    """Register a resolved term for the report, or fail the rule as
    unevaluable. Terms read at a lag are labelled with it so a report never
    shows two different numbers under the same name."""
    label = term if offset == 0 or "[" in term else f"{term}[{offset}]"
    if value is None:
        raise InsufficientData(label)
    subs[label] = float(value)
    return float(value)
