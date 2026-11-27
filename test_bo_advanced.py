import math
import random
import time
import gc
from bayes_opt import BayesianOptimizer

TRIAL_COUNT = 30
GRID_SIZE = 21
RANDOM_REPEATS = 30
INITIAL = [(0., 0.), (0., 1.), (1., 0.), (1., 1.), (.5, .5)]
PATH = '/flash/bo_advanced.csv'


def true_value(case, x, y):
    a = x - 0.7
    b = y - 0.3
    v = a*a + b*b
    if case == 'multi':
        v += 0.1*(math.sin(5*math.pi*a)**2 + math.sin(5*math.pi*b)**2)
    return v


def normal_noise():
    u = max(random.random(), 1e-7)
    return 0.02*math.sqrt(-2*math.log(u))*math.cos(2*math.pi*random.random())


def run(f, case, method, repeat):
    random.seed(2026 + repeat)
    noise = [normal_noise() for _ in range(TRIAL_COUNT)] if case == 'noisy' else [0.0]*TRIAL_COUNT
    bo = BayesianOptimizer(length_scale=0.15 if case == 'multi' else 0.25,
                           noise=0.01 if case == 'noisy' else 0.000001,
                           kappa=2.0, grid_size=GRID_SIZE)
    used = list(INITIAL)
    best_obs = float('inf')
    best_true = float('inf')
    selected_true = float('inf')
    bx = by = 0.0
    for t in range(TRIAL_COUNT):
        gc.collect()
        start = time.ticks_ms()
        if t < len(INITIAL):
            x, y = INITIAL[t]
        elif method == 'BO':
            x, y = bo.suggest()
        else:
            while True:
                p = (random.randrange(GRID_SIZE)/(GRID_SIZE-1),
                     random.randrange(GRID_SIZE)/(GRID_SIZE-1))
                if p not in used:
                    x, y = p
                    break
        ms = time.ticks_diff(time.ticks_ms(), start)
        used.append((x,y))
        truth = true_value(case, x, y)
        observed = truth + noise[t]
        if method == 'BO':
            bo.add(x,y,observed)
        if observed < best_obs:
            best_obs = observed
            bx, by = x, y
            selected_true = truth
        best_true = min(best_true, truth)
        gc.collect()
        mem = gc.mem_free()
        f.write('%s,%s,%d,%d,%.4f,%.4f,%.8f,%.8f,%.8f,%.8f,%.4f,%.4f,%.8f,%d,%d\n' %
                (case,method,repeat,t+1,x,y,observed,truth,best_obs,best_true,bx,by,selected_true,ms,mem))
        f.flush()
        if method == 'BO':
            print('%s %02d: x=%.2f y=%.2f obs=%.5f true=%.5f best_true=%.5f time=%d ms' %
                  (case,t+1,x,y,observed,truth,best_true,ms))
    print('%s %s run=%d: selected=(%.2f, %.2f), true=%.6f, best sampled=%.6f' %
          (case,method,repeat,bx,by,selected_true,best_true))


with open(PATH, 'w') as f:
    f.write('case,method,repeat,trial,x,y,observed,true_value,best_observed,best_true,best_x,best_y,selected_true,calc_ms,free_memory\n')
    for case in ('multi','noisy'):
        run(f,case,'BO',0)
        for repeat in range(RANDOM_REPEATS):
            run(f,case,'random',repeat)
print('Saved:',PATH)
