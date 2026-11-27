import math
import random
import time
import gc
from bayes_opt import BayesianOptimizer

REPEATS = 5
TRIALS = 30
RECHECK = 5
GRID = 21
INITIAL = [(0.,0.), (0.,1.), (1.,0.), (1.,1.), (.5,.5)]
PATH = '/flash/bo_recheck.csv'


def truth(p):
    return (p[0]-.7)**2 + (p[1]-.3)**2


def observe(p):
    u = max(random.random(), 1e-7)
    return truth(p) + .02*math.sqrt(-2*math.log(u))*math.cos(2*math.pi*random.random())


def predicted_best(bo):
    # Same standardized GP as suggest(), but minimize posterior mean.
    n = len(bo.X)
    K = [[bo.kernel(a,b) for b in bo.X] for a in bo.X]
    for i in range(n):
        K[i][i] += bo.noise
    L = bo.cholesky(K)
    mean = sum(bo.Y)/n
    sd = max(1e-8, math.sqrt(sum((v-mean)**2 for v in bo.Y)/n))
    alpha = bo.backward(L, bo.forward(L, [(v-mean)/sd for v in bo.Y]))
    best = None
    low = float('inf')
    for i in range(GRID):
        for j in range(GRID):
            p = (i/(GRID-1), j/(GRID-1))
            mu = sum(bo.kernel(p,bo.X[t])*alpha[t] for t in range(n))
            if mu < low:
                low, best = mu, p
    return best


def run(f, r):
    random.seed(2026+r)
    bo = BayesianOptimizer(length_scale=.25, noise=.01, kappa=2., grid_size=GRID)
    def log(stage, method, trial, p, obs, ms=0):
        f.write('%d,%s,%s,%d,%.4f,%.4f,%.8f,%.8f,%d\n' %
                (r,stage,method,trial,p[0],p[1],obs,truth(p),ms))
        f.flush()
    for t in range(TRIALS):
        gc.collect()
        start = time.ticks_ms()
        p = INITIAL[t] if t < len(INITIAL) else bo.suggest()
        ms = time.ticks_diff(time.ticks_ms(),start)
        v = observe(p)
        bo.add(p[0],p[1],v)
        log('search','BO',t+1,p,v,ms)
        print('Run %d trial %d: %.2f %.2f obs=%.5f ms=%d' % (r,t+1,p[0],p[1],v,ms))
    order = sorted(range(TRIALS), key=lambda i: bo.Y[i])
    top = [bo.X[i] for i in order[:3]]
    start = time.ticks_ms()
    pred = predicted_best(bo)
    ms = time.ticks_diff(time.ticks_ms(),start)
    log('prediction','C',0,pred,0.,ms)
    candidates = top[:]
    if pred not in candidates:
        candidates.append(pred)
    averages = {}
    # Independent validation noise; shared evaluations for B and C.
    random.seed(12026+r)
    for i,p in enumerate(candidates):
        vals = []
        for j in range(RECHECK):
            v = observe(p)
            vals.append(v)
            log('recheck','BC' if i<3 else 'C',j+1,p,v)
        averages[p] = sum(vals)/RECHECK
        log('mean','BC' if i<3 else 'C',RECHECK,p,averages[p])
    a = top[0]
    b = min(top,key=lambda p: averages[p])
    c = min(candidates,key=lambda p: averages[p])
    for method,p,v in [('A',a,bo.Y[order[0]]),('B',b,averages[b]),('C',c,averages[c])]:
        log('selected',method,0,p,v)
        print('Run %d %s: (%.2f, %.2f) true=%.6f' % (r,method,p[0],p[1],truth(p)))


with open(PATH,'w') as f:
    f.write('repeat,stage,method,trial,x,y,observed,true_value,calc_ms\n')
    for r in range(REPEATS):
        run(f,r)
        gc.collect()
print('Saved:',PATH)
