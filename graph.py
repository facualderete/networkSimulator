import math
import simpy

from collections import deque
from random import expovariate, normalvariate, choice, seed

SIMULATION_TIME = 100

destination_random_vars = {
    'A' : { 'B' : 0.1 },
    'B' : { 'A' : 0.05 }
}

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


    """ Dijkstra pseudocode
    initialize distance to self to 0
    initialize distance to every other node to INF
    insert self with priority (weight) 0 into PQ
    while PQ not empty:
      pick next node in PQ
      for each edge in node
          if distance from node through edge is smaller than the one stored:
              update and insert node-pointed-to into PQ
    """
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

        return arc_to



class Arc():
    def __init__(self, environment, source, destination, weight):
        self.src = source
        self.dst = destination
        self.weight = weight
        self.queue = []

    def __str__(self):
        return "SRC_" + str(self.src) + " - DST_" + str(self.dst)


class Node():
    def __init__(self, environment, id):
        self.env = environment
        self.id = id
        self.routing_table = {}

    def __lt__(self, other):
        return self.id < other.id

    def __str__(self):
        return "ID = " + self.id

    def trigger(self):
        while self.env.now < SIMULATION_TIME:
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

    def build_routing_table(self, arc_to):
        # TODO: que agarre lo que devolvió el dijkstra y busque el camino hasta self
        return


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

class Message():
    def __init__(self, environment, origin, destination):
        self.env = environment
        self.origin_timestamp = None
        self.timestamp = None
        self.origin = origin
        self.destination = destination
        self.follow_up_node = None

    def update_timestamp(self, time):
        assert self.timestamp is not None
        self.timestamp += time

    def init_timestamp(self):
        self.timestamp = self.origin_timestamp = self.env.now

    def time_in_transit(self):
        return self.timestamp - self.origin_timestamp

    def update_follow_up_node(self, node_id):
        self.follow_up_node = node_id

class Queue(deque):
    def __init__(self, serv_time_mean, serv_time_dev):
        super().__init__()
        self.mean = serv_time_mean
        self.dev = serv_time_dev

    def popleft(self):
        service_time = normalvariate(self.mean, self.dev)
        return service_time, super().popleft()

def generate_graph(env):
    g = Graph(env, 4)
    A = Node(env, 'A')
    B = Node(env, 'B')
    C = Node(env, 'C')
    D = Node(env, 'D')
    g.add_node(A)
    g.add_node(B)
    g.add_node(C)
    g.add_node(D)
    g.add_arc(Arc(env, A, B, 1))
    g.add_arc(Arc(env, B, A, 1))
    g.add_arc(Arc(env, A, D, 1))
    g.add_arc(Arc(env, D, A, 1))
    g.add_arc(Arc(env, B, D, 1))
    g.add_arc(Arc(env, D, B, 1))
    g.add_arc(Arc(env, B, C, 1))
    g.add_arc(Arc(env, C, B, 1))
    g.add_arc(Arc(env, D, C, 1))
    g.add_arc(Arc(env, C, D, 1))

    print(str(A.routing_table))

    g.dijkstra(A)

    for n in A.routing_table.keys():
        print(n)
        print(A.routing_table[n])

if __name__ == '__main__':
    seed(42)
    env = simpy.Environment()
    generate_graph(env)
    # processes = [simpy.events.Process(env, node.trigger()) for node in nodes]
    # env.run()