import networkx as nx
import simpy
from collections import deque
from random import expovariate, normalvariate, choice, seed
from matplotlib import pyplot as plt
import numpy as np

SIMULATION_TIME = 1000

pkt_count = 0
pkt_total = 0

def exponential_var_gen(var_lambda):
    while True:
        yield int(round(expovariate(var_lambda)))


def normal_var_gen(var_mu, var_sigma):
    while True:
        yield int(round(normalvariate(var_mu, var_sigma)))


def debug_print(*args):
    #print(*args)
    pass


class MessageRouter(object):
    def __init__(self, env, node, queues):
        self.queues = queues
        self.node = node
        self.env = env

    def set_route(self, target, queue):
        self.queues[target] = queue

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
    def __init__(self, env, origin, origin_router, demand):
        self.env = env
        self.origin = origin
        self.origin_router = origin_router
        self.demand = demand

    def initialize(self):
        for destination, spawn_times in self.demand.items():
            simpy.events.Process(env, self._trigger(destination, spawn_times))

    def _trigger(self, destination, spawn_times):
        while self.env.now < SIMULATION_TIME:
            yield self.env.timeout(next(spawn_times))
            msg = Message(self.env, self.origin, destination)
            msg.initialize()
            self.origin_router.route(msg)


class Message(object):
    def __init__(self, env, origin, destination):
        self.env = env
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
    def __init__(self, env, data = None, **attr):
        super(NetworkGraph, self).__init__(data, **attr)
        self.env = env

    def add_network_node(self, name, demand):
        demand = dict(map(lambda kv: (kv[0], exponential_var_gen(kv[1])), demand.items()))
        router = MessageRouter(self.env, name, {})
        spawner = MessageSpawner(self.env, name, router, demand)
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
        for node, paths in results.items():
            for target, path in paths.items():
                if len(path) > 1:
                    router = self.node[node]['router']
                    next_node = path[1]
                    queue = self.edge[node][next_node]['queue']
                    router.set_route(target, queue)
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

def create_graph(env):
    new_graph = NetworkGraph(env)
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
    global env, pkt_count, pkt_total, SIMULATION_TIME
    SIMULATION_TIME = sim_time
    pkt_count = 0
    pkt_total = 0
    #seed(42)
    env = simpy.Environment()
    graph = create_graph(env)
    graph.update_times()
    graph.update_routing("wait_time")
    if update_times is not None:
        graph.initialize(update_times)
    print_routing_status(graph)
    graph.initialize_spawners()
    env.run()
    return pkt_count, pkt_total, pkt_total/pkt_count


def run_batch(t, n):
    t_means = 0
    for k in range(n):
        count, total, mean = run(t, 20000)
        t_means += mean
    return t_means/n

if __name__ == '__main__':
    x = []
    y = []
    inf_mean = run_batch(None, 50)

    for t in range(1, 800, 10):
        t_mean = run_batch(t, 20)
        x.append(t)
        y.append(t_mean)
        print(t, t_mean)

    x = np.array(x)
    y = np.array(y)
    yinf = np.array([inf_mean]*len(x))
    plt.plot(x, y, 'o', x, yinf)
    plt.show()
    print(inf_mean)

