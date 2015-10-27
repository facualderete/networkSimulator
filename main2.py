import networkx as nx
import simpy
from math import *
from collections import deque
from random import expovariate, normalvariate, choice, seed
from matplotlib import pyplot as plt

SIMULATION_TIME = 100


def exponential_var_gen(var_lambda):
    while True:
        return expovariate(var_lambda)


def normal_var_gen(var_mu, var_sigma):
    while True:
        return normalvariate(var_mu, var_sigma)


class MessageRouter():
    def __init__(self, node, queues):
        self.queues = queues
        self.node = node

    def route(self, msg):
        if msg.destination == self.node:
            return
        next_queue = self.queues.get(msg.destination, None)
        if next_queue is None:
            raise Exception("Se cago todo error")
        next_queue.enqueue(msg)


class MessageQueue():
    def __init__(self, env, next_router, service_times):
        self.next_router = next_router
        self.queue = deque([])
        self.env = env
        self.service_times = service_times

    def enqueue(self, msg):
        self.queue.append(msg)
        if len(self.queue) == 1:
            self.env.process()

    def _process_next(self, queue):
        while len(queue) > 0:
            service_time = next(self.service_times)
            msg = self.queue.popleft()
            yield self.env.timeout(service_time)
            self.next_router.route(msg)


class MessageSpawner():
    def __init__(self, env, origin, origin_router, demand):
        self.env = env
        self.origin = origin
        self.origin_router = origin_router
        self.demand = demand

    def initialize(self):
        for destination, spawn_times in self.demand.items():
            self.env.process(self._trigger(destination, spawn_times))

    def _trigger(self, destination, spawn_times):
        while self.env.now < SIMULATION_TIME:
            msg = self._generate_msg(destination)
            yield self.env.timeout(next(spawn_times))
            msg.init_timestamp()
            self._send_msg(msg)

    def _send_msg(self, msg):
        self.origin_router.route(msg)

    def _generate_msg(self, destination):
        return Message(self.env, self.origin, destination)


class Message():
    def __init__(self, environment, origin, destination):
        self.env = environment
        self.origin_timestamp = None
        self.timestamp = None
        self.origin = origin
        self.destination = destination

    def update_timestamp(self, time):
        assert self.timestamp is not None
        self.timestamp += time

    def init_timestamp(self):
        self.timestamp = self.origin_timestamp = self.env.now

    def time_in_transit(self):
        return self.timestamp - self.origin_timestamp


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


def create_graph(env):
    graph = NetworkGraph(env)
    graph.add_network_node('A', {'B': 1})
    graph.add_network_node('B', {'A': 1})
    graph.add_network_node('C', {'B': 1, 'A': 2})
    graph.add_network_edge('A', 'B', 10, 1)
    graph.add_network_edge('B', 'A', 10, 1)
    graph.add_network_edge('A', 'C', 10, 1)
    graph.add_network_edge('C', 'A', 10, 1)
    graph.add_network_edge('B', 'C', 10, 1)
    graph.add_network_edge('C', 'B', 10, 1)
    return graph

def graph_update_routing(graph):
    pass

def print_routing_status(graph):
    for node, attr in graph.node:
        print node, attr['router'].queues.keys()


graph = create_graph(None)
nx.draw(graph)
plt.show()
