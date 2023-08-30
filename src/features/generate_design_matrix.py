import numpy as np
import pandas as pd


def generate_design_mat_and_labels(df, columns_to_filter, taus, verbose=True):
    """
    Wrapper function used to generate a design matrix for PWM
    multi-class logistic regression. Allows for the creation
    of the base design matrix used by Nick Roy (and modified)
    for 3 choices, as well as columns generated with exp kernel
    filters.

    N = number of trials
    D = number of features
    C = number of classes, in this case 3 (L, R, Violation)

    params
    ------
    df : pd.DataFrame
        dataframe with columns `s_a` `s_b` `session`, `violation`
        `correct_side` and `choice`, likely generated by
        get_rat_viol_data()
    columns_to_filter : list of str
        column(s) to apply exponential filter to
    taus : list of float
        tau(s) to use for generating exponential filter
    verbose : bool (default = True)
        whether to print out information about the design matrix

    returns
    -------
    X : pd.DataFrame, shape (N, D + 1)
        design matrix with all the features from
        generate_base_design_matrix() with all column/tau
        combinations created by create_exp_filter()
    Y : np.ndarray, shape (N, C), where C = 3
        one-hot encoded choice labels for each trial as left,
        right or violation
    """

    assert type(taus) == list, "taus must be in a list"
    assert type(columns_to_filter) == list, "columns_to_filter must be in a list"

    X, Y = generate_base_design_matrix(df, return_labels=True)

    for column in columns_to_filter:
        for tau in taus:
            create_exp_filter(
                source_df=df,
                tau=tau,
                output_df=X,
                column=column,
                len_factor=5,  # default
                scale=True,  # default
                verbose=verbose,
            )

    assert len(X) == len(Y), "X and Y must have same number of rows"
    if verbose:
        print(f"\nDesign Matrix generated with features:\n {X.columns}")

    return X, Y


def generate_base_design_matrix(df, return_labels=True):
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
    return_label : bool (default: True)
        whether to return one-hot encoded choice labels

    returns
    -------
    X : pd.DataFrame, shape (N, D + 1)
        design matrix with regressors for s_a, s_b,
        prev sound avg, correct side and choice info,
        normalized to standard normal with bias column added
    Y : np.ndarray, shape (N, C), where C = 3
        one-hot encoded choice labels for each trial as left,
        right or violation
    """

    X = pd.DataFrame()

    # normalize sa/sb to standard normal
    X["s_a"] = (df.s_a - df.s_a.mean()) / df.s_a.std()
    X["s_b"] = (df.s_b - df.s_b.mean()) / df.s_b.std()

    # mask session boundaries to 0
    session_boundaries_mask = df["session"].diff() == 0

    # mask previous violations to 0
    X["prev_violation"] = (df.violation.shift() * session_boundaries_mask).fillna(0)
    prev_violation_mask = X.prev_violation == 0

    # get average stimulus loudness from previous trial (if exists)
    # and normalize to standard normal
    # here we assume, if prev trial was violation or session boundary
    # that the sound avg is 0
    X["prev_sound_avg"] = df[["s_a", "s_b"]].shift().mean(axis=1)
    X["prev_sound_avg"] = (
        X.prev_sound_avg - X.prev_sound_avg.mean()
    ) / X.prev_sound_avg.std()
    X["prev_sound_avg"] = (
        X.prev_sound_avg * session_boundaries_mask * prev_violation_mask
    )

    # prev correct side (L, R) (0, 1) -> (-1, 1),
    # here we assume, if prev trial was violation or session boundary
    # that the correct is 0
    X["prev_correct"] = (
        df.correct_side.replace({0: -1}).astype(int).shift()
        * session_boundaries_mask
        * prev_violation_mask
    )

    # prev choice regressors (L, R) (0, 1) -> (-1, 1),
    # here we assume, if prev trial was violation (coded as nan)
    # or session boundary that the choice is 0
    X["prev_choice"] = (
        df.choice.replace({0: -1}).fillna(0).astype(int).shift()
        * session_boundaries_mask
    )

    X.fillna(0, inplace=True)  # .shifts() make trial 0 nan, remove this
    X.insert(0, "bias", 1)
    X.drop(columns=["prev_violation"], inplace=True)

    if return_labels:
        Y = one_hot_encode_labels(df)
        return X, Y
    else:
        return X


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


def create_exp_filter(
    source_df,
    tau,
    output_df=None,
    column="violation",
    len_factor=5,
    scale=True,
    verbose=True,
):
    """
    Function to create an exponential filter to a given dataframe column with
    specified parameters. Returns filter to initial dataframe or supplied
    design matrix (X).

    Note: at the time of writing this, the use case was to make an
    exp filter for violations. This column was not included in the
    design matrix and came from the primary trial matrix (df) which
    is why 2 dataframes (source_df, X) may be passed in.

    source_df : pd.DataFrame
        dataframe with column to create filter of (typically `violation`)
    tau : int
        time constant of exponential decay function
    output_df : pd.DataFrame or None (default = None)
        dataframe to append filtered column to, will default to
        source_df if None is supplied
    column : str (default = "violation")
        column of df to apply filter to
    len_factor : int (default = 5)
        how many multiples of tau filter should be in length. Jpillow
        suggested 5 so there is no drop-off at the tail
    scale : bool (default = True)
        if filter should be scaled between 0 and 1
    verbose : bool (default = True)
        whether to print out information about the design matrix

    returns
    -------
    None : appends new filter column to df or X (if supplied)
    """
    if tau is None:
        return

    # create kernel
    kernel = np.array([np.exp(-i / tau) for i in range(len_factor * tau)])

    # Convolve the kernel selected column
    convolution_result = np.convolve(source_df[column], kernel, mode="full")[
        : len(source_df)
    ]

    if scale:
        convolution_result = convolution_result / convolution_result.max()

    # add new column
    if output_df is not None:
        output_df[f"{column}_exp_{tau}"] = convolution_result
    else:
        source_df[f"{column}_exp_{tau}"] = convolution_result

    if verbose:
        print(f"Exp filter added | Column: {column}, Tau: {tau}")

    return None
