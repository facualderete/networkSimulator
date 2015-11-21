import networkx as nx
import simpy
import time
from collections import deque
from random import expovariate, normalvariate, choice, seed

import sys
if sys.platform == 'linux':
    import matplotlib; matplotlib.use('Qt5Agg')

from matplotlib import pyplot as plt
import numpy as np


def exponential_var_gen(var_lambda):
    while True:
        yield round(expovariate(var_lambda))


def normal_var_gen(var_mu, var_sigma):
    while True:
        yield round(normalvariate(var_mu, var_sigma))


def debug_print(*args):
    # print(*args)
    pass


class Statistics(object):

    def __init__(self, environment, sim_time):
        self.change_count_matrix = {}
        self.demand_matrix = {}
        self.delay_matrix = {}
        self.arrived_matrix = {}
        self.routing_path_matrix = {}
        self.routing_amount_matrix = {}
        self.env = environment
        self.current_update = 0
        self.hl = []  # used for plotting
        self.sim_time = sim_time

    def init_dynamic_plots(self):
        self.hl, = plt.plot([], [], 'b-')
        plt.axis([0, 200, 0, 500])
        plt.ion()
        plt.draw()

    def update_path_for(self, origin, destination, path):
        self.routing_path_matrix[(origin, destination)] = path

    def add_routing_amount_for(self, origin, destination):
        if not (origin, destination) in self.routing_amount_matrix.keys():
            self.routing_amount_matrix[(origin, destination)] = 0
        self.routing_amount_matrix[(origin, destination)] += 1

    def add_demand_count(self, origin, destination):
        if not (origin, destination) in self.demand_matrix.keys():
            self.demand_matrix[(origin, destination)] = 0
        self.demand_matrix[(origin, destination)] += 1

    def add_delay_count(self, origin, destination, delay):
        if not (origin, destination) in self.delay_matrix:
            self.delay_matrix[(origin, destination)] = 0
        self.delay_matrix[(origin, destination)] += delay

    def add_arrived_count(self, origin, destination):
        if not (origin, destination) in self.arrived_matrix:
            self.arrived_matrix[(origin, destination)] = 0
        self.arrived_matrix[(origin, destination)] += 1

    def print_demand_count(self):
        for (origin, destination) in self.demand_matrix.keys():
            print("DEMAND ", origin, " -> ", destination, " : ", self.demand_matrix[(origin, destination)])

    def print_delay_count(self):
        for (origin, destination) in self.delay_matrix.keys():
            # imprime el promedio de lo que tarda um paquete en llegar de un punto a otro
            # divide el total de tardanza de todos los paquetes por la cantidad de paquetes enviados
            print("DELAY ", origin, " -> ", destination, " : ", self.delay_matrix[(origin, destination)] / self.demand_matrix[(origin, destination)])

    def update_path_change_counter(self, node, target, queue1, queue2):
        if not queue1 or not queue2:
            return
        if queue1.next_node != queue2.next_node:
            if self.current_update not in self.change_count_matrix:
                self.change_count_matrix[self.current_update] = 0
            self.change_count_matrix[self.current_update] += 1
            print('{:^18d} {:^5s} {:^5s} {:^3s}'.format(self.current_update, node, target, queue1.next_node))

    def get_avg_path_change(self):
        n = len(self.change_count_matrix)
        if n != 0:
            return sum(self.change_count_matrix.values()) / n
        return 0

    def get_total_avg_delay(self):
        total_arrivals = sum(self.arrived_matrix.values())
        total_delays = sum(self.delay_matrix.values())
        if total_delays > 0 and total_arrivals > 0:
            return float(total_delays)/float(total_arrivals)
        else:
            return 0


