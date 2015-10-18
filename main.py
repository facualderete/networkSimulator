import simpy
from random import expovariate
import collections.deque as deque
from random import normalvariate

var_lambda = 0.1
muA = 1
sigmaA = 0.1
muB = 2
sigmaB = 0.2


class Node():
    #constructor
    def __init__(self, environment, identifier):
        self.identifier = identifier
        self.env = environment

    def trigger(self):
        while True:
            time_between_arrivals = expovariate(var_lambda)
            yield self.env.timeout(time_between_arrivals)
            msg = self._generate_msg()
            self._send_msg(msg)

    def receive_msg(self, msg):
        """
        Processes the msg, this can mean sending it through another
        arc or finishing its journey and sending data to statistics
        :param msg:
        :return:
        """

    def _send_msg(self, msg):
        arc = self._choose_arc(msg.destination)
        arc.queue_msg(msg)

    def _choose_arc(self, destination):
        pass

    def _generate_msg(self):
        pass


class Arc():
    def __init__(self, environment, fwd_id, bck_id):
        self.env = environment

        # TODO: Create a wrapper deque class that knows about service times
        self.forward_queue = deque()
        self.backward_queue = deque()

    def queue_msg(self, msg):
        queue = self._get_queue(msg)
        queue.append(msg)
        if len(queue) == 1:
            self._process_queue_element(queue)

    def _get_queue(self):
        pass

    def _process_queue_element(self, queue):
        msg = queue.popleft()
        # TODO: the deque should know how to produce its own service times
        service_time = normalvariate(muA, sigmaA)
        msg.update_timestamp(service_time)
        yield self.env.timeout(service_time)
        self._deliver_msg(msg)
        if len(queue) > 0:
            self._process_queue_element(queue)

    def _deliver_msg(self, msg):
        """
        Delivers message to the corresponding node, which should be
        the one corresponding to either the forward or backward node
        :param msg:
        :return:
        """
        pass


class Message():
    def __init__(self, environment):
        self.env = environment
        self.timestamp = self.env.now

    def update_timestamp(self, time):
        self.timestamp += time



if __name__ == '__main__':
    env.run()