def required_n_people(requirement):
    if not isinstance(requirement.required_people, int):
        raise NotImplementedError("required_people with type other than int is not supported yet")
    return requirement.required_people
