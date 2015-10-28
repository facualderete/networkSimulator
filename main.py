import networkx as nx
import simpy
from collections import deque
from random import expovariate, normalvariate, choice, seed
from matplotlib import pyplot as plt

SIMULATION_TIME = 100


def exponential_var_gen(var_lambda):
    while True:
        yield int(round(expovariate(var_lambda)))


def normal_var_gen(var_mu, var_sigma):
    while True:
        yield int(round(normalvariate(var_mu, var_sigma)))


class MessageRouter(object):
    def __init__(self, node, queues):
        self.queues = queues
        self.node = node

    def set_route(self, target, queue):
        self.queues[target] = queue

    def route(self, msg):
        if msg.destination == self.node:
            print('DESTROY', msg, ' in ', self.node, ' at ', msg.env.now)
            return
        next_queue = self.queues.get(msg.destination, None)
        if next_queue is None:
            raise Exception("Se cago todo error")
        print('ROUTE', msg, ' from ', self.node, ' to ', next_queue.next_router.node, ' at ', msg.env.now)
        next_queue.enqueue(msg)


class MessageQueue(object):
    def __init__(self, env, next_router, service_times):
        self.next_router = next_router
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
            print('TRANSIT', msg, ' to ', self.next_router.node, ' at ', self.env.now, ' in ', service_time)
            self.next_router.route(msg)


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
            msg = self._generate_msg(destination)
            msg.init_timestamp()
            print('CREATE', msg)
            self._send_msg(msg)

    def _send_msg(self, msg):
        self.origin_router.route(msg)

    def _generate_msg(self, destination):
        return Message(self.env, self.origin, destination)


class Message(object):
    def __init__(self, environment, origin, destination):
        self.env = environment
        self.timestamp = None
        self.origin = origin
        self.destination = destination

    def init_timestamp(self):
        self.timestamp = self.env.now

    def time_in_transit(self):
        return self.timestamp - self.env.now

    def __str__(self):
        return '<Message (' + str(self.origin) + \
               ' -> ' + str(self.destination) + \
               ') created at ' + str(self.timestamp) + \
               '>'


class NetworkGraph(nx.DiGraph):
    def __init__(self, env, data = None, **attr):
        super(NetworkGraph, self).__init__(data, **attr)
        self.env = env

    def add_network_node(self, name, demand):
        demand = dict(map(lambda kv: (kv[0], exponential_var_gen(kv[1])), demand.items()))
        router = MessageRouter(name, {})
        spawner = MessageSpawner(self.env, name, router, demand)
        self.add_node(name, router=router, spawner=spawner)

    def add_network_edge(self, source, destination, mu, sigma):
        destination_router = self.node[destination]['router']
        queue = MessageQueue(self.env, destination_router, normal_var_gen(mu, sigma))
        self.add_edge(source, destination, queue=queue, mu=mu, sigma=sigma)

    def add_network_double_edge(self, u, v, mu, sigma):
        self.add_network_edge(u, v, mu, sigma)
        self.add_network_edge(v, u, mu, sigma)

    def update_routing(self, weight):
        results = nx.shortest_path(self, weight=weight)
        for node, paths in results.items():
            for target, path in paths.items():
                if len(path) > 1:
                    router = self.node[node]['router']
                    next_node = path[1]
                    queue = self.edge[node][next_node]['queue']
                    router.set_route(target, queue)
                    print(node, target, path)

    def initialize_spawners(self):
        for node, attributes in self.node.items():
            attributes['spawner'].initialize()


def create_graph(env):
    new_graph = NetworkGraph(env)
    new_graph.add_network_node('A', {'B': 1.0/100})
    new_graph.add_network_node('B', {'A': 1.0/100})
    new_graph.add_network_node('C', {})
    new_graph.add_network_double_edge('A', 'B', 50, 5)
    new_graph.add_network_double_edge('A', 'C', 10, 1)
    new_graph.add_network_double_edge('B', 'C', 10, 1)
    return new_graph


def print_routing_status(graph):
    for node, attr in graph.node.items():
        for target, queue in attr['router'].queues.items():
            print(node, target, queue.next_router.node)


if __name__ == '__main__':
    seed(42)
    env = simpy.Environment()
    graph = create_graph(env)
    graph.update_routing("mu")
    print_routing_status(graph)
    print(graph.node.items())
    graph.initialize_spawners()
    env.run()
