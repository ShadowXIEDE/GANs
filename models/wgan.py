from __future__ import print_function
import mxnet as mx
import numpy as np
import logging
from datetime import datetime


class WGAN():

    def name(self):
        return 'WGAN Model'

    def __init__(self, opt, batch_size):
        self.opt = opt
        self.ngf = 64
        self.ndf = 64
        self.input_nc = 3
        self.batch_size = batch_size
        self.symG, self.symD = make_wgan_sym(self.ngf, self.ndf, self.input_nc)
        self.ctx = mx.gpu(0)
        self.lr = 0.0002
        self.wclip = 0.01

    def bind(self, rand_iter, train_iter):
        # bind symbol to module
        modG = mx.mod.Module(symbol=self.symG, data_names=('rand',), label_names=None, context=self.ctx)
        modG.bind(data_shapes=rand_iter.provide_data)
        modG.init_params(initializer=mx.init.Normal(0.02))
        modG.init_optimizer(
            optimizer='sgd',
            optimizer_params={
                'learning_rate': self.lr,
            })

        modD = mx.mod.Module(symbol=self.symD, data_names=('data',), label_names=None, context=self.ctx)
        modD.bind(data_shapes=train_iter.provide_data,
                  inputs_need_grad=True)
        modD.init_params(initializer=mx.init.Normal(0.02))
        modD.init_optimizer(
            optimizer='sgd',
            optimizer_params={
                'learning_rate': self.lr,
            })

        self.modG = modG
        self.modD = modD

    def generate(self, rbatch):
        self.modG.forward(rbatch, is_train=True)
        outG = self.modG.get_outputs()
        return outG

    def update(self, rbatch, batch):
        # clip weights
        for params in self.modD._exec_group.param_arrays:
            for param in params:
                mx.nd.clip(param, -self.wclip, self.wclip, out=param)

        # generate fake data
        self.modG.forward(rbatch, is_train=True)
        outG = self.modG.get_outputs()

        # update discriminator on fake
        self.modD.forward(mx.io.DataBatch(outG, label=None), is_train=True)
        self.modD.backward([-mx.nd.ones((self.batch_size, 1))])
        gradD = [[grad.copyto(grad.context) for grad in grads] for grads in self.modD._exec_group.grad_arrays]

        # update discriminator on real
        self.modD.forward(batch, is_train=True)
        self.modD.backward([mx.nd.ones((self.batch_size, 1))])
        for gradsr, gradsf in zip(self.modD._exec_group.grad_arrays, gradD):
            for gradr, gradf in zip(gradsr, gradsf):
                gradr += gradf
        self.modD.update()

        # update generator
        self.modD.forward(mx.io.DataBatch(outG, label=None), is_train=True)
        self.modD.backward([mx.nd.ones((self.batch_size, 1))])
        diffD = self.modD.get_input_grads()
        self.modG.backward(diffD)
        self.modG.update()


def make_wgan_sym(ngf, ndf, nc, no_bias=True, fix_gamma=True, eps=1e-5 + 1e-12):
    '''
    generate dcgan generator and discrimator
    '''
    BatchNorm = mx.sym.BatchNorm
    rand = mx.sym.Variable('rand')

    g1 = mx.sym.Deconvolution(rand, name='g1', kernel=(4, 4), num_filter=ngf * 8, no_bias=no_bias)
    gbn1 = BatchNorm(g1, name='gbn1', fix_gamma=fix_gamma, eps=eps)
    gact1 = mx.sym.Activation(gbn1, name='gact1', act_type='relu')

    g2 = mx.sym.Deconvolution(gact1, name='g2', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ngf * 4, no_bias=no_bias)
    gbn2 = BatchNorm(g2, name='gbn2', fix_gamma=fix_gamma, eps=eps)
    gact2 = mx.sym.Activation(gbn2, name='gact2', act_type='relu')

    g3 = mx.sym.Deconvolution(gact2, name='g3', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ngf * 2, no_bias=no_bias)
    gbn3 = BatchNorm(g3, name='gbn3', fix_gamma=fix_gamma, eps=eps)
    gact3 = mx.sym.Activation(gbn3, name='gact3', act_type='relu')

    g4 = mx.sym.Deconvolution(gact3, name='g4', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ngf, no_bias=no_bias)
    gbn4 = BatchNorm(g4, name='gbn4', fix_gamma=fix_gamma, eps=eps)
    gact4 = mx.sym.Activation(gbn4, name='gact4', act_type='relu')

    g5 = mx.sym.Deconvolution(gact4, name='g5', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=nc, no_bias=no_bias)
    gout = mx.sym.Activation(g5, name='gact5', act_type='tanh')

    data = mx.sym.Variable('data')

    d1 = mx.sym.Convolution(data, name='d1', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ndf, no_bias=no_bias)
    dact1 = mx.sym.LeakyReLU(d1, name='dact1', act_type='leaky', slope=0.2)

    d2 = mx.sym.Convolution(dact1, name='d2', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ndf * 2, no_bias=no_bias)
    dbn2 = BatchNorm(d2, name='dbn2', fix_gamma=fix_gamma, eps=eps)
    dact2 = mx.sym.LeakyReLU(dbn2, name='dact2', act_type='leaky', slope=0.2)

    d3 = mx.sym.Convolution(dact2, name='d3', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ndf * 4, no_bias=no_bias)
    dbn3 = BatchNorm(d3, name='dbn3', fix_gamma=fix_gamma, eps=eps)
    dact3 = mx.sym.LeakyReLU(dbn3, name='dact3', act_type='leaky', slope=0.2)

    d4 = mx.sym.Convolution(dact3, name='d4', kernel=(4, 4), stride=(2, 2), pad=(1, 1), num_filter=ndf * 8, no_bias=no_bias)
    dbn4 = BatchNorm(d4, name='dbn4', fix_gamma=fix_gamma, eps=eps)
    dact4 = mx.sym.LeakyReLU(dbn4, name='dact4', act_type='leaky', slope=0.2)

    d5 = mx.sym.Convolution(dact4, name='d5', kernel=(4, 4), num_filter=1, no_bias=no_bias)
    d5 = mx.sym.Flatten(d5)

    return gout, d5