import pandas as pd
import numpy as np
from scipy.optimize import minimize


class BinaryLogisticRegression:
    def __init__(self, sigma=None, method="BFGS", disp=True):
        self.w = None
        self.sigma = sigma
        self.method = method
        self.disp = disp

    def fit(self, X, y):
        N, D_w_bias = X.shape
        initial_w = np.random.normal(0, 0.1, D_w_bias)

        if isinstance(X, pd.DataFrame):
            X = X.to_numpy()

        result = minimize(
            fun=self.cost,
            x0=initial_w,
            args=(X, y, self.sigma),
            method=self.method,
            jac=self._gradient,
            options={"disp": self.disp, "maxiter": 10000},
        )

        self.w = result.x
        return self.w

    def eval(self, X: pd.DataFrame, y: np.ndarray):
        return self.cost(self.w, X.to_numpy(), y, sigma=None)

    def cost(self, w, X, y, sigma):
        """
        Compute the negative log-likelihood for binary
        logistic regression with L2 regularization (or MAP).

        params
        ------
        w : np.ndarray, shape (D + 1, )
            weight vector with bias
        X : pd.DataFrame, shape (N, D + 1)
            design matrix with bias column
        y : np.ndarray, shape (N, )
            binary encoded choice labels where 0 is left and
            1 is right
        sigma : float (default=None)
            standard deviation of Gaussian prior, if None no
            regularization is applied

        returns
        -------
        - nll : float
            negative log-likelihood
        """

        logits = X @ w
        if sigma:
            penalty = (1 / (2 * sigma**2)) * np.sum(w**2)
        else:
            penalty = 0

        stable_log_term = np.vectorize(self.stable_log_one_plus_exp)(logits)
        nll = -np.mean(y * logits - stable_log_term) + penalty

        return nll

    def _gradient(self, w, X, y, sigma):
        """
        Compute the gradient of the negative log-likelihood for
        binary logistic regression with L2 regularization (or MAP).

        params
        ------
        w : np.ndarray, shape (D + 1, )
            weight vector with bias
        X : pd.DataFrame, shape (N, D + 1)
            design matrix with bias column
        y : np.ndarray, shape (N, )
            binary encoded choice labels where 0 is left and
            1 is right
        sigma : float (default=None)
            standard deviation of Gaussian prior, if None no
            regularization is applied

        returns
        -------
        gradient :  np.ndarray, shape (D + 1, )
            gradient of the negative log-likelihood

        """
        logits = X @ w
        # p = self.sigmoid(logits)

        # Use stable_log_one_plus_exp to make the calculation numerically stable
        stable_log_term = self.stable_log_one_plus_exp(-logits)

        # Compute p in a stable way
        p = np.exp(-stable_log_term)

        if sigma:
            penalty_gradient = w / sigma**2
            penalty_gradient[0] = 0  # No penalty for bias
        else:
            penalty_gradient = 0

        gradient = (np.dot(X.T, (p - y)) / len(y)) + penalty_gradient
        return gradient

    @staticmethod
    def sigmoid(z):
        return 1 / (1 + np.exp(-z))

    @staticmethod
    def stable_log_one_plus_exp(a):
        """
        Compute log(1 + exp(x)) in a numerically stable way
        to avoid overflow errors.

        params
        ------
        a : np.ndarray
            logit values (w^TX)

        returns
        -------
        log(1 + exp(a))
        """
        max_a = np.maximum(0, a)
        return max_a + np.log(np.exp(-max_a) + np.exp(a - max_a))

    def generate_data(self, N, D, sigma=None, random_state=None):
        """
        Generate data from a binary logistic regression
        model with optional L2 regularization (or MAP).

        params
        ------
        N : int
            number of trials/samples
        D : int
            number of features
        sigma : float (default=None)
            standard deviation of true weights, if None
            generated with std of 1
        random_state : int (default=None)
            random seed

        returns
        -------
        w : np.ndarray, shape (D + 1, )
            true weight vector
        X : pd.DataFrame, shape (N, D + 1)
            design matrix with bias column
        y : np.ndarray, shape (N, )
            binary encoded choice labels
        """

        ## Design Matrix
        X = np.random.normal(size=(N, D))
        X = np.c_[np.ones(N), X]  # bias column

        ## True Weights
        np.random.seed(random_state)
        if sigma:
            w = np.random.normal(loc=0, scale=sigma, size=(D + 1))
        else:
            w = np.random.normal(loc=0, scale=1, size=(D + 1))

        ## Choice Labels
        a = X @ w  # logits
        p = self.sigmoid(a)  # probabilities
        y = np.random.binomial(1, p)

        print(f"Generated {N} samples with {D} features")
        print(f"w is {w.shape} \nX is {X.shape} \ny is {y.shape}")
        print(f"w has mean {np.mean(w):.3f} and std {np.std(w):.3f}")

        return w, X, y
