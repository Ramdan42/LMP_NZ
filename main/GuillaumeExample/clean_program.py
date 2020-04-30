import numpy as np
import pyomo.environ as pyo

L = 10000
def run_program(d, b, P_max, P_min, H, h, Mn, i_battery=None, z_start=1, cost_of_battery=1):

    """
    Defining spatial and temporal constants
    """
    Horizon_T = d.shape[1]
    n_nodes = d.shape[0]
    Battery_Horizon = Horizon_T + 1
    n_generators = b.shape[0]
    n_lines = H.shape[0]

    """
    Battery state equations
    """
    A, z_bar, I_tilde, E = get_battery_matrices(Battery_Horizon, z_max=10, z_min=1)
    Mu = np.zeros((n_nodes, 1))
    # Mu[i_battery] = 1

    """
    Defining optimization variables
    """
    model = pyo.ConcreteModel(name="feasibility_analysis")

    # Indexes over the optimization variables
    model.prod_times_index = pyo.Set(initialize=list((i, j) for i in range(b.shape[0]) for j in range(Horizon_T)))
    model.time_index = range(Horizon_T)
    model.battery_index = range(Battery_Horizon)
    model.mu_index = range(n_nodes)
    model.nodal_index = pyo.Set(initialize=list((i, j) for i in range(n_nodes) for j in range(Horizon_T)))
    model.beta_index = pyo.Set(initialize=list((i, j) for i in range(n_lines) for j in range(Horizon_T)))
    model.A = pyo.RangeSet(0, 2 * Battery_Horizon - 1)
    model.H_index =  pyo.Set(initialize=list((i, j) for i in range(n_lines) for j in range(H.shape[1])))

    """
    H parameter
    """
    model.H = pyo.Param(model.H_index, initialize=lambda model, i, j: H_init(model, i, j, H), mutable=True)

    """
    Battery variables
    """
    model.z = pyo.Var(model.battery_index, domain=pyo.NonNegativeReals)
    model.q_u = pyo.Var(model.time_index, domain=pyo.NonNegativeReals)
    model.q_u_test = pyo.Var(domain=pyo.NonNegativeReals) #max capacity
    model.c_u = pyo.Var(model.time_index, domain=pyo.NonNegativeReals)
    model.M_u = pyo.Var(model.mu_index, domain=pyo.Binary)
    model.starting_z = pyo.Var(domain=pyo.NonNegativeReals)
    # model.i = pyo.Var(domain_type=pyo.IntegerSet, lb=0, ub=n_nodes)

    """
    E.D primal variables
    """
    model.g_t = pyo.Var(model.prod_times_index, domain=pyo.Reals)
    model.p_t = pyo.Var(model.nodal_index, domain=pyo.Reals)
    model.u = pyo.Var(model.time_index, domain=pyo.Reals)

    """
    E.D dual variables
    """
    model.lambda_ = pyo.Var(model.nodal_index, domain=pyo.Reals)
    model.gamma_ = pyo.Var(model.time_index, domain=pyo.Reals)
    model.beta = pyo.Var(model.beta_index, domain=pyo.NonNegativeReals)
    model.sigma = pyo.Var(model.prod_times_index, domain=pyo.NonNegativeReals)
    model.mu = pyo.Var(model.prod_times_index, domain=pyo.NonPositiveReals)
    model.sigma_u = pyo.Var(model.time_index, domain=pyo.NonNegativeReals)
    model.mu_u = pyo.Var(model.time_index, domain=pyo.NonPositiveReals)

    """
    Binary variables for slack constraints
    """
    # model.r_lambda_ = pyo.Var(model.nodal_index, domain=pyo.Binary)
    # model.r_gamma_ = pyo.Var(model.time_index, domain=pyo.Binary)
    model.r_beta_ = pyo.Var(model.beta_index, domain=pyo.Binary)
    model.r_sigma_g = pyo.Var(model.prod_times_index, domain=pyo.Binary)
    model.r_g_t = pyo.Var(model.prod_times_index, domain=pyo.Binary)
    model.r_mu_t = pyo.Var(model.prod_times_index, domain=pyo.Binary)
    model.r_sigma_g_u = pyo.Var(model.time_index, domain=pyo.Binary)
    model.r_g_t_u = pyo.Var(model.time_index, domain=pyo.Binary)
    model.r_u = pyo.Var(model.time_index, domain=pyo.Binary)

    """
    Define objective
    """
    model.obj = pyo.Objective(rule=lambda model : obj_func(model, Horizon_T, d, b, P_max, P_min, n_nodes, h, cost_of_battery))
    # model.obj = pyo.Objective(rule=lambda model : 1)

    """
    Injection feasibility constraints
    """
    model.injection_definition = pyo.Constraint(model.nodal_index, rule=lambda model, j, t :
                                                            pt_definition(model, j, t, n_nodes, Mn, d, n_generators))
    model.injection_balance = pyo.Constraint(model.time_index, rule=lambda model, t : injection_balance(model, t, n_nodes))
    model.line_constraints = pyo.Constraint(model.beta_index, rule=lambda model, j,
                                                                           t : line_constraints(model, j, t, n_nodes, h))

    """
    Upper bounds on bids
    """
    model.upper_bound_bid_generators = pyo.Constraint(model.prod_times_index, rule=lambda model, i, t:
                                                                                    prod_constraint(model, i, t, P_max))
    model.upper_bound_bid_battery = pyo.Constraint(model.time_index, rule=prod_constraint_u)
    model.down_bound_bid_generators =  pyo.Constraint(model.prod_times_index, rule=lambda model, i, t:
                                                                                    prod_constraint_min(model, i, t, P_min))

    """
    Cost and dual prices for generators
    """
    model.dual_generator_constraint = pyo.Constraint(model.prod_times_index, rule=lambda model, i, t:
                                                                        generator_price(model, i, t, n_nodes, Mn, b))
    model.dual_battery_constraint = pyo.Constraint(model.time_index, rule=lambda model, t:
                                                                        battery_price(model, t, n_nodes))
    model.LMPs = pyo.Constraint(model.nodal_index, rule=lambda model, i, t: LMP_s(model, i, t, n_nodes, H))


    """
    Battery states
    """
    model.Mu_set = pyo.Constraint(rule=lambda model : Mu_set(model, n_nodes))
    if i_battery is not None:
        model.Battery = pyo.Constraint(rule=lambda model: Mu_battery(model, i_battery))

    model.battery_states_limits = pyo.Constraint(model.A,
                                                 rule=lambda model, a : battery_states_limits(model, a, Battery_Horizon, A, z_bar))
    model.battery_states_update = pyo.Constraint(model.time_index,
                                                 rule=lambda model, t : battery_states_update(model, t, Battery_Horizon, E, Horizon_T,
                                                                            I_tilde))
    model.initial_state = pyo.Constraint(rule=initial_state)
    model.final_state = pyo.Constraint(rule=lambda model : final_state(model, Battery_Horizon))
    model.battery_bid_cstr = pyo.Constraint(model.time_index, rule=battery_bid_cstr)
    model.capacity_constraint = pyo.Constraint(rule=battery_capacity_cstr)

    """
    Slack constraints
    """
    # model.gamma_cstr1 = pyo.Constraint(model.time_index, rule=gamma_cstr1)
    # model.gamma_cstr2 = pyo.Constraint(model.time_index, rule=lambda model, t: gamma_cstr2(model, t, n_nodes))
    model.beta_cstr1 = pyo.Constraint(model.beta_index, rule=beta_cstr1)
    model.beta_cstr2 = pyo.Constraint(model.beta_index, rule=lambda model, j, t : beta_cstr2(model, j, t, n_nodes, h))
    # model.lambda_cstr1 = pyo.Constraint(model.nodal_index, rule=lambda_cstr1)
    # model.lambda_cstr2 = pyo.Constraint(model.nodal_index,
    #                                     rule=lambda model, j, t : lambda_cstr2(model, j, t, n_nodes, n_generators, Mn, Mu, d))
    model.sigma_g_cstr1 = pyo.Constraint(model.prod_times_index, rule=sigma_g_cstr1)
    model.sigma_g_cstr2 = pyo.Constraint(model.prod_times_index, rule=lambda model, i, t :sigma_g_cstr2(model, i, t, P_max))
    model.sigma_g_cstr1_u = pyo.Constraint(model.time_index, rule=sigma_g_cstr1_u)
    model.sigma_g_cstr2_u = pyo.Constraint(model.time_index, rule=sigma_g_cstr2_u)
    model.slack_pos1 = pyo.Constraint(model.prod_times_index, rule=lambda model, i, t: sigma_cstrmu_q(model, i, t, P_min))
    model.slack_pos2 = pyo.Constraint(model.prod_times_index, rule=sigma_cstrmu)
    model.slack_pos1_u = pyo.Constraint(model.time_index, rule=sigma_cstrmu_qu)
    model.slack_pos2_u = pyo.Constraint(model.time_index, rule=sigma_cstrmu_u)

    """
    Solve and store
    """
    model.dual = pyo.Suffix(direction=pyo.Suffix.IMPORT_EXPORT)

    solver = pyo.SolverFactory('gurobi')
    res = solver.solve(model)
    return model


