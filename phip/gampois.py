# Copyright 2017 Uri Laserson
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import numpy as np
import pandas as pd
import scipy as sp
import scipy.stats


def poisson_logsf(counts, rate):
    counts = np.array(counts) + 1
    accum = counts * np.log(rate) - rate - sp.special.gammaln(counts + 1)
    while True:
        counts += 1
        next_terms = counts * np.log(rate) - rate - sp.special.gammaln(counts + 1)
        new = np.logaddexp(accum, next_terms)
        if np.all(new - accum < 0.0001):
            break
        accum = new
    return new


def fit_gamma(x):
    """Fit a gamma distribution

    Uses the "alpha, beta" parametrization, as commonly described
    """
    # define the log likelihood function
    m = len(x)
    s = x[x > 0].sum()
    sl = np.log(x[x > 0]).sum()

    def ll(x):
        return -1 * (
            m * x[0] * np.log(x[1])
            - m * sp.special.gammaln(x[0])
            + (x[0] - 1) * sl
            - x[1] * s
        )

    param = sp.optimize.minimize(
        ll,
        np.asarray([2, 1]),
        bounds=[(np.nextafter(0, 1), None), (np.nextafter(0, 1), None)],
    )
    (alpha, beta) = param.x
    return (alpha, beta)


def gamma_poisson_posterior_rates(counts, alpha, beta, upper_bound):
    """Infer rates for gamma-poisson mixture

    Each row of counts (DataFrame) is assumed to derive from a poisson
    distribution with some rate.  This function returns the mean of the
    posterior distribution of the rate for each row, assuming the prior is
    distributed as gamma(alpha, beta).

    Any count values above upper_bound are removed before inference.

    It is assumed that the columns of counts are normalized to some size
    factor.
    """

    # Assumes the counts for each clone are Poisson distributed with (learned)
    # Gamma prior. Therefore, the posterior is Gamma distributed, and we use
    # the expression for its expected value.
    masked = np.ma.masked_greater(counts.values, upper_bound)
    trimmed_sums = np.ma.sum(masked, axis=1).data
    trimmed_sizes = (~np.ma.getmaskarray(masked)).sum(axis=1)
    return (alpha + trimmed_sums) / (beta + trimmed_sizes)


def mlxp_gamma_poisson(counts, rates):
    """Compute -log10(pval) for Poisson variables

    counts is DataFrame where each row is assumed to be a set of Poisson draws
    from a variable with Poisson rate in rates.
    """
    mlxp = []
    for i in range(counts.shape[0]):
        mlxp.append(-poisson_logsf(counts.iloc[i].values, rates[i]) / np.log(10))
    mlxp = np.asarray(mlxp)
    mlxp = pd.DataFrame(data=mlxp, index=counts.index, columns=counts.columns)
    mlxp.replace(np.inf, -np.log10(np.finfo(np.float64).tiny), inplace=True)
    return mlxp


def gamma_poisson_model(counts, trim_percentile=99.9):
    """Compute -log10(pval) for counts matrix

    counts is DataFrame; assumed columns are normalized to some size factor.
    """
    upper_bound = sp.stats.scoreatpercentile(counts.values, trim_percentile)
    trimmed_means = np.ma.mean(
        np.ma.masked_greater(counts.values, upper_bound), axis=1
    ).data
    alpha, beta = fit_gamma(trimmed_means)
    background_rates = gamma_poisson_posterior_rates(counts, alpha, beta, upper_bound)
    mlxp = mlxp_gamma_poisson(counts, background_rates)
    return alpha, beta, background_rates, mlxp