class MessageRouter(object):
    def __init__(self, env, node, queues):
        self.queues = queues
        self.node = node
        self.env = env

    def set_route(self, target, queue):
        self.queues[target] = queue

    def get_queue(self, target):
        return self.queues[target] if target in self.queues else None

    def route(self, msg):
        if msg.destination == self.node:
            msg.terminate()
            return
        next_queue = self.queues.get(msg.destination, None)
        if next_queue is None:
            raise Exception("Se cago todo error")
        debug_print('ROUTE', msg, ' (' + self.node + ' -> ' + next_queue.next_node + ')')
        next_queue.enqueue(msg)


class MessageQueue(object):
    def __init__(self, env, next_node, next_node_router, service_times):
        self.next_node = next_node
        self.next_node_router = next_node_router
        self.queue = deque([])
        self.env = env
        self.service_times = service_times

    def enqueue(self, msg):
        self.queue.append(msg)
        if len(self.queue) == 1:
            self.env.process(self._process_next())

    def _process_next(self):
        while len(self.queue) > 0:
            service_time = next(self.service_times)
            yield self.env.timeout(service_time)
            msg = self.queue.popleft()
            debug_print('TRANSIT', msg, ' (-> ' + self.next_node + ')', '{service_time: ' + str(service_time) + '}')
            self.next_node_router.route(msg)

    def get_queued_messages(self):
        return len(self.queue)


class MessageSpawner(object):
    def __init__(self, env, statistics, sim_time, origin, origin_router, demand):
        self.env = env
        self.origin = origin
        self.origin_router = origin_router
        self.demand = demand
        self.statistics = statistics
        self.sim_time = sim_time

    def initialize(self):
        for destination, spawn_times in self.demand.items():
            simpy.events.Process(env, self._trigger(destination, spawn_times))

    def _trigger(self, destination, spawn_times):
        while self.env.now < self.sim_time:
            yield self.env.timeout(next(spawn_times))
            msg = Message(self.env, self.statistics, self.origin, destination)
            self.statistics.add_demand_count(self.origin, destination)
            msg.initialize()
            self.origin_router.route(msg)


class Message(object):
    def __init__(self, env, statistics, origin, destination):
        self.env = env
        self.statistics = statistics
        self.timestamp = None
        self.origin = origin
        self.destination = destination

    def initialize(self):
        self.timestamp = self.env.now
        debug_print('CREATE', self)

    def terminate(self):
        self.statistics.add_delay_count(self.origin, self.destination, self.time_in_transit())
        self.statistics.add_arrived_count(self.origin, self.destination)
        debug_print('DESTROY', self)

    def time_in_transit(self):
        return self.env.now - self.timestamp

    def __str__(self):
        return '<Message 0x' + format(self.__hash__() % 0x10000, '04X') + \
               ' (' + str(self.origin) + \
               ' -> ' + str(self.destination) + \
               ') {created: ' + str(self.timestamp) + \
               ', alive: ' + str(self.time_in_transit()) + \
               ', now: ' + str(self.env.now) + \
               '}>'