def Mu_set(model, n_nodes):
    S = 0
    for i in range(n_nodes):
        S += model.M_u[i]
    return S == 1

def Mu_battery(model, i_battery):
    return model.M_u[i_battery] == 1


def injection_balance(model, t, n_nodes):
    S = 0
    for j in range(n_nodes):
        S += model.p_t[j, t]
    return S == 0


def line_constraints(model, j, t, n_nodes, h):
    S = 0
    for i in range(n_nodes):
        S += model.H[j, i]*model.p_t[i, t]
    return S <= h[j]


def pt_definition(model, j, t, n_nodes, Mn, d, n_generators):
    S = 0
    # for i in range(n_nodes):
    for b_ in range(n_generators):
        S += Mn[j,b_]*model.g_t[b_, t]
    S += model.M_u[j]*model.u[t]
    return model.p_t[j,t] - S + d[j, t] == 0

# S=0
# t=0
# i = 0
# for b_ in range(n_generator):
#     if Mn[i, b_] > 0 :
#         print(i, b_)
#     S += pyo.value(Mn[i, b_] * model.g_t[b_, 0])
# S += pyo.value(Mu[i][0]*model.u[t])
# d[0,0]
# pyo.value(model.p_t[0,0])


def prod_constraint(model, i, t, P_max):
    return model.g_t[i, t] <= P_max[i,t]


