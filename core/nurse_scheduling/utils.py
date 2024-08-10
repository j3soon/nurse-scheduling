def ensure_list(val):
    if val is None:
        return []
    return [val] if not isinstance(val, list) else val

def required_n_people(requirement):
    if not isinstance(requirement.required_people, int):
        raise NotImplementedError("required_people with type other than int is not supported yet")
    return requirement.required_people

def ortools_expression_to_bool_var(
        model, varname, true_expression, false_expression
    ):
    # Ref: https://stackoverflow.com/a/70571397
    var = model.NewBoolVar(varname)
    model.Add(true_expression).OnlyEnforceIf(var)
    model.Add(false_expression).OnlyEnforceIf(var.Not())
    return var