class NetworkGraph(nx.DiGraph):
    def __init__(self, env, statistics, sim_time, data = None, **attr):
        super(NetworkGraph, self).__init__(data, **attr)
        self.env = env
        self.statistics = statistics
        self.sim_time = sim_time

    def add_network_node(self, name, demand):
        demand = dict(map(lambda kv: (kv[0], exponential_var_gen(kv[1])), demand.items()))
        router = MessageRouter(self.env, name, {})
        spawner = MessageSpawner(self.env, self.statistics, self.sim_time, name, router, demand)
        self.add_node(name, router=router, spawner=spawner)

    def add_network_edge(self, source, destination, mu, sigma):
        destination_router = self.node[destination]['router']
        queue = MessageQueue(self.env, destination, destination_router, normal_var_gen(mu, sigma))
        self.add_edge(source, destination, queue=queue, mu=mu, sigma=sigma)

    def add_network_double_edge(self, u, v, mu, sigma):
        self.add_network_edge(u, v, mu, sigma)
        self.add_network_edge(v, u, mu, sigma)

    def add_network_double_edge(self, u, v):
        mean = normalvariate(35, 16)
        dev = 4
        self.add_network_double_edge(u, v, mean, dev)

    def update_times(self):
        for (u, v) in self.edges():
            attrs = self.edge[u][v]
            attrs['wait_time'] = (attrs['queue'].get_queued_messages() + 1)*attrs['mu']

    def update_routing(self, weight):
        results = nx.shortest_path(self, weight=weight)
        for node, paths in results.items():
            for target, path in paths.items():
                if len(path) > 1:
                    next_node = path[1]
                    router = self.node[node]['router']
                    current_queue = router.get_queue(target)
                    queue = self.edge[node][next_node]['queue']
                    router.set_route(target, queue)
                    self.statistics.update_path_change_counter(node, target, current_queue, queue)
                    # plot_routing_table(self.statistics)
                    debug_print(node, target, path)
        self.statistics.current_update += 1

    def initialize_spawners(self):
        for node, attributes in self.node.items():
            attributes['spawner'].initialize()

    def initialize(self, update_time):
        simpy.events.Process(env, self._update_routing_events(update_time))
        # simpy.events.Process(env, update_elements_plot(self, self.env.now, self.sim_time,
        #                                                self.statistics.hl))

    def _update_routing_events(self, update_time):
        while self.env.now < self.sim_time:
            yield self.env.timeout(update_time)
            self.update_times()
            self.update_routing('wait_time')
            debug_print('UPDATE ROUTING')

def create_big_graph(env, statistics, sim_time, demand_mult):
    new_graph = NetworkGraph(env, statistics, sim_time)
    nodes = set([chr(ord('A') + j) for j in range(12)])

    for node in nodes:
        demand = dict(map(lambda n: (n, float(demand_mult)/10.0), nodes - set([node])))
        new_graph.add_network_node(node, demand)

    new_graph.add_network_double_edge('A', 'B')
    new_graph.add_network_double_edge('A', 'D')
    new_graph.add_network_double_edge('A', 'C')
    # new_graph.add_network_double_edge('B', 'A', 8, 1)
    new_graph.add_network_double_edge('B', 'G')
    new_graph.add_network_double_edge('B', 'E')
    # new_graph.add_network_double_edge('C', 'A', 12, 1)
    new_graph.add_network_double_edge('C', 'H')
    new_graph.add_network_double_edge('C', 'G')
    # new_graph.add_network_double_edge('D', 'A', 6, 1)
    new_graph.add_network_double_edge('D', 'E')
    new_graph.add_network_double_edge('D', 'F')
    new_graph.add_network_double_edge('D', 'H')
    # new_graph.add_network_double_edge('E', 'B', 21, 1)
    # new_graph.add_network_double_edge('E', 'D', 10, 1)
    new_graph.add_network_double_edge('E', 'F')
    # new_graph.add_network_double_edge('F', 'D', 7, 1)
    # new_graph.add_network_double_edge('F', 'E', 5, 1)
    new_graph.add_network_double_edge('F', 'J')
    # new_graph.add_network_double_edge('G', 'C', 6, 1)
    # new_graph.add_network_double_edge('G', 'B', 14, 1)
    new_graph.add_network_double_edge('G', 'L')
    # new_graph.add_network_double_edge('H', 'C', 25, 1)
    new_graph.add_network_double_edge('H', 'L')
    new_graph.add_network_double_edge('H', 'I')
    # new_graph.add_network_double_edge('H', 'D', 15, 1)
    new_graph.add_network_double_edge('I', 'J')
    new_graph.add_network_double_edge('I', 'K')
    # new_graph.add_network_double_edge('I', 'H', 11, 1)
    # new_graph.add_network_double_edge('J', 'F', 8, 1)
    new_graph.add_network_double_edge('J', 'K')
    # new_graph.add_network_double_edge('J', 'I', 6, 1)
    # new_graph.add_network_double_edge('K', 'I', 7, 1)
    # new_graph.add_network_double_edge('K', 'J', 10, 1)
    new_graph.add_network_double_edge('K', 'L')
    # new_graph.add_network_double_edge('L', 'G', 5, 1)
    # new_graph.add_network_double_edge('L', 'H', 9, 1)
    # new_graph.add_network_double_edge('L', 'K', 11, 1)

    return new_graph

