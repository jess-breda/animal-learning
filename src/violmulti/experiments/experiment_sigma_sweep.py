"""
Child Experiment class that specifically runs a sigma
sweep over a stable (provided) design matrix for each
animal. Model can be binary or multi

Written by Jess Breda
"""

import pandas as pd
from violmulti.experiments.experiment import Experiment


class ExperimentSigmaSweep(Experiment):
    """
    Model that runs a sigma sweep for a given
    set of animals, sigmas and parameters
    """

    def __init__(self, params):
        super().__init__(params)
        super().unpack_config_for_single_model()  # gets model name and type

    def run(self):
        for animal_id in self.animals:
            animal_df = self.df.query("animal_id == @animal_id")

            print(f"\n >>>> evaluating animal {animal_id} <<<<")
            self.run_single_animal(animal_id, animal_df)

    def run_single_animal(self, animal_id, animal_df):
        """
        Run an experiment given a fixed design matrix for
        a single animal that sweeps over sigmas
        """
        # build design matrix- using model_names' dmg_config
        X, Y = super().generate_design_matrix_for_animal(animal_df, self.model_name)

        # train test split
        tts = super().get_animal_train_test_sessions(animal_df)
        X_train, X_test, Y_train, Y_test = tts.apply_session_split(X, Y)

        for sigma in self.sigmas:
            print(f"\n ***** evaluating model {self.model_name} w/ sigma {sigma} *****")
            W_fit, test_nll, train_nll = super().fit_and_evaluate_model(
                X_train,
                X_test,
                Y_train,
                Y_test,
                sigma,
                self.model_name,
                lr_only=False,
            )

            # Store
            data = {
                "animal_id": animal_id,
                "model_name": self.model_name,
                "model_type": self.model_type,
                "nll": test_nll,
                "train_nll": train_nll,
                "sigma": sigma,
                "features": X_test.columns,
                "weights": W_fit,
                "n_train_trials": len(X_train),
                "n_test_trials": len(X_test),
            }
            super().store(data, self.fit_models)
