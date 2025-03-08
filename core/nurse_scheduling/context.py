from ortools.sat.python import cp_model


class Context:
    def __init__(self) -> None:
        self.startdate = None
        self.enddate = None
        self.requirements = None
        self.people = None
        self.preferences = None
        self.dates = None
        self.n_days = None
        self.n_requirements = None
        self.n_people = None
        self.map_rid_r = None
        self.map_pid_p = None
        self.model: cp_model.CpModel = None
        self.model_vars = None
        self.shifts = None
        self.map_dr_p = None
        self.map_dp_r = None
        self.map_d_rp = None
        self.map_r_dp = None
        self.map_p_dr = None
        self.objective = None
