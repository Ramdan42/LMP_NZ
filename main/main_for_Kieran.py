from main.GuillaumeExample import price_making_algorithm
from main.GuillaumeExample import economic_dispatch
from main.GuillaumeExample import price_taking_algorithm
import imp
imp.reload(economic_dispatch)
import json
import math
import numpy as np
import pandas as pd
import pyomo.environ as pyo
import main.Network.PriceBids.Load.Load as ld
import stored_path
from main.GuillaumeExample import LMP
from main.Network.PriceBids.Generator.Generator import Generator
from main.Network.PriceBids.Load.Load import Load
from main.Network.Topology.Topology import Topology as top

"""
Hello Kieran ! 

I hope you slept well cause this is amazing !! 

Brace for it and follow me : start by reading exp1 and then do exp2
"""


def how_to_deal_with_price_maker_algo(Horizon_T=48, day=2):
    """
    Choose your number of trading period : Horizon T and your day. By default let's do everything
    on day 2 and Horizon_T = 48
    :param Horizon_T:
    :param day:
    :return:
    """

    """
    The following line gets you the H,h, Mn (you already know)
    b, P_max, P_min => the bids of each generator for the whole day (dimension g X horizonT)
    d => demand of each node but we tweaked the case (look at tweak_d if you want to see how i do that)
    
    Don't panic it takes a lot of time !!
    """
    H, h, Mn, b, P_max, P_min, d = get_basics(Horizon_T, day)
    """
    Below a first example how to run the price making algo :
    
    some parameters are exogenous : d, b, P_max, P_min, H, h, Mn.
    But  : 
        @ always choose the location of the battery, 
        @ if you want to fix the maximum capacity fix it to something otherwise say "=None" and the algorithm will
        find the best capacity
        @cost of the battery the "B" of the article
        
    In the example below best capacity for 0 cost of capacity at node 1
    """
    model = price_making_algorithm.run_program(d, b, P_max, P_min, H, h, Mn, i_battery=1,
                                               max_capacity=None, cost_of_battery=0)
    model.z_cap.pprint() #To print the content of a variable or constraint do model.[name of variable].pprint()
    # to see all the variables open the workspace and see all of the variables model contains
    z_cap_store = pyo.value(model.z_cap) #use pyo.value to store
    q_u_store = [pyo.value(model.q_u[t]) for t in range(Horizon_T)] #or do that for array variable

    """
    You can also save the results using save_results function (as we did last week)
    """
    y = 10  # amortize in 10 years
    cost_of_battery = 200 * 1000 / (y * 365)

    print("Launching model...")
    model = price_making_algorithm.run_program(d, b, P_max, P_min, H, h, Mn, i_battery=1,
                                               max_capacity=None, cost_of_battery=cost_of_battery)
    print("Model computed")
    save_results(model, d, Horizon_T, i_test=0) #i-test is the number of the folder in which you store the results

    """
    Let's get to it and store some nice output !!!!
    
    Let's do it man !!
    """

    """
    1st example : get the objective function value and zcap in function of the index of the nodes
    
        WARNING : the profit of the battery is different from the objective function.
        Obj function = profit - B*z_cap !
    """
    benefits_per_node = []
    zcap_per_node = []
    for j in range(1, d.shape[0]):
        print("Launching model for node {}...".format(j))
        model = price_making_algorithm.run_program(d, b, P_max, P_min, H, h, Mn, i_battery=j,
                                                   max_capacity=None, cost_of_battery=cost_of_battery)
        print("Model computed")

        print("\n___ OBJ ____")
        print(pyo.value(model.obj))
        benefits_per_node.append(pyo.value(model.obj)) #here we store the result of the constraint obj (not the variable)
        zcap_per_node.append(pyo.value(model.z_cap))
        print("\n")

    """
    second example : get the objective function value and zcap of node 10 (the congested node remember)
    in function of amortizement.
    
    The longer you can wait to amortize your investment the more likely you will install a fucking fat battery
    """
    benefits_per_node = []
    zcap_per_node = []
    for y in list(range(1, 10))+[1000]:
        print("Launching model...")
        cost_of_battery = 200 * 1000 / (y * 365)
        model = price_making_algorithm.run_program(d, b, P_max, P_min, H, h, Mn, i_battery=10,
                                                   max_capacity=None, cost_of_battery=cost_of_battery)
        print("Model computed")

        print("\n___ OBJ ____")
        print(pyo.value(model.obj))  # get the benefits
        benefits_per_node.append(pyo.value(model.obj))
        zcap_per_node.append(pyo.value(model.z_cap))
        print("\n")

    """
    Let's see the next step
    """


