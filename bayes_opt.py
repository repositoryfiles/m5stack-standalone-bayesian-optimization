
import math


class BayesianOptimizer:

    def __init__(self, length_scale=0.25,
                 noise=0.000001, kappa=2.0,
                 grid_size=21):

        self.length_scale = length_scale
        self.noise = noise
        self.kappa = kappa
        self.grid_size = grid_size

        self.X = []
        self.Y = []

    # RBFカーネル
    def kernel(self, a, b):
        dx = a[0] - b[0]
        dy = a[1] - b[1]

        r2 = dx * dx + dy * dy

        return math.exp(
            -r2 / (2 * self.length_scale ** 2)
        )

    # 実験結果の登録
    def add(self, x, y, value):
        self.X.append((x, y))
        self.Y.append(value)

    # コレスキー分解
    def cholesky(self, A):
        n = len(A)

        L = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1):

                s = A[i][j]

                for k in range(j):
                    s -= L[i][k] * L[j][k]

                if i == j:
                    L[i][j] = math.sqrt(
                        max(s, 1e-12)
                    )
                else:
                    L[i][j] = s / L[j][j]

        return L

    # 前進代入
    def forward(self, L, b):
        n = len(b)
        x = [0.0] * n

        for i in range(n):
            s = b[i]

            for j in range(i):
                s -= L[i][j] * x[j]

            x[i] = s / L[i][i]

        return x

    # 後退代入
    def backward(self, L, b):
        n = len(b)
        x = [0.0] * n

        for i in range(n - 1, -1, -1):
            s = b[i]

            for j in range(i + 1, n):
                s -= L[j][i] * x[j]

            x[i] = s / L[i][i]

        return x

    # 次の探索点を決定
    def suggest(self):

        n = len(self.X)

        if n == 0:
            return 0.5, 0.5

        # 共分散行列
        K = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(i + 1):
                v = self.kernel(
                    self.X[i], self.X[j]
                )
                K[i][j] = v
                K[j][i] = v

            K[i][i] += self.noise

        L = self.cholesky(K)

        # 評価値の標準化
        mean_y = sum(self.Y) / n

        std_y = math.sqrt(
            sum((v - mean_y) ** 2
                for v in self.Y) / n
        )

        std_y = max(std_y, 1e-8)

        yn = [
            (v - mean_y) / std_y
            for v in self.Y
        ]

        alpha = self.backward(
            L, self.forward(L, yn)
        )

        best_lcb = float("inf")
        best_point = None

        m = self.grid_size - 1

        # グリッド探索
        for i in range(self.grid_size):
            for j in range(self.grid_size):

                p = (i / m, j / m)

                # 評価済みの点は除外
                if p in self.X:
                    continue

                k = [
                    self.kernel(p, q)
                    for q in self.X
                ]

                # 予測平均
                mu = sum(
                    k[t] * alpha[t]
                    for t in range(n)
                )

                # 予測分散
                v = self.forward(L, k)

                var = max(
                    0.0,
                    1.0 - sum(a * a for a in v)
                )

                sigma = math.sqrt(var)

                # LCB獲得関数
                lcb = mu - self.kappa * sigma

                if lcb < best_lcb:
                    best_lcb = lcb
                    best_point = p

        return best_point

    # 現時点での最良条件
    def best(self):

        i = self.Y.index(min(self.Y))

        return (
            self.X[i][0],
            self.X[i][1],
            self.Y[i]
        )
