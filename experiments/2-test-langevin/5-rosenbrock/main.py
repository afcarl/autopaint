# Main demo script
import autograd.numpy as np
from autograd import value_and_grad
import numpy.linalg
import matplotlib.image
import pickle
import time

from autograd import grad

import matplotlib.pyplot as plt

from autopaint.plotting import *
from autopaint.langevin import build_langevin_sampler
from autopaint.util import log_tapered_inv_rosenbrock
from autopaint.optimizers import adam

def plot_sampler_params(params, filename):

    mean = parser.get(params, 'mean')
    stddev = np.exp(parser.get(params, 'log_stddev'))
    stepsizes = np.exp(parser.get(params, 'log_stepsizes'))
    noise_sizes = np.exp(parser.get(params, 'log_noise_sizes'))

    # ----- Nice versions of Alpha and beta schedules for paper -----
    fig = plt.figure(0)
    fig.clf()
    ax = fig.add_subplot(411)
    ax.plot(mean, 'o-')
    ax.set_ylabel('Mean', fontproperties='serif')

    ax = fig.add_subplot(412)
    ax.plot(stddev, 'o-')
    ax.set_ylabel('stddev', fontproperties='serif')

    ax = fig.add_subplot(413)
    ax.plot(stepsizes, 'o-')
    ax.set_ylabel('stepsizes', fontproperties='serif')
    ax.set_xlabel('Langevin iterations', fontproperties='serif')

    ax = fig.add_subplot(414)
    ax.plot(noise_sizes, 'o-')
    ax.set_ylabel('noise_sizes', fontproperties='serif')
    ax.set_xlabel('Langevin iterations', fontproperties='serif')

    fig.subplots_adjust(hspace=.5)
    plt.savefig(filename)


if __name__ == '__main__':

    t0 = time.time()

    num_samples = 50
    num_langevin_steps = 10
    num_sampler_optimization_steps = 400

    D = 200

    init_mean = np.zeros(D)
    init_log_stddevs = np.log(1e-4*np.ones(D))
    init_log_stepsizes = np.log(0.1*np.ones(num_langevin_steps))
    init_log_noise_sizes = np.log(0.1*np.ones(num_langevin_steps))

    rs = np.random.npr.RandomState(0)

    sample_and_run_langevin, parser = build_langevin_sampler(log_tapered_inv_rosenbrock, D, num_langevin_steps, approx=True)

    sampler_params = np.zeros(len(parser))
    parser.put(sampler_params, 'mean', init_mean)
    parser.put(sampler_params, 'log_stddev', init_log_stddevs)
    parser.put(sampler_params, 'log_stepsizes', init_log_stepsizes)
    parser.put(sampler_params, 'log_noise_sizes', init_log_noise_sizes)

    def get_batch_marginal_likelihood_estimate(sampler_params):
        samples, loglik_estimates, entropy_estimates = sample_and_run_langevin(sampler_params, rs, num_samples)
        marginal_likelihood_estimates = loglik_estimates + entropy_estimates
        print "mean loglik:", np.mean(loglik_estimates).value, " mean entropy:", np.mean(entropy_estimates).value
        plot_density(samples.value, "approximating_dist.png")
        return np.mean(marginal_likelihood_estimates)

    ml_and_grad = value_and_grad(get_batch_marginal_likelihood_estimate)

    global start
    start= None

    def print_ml(ml,params):
        print "log marginal likelihood:", ml



    startOpt = time.time()
    # Optimize Langevin parameters.
    final_params, final_value = adam(ml_and_grad,sampler_params,num_sampler_optimization_steps,callback=print_ml)
    endOpt = time.time()


    t1 = time.time()
    print "total runtime", t1-t0