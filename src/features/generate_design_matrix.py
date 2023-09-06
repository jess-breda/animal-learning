import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from sklearn.model_selection import train_test_split


class DesignMatrixGenerator:
    def __init__(self, verbose=True):
        self.verbose = verbose

    @staticmethod
    def normalize_column(col):
        return (col - col.mean()) / col.std()

    def generate_design_matrix(
        self, df, tau, return_labels=True, drop_session_column=False
    ):
        """
        Function to generate "base" design matrix given a dataframe
        with violations tracked. In this case "base" means using the
        same regressors as Nick Roy did in Psytrack, but adjusted to
        take into account 3 choice options (L,R, Violation).

        N = number of trials
        D = number of features
        C = number of classes, in this case 3 (L, R, Violation)

        params
        ------
        df : pd.DataFrame
            dataframe with columns `s_a` `s_b` `session`, `violation`
            `correct_side` and `choice`, likely generated by
            get_rat_viol_data()
        return_label : bool (default = True)
            whether to return one-hot encoded choice labels
        drop_session_column : bool (default = False)
            whether to drop 'session' column. should be set to
            false if doing session based train/test split
            following design matrix generation

        returns
        -------
        X : pd.DataFrame, shape (N, D + 1)
            design matrix with regressors for s_a, s_b,
            prev sound avg, correct side and choice info,
            normalized to standard normal with bias column added
        Y : np.ndarray, shape (N, C), where C = 3 if return_labels=True
            one-hot encoded choice labels for each trial as left,
            right or violation
        """
        # Initialize
        X = pd.DataFrame()
        stim_cols = ["s_a", "s_b"]

        # Masks- if first trial in a session and/or previous trial
        # was a violation, "prev" variables get set to 0
        session_boundaries_mask = df["session"].diff() == 0
        prev_violation_mask = (
            df["violation"].shift() * session_boundaries_mask
        ).fillna(0) == 0

        # Stimuli (s_a, s_b) get normalized
        for col in stim_cols:
            X[stim_cols] = self.normalize_column(df[stim_cols])

        # Average previous stimulus (s_a, s_b) loudness
        X["prev_sound_avg"] = df[stim_cols].shift().mean(axis=1)
        X["prev_sound_avg"] = self.normalize_column(X["prev_sound_avg"])
        X["prev_sound_avg"] *= session_boundaries_mask * prev_violation_mask

        # Prev correct side (L, R) (0, 1) -> (-1, 1),
        X["prev_correct"] = (
            df.correct_side.replace({0: -1}).astype(int).shift()
            * session_boundaries_mask
            * prev_violation_mask
        )

        # prev choice regressors (L, R, V) (0, 1, Nan) -> (-1, 1, 0),
        X["prev_choice"] = (
            df.choice.replace({0: -1}).fillna(0).astype(int).shift()
            * session_boundaries_mask
        )

        X.fillna(0, inplace=True)  # remove nan from shift()
        X.insert(0, "bias", 1)  # add bias column
        X["session"] = df.session

        # Apply exponential filter if tau is not None
        if tau is not None:
            self.exp_filter = ExpFilter(tau=tau, verbose=self.verbose)
            self.exp_filter.apply_filter_to_dataframe(df, output_df=X)

        if drop_session_column:
            X.drop(columns=["session"], inplace=True)

        if return_labels:
            Y = self.one_hot_encode_labels(df)
            return X, Y
        else:
            return X

    @staticmethod
    def one_hot_encode_labels(df):
        """
        Function to one-hot encode choice labels for each trial as
        left, right or violation (C = 3)

        params
        ------
        df : pd.DataFrame
            dataframe with columns `choice` likely generated by
            get_rat_viol_data()

        returns
        -------
        Y : np.ndarray, shape (N, C), where C = 3
            one-hot encoded choice labels for each trial as left,
            right or violation
        """

        Y = pd.get_dummies(df["choice"], "choice", dummy_na=True).to_numpy(copy=True)
        return Y

    def get_train_test_sessions(self, df, test_size, random_state=45):
        """
        This function will return a list of sessions to use for training
        and testing respectively. To apply, see function
        see apply_session_train_test_split()


        Parameters:
        -----------
        df : pd.DataFrame
            dataframe with `sessions` column
        test_size : float
            Proportion of data to use for test set
        """
        unique_sessions = df["session"].unique()
        train_sessions, test_sessions = train_test_split(
            unique_sessions, test_size=test_size, random_state=random_state
        )

        self.train_sessions = train_sessions
        self.test_sessions = test_sessions

    def apply_session_train_test_split(self, X, Y):
        """
        train_sessions = np.array
            sessions for the
        test_values = np.array indices for the test values

        """
        # TODO add in a check to see if self._train_session
        # TODO exists, and if not, call get_train_test_sessions

        # Filter rows based on session values for X
        X_train = X[X["session"].isin(self.train_sessions)].copy()
        X_test = X[X["session"].isin(self.test_sessions)].copy()

        # Filter rows based on session values for Y
        # Assuming the index of Y corresponds to that of X
        Y_train = Y[X["session"].isin(self.train_sessions).values]
        Y_test = Y[X["session"].isin(self.test_sessions).values]

        X_train.drop(columns=["session"], inplace=True)
        X_test.drop(columns=["session"], inplace=True)

        return X_train, X_test, Y_train, Y_test


class ExpFilter:
    def __init__(self, tau, column="violation", len_factor=5, verbose=True):
        self.tau = tau
        self.column = column
        self.len_factor = len_factor
        self.verbose = verbose

    def create_kernel(self):
        """
        create an exp decay kernal with time constant tau and
        kernel length = len factor * tau
        """

        return np.array(
            [np.exp(-i / self.tau) for i in range(self.len_factor * self.tau)]
        )

    def plot_kernel(self):
        kernel = self.create_kernel()
        fig, ax = plt.subplots(figsize=(6, 4))
        plt.plot(kernel)
        plt.title(f"Exponential filter kernel | Tau: {self.tau}")
        plt.show()

    def apply_filter_to_session(self, session_df):
        """
        apply kernel to individual sessions for independent
        filtering of column history
        """
        kernel = self.create_kernel()

        # Convolve the kernel with selected column
        convolution_result = np.convolve(session_df[self.column], kernel, mode="full")[
            : len(session_df)
        ]

        session_df[f"{self.column}_exp_{self.tau}"] = convolution_result

        return session_df

    def apply_filter_to_dataframe(self, source_df, output_df=None):
        """
        Function to apply exp kernel to a column given and
        entire dataframe on a session-by-session basis
        """
        if self.tau is None:
            return

        if output_df is None:
            output_df = source_df

        for session_id, session_data in source_df.groupby("session"):
            filtered_session = self.apply_filter_to_session(session_data.copy())
            output_df.loc[
                output_df["session"] == session_id, f"{self.column}_exp_{self.tau}"
            ] = filtered_session[f"{self.column}_exp_{self.tau}"]

            if self.verbose:
                print(
                    f"Exp filter added for session {session_id} | Column: {self.column}, Tau: {self.tau}"
                )

        # scale column by max to bound between 0 and 1
        output_df[f"{self.column}_exp_{self.tau}"] /= output_df[
            f"{self.column}_exp_{self.tau}"
        ].max()
