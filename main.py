import networkx as nx
import simpy
import time
from collections import deque
from random import expovariate, normalvariate, choice, seed
import matplotlib
# matplotlib.use("Qt5Agg")
from matplotlib import pyplot as plt
import numpy as np

SIMULATION_TIME = 2000

pkt_count = 0
pkt_total = 0

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
    def __init__(self, environment):
        self.demand_matrix = {}
        self.delay_matrix = {}
        self.routing_path_matrix = {}
        self.routing_amount_matrix = {}
        self.env = environment
        self.change_count_matrix = {}
        self.hl = []

    def plot_elements_vs_time(self):
        global SIMULATION_TIME
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
        if not (origin, destination) in self.delay_matrix.keys():
            self.delay_matrix[(origin, destination)] = 0
        self.delay_matrix[(origin, destination)] += delay

    def print_demand_count(self):
        for (origin, destination) in self.demand_matrix.keys():
            print("DEMAND ", origin, " -> ", destination, " : ", self.demand_matrix[(origin, destination)])

    def print_delay_count(self):
        for (origin, destination) in self.delay_matrix.keys():
            # imprime el promedio de lo que tarda um paquete en llegar de un punto a otro
            # divide el total de tardanza de todos los paquetes por la cantidad de paquetes enviados
            print("DELAY ", origin, " -> ", destination, " : ", self.delay_matrix[(origin, destination)] / self.demand_matrix[(origin, destination)])

    def update_path_change_counter(self, queue1, queue2):
        if not queue1 or not queue2:
            return
        if queue1.next_node != queue2.next_node:
            if env.now not in self.change_count_matrix:
                self.change_count_matrix[self.env.now] = 0
            self.change_count_matrix[self.env.now] += 1

    def get_avg_path_change(self):
        n = len(self.change_count_matrix)
        if n != 0:
            return sum(self.change_count_matrix.values()) / n
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
    def __init__(self, env, statistics, origin, origin_router, demand):
        self.env = env
        self.origin = origin
        self.origin_router = origin_router
        self.demand = demand
        self.statistics = statistics

    def initialize(self):
        for destination, spawn_times in self.demand.items():
            simpy.events.Process(env, self._trigger(destination, spawn_times))

    def _trigger(self, destination, spawn_times):
        while self.env.now < SIMULATION_TIME:
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
        global pkt_count, pkt_total
        pkt_count += 1
        pkt_total += self.time_in_transit()
        self.statistics.add_delay_count(self.origin, self.destination, self.time_in_transit())
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
    def __init__(self, env, statistics, data = None, **attr):
        super(NetworkGraph, self).__init__(data, **attr)
        self.env = env
        self.statistics = statistics

    def add_network_node(self, name, demand):
        demand = dict(map(lambda kv: (kv[0], exponential_var_gen(kv[1])), demand.items()))
        router = MessageRouter(self.env, name, {})
        spawner = MessageSpawner(self.env, self.statistics, name, router, demand)
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
        update_elements_plot(self, self.env.now, self.statistics.hl)
        for node, paths in results.items():
            for target, path in paths.items():
                if len(path) > 1:
                    next_node = path[1]
                    router = self.node[node]['router']
                    current_queue = router.get_queue(target)
                    queue = self.edge[node][next_node]['queue']
                    router.set_route(target, queue)
                    self.statistics.update_path_change_counter(current_queue, queue)
                    # plot_routing_table(self.statistics)
                    debug_print(node, target, path)

    def initialize_spawners(self):
        for node, attributes in self.node.items():
            attributes['spawner'].initialize()

    def initialize(self, update_time):
        simpy.events.Process(env, self._update_routing_events(update_time))

    def _update_routing_events(self, update_time):
        while self.env.now < SIMULATION_TIME:
            yield self.env.timeout(update_time)
            self.update_times()
            self.update_routing('wait_time')
            debug_print('UPDATE ROUTING')


