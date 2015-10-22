import simpy
import math

from collections import deque
from random import expovariate, normalvariate, choice, seed

SIMULATION_TIME = 100

class Graph():
    def __init__(self, environment, total_nodes):
        self.env = environment
        self.total_nodes = total_nodes
        self.total_arcs = 0
        self.adjacency_map = {}

    def add_arc(self, arc):
        src = arc.src
        if src in self.adjacency_map:
            self.adjacency_map[src].append(arc)
        else:
            self.adjacency_map[src] = arc
        self.total_arcs += 1

    def add_node(self, node):
        assert node.id not in self.adjacency_map
        self.adjacency_map[node] = []


    # Dijkstra pseudocode
    # initialize distance to self to 0
    # initialize distance to every other node to INF
    # insert self with priority (weight) 0 into PQ
    # while PQ not empty:
    #   pick next node in PQ
    #   for each edge in node
    #       if distance from node through edge is smaller than the one stored:
    #           update and insert node-pointed-to into PQ
    def dijkstra(self, node):
        distance_to = {}
        arc_to = {}
        for k in self.adjacency_map.keys():
            distance_to[k] = math.inf
        distance_to[node] = 0
        pq = [(0, node)]
        while not len(pq) == 0:
            (p, n) = min(pq)
            pq.remove((p, n))
            for arc in self.adjacency_map[n]:
                dst = arc.dst
                if distance_to[dst] > distance_to[n] + arc.weight:
                    distance_to[dst] = distance_to[n] + arc.weight
                    arc_to[dst] = arc
                    if (p, dst) in pq:
                        pq.remove((p, dst))
                    pq.append((distance_to[dst], dst))
        node.routing_table = arc_to


class Arc():
    def __init__(self, environment, source, destination, weight):
        self.src = source
        self.dst = destination
        self.weight = weight
        self.queue = []


class Node():
    def __init__(self, environment):
        self.env = environment
        self.routing_table = {}

    def trigger(self):
        while env.now < SIMULATION_TIME:
            msg = self._generate_msg()
            var_lambda = destination_random_vars[self.id][msg.destination]
            time_between_arrivals = expovariate(var_lambda)
            yield self.env.timeout(time_between_arrivals)
            msg.init_timestamp()
            self._send_msg(msg)

    def receive_msg(self, msg):
        if msg.destination == self.id:
            params = (self.id, msg.origin, self.env.now, msg.time_in_transit())
            print("%s: Received msg from %s at %f, took %f to arrive" % params)
        else:
            self._send_msg(msg)

    def _send_msg(self, msg):
        self._update_follow_up_node(msg)
        arc = self._choose_arc(msg.follow_up_node)
        arc.queue_msg(msg)

    def _choose_arc(self, follow_up_node):
        return self.arcs[follow_up_node]

    def _generate_msg(self):
        network_nodes = tuple(destination_random_vars[self.id].keys())
        destination = choice(network_nodes)
        return Message(self.env, self.id, destination)

    def _update_follow_up_node(self, msg):
        follow_up_node = self.routing_table[msg.destination]
        msg.update_follow_up_node(follow_up_node)


class Queue(deque):
    def __init__(self, arrival_rate_mean, arrival_rate_dev):
        super().__init__()
        self.mean = arrival_rate_mean
        self.dev = arrival_rate_dev

    def popleft(self):
        service_time = normalvariate(self.mean, self.dev)
        return service_time, super().popleft()