def prod_constraint_u(model, t):
    return model.u[t] <= model.q_u[t]


def prod_constraint_min(model, i, t, P_min):
    return model.g_t[i, t] >= P_min[i,t]


def generator_price(model, i, t, n_nodes, Mn, b):
    S = 0
    for j in range(n_nodes):
        S += Mn.T[i,j]*model.lambda_[j, t]
    return b[i,t] - S + model.sigma[i, t] + model.mu[i, t] == 0


def battery_price(model, t, n_nodes):
    S = 0
    for j in range(n_nodes):
        S += model.M_u[j] * model.lambda_[j, t]
    return model.c_u[t] - S + model.sigma_u[t] + model.mu_u[t] == 0


def LMP_s(model, i, t, n_nodes, H):
    S = 0
    for j in range(2*n_nodes):
        S += H.T[i,j] * model.beta[j, t]
    return model.gamma_[t] + S - model.lambda_[i,t] == 0


def gamma_cstr1(model, t):
    return model.gamma_[t] <= (1 - model.r_gamma_[t]) * L

def gamma_cstr2(model, t, n_nodes):
    S = 0
    for j in range(n_nodes):
        S += model.p_t[j, t]
    return S <= model.r_gamma_[t]* L


def beta_cstr1(model, i, t):
    return model.beta[i,t] <= (1-model.r_beta_[i,t]) * 10000

def beta_cstr2(model, j, t, n_nodes, h):
    S = 0
    for i in range(n_nodes):
        S += model.H[j, i] * model.p_t[i, t]
    return h[j] - S <= model.r_beta_[j,t] * 1E7

# def lambda_cstr1(model, i, t):
#     return model.lambda_[i,t] <= (1 - model.r_lambda_[i,t]) * L
#
#
# def lambda_cstr2(model, j, t, n_nodes, n_generators, Mn, Mu, d):
#     S = 0
#     for i in range(n_nodes):
#         for b_ in range(n_generators):
#             S += Mn[i, b_] * model.g_t[b_, t]
#         S += Mu[i][0] * model.u[t]
#     return S - d[j,t] - model.p_t[j,t] <= model.r_lambda_[j,t] * L #model.p_t[j, t] == S - d[j, t]

def sigma_g_cstr1(model, i, t):
    return model.sigma[i, t] <= (1 - model.r_sigma_g[i, t]) * L

def sigma_g_cstr2(model, i, t, P_max):
    return P_max[i,t] - model.g_t[i, t] <= model.r_sigma_g[i, t] * L

# def mu_g_cstr1(model, i, t):
#     return model.mu[i, t] <= (1 - model.r_mu_t[i, t]) * L
#
# def mu_g_cstr2(model, i, t, P_min):
#     return model.g_t[i, t] - P_min[i] <= model.r_mu_t[i, t] * L

def sigma_g_cstr1_u(model, t):
    return model.sigma_u[t] <= (1 - model.r_sigma_g_u[t]) * L

def sigma_g_cstr2_u(model, t):
    return model.q_u[t] - model.u[t] <= model.r_sigma_g_u[t] * L