def create_graph(env, statistics, sim_time):
    new_graph = NetworkGraph(env, statistics, sim_time)
    new_graph.add_network_node('A', {'B': 1.0/10})
    new_graph.add_network_node('B', {'A': 1.0/10})
    new_graph.add_network_node('C', {})
    new_graph.add_network_double_edge('A', 'B', 25, 1)
    new_graph.add_network_double_edge('A', 'C', 10, 1)
    new_graph.add_network_double_edge('B', 'C', 10, 1)
    return new_graph

def print_routing_status(graph):
    for node, attr in graph.node.items():
        for target, queue in attr['router'].queues.items():
            debug_print(node, target, queue.next_node)


def run(update_times, sim_time):
    global env
    #seed(42)
    env = simpy.Environment()
    statistics = Statistics(env, sim_time)
    # statistics.init_dynamic_plots()
    graph = create_big_graph(env, statistics, sim_time, 0.15) # era create_graph
    graph.update_times()
    graph.update_routing("wait_time")
    if update_times is not None:
        print("Número de Refresco|Desde|Hasta|Por")
        graph.initialize(update_times)
    # print_routing_status(graph)
    graph.initialize_spawners()
    env.run()
    # statistics.print_demand_count()
    # statistics.print_delay_count()
    avg_path_change = statistics.get_avg_path_change()
    return statistics.get_total_avg_delay(), avg_path_change


def run_batch(update_time, batch_size):
    t_means = 0
    avg_path_change = 0
    for k in range(batch_size):
        mean, avg_pchg = run(update_time, 500) # decia 20000
        #mean, avg_pchg = run(update_time, 100 + (update_time if update_time is not None else 0)*10) # decia 20000
        # acá imprimir mean (es el tiempo promedio de viaje de la corrida) y 1/updade_time
        if update_time is not None:
            print_to_file(str(1/update_time)+";"+str(mean))
        t_means += mean
        avg_path_change += avg_pchg
    return t_means / batch_size, avg_path_change / batch_size

def print_to_file(line):
    f = open('output.csv', 'a')
    f.write(line + '\n')
    f.close()

def update_elements_plot(g, curr_time, sim_time, hl):
    edges_dict = g.edge
    while env.now < sim_time:
        yield env.timeout(1)

        elements = 0

        for origin in edges_dict.keys():
            for dest in edges_dict.get(origin):
                elements += len(g.get_edge_data(origin, dest)['queue'].queue)

        # print("t: %f, elements: %d" % (env.now, elements))
        xs = np.append(hl.get_xdata(), env.now)
        ys = np.append(hl.get_ydata(), elements)

        hl.set_xdata(xs)
        hl.set_ydata(ys)
        plt.pause(0.01)
    plt.clf()

if __name__ == '__main__':
    x = []
    y = []
    z = []

    print_to_file("frequency; avg_travel_time")

    inf_mean = run_batch(None, 50)
    for t in range(1, 300, 10): # decia (1, 800, 10)
        t_mean, path_change = run_batch(t, 20)
        x.append(t)
        y.append(t_mean)
        z.append(path_change)
        print(t, t_mean)
        print("Path change: %f, %f" % (t, path_change))

    x = np.array(x)
    y = np.array(y)
    yinf = np.array([inf_mean]*len(x))
    plt.figure(1)
    plt.subplot(211)
    plt.plot(x, y, 'o')
    plt.grid(True)
    plt.xlabel("Tiempo de refresco")
    plt.ylabel("Tiempo promedio en el sistema")
    plt.title("Tiempo en el sistema de cada mensaje en función del refresco")

    plt.subplot(212)
    plt.plot(x, z, 'x')
    plt.grid(True)
    plt.xlabel("Tiempo de refresco")
    plt.ylabel("Cambio promedio en el routeo")
    plt.show()
    print(inf_mean)