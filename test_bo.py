
import time
import gc

from bayes_opt import BayesianOptimizer


# 実験条件
TRIAL_COUNT = 30

bo = BayesianOptimizer(
    length_scale=0.25,
    noise=0.000001,
    kappa=2.0,
    grid_size=21
)


# 評価関数
def objective(x, y):
    return (x - 0.7)**2 + (y - 0.3)**2


# 初期探索点
initial_points = [
    (0.0, 0.0),
    (0.0, 1.0),
    (1.0, 0.0),
    (1.0, 1.0),
    (0.5, 0.5)
]


print("Bayesian Optimization Test")
print("Trials:", TRIAL_COUNT)
print("Grid: 21 x 21")
print("----------------------------")

gc.collect()

total_start = time.ticks_ms()

# CSVファイル
with open("/flash/bo_test.csv", "w") as f:

    header = (
        "trial,x,y,value,"
        "best_x,best_y,best_value,"
        "calc_ms,free_memory\n"
    )

    f.write(header)

    for trial in range(TRIAL_COUNT):

        gc.collect()

        start = time.ticks_ms()

        # 探索点の決定
        if trial < len(initial_points):
            x, y = initial_points[trial]
        else:
            x, y = bo.suggest()

        calc_ms = time.ticks_diff(
            time.ticks_ms(), start
        )

        # 評価
        value = objective(x, y)

        # 結果を登録
        bo.add(x, y, value)

        # 最良条件
        bx, by, bv = bo.best()

        gc.collect()
        free_mem = gc.mem_free()

        # シェルに表示
        print(
            "Trial %02d: x=%.3f y=%.3f "
            "f=%.6f best=%.6f "
            "time=%d ms mem=%d"
            % (
                trial + 1,
                x, y, value, bv,
                calc_ms, free_mem
            )
        )

        # CSVに保存
        f.write(
            "%d,%.4f,%.4f,%.8f,"
            "%.4f,%.4f,%.8f,%d,%d\n"
            % (
                trial + 1,
                x, y, value,
                bx, by, bv,
                calc_ms, free_mem
            )
        )

        f.flush()


total_ms = time.ticks_diff(
    time.ticks_ms(), total_start
)

bx, by, bv = bo.best()

print("----------------------------")
print("Optimization completed")
print("Best x:", bx)
print("Best y:", by)
print("Best value:", bv)
print("Total time:", total_ms / 1000, "s")
print("Saved: /flash/bo_test.csv")
