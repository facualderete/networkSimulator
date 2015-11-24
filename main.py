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


PLOT_RESULTS = False
DEFAULT_LAMBDA = 0.01 # ms/msg
BATCH_SIZE = 20
RUNS = 700
WARM_UP_PERIOD = 0


def exponential_var_gen(var_lambda):
    while True:
        val = expovariate(var_lambda)
        yield val if val > 0 else 1


def normal_var_gen(var_mu, var_sigma):
    while True:
        val = normalvariate(var_mu, var_sigma)
        yield val if val > 0 else 1


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
        self.warmup_updates = WARM_UP_PERIOD

    def init_dynamic_plots(self):
        fig = plt.figure(1)
        self.hl = fig

        fig.add_subplot(311)
        ax = fig.gca()
        ax.set_ylabel("Cantidad de elementos")
        ax.grid(True)
        ax.set_xlim([self.warmup_updates, RUNS])
        plt.plot([], [], 'b-')

        fig.add_subplot(312)
        ax = fig.gca()
        ax.set_ylabel("Tiempo en el sistema")
        ax.grid(True)
        ax.set_xlim([self.warmup_updates, RUNS])
        plt.plot([], [], 'b-')

        fig.add_subplot(313)
        ax = fig.gca()
        ax.set_xlabel("Tiempo del simulador")
        ax.set_ylabel("Cambios en el routeo")
        ax.grid(True)
        ax.set_xlim([self.warmup_updates, RUNS])
        plt.plot([], [], 'b-')

        fig.subplots_adjust(hspace=0)

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
        if self.current_update < self.warmup_updates:
            return
        if not (origin, destination) in self.delay_matrix:
            self.delay_matrix[(origin, destination)] = 0
        self.delay_matrix[(origin, destination)] += delay

    def add_arrived_count(self, origin, destination):
        if self.current_update < self.warmup_updates:
            return
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
            # print('{:^18d} {:^5s} {:^5s} {:^3s}'.format(self.current_update, node, target, queue1.next_node))

    def get_avg_path_change(self):
        if self.current_update not in self.change_count_matrix:
            self.change_count_matrix[self.current_update] = 0
        return self.change_count_matrix[self.current_update]

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
        if self.origin != "A":
            return
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

    def update_times(self):
        for (u, v) in self.edges():
            attrs = self.edge[u][v]
            attrs['wait_time'] = (attrs['queue'].get_queued_messages() + 1)*attrs['mu']

    def update_routing(self, weight):
        results = nx.shortest_path(self, weight=weight)
        self.statistics.current_update += 1
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

    def initialize_spawners(self):
        for node, attributes in self.node.items():
            attributes['spawner'].initialize()

    def initialize(self, update_time):
        simpy.events.Process(env, self._update_routing_events(update_time))
        if PLOT_RESULTS:
            callback = update_elements_plot(self, update_time, self.sim_time, self.statistics.hl)
            simpy.events.Process(env, callback)

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
        demand = dict(map(lambda n: (n, float(demand_mult)), nodes - set([node])))
        new_graph.add_network_node(node, demand)

    new_graph.add_network_double_edge('A', 'B', 26, 4)
    new_graph.add_network_double_edge('A', 'D', 55, 4)
    new_graph.add_network_double_edge('A', 'C', 47, 4)
    new_graph.add_network_double_edge('B', 'G', 32, 4)
    new_graph.add_network_double_edge('B', 'E', 38, 4)
    new_graph.add_network_double_edge('C', 'H', 33, 4)
    new_graph.add_network_double_edge('C', 'G', 61, 4)
    new_graph.add_network_double_edge('D', 'E', 29, 4)
    new_graph.add_network_double_edge('D', 'F', 34, 4)
    new_graph.add_network_double_edge('D', 'H', 51, 4)
    new_graph.add_network_double_edge('E', 'F', 34, 4)
    new_graph.add_network_double_edge('F', 'J', 8, 4)
    new_graph.add_network_double_edge('G', 'L', 46, 4)
    new_graph.add_network_double_edge('H', 'L', 38, 4)
    new_graph.add_network_double_edge('H', 'I', 39, 4)
    new_graph.add_network_double_edge('I', 'J', 41, 4)
    new_graph.add_network_double_edge('I', 'K', 22, 4)
    new_graph.add_network_double_edge('J', 'K', 12, 4)
    new_graph.add_network_double_edge('K', 'L', 36, 4)

    # Para hacer el grafo 4-conexo agregar estos
    #new_graph.add_network_double_edge('B', 'F', 48, 4)
    #new_graph.add_network_double_edge('G', 'J', 8, 4)
    #new_graph.add_network_double_edge('C', 'L', 35, 4)
    #new_graph.add_network_double_edge('A', 'I', 26, 4)
    #new_graph.add_network_double_edge('E', 'H', 8, 4)
    #new_graph.add_network_double_edge('D', 'K', 8, 4)
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
    env = simpy.Environment()
    statistics = Statistics(env, sim_time)

    if PLOT_RESULTS:
        statistics.init_dynamic_plots()

    graph = create_big_graph(env, statistics, sim_time, DEFAULT_LAMBDA) # era create_graph
    graph.update_times()
    graph.update_routing("wait_time")
    if update_times is not None:
        # print("Número de Refresco|Desde|Hasta|Por")
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
    if update_time is not None:
        print("Running with update time %d and batch size %d" % (update_time, batch_size))
    for k in range(batch_size):
        if update_time is not None:
            print(k)
        mean, avg_pchg = run(update_time, RUNS) # decia 20000
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


def update_elements_plot(g, update_time, sim_time, hl):
    edges_dict = g.edge
    ax1, ax2, ax3 = hl.get_axes()
    str = "Frec. Refres.: %.2f" % (1 / update_time)
    plt.text(0, 1.1, str, fontsize=12, transform=ax1.transAxes)
    while env.now < sim_time:
        yield env.timeout(1)

        elements = 0

        for origin in edges_dict.keys():
            for dest in edges_dict.get(origin):
                elements += len(g.get_edge_data(origin, dest)['queue'].queue)
        line = ax1.get_lines()[0]
        xs = np.append(line.get_xdata(), env.now)
        ys = np.append(line.get_ydata(), elements)
        ax1.set_ylim([0, int(max(ys) * 1.2)])
        line.set_xdata(xs)
        line.set_ydata(ys)

        line = ax2.get_lines()[0]
        ys = np.append(line.get_ydata(), g.statistics.get_total_avg_delay())
        ax2.set_ylim([0, max(ys) * 1.2])
        line.set_xdata(xs)
        line.set_ydata(ys)

        line = ax3.get_lines()[0]
        ys = np.append(line.get_ydata(), g.statistics.get_avg_path_change())
        ax3.set_ylim([0, max(ys) * 1.2])
        line.set_xdata(xs)
        line.set_ydata(ys)

        plt.pause(0.001)
    plt.clf()

if __name__ == '__main__':
    x = []
    y = []
    z = []

    print_to_file("frequency; avg_travel_time")

    inf_mean = run_batch(None, 50)
    for t in range(1, 300, 10): # decia (1, 800, 10)
        t_mean, path_change = run_batch(t, BATCH_SIZE)
        x.append(t)
        y.append(t_mean)
        z.append(path_change)
        print(t, t_mean)
        print("Path change: %f, %f" % (t, path_change))

    if PLOT_RESULTS:
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