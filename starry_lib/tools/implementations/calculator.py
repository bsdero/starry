#! /usr/bin/env python3
#
# Copyright 2025-present bsdero
#
# NAME:       calculator.py
# DESCRIPTION: Calculator tool — evaluates math expressions
# SUMMARY: Safely evaluates arithmetic and math-function
#          expressions using Python's ast module.
#          No arbitrary code execution.
# NOTES: Supported: +, -, *, /, //, %, **, unary +/-,
#        and all functions/constants from the math module.
#
# BACKLOG:
# Date m/d/Y    Engineer        Summary
# 04/29/2026    bsdero    Initial implementation
"""calculator tool: evaluate mathematical expressions safely."""

from __future__ import annotations

import ast
import math
import operator

# Allowed binary operators
_BINOPS = {
    ast.Add:      operator.add,
    ast.Sub:      operator.sub,
    ast.Mult:     operator.mul,
    ast.Div:      operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod:      operator.mod,
    ast.Pow:      operator.pow,
}

# Allowed unary operators
_UNOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}

# Allowed names: math constants and functions
_NAMES: dict[str, object] = {
    "pi":        math.pi,
    "e":         math.e,
    "tau":       math.tau,
    "inf":       math.inf,
    "nan":       math.nan,
    "sin":       math.sin,
    "cos":       math.cos,
    "tan":       math.tan,
    "asin":      math.asin,
    "acos":      math.acos,
    "atan":      math.atan,
    "atan2":     math.atan2,
    "sinh":      math.sinh,
    "cosh":      math.cosh,
    "tanh":      math.tanh,
    "sqrt":      math.sqrt,
    "log":       math.log,
    "log2":      math.log2,
    "log10":     math.log10,
    "exp":       math.exp,
    "abs":       abs,
    "ceil":      math.ceil,
    "floor":     math.floor,
    "round":     round,
    "factorial": math.factorial,
    "degrees":   math.degrees,
    "radians":   math.radians,
    "hypot":     math.hypot,
    "gcd":       math.gcd,
    "comb":      math.comb,
    "perm":      math.perm,
    "isnan":     math.isnan,
    "isinf":     math.isinf,
    "pow":       math.pow,
    "fabs":      math.fabs,
    "trunc":     math.trunc,
    "copysign":  math.copysign,
    "ldexp":     math.ldexp,
    "frexp":     math.frexp,
    "modf":      math.modf,
    "fmod":      math.fmod,
    "remainder": math.remainder,
}


def _eval_node(node):
    """Recursively evaluate an ast node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float, complex)):
            return node.value
        raise ValueError(
            f"Unsupported constant type: "
            f"{type(node.value).__name__}"
        )
    if isinstance(node, ast.BinOp):
        op_fn = _BINOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(
                f"Unsupported operator: "
                f"{type(node.op).__name__}"
            )
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        return op_fn(left, right)
    if isinstance(node, ast.UnaryOp):
        op_fn = _UNOPS.get(type(node.op))
        if op_fn is None:
            raise ValueError(
                f"Unsupported unary operator: "
                f"{type(node.op).__name__}"
            )
        return op_fn(_eval_node(node.operand))
    if isinstance(node, ast.Name):
        name = node.id
        if name not in _NAMES:
            raise ValueError(
                f"Unknown name: '{name}'"
            )
        return _NAMES[name]
    if isinstance(node, ast.Call):
        func = _eval_node(node.func)
        if not callable(func):
            raise ValueError(
                f"Not callable: "
                f"{getattr(node.func, 'id', '?')}"
            )
        args = [_eval_node(a) for a in node.args]
        kwargs = {
            kw.arg: _eval_node(kw.value)
            for kw in node.keywords
            if kw.arg is not None
        }
        return func(*args, **kwargs)
    if isinstance(node, ast.Tuple):
        return tuple(_eval_node(e) for e in node.elts)
    raise ValueError(
        f"Unsupported expression node: "
        f"{type(node).__name__}"
    )


def _safe_eval(expression: str):
    """Parse and evaluate a math expression safely."""
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Syntax error: {exc}") from exc
    return _eval_node(tree.body)


SCHEMA = {
    "type": "function",
    "function": {
        "name": "calculator",
        "description": (
            "Evaluate a mathematical expression. "
            "Supports arithmetic operators "
            "(+, -, *, /, //, %, **) and math "
            "functions (sin, cos, sqrt, log, etc.) "
            "and constants (pi, e, tau). "
            "Returns the original expression and "
            "the computed result."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": (
                        "Mathematical expression to "
                        "evaluate, e.g. "
                        "'sqrt(2) * pi' or "
                        "'2 ** 10 + 1'."
                    ),
                },
            },
            "required": ["expression"],
        },
    },
}


def execute(expression: str) -> dict:
    """Safely evaluate a math expression."""
    expr = expression.strip()
    try:
        result = _safe_eval(expr)
        return {
            "expression": expr,
            "result": result,
        }
    except Exception as exc:
        return {
            "expression": expr,
            "error": str(exc),
        }