def sigma_cstrmu_q(model, i, t, P_min):
    return model.g_t[i, t] - P_min[i,t] <= model.r_g_t[i, t] * L

def sigma_cstrmu(model, i, t):
    return -model.mu[i, t] <= (1 - model.r_g_t[i, t]) * L


def sigma_cstrmu_qu(model, t):
    return model.u[t] <= model.r_g_t_u[t] * L


def sigma_cstrmu_u(model, t):
    return -model.mu_u[t] <= (1 - model.r_g_t_u[t]) * L

def battery_bid_cstr(model,t):
    return model.q_u[t] <= model.q_u_test

def battery_capacity_cstr(model):
    return model.q_u_test <= 30

def battery_states_limits(model, a, Battery_Horizon, A, z_bar):
    S = 0
    for i in range(Battery_Horizon):
        S += A[a, i] * model.z[i]
    if a % 2 == 0:
        return S <= model.q_u_test
    else:
        return S <= z_bar[a]

def battery_states_update(model, t, Battery_Horizon, E, Horizon_T, I_tilde):
    S = 0
    for i in range(Battery_Horizon):
        S += E[t,i]*model.z[i]
    for i in range(Horizon_T):
        S += I_tilde[t, i] * model.u[i]
    return S == 0

def initial_state(model):
    return model.z[0] == model.starting_z

def final_state(model, Battery_Horizon):
    return model.z[Battery_Horizon-1] == model.starting_z


def get_battery_matrices(Battery_Horizon, z_max=10, z_min=1):
    A = np.zeros((2 * Battery_Horizon, Battery_Horizon))
    for t in range(Battery_Horizon):
        A[2 * t, t] = 1
        A[2 * t + 1, t] = -1
    z_bar = np.array([z_max, -z_min] * Battery_Horizon)

    E = np.zeros((Battery_Horizon-1, Battery_Horizon))
    for t in range(0, Battery_Horizon-1):
        E[t, t + 1] = 1
        E[t, t] = -1
    I_tilde = np.eye(Battery_Horizon-1)
    return A, z_bar, I_tilde, E


def H_init(model, i, j, H):
    return H[i,j]


def obj_func(model, Horizon_T, d, b, P_max, P_min, n_nodes, h, cost_of_battery):
    S = 0
    for t in range(Horizon_T):
        for j in range(n_nodes):
            S += d[j, t] * model.lambda_[j, t]
        for j in range(2 * n_nodes):
            S += - h[j] * model.beta[j, t]
        for i in range(len(b)):
            S += - b[i,t] * (model.g_t[i, t]-P_min[i,t]) - P_max[i,t] * model.sigma[i, t]
    return -S + cost_of_battery * model.q_u_test


def launch_model():
    from main.Network.Topology.Topology import Topology as top
    import main.Network.PriceBids.Load.Load as ld
    from main.Network.PriceBids.Generator.Generator import Generator
    from main.Network.PriceBids.Load.Load import Load
    import pandas as pd
    import stored_path
    import json
    import math
    from main.GuillaumeExample import LMP

    AMB_network = top(network="ABM")

    """
    Create loads on each node
    """
    Existing_sub_nodes = ld.get_existing_subnodes()
    historical_loads = ld.get_historical_loads()
    Simp_nodes_dict = ld.get_nodes_to_subnodes()
    Simp_nodes_dict["MAN"] = ["MAN2201"]
    Existing_sub_nodes.append("MAN2201")
    nodes_to_index = pd.read_csv(stored_path.main_path + '/data/ABM/ABM_Nodes.csv')
    for i, node in enumerate(AMB_network.names_2_nodes.keys()):
        # print("Load added at node : " + node)
        index = nodes_to_index[nodes_to_index["Node names"] == node]["Node index"].values[0]
        load = Load(node, node, index, type="real_load")
        load.add_load_data(historical_loads, Simp_nodes_dict, Existing_sub_nodes)
        AMB_network.add_load(load)

    file_path = stored_path.main_path + '/data/generators/generator_adjacency_matrix_dict.json'
    with open(file_path) as f:
        data = json.loads(f.read())

    number_of_added_generators = 0
    for name_generator in data.keys():
        L_ = data[name_generator]
        try:
            if type(L_[0]) != float:
                if not math.isnan(L_[-2]):
                    if L_[-1] == "Gas" or L_[-1] == "Biogas":
                        add = 35
                    if L_[-1] == "Geothermal":
                        add = 10
                    if L_[-1] == "Coal":
                        add = 50
                    if L_[-1] == "Diesel":
                        add = 150

                    if L_[-1] == 'Hydro':
                        P_min = 0.1 * L_[-2]
                    else:
                        P_min = 0

                    g = Generator(name_generator, L_[0], 0, L_[-1], Pmax=L_[-2], Pmin=P_min,
                                  marginal_cost=add + np.array(L_[1]))
                    AMB_network.add_generator(g)
                    number_of_added_generators += 1
        except:
            pass

    """
    get d_t for day 12 and trading period 1
    """
    Horizon_T = 12
    d = []
    for k, node in enumerate(AMB_network.loads.keys()):
        d.append([])
        for j in range(Horizon_T):
            d[k].append(1000 * AMB_network.loads[node][0].return_d(1, j + 1))

    d = np.array(d)
    # d = np.zeros((d.shape[0], Horizon_T))
    # d = P_min

    """
    Add topology specific characteristics
    """
    n_generator = AMB_network.get_number_of_gen()
    b = np.zeros((n_generator, Horizon_T))
    P_max = np.zeros((n_generator, Horizon_T))
    P_min = np.zeros((n_generator, Horizon_T))
    for node in AMB_network.generators.keys():
        for g in AMB_network.generators[node]:
            for i in range(Horizon_T):
                pmax, pmin, a = LMP.get_P_min_a(g.name, 1, i + 1)
                P_max[g.index, i] = pmax + 1
                P_min[g.index, i] = pmin if g.type == "Hydro" else 0
                b[g.index, i] = a
    print("Loading data done")
    # name = list_of_generator[1].name
    # LMP.get_P_min_a(name, 1, 36)
    # b[list_of_generator[1].index]

    list_of_generator = {}
    for node in AMB_network.generators.keys():
        for g in AMB_network.generators[node]:
            list_of_generator[g.index] = g
    new_dict = {}
    for key in sorted(list_of_generator.keys()):
        new_dict[key] = list_of_generator[key]

    # P_min, P_max = AMB_network.create_Pmin_Pmax()
    # P_max = P_max.reshape(-1) #*10
    H, h = AMB_network.H, AMB_network.h
    # h = h
    # h = np.array(list(h)[:23] + list(-h)[:23])
    Mn = AMB_network.Mn
    i_battery = 1
    model = run_program(d, b, P_max, P_min, H, h, Mn, i_battery=11, z_start=1, cost_of_battery=22)
    model.pprint()
    print("\n___ OBJ ____")
    print(pyo.value(model.obj))

    lambdas = np.array([pyo.value(model.lambda_[11, t]) for t in range(Horizon_T)])
    u = np.array([pyo.value(model.u[t]) for t in range(Horizon_T)])
    lambdas@u


if __name__ == '__main__':
    b = np.array([0, 25, 50, 200])  # 4 generators
    P_max = np.array([1, 3, 3, 5])
    P_min = np.array([0,0,0,1])

    Horizon_T = 1
    Battery_Horizon = Horizon_T + 1
    d = np.array([6] * Horizon_T)
    interesting_D = [6] * Horizon_T
    interesting_D[Horizon_T // 2] = 1
    interesting_D[0] = 6
    # interesting_D = np.arange(1, 12)

    n_nodes = 1
    i_battery = 0
    d = np.array([interesting_D for n in range(n_nodes)])

    ### Define Mn
    Mn = np.ones((n_nodes, len(b)))
    Mu = np.zeros((n_nodes, 1))
    Mu[i_battery] = 1

    ### Define H, h
    H = np.concatenate([np.ones((n_nodes, n_nodes)), -np.ones((n_nodes, n_nodes))])
    h = 15 * np.zeros(2 * H.shape[0])
    h = np.array([0, 0])

    # model = run_program(d, b, P_max, P_min,  H, h, Mn, i_battery, z_start=1, cost_of_battery=1)
    #
    #
    # model.pprint()
    # print("\n___ OBJ ____")
    # print(pyo.value(model.obj))


    """
    Real test 
    """





    # model.pprint()
    # print("\n___ OBJ ____")
    # print(pyo.value(model.obj))

    # for v in model.component_objects(pyo.Var, descend_into=True):
    #     v.pprint()


    # AMB_network.generators[0][0].index

    # H.shape
    # pt = np.ones(20)
    # H@pt <= h

    ## Test
    # gt = d[:,0]
    # pt = gt - d[:,0]
    # H @ pt <= h
    # S=0
    # for j in range(H.shape[0]) :
    #     if abs(H.T[1, j]) > 0.1:
    #         print(j, 1)
    #         S+=pyo.value(H.T[1, j] * model.beta[j,1])


    # model.beta_index = pyo.Set(initialize=list((i, j) for i in range(H.shape[0]) for j in range(H.shape[1])))
