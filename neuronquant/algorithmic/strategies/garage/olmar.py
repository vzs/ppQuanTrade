#
# Copyright 2012 Xavier Bruhiere
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

# From quantopian: https://github.com/quantopian/quantopian-algos


import numpy as np

from zipline.algorithm import TradingAlgorithm
from zipline.transforms import MovingAverage
from zipline.finance.slippage import VolumeShareSlippage
from zipline.finance.commission import PerShare


class OLMAR(TradingAlgorithm):
    """
    On-Line Portfolio Moving Average Reversion

    More info can be found in the corresponding paper:
    http://icml.cc/2012/papers/168.pdf
    """
    def initialize(self, properties):
        self.price = {}
        self.eps = properties.get('eps', 1)
        self.days = 0
        self.window_length = properties.get('window_length', 5)
        self.add_transform(MovingAverage, 'mavg', ['price'],
                           window_length=self.window_length)

        #slip = VolumeShareSlippage(volume_limit=0.25, price_impact=0)
        #self.set_slippage(slip)
        #self.set_commission(PerShare(cost=0))

        self.stocks = None
        self.m = None
        self.b_t = None
        self.last_desired_port = None

    def handle_data(self, data):
        self.days += 1
        if self.days < self.window_length:
            return

        if not self.initialized:
            self.stocks = data.keys()
            self.m = len(data.keys())
            self.b_t = np.ones(self.m) / self.m
            self.last_desired_port = np.ones(self.m) / self.m
            self.rebalance_portfolio(data, self.b_t)
            self.initialized = True
            return

        m = self.m

        x_tilde = np.zeros(m)
        b = np.zeros(m)

        # find relative moving average price for each security
        for i, stock in enumerate(self.stocks):
            price = data[stock].price
            # Relative mean deviation
            x_tilde[i] = data[stock]['mavg']['price'] / price

        ###########################
        # Inside of OLMAR (algo 2)
        x_bar = x_tilde.mean()

        # market relative deviation
        mark_rel_dev = x_tilde - x_bar

        # Expected return with current portfolio
        exp_return = np.dot(self.b_t, x_tilde)
        weight = self.eps - exp_return
        variability = (np.linalg.norm(mark_rel_dev)) ** 2

        # test for divide-by-zero case
        if variability == 0.0:
            step_size = 0
        else:
            step_size = max(0, weight / variability)

        b = self.b_t + step_size * mark_rel_dev
        b_norm = simplex_projection(b)
        np.testing.assert_almost_equal(b_norm.sum(), 1)

        self.rebalance_portfolio(data, b_norm)

        # update portfolio
        self.b_t = b_norm

    #NOTE Here is a new manager !
    def rebalance_portfolio(self, data, desired_port):
        #rebalance portfolio
        desired_amount = np.zeros_like(desired_port)
        current_amount = np.zeros_like(desired_port)
        prices = np.zeros_like(desired_port)

        if not self.initialized:
            positions_value = self.portfolio.starting_cash
        else:
            positions_value = self.portfolio.positions_value + \
                self.portfolio.cash

        for i, stock in enumerate(self.stocks):
            current_amount[i] = self.portfolio.positions[stock].amount
            prices[i] = data[stock].price

        desired_amount = np.round(desired_port * positions_value / prices)

        self.last_desired_port = desired_port
        diff_amount = np.nan_to_num(desired_amount - current_amount)

        for i, stock in enumerate(self.stocks):
            self.order(stock, diff_amount[i])


def simplex_projection(v, b=1):
    """Projection vectors to the simplex domain

    Implemented according to the paper: Efficient projections onto the
    l1-ball for learning in high dimensions, John Duchi, et al. ICML 2008.
    Implementation Time: 2011 June 17 by Bin@libin AT pmail.ntu.edu.sg
    Optimization Problem: min_{w}\| w - v \|_{2}^{2}
    s.t. sum_{i=1}^{m}=z, w_{i}\geq 0

    Input: A vector v \in R^{m}, and a scalar z > 0 (default=1)
    Output: Projection vector w

    :Example:
    >>> proj = simplex_projection([.4 ,.3, -.4, .5])
    >>> print proj
    array([ 0.33333333, 0.23333333, 0. , 0.43333333])
    >>> print proj.sum()
    1.0

    Original matlab implementation: John Duchi (jduchi@cs.berkeley.edu)
    Python-port: Copyright 2012 by Thomas Wiecki (thomas.wiecki@gmail.com).
    """

    v = np.asarray(v)
    if np.isnan(v).any():
        return np.ones(len(v))
    #v = np.nan_to_num(np.asarray(v))
    p = len(v)

    # Sort v into u in descending order
    v = (v > 0) * v
    u = np.sort(v)[::-1]
    sv = np.cumsum(u)

    try:
        rho = np.where(u > (sv - b) / np.arange(1, p + 1))[0][-1]
        theta = np.max([0, (sv[rho] - b) / (rho + 1)])
        w = (v - theta)
        w[w < 0] = 0
    except:
        import ipdb; ipdb.set_trace()
    return w
    #return np.nan_to_num(w)
