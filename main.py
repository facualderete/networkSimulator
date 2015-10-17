import simpy
from random import expovariate

var_lambda = 0.1

def node(env):
    times = 10
    while times > 0:
        time_between_arrivals = expovariate(var_lambda)
        yield env.timeout(time_between_arrivals)
        print('Event %d triggered at time %d' % (times, env.now) )
        times -= 1

env = simpy.Environment()
gen = node(env)
p = simpy.events.Process(env, gen)

if __name__ == '__main__':
    env.run()