def how_to_deal_with_price_taker_algo(Horizon_T = 48, day = 2):
    """
    You already know all this shit man
    """
    H, h, Mn, b, P_max, P_min, d = get_basics(Horizon_T, day)
    n = d.shape[0] #number of nodes

    """
    Find lambdas for the day (they will be deemed exogenous)
    """
    lambdas = np.zeros((n, Horizon_T))
    for j in range(Horizon_T):
        """
        Here is a new optimization framework which is rigoursely the same as devised in the algorithm, 
        WARNING this is just for time period j.
        
        We input the c and q, the price and quantity offered by the battery. Here 0,0 because we want the LMPs
        without the battery
        """
        c = 0
        q = 0
        model = economic_dispatch.run_ED_1period(d[:,j], b[:,j], P_max[:,j], P_min[:,j], c, q, H, h, Mn)
        for k in range(n):
            lambdas[k,j] = model.dual[model.injection_definition[k]] #here we store the dual variables of the injection definition constraint

    """
    Can you compare the lambdas of the economic dispatch with the one we find with the price maker dispatch ?
    """

    """
    Price taking let's go !!
    
    As for the maker, you choose the node of the battery, the cost (B), and the max_capacity (if none, will find the best)
    """
    model = price_taking_algorithm.run_program(lambdas, i_battery=10, cost_of_battery=100, max_capacity=None)
    planning = [pyo.value(model.u[t]) for t in range(Horizon_T)] #planning of push and pull from the network
    expected_profits = sum([planning[i]*lambdas[1,i] for i in range(Horizon_T)]) #expected profits (lambda cross u with lambdas as exogenous)

    n_lambdas = np.zeros((n, Horizon_T)) #new prices !
    for j in range(Horizon_T):
        """
        Here we sell and buy at 0 (i.e we self-schedule_) the quantity devised in the optimization algorithm
        """
        model = economic_dispatch.run_ED_1period(d[:, j], b[:, j], P_max[:, j], P_min[:, j], 0, planning[j], H, h, Mn,
                                                 i_battery=10)
        for k in range(n):
            n_lambdas[k, j] = model.dual[model.injection_definition[k]]

    actual_profits = sum([planning[i] * n_lambdas[1, i] for i in range(Horizon_T)])
    """
    Actual profits.
    """

def get_basics(Horizon_T, day):
    AMB_network = top(network="ABM")
    AMB_network = add_loads_to_topology(AMB_network)
    AMB_network = add_generators_to_topology(AMB_network)
    H, h = AMB_network.H, AMB_network.h
    print("Topology loaded")
    """
    Tweak case  : add a fake generator
    """
    node_name = "MDN"
    # index = 10
    AMB_network.add_generator(Generator("diesel_gen", node_name, 0, 0, Pmax=200, Pmin=0,
                                        marginal_cost=[0, 0]))

    """
    Get the load data
    """
    d = get_load_matrix(AMB_network, day, Horizon_T)
    d = tweak_d(d, load_factor = 1.3, index_to_tweak = 10, load_factor_for_node=12.1)
    print("Load historical data loaded and tweaked")

    """
    Get the bid matrices
    """
    b, P_max, P_min = get_producers_matrices(AMB_network, day, Horizon_T)
    print("Load historical bids")

    """
    Load now the topology of generators
    """
    Mn = AMB_network.Mn
    return H, h, Mn, b, P_max, P_min, d






def tweak_d(d, load_factor = 1.3, index_to_tweak = 10, load_factor_for_node=12.1):
    save = d[index_to_tweak].copy()
    save_d = d.copy()
    d[index_to_tweak] = save
    d = load_factor * save_d.copy()
    d[index_to_tweak] = save * load_factor_for_node
    return d


def add_loads_to_topology(AMB_network):
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
    return AMB_network

def add_generators_to_topology(AMB_network):
    file_path = stored_path.main_path + '/data/generators/generator_adjacency_matrix_dict1.json'
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

    return AMB_network


def get_load_matrix(AMB_network, day, Horizon_T):
    d = []
    for k, node in enumerate(AMB_network.loads.keys()):
        d.append([])
        for j in range(day * 48, day * 48 + Horizon_T):
            d[k].append(1 * 1000 * AMB_network.loads[node][0].return_d(1 + j // 48, j % 48 + 1))
    d = np.array(d)
    return d


def get_producers_matrices(AMB_network, day, Horizon_T):
    n_generator = AMB_network.get_number_of_gen()
    b = np.zeros((n_generator, Horizon_T))
    P_max = np.zeros((n_generator, Horizon_T))
    P_min = np.zeros((n_generator, Horizon_T))
    for node in AMB_network.generators.keys():
        for g in AMB_network.generators[node]:
            for i, j in enumerate(range(day * 48, day * 48 + Horizon_T)):
                if g.name == "diesel_gen":
                    pmax, pmin, a = 500, 0, 200
                else:
                    pmax, pmin, a = LMP.get_P_min_a(g.name, 1 + j // 48, j % 48 + 1, g.type)
                P_max[g.index, i] = pmax
                P_min[g.index, i] = pmin if g.type == "Hydro" else 0
                b[g.index, i] = a if a > 0 else np.random.randint(0, 100)
    return b, P_max, P_min


def save_results(model, d, Horizon_T, i_test=0):
    import os
    path = stored_path.main_path + "/data/results" + "/test{}".format(i_test)
    try:
        os.mkdir(path)
    except:
        pass
    lambdas = np.array([[pyo.value(model.lambda_[t, i]) for i in range(Horizon_T)] for t in range(d.shape[0])])
    df_lambda = pd.DataFrame(data=lambdas)
    df_lambda.to_csv(path+"/df_lambda.csv")
    p_t = np.array([[pyo.value(model.p_t[t, i]) for i in range(Horizon_T)] for t in range(d.shape[0])])
    df_p_t = pd.DataFrame(data=p_t)
    df_p_t.to_csv(path + "/df_p_t.csv")
    df_demand = pd.DataFrame(data=d)
    df_demand.to_csv(path + "/df_demand.csv")
    df_gamma = pd.DataFrame(data=[pyo.value(model.gamma_[t]) for t in range(Horizon_T)])
    df_gamma.to_csv(path + "/df_gamma.csv")

    u = np.array([pyo.value(model.u[t]) for t in range(Horizon_T)])
    z = np.array([pyo.value(model.z[i]) for i in range(Horizon_T)])
    c_u = np.array([pyo.value(model.c_u[t]) for t in range(Horizon_T)])
    q_u = np.array([pyo.value(model.q_u[t]) for t in range(Horizon_T)])
    df_z = pd.DataFrame(data=np.array([z,u,c_u,q_u]).T, columns=["z", "u", "c_u", "q_u"])
    df_z.to_csv(path + "/df_z.csv")
    return True




