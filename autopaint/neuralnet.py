import time
import autograd.numpy as np
import autograd.numpy.random as npr
from autograd.scipy.misc import logsumexp
from autograd import grad
from autograd.util import quick_grad_check
from autopaint.util import sigmoid,build_logprob_mvn



# Network parameters   TODO: move these into experiment scripts.
layer_sizes = [784, 200, 100, 10]
L2_reg = 1.0

# Training parameters
param_scale = 0.1
learning_rate = 1e-3
momentum = 0.9
batch_size = 256
num_epochs = 50


def make_nn_funs(layer_sizes, L2_reg):
    shapes = zip(layer_sizes[:-1], layer_sizes[1:])
    N = sum((m+1)*n for m, n in shapes)

    def unpack_layers(W_vect):
        for m, n in shapes:
            yield W_vect[:m*n].reshape((m,n)), W_vect[m*n:m*n+n]
            W_vect = W_vect[(m+1)*n:]

    def predict_fun(W_vect, inputs):
        """Returns normalized log-prob of all classes."""
        for W, b in unpack_layers(W_vect):
            outputs = np.dot(inputs, W) + b
            inputs = np.tanh(outputs)
        return outputs - logsumexp(outputs, axis=1, keepdims=True)

    def loss(W_vect, X, T):
        log_prior = -L2_reg * np.dot(W_vect, W_vect)
        log_lik = np.sum(predict_fun(W_vect, X) * T)
        return - log_prior - log_lik

    def likelihood(W_vect, X, T):
        return np.sum(predict_fun(W_vect, X) * T, axis=1)

    def frac_err(W_vect, X, T):
        return np.mean(np.argmax(T, axis=1) != np.argmax(predict_fun(W_vect, X), axis=1))

    return N, predict_fun, loss, frac_err, likelihood


def make_binarized_nn_funs(layer_sizes, L2_reg):
    #Like a neural net, but now our outputs are in [0,1]^D and the labels are {0,1}^D
    shapes = zip(layer_sizes[:-1], layer_sizes[1:])
    N = sum((m+1)*n for m, n in shapes)

    def unpack_layers(W_vect):
        for m, n in shapes:
            yield W_vect[:m*n].reshape((m,n)), W_vect[m*n:m*n+n]
            W_vect = W_vect[(m+1)*n:]

    def predict_fun(W_vect, inputs):
        """Probability of activation of outputs"""
        for W, b in unpack_layers(W_vect):
            outputs = np.dot(inputs, W) + b
            inputs = np.tanh(outputs)
        return sigmoid(outputs)

    def likelihood(W_vect, X, T):
        pred_probs = predict_fun(W_vect,X)
        label_probabilities =  np.log(pred_probs)* T + np.log((1 - pred_probs))* (1 - T)
        #TODO: Mean or sum?
        ll_vect = np.sum(label_probabilities,axis = 1)
        return np.mean(ll_vect)

    return N, predict_fun, likelihood


def make_gaussian_nn_funs(layer_sizes, L2_reg):
    #Like a neural net, but now our outputs are a mean and the log of a diagonal covariance matrix
    shapes = zip(layer_sizes[:-1], layer_sizes[1:])
    N = sum((m+1)*n for m, n in shapes)

    def unpack_layers(W_vect):
        for m, n in shapes:
            yield W_vect[:m*n].reshape((m,n)), W_vect[m*n:m*n+n]
            W_vect = W_vect[(m+1)*n:]

    def predict_fun(W_vect, inputs):
        """Returns the mean of a gaussian and the log of a diagonal covariance matrix """
        for W, b in unpack_layers(W_vect):
            outputs = np.dot(inputs, W) + b
            inputs = np.tanh(outputs)
        D = inputs.shape[1]/2
        mu = outputs[:,0:D]
        log_sig = outputs[:,D:2*D]
        return mu,log_sig

    def likelihood(W_vect, X, T):
        mu,log_sig = predict_fun(W_vect,X)
        N = mu.shape[0]
        #TODO: Vectorize
        sum_logprobs = 0.0
        for i in xrange(N):
            curMu = mu[i,:]
            curCov = np.diag(np.exp(log_sig[i,:])**2)
            cur_log_prob = build_logprob_mvn(curMu,curCov,pseudo_inv=False)
            sum_logprobs = sum_logprobs + cur_log_prob(T[i,:])
        return sum_logprobs/N

    return N, predict_fun, likelihood

one_hot = lambda x, K: np.array(x[:,None] == np.arange(K)[None, :], dtype=int)

def load_mnist():
    print "Loading training data..."
    import imp, urllib
    partial_flatten = lambda x : np.reshape(x, (x.shape[0], np.prod(x.shape[1:])))

    source, _ = urllib.urlretrieve(
        'https://raw.githubusercontent.com/HIPS/Kayak/master/examples/data.py')
    data = imp.load_source('data', source).mnist()
    train_images, train_labels, test_images, test_labels = data
    train_images = partial_flatten(train_images) / 255.0
    test_images  = partial_flatten(test_images)  / 255.0
    train_labels = one_hot(train_labels, 10)
    test_labels = one_hot(test_labels, 10)
    N_data = train_images.shape[0]

    return N_data, train_images, train_labels, test_images, test_labels


def make_batches(N_data, batch_size):
    return [slice(i, min(i+batch_size, N_data))
            for i in range(0, N_data, batch_size)]


def sgd(grad, x, callback=None, num_iters=200, step_size=0.1, mass=0.9):
    """Stochastic gradient descent with momentum.
    grad() must have signature grad(x, i), where i is the iteration number."""
    velocity = np.zeros(len(x))
    for i in range(num_iters):
        g = grad(x)
        if callback: callback(x, i, g)
        velocity = mass * velocity - (1.0 - mass) * g
        x = x + step_size * velocity
    return x


def train_nn(train_images, train_labels, test_images, test_labels):

    # Make neural net functions
    N_weights, predict_fun, loss_fun, frac_err, likelihood = make_nn_funs(layer_sizes, L2_reg)
    loss_grad = grad(loss_fun)

    # Initialize weights
    rs = npr.RandomState()
    weights = rs.randn(N_weights) * param_scale

    # Check the gradients numerically, just to be safe
    quick_grad_check(loss_fun, weights, (train_images, train_labels))

    print "    Epoch      |    Train err  |   Test err  "

    def print_perf(epoch, weights):
        test_perf  = frac_err(weights, test_images, test_labels)
        train_perf = frac_err(weights, train_images, train_labels)
        print "{0:15}|{1:15}|{2:15}".format(epoch, train_perf, test_perf)

    # Train with sgd
    batch_idxs = make_batches(train_images.shape[0], batch_size)
    cur_dir = np.zeros(N_weights)

    for epoch in range(num_epochs):
        print_perf(epoch, weights)
        for idxs in batch_idxs:
            grad_W = loss_grad(weights, train_images[idxs], train_labels[idxs])
            cur_dir = momentum * cur_dir + (1.0 - momentum) * grad_W
            weights -= learning_rate * cur_dir

    return weights, predict_fun, likelihood