def create_big_graph(env, statistics, demand_mult):
    new_graph = NetworkGraph(env, statistics)
    nodes = set([chr(ord('A') + j) for j in range(12)])

    for node in nodes:
        demand = dict(map(lambda n: (n, float(demand_mult)/10.0), nodes - set([node])))
        new_graph.add_network_node(node, demand)

    new_graph.add_network_double_edge('A', 'B', 4, 1)
    new_graph.add_network_double_edge('A', 'D', 7, 1)
    new_graph.add_network_double_edge('A', 'C', 5, 1)
    new_graph.add_network_double_edge('B', 'A', 8, 1)
    new_graph.add_network_double_edge('B', 'G', 9, 1)
    new_graph.add_network_double_edge('B', 'E', 15, 1)
    new_graph.add_network_double_edge('C', 'A', 12, 1)
    new_graph.add_network_double_edge('C', 'H', 6, 1)
    new_graph.add_network_double_edge('C', 'G', 17, 1)
    new_graph.add_network_double_edge('D', 'A', 6, 1)
    new_graph.add_network_double_edge('D', 'E', 7, 1)
    new_graph.add_network_double_edge('D', 'F', 7, 1)
    new_graph.add_network_double_edge('D', 'H', 13, 1)
    new_graph.add_network_double_edge('E', 'B', 21, 1)
    new_graph.add_network_double_edge('E', 'D', 10, 1)
    new_graph.add_network_double_edge('E', 'F', 6, 1)
    new_graph.add_network_double_edge('F', 'D', 7, 1)
    new_graph.add_network_double_edge('F', 'E', 5, 1)
    new_graph.add_network_double_edge('F', 'J', 13, 1)
    new_graph.add_network_double_edge('G', 'C', 6, 1)
    new_graph.add_network_double_edge('G', 'B', 14, 1)
    new_graph.add_network_double_edge('G', 'L', 3, 1)
    new_graph.add_network_double_edge('H', 'C', 25, 1)
    new_graph.add_network_double_edge('H', 'L', 20, 1)
    new_graph.add_network_double_edge('H', 'I', 10, 1)
    new_graph.add_network_double_edge('H', 'D', 15, 1)
    new_graph.add_network_double_edge('I', 'J', 13, 1)
    new_graph.add_network_double_edge('I', 'K', 4, 1)
    new_graph.add_network_double_edge('I', 'H', 11, 1)
    new_graph.add_network_double_edge('J', 'F', 8, 1)
    new_graph.add_network_double_edge('J', 'K', 9, 1)
    new_graph.add_network_double_edge('J', 'I', 6, 1)
    new_graph.add_network_double_edge('K', 'I', 7, 1)
    new_graph.add_network_double_edge('K', 'J', 10, 1)
    new_graph.add_network_double_edge('K', 'L', 8, 1)
    new_graph.add_network_double_edge('L', 'G', 5, 1)
    new_graph.add_network_double_edge('L', 'H', 9, 1)
    new_graph.add_network_double_edge('L', 'K', 11, 1)

    return new_graph

def create_graph(env, statistics):
    new_graph = NetworkGraph(env, statistics)
    new_graph.add_network_node('A', {'B': 1.0/10})
    new_graph.add_network_node('B', {'A': 1.0/10})
    new_graph.add_network_node('C', {})
    new_graph.add_network_double_edge('A', 'B', 25, 1)
    new_graph.add_network_double_edge('A', 'C', 10, 1)
    new_graph.add_network_double_edge('B', 'C', 10, 1)
    return new_graph

def plot_routing_table(statistics):
    # plt.close()
    columns = ('# refrescos', 'Origen - Destino', 'Por arista...')
    rows = []
    refresh = []
    route = []
    for (origin, destination) in statistics.routing_amount_matrix.keys():
        rows.append((statistics.routing_amount_matrix[(origin, destination)],
                     origin + " - " + destination,
                    statistics.routing_path_matrix[(origin, destination)]
                     ))
        refresh.append(statistics.routing_amount_matrix[(origin, destination)])
        route.append(statistics.routing_path_matrix[(origin, destination)])

    plt.table(cellText=rows,
              colLabels=columns,
              loc='center')
    # plt.draw()
    # plt.show()


def print_routing_status(graph):
    for node, attr in graph.node.items():
        for target, queue in attr['router'].queues.items():
            debug_print(node, target, queue.next_node)


def run(update_times, sim_time):
    global env, pkt_count, pkt_total, SIMULATION_TIME
    SIMULATION_TIME = sim_time
    pkt_count = 0
    pkt_total = 0


    #seed(42)
    env = simpy.Environment()
    statistics = Statistics(env)
    statistics.plot_elements_vs_time()
    graph = create_big_graph(env, statistics, 0.2) # era create_graph
    graph.update_times()
    graph.update_routing("wait_time")
    if update_times is not None:
        graph.initialize(update_times)
    # print_routing_status(graph)
    graph.initialize_spawners()
    env.run()
    # statistics.print_demand_count()
    # statistics.print_delay_count()
    avg_path_change = statistics.get_avg_path_change()
    return pkt_count, pkt_total, pkt_total/pkt_count, avg_path_change




def run_batch(update_time, batch_size):
    t_means = 0
    avg_path_change = 0
    for k in range(batch_size):
        # count, total, mean, avg_pchg = run(update_time, 100 + (update_time if update_time is not None else 0)*10) # decia 20000
        count, total, mean, avg_pchg = run(update_time, 200) # decia 20000
        t_means += mean
        avg_path_change += avg_pchg
    return t_means / batch_size, avg_path_change / batch_size


def update_elements_plot(g, curr_time, hl):
    global SIMULATION_TIME
    edges_dict = g.edge
    elements = 0

    for origin in edges_dict.keys():
        for dest in edges_dict.get(origin):
            elements += len(g.get_edge_data(origin, dest)['queue'].queue)

    print("t: %f, elements: %d" % (curr_time, elements))
    xs = np.append(hl.get_xdata(), curr_time)
    ys = np.append(hl.get_ydata(), elements)

    hl.set_xdata(xs)
    hl.set_ydata(ys)
    plt.pause(0.01)

if __name__ == '__main__':
    x = []
    y = []
    z = []

    """
    #Ejemplo de plot para un grafo
    labels = {'A': "A", 'B': "B", 'C': "C", 'D': "D", 'E': "E", 'F': "F", 'G': "G", 'H': "H", 'I': "I", 'J': "J",
              'K': "K", 'L': "L"}
    statistics = Statistics()
    graph = create_big_graph(simpy.Environment(), statistics)
    nx.draw(G=graph, labels=labels)
    plt.show()
    """

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