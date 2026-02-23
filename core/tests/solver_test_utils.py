from nurse_scheduling.constants import Operator


def expected_bool_value(operator: Operator, x_value: int, k: int) -> int:
    if operator == Operator.EQ:
        return 1 if x_value == k else 0
    if operator == Operator.NE:
        return 1 if x_value != k else 0
    if operator == Operator.GE:
        return 1 if x_value >= k else 0
    if operator == Operator.GT:
        return 1 if x_value > k else 0
    if operator == Operator.LE:
        return 1 if x_value <= k else 0
    if operator == Operator.LT:
        return 1 if x_value < k else 0
    raise AssertionError(f"Unhandled operator in test: {operator}")
