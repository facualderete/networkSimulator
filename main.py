import simpy
from math import *

from collections import deque
from random import expovariate, normalvariate, choice, seed


var_lambda = 0.1
muA = 1
sigmaA = 0.1
muB = 2
sigmaB = 0.2

destination_random_vars = {
    'A' : { 'B' : 0.1 },
    'B' : { 'A' : 0.05 }
}

# Matriz de tiempo de viaje sin carga
# contains: (mean, std deviation)
service_times = {
    'A' : { 'B' : (7, 1) },
    'B' : { 'A' : (30, 3) }
}

SIMULATION_TIME = 100

class Node():
    #constructor
    def __init__(self, environment, identifier):
        self.id = identifier
        self.env = environment
        self.arcs = {}
        self.routing_table = {'B' : 'B', 'A' : 'A'}

    def add_arc(self, arc, node):
        assert node.id not in self.arcs
        self.arcs[node.id] = arc

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


class Arc():
    def __init__(self, environment, source_node, target_node, weight):
        self.env = environment
        self.source = source_node
        self.target = target_node
        self.weight = weight

        # returns queue for each destination
        bck_id = bck_node.id
        fwd_id = fwd_node.id
        self.queues = {
            bck_id : Queue(*service_times[fwd_id][bck_id]),
            fwd_id : Queue(*service_times[bck_id][fwd_id])
        }

    def queue_msg(self, msg):
        queue = self._get_queue(msg)
        queue.append(msg)
        if len(queue) == 1:
            env.process(self._process_queue_element(queue))

    def _get_queue(self, msg):
        return self.queues[msg.follow_up_node]

    def _process_queue_element(self, queue):
        while len(queue) > 0:
            service_time, msg = queue.popleft()
            msg.update_timestamp(service_time)
            yield self.env.timeout(service_time)
            self._deliver_msg(msg)

    def _deliver_msg(self, msg):
        if msg.follow_up_node == self.fwd_node.id:
            self.fwd_node.receive_msg(msg)
        else:
            self.bck_node.receive_msg(msg)


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
    A = Node(env, 'A')
    B = Node(env, 'B')
    arc = Arc(env, A, B)
    A.add_arc(arc, B)
    B.add_arc(arc, A)
    return A, B

if __name__ == '__main__':
    seed(42)
    env = simpy.Environment()
    nodes = generate_graph(env)
    processes = [simpy.events.Process(env, node.trigger()) for node in nodes]
    env.run()
