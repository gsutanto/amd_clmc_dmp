#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""
Created on Wed Apr 10 15:00:00 2017

@author: gsutanto
"""

import scipy.io as sio
import numpy as np
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../../utilities/'))
from FeedForwardNeuralNetwork import *
from utilities import *
from copy import deepcopy

class RPMNN(FeedForwardNeuralNetwork):
    """
    Class for special feed-forward neural network,
    the final hidden layer is gated/modulated by phase-LWR.
    For each dimension of the output, there is one dedicated neural network.
    All neural networks (i.e. for all output dimensions) are optimized together.
    """
    
    def __init__(self, name, D_input, 
                 regular_hidden_layer_topology, regular_hidden_layer_activation_func_list, 
                 N_phaseLWR_kernels, D_output, 
                 path="", is_using_phase_kernel_modulation=True, is_predicting_only=False):
        self.name = name
        
        self.neural_net_topology = [D_input] + regular_hidden_layer_topology + [N_phaseLWR_kernels, D_output]
        print ("RPMNN Topology:")
        print (self.neural_net_topology)
        
        self.D_output = D_output
        self.N_layers = len(self.neural_net_topology)
        
        if (regular_hidden_layer_activation_func_list == []):
            self.neural_net_activation_func_list = ['identity'] * self.N_layers
        else:
            assert (len(regular_hidden_layer_activation_func_list) == len(regular_hidden_layer_topology)), "len(regular_hidden_layer_activation_func_list) must be == len(regular_hidden_layer_topology)"
            self.neural_net_activation_func_list = ['identity'] + regular_hidden_layer_activation_func_list + ['identity', 'identity']
        # First Layer (Input Layer) always uses 'identity' activation function (and it does NOT matter actually; this is mainly for the sake of layer-indexing consistency...).
        assert (len(self.neural_net_activation_func_list) == self.N_layers), "len(self.neural_net_activation_func_list) must be == self.N_layers"
        print ("Neural Network Activation Function List:")
        print (self.neural_net_activation_func_list)
        
        self.model_params = {}
        
        self.is_predicting_only = is_predicting_only
        if (self.is_predicting_only == False): # means both predicting and learning, i.e. this requires to be called from inside a TensorFlow session.
            if (path == ""):
                self.num_params = self.defineNeuralNetworkModel()
            else:
                self.num_params = self.loadNeuralNetworkFromPath(path)
        else: # only doing predictions, do NOT need to be called from inside a TensorFlow session
            self.num_params = self.loadNeuralNetworkFromPath(path)
        
        self.is_using_phase_kernel_modulation = is_using_phase_kernel_modulation
    
    def getLayerName(self, layer_index):
        assert layer_index > 0, "layer_index must be > 0"
        assert layer_index < self.N_layers, "layer_index must be < N_layers"
        if (layer_index == self.N_layers - 1):  # Output Layer
            layer_name = 'output'
        elif (layer_index == self.N_layers - 2):  # Final Hidden Layer with Phase LWR Gating/Modulation
            layer_name = 'phaseLWR'
        else:  # Hidden Layer
            layer_name = 'hidden' + str(layer_index)
        return layer_name
    
    def defineNeuralNetworkModel(self):
        """
        Define the Neural Network model.
        """
        assert (self.is_predicting_only == False), 'Needs to be inside a TensorFlow session, therefore self.is_predicting_only must be False!'
        
        num_params = 0
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
            
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=False):
                    if (i == self.N_layers - 1):
                        # neg_low_pass_filt_const == -alpha_C = -low_pass_filter_constant
                        neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1], trainable=False, initializer=tf.random_normal_initializer((-0.5), 1e-14, seed=38))
                        neg_low_pass_filt_const_dim = neg_low_pass_filt_const.get_shape().as_list()
                        num_params += neg_low_pass_filt_const_dim[0] * neg_low_pass_filt_const_dim[1]
                    weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size], initializer=tf.random_normal_initializer(0.0, 1e-14, seed=38))
                    weights_dim = weights.get_shape().as_list()
                    num_params += weights_dim[0] * weights_dim[1]
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        # biases = tf.get_variable('biases', [current_layer_dim_size], initializer=tf.constant_initializer(0.0))
                        biases = tf.get_variable('biases', [current_layer_dim_size], initializer=tf.random_normal_initializer(0.0, 1e-14, seed=38))
                        num_params += biases.get_shape().as_list()[0]
        num_params /= self.D_output
        print("Total # of Parameters = %d" % num_params)
        return num_params
    
    def performNeuralNetworkPrediction(self, dataset, normalized_phase_kernels_times_dt_per_tau, 
                                       Ct_t_minus_1_times_dt_per_tau, Ct_t_minus_1,
                                       dropout_keep_prob=1.0, layer_num=-1):
        """
        Perform Neural Network Prediction on a given dataset.
        :param dataset: dataset on which prediction will be performed
        :param normalized_phase_kernels_times_dt_per_tau: (dt/tau) * normalized phase-based Gaussian kernels activation associated with the dataset
        :param dropout_keep_prob: probability of keeping a node (instead of dropping it; 1.0 means no drop-out)
        :param Ct_t_minus_1_times_dt_per_tau: (Ct[t-1] * (dt/tau))
        :param Ct_t_minus_1:                  (Ct[t-1])
        :param layer_num: layer number, at which the prediction would like to be made (default is at output (self.N_layers-1))
        :return: output tensor (in output layer; in this case is Ct[t])
        """
        if (layer_num == -1):
            layer_num = self.N_layers-1 # Output Layer (default)
        assert layer_num < self.N_layers, "layer_num must be < N_layers"
        hidden_dim = [None] * self.D_output
        hidden_drop_dim = [dataset] * self.D_output
        output_dim = [None] * self.D_output
        Ct_t_minus_1_times_dt_per_tau_dim = [None] * self.D_output
        Ct_t_minus_1_dim = [None] * self.D_output
        for dim_out in range(self.D_output):
            if (self.is_predicting_only == False):
                Ct_t_minus_1_times_dt_per_tau_dim[dim_out] = tf.slice(Ct_t_minus_1_times_dt_per_tau, [0, dim_out], [-1, 1])
                Ct_t_minus_1_dim[dim_out] = tf.slice(Ct_t_minus_1, [0, dim_out], [-1, 1])
            else:
                Ct_t_minus_1_times_dt_per_tau_dim[dim_out] = Ct_t_minus_1_times_dt_per_tau[:,dim_out]
                Ct_t_minus_1_dim[dim_out] = Ct_t_minus_1[:,dim_out]
        
        for i in range(1, layer_num+1):
            layer_name = self.getLayerName(i)
    
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                
                if (self.is_predicting_only == False):
                    with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                        if (i == self.N_layers - 1):
                            # neg_low_pass_filt_const == -alpha_C = -low_pass_filter_constant
                            neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1])
                        weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                        if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                            biases = tf.get_variable('biases', [current_layer_dim_size])
                        
                        if (i < self.N_layers - 2):  # Regular Hidden Layer
                            affine_intermediate_result = tf.matmul(hidden_drop_dim[dim_out], weights) + biases
                            if (self.neural_net_activation_func_list[i] == 'identity'):
                                activation_func_output = affine_intermediate_result
                            elif (self.neural_net_activation_func_list[i] == 'tanh'):
                                activation_func_output = tf.nn.tanh(affine_intermediate_result)
                            elif (self.neural_net_activation_func_list[i] == 'relu'):
                                activation_func_output = tf.nn.relu(affine_intermediate_result)
                            else:
                                sys.exit('Unrecognized activation function: ' + self.neural_net_activation_func_list[i])
                            
                            hidden_dim[dim_out] = activation_func_output
                            hidden_drop_dim[dim_out] = tf.nn.dropout(hidden_dim[dim_out], dropout_keep_prob)
                        elif (i == self.N_layers - 2): # Final Hidden Layer with Phase LWR Gating/Modulation
                            if (self.is_using_phase_kernel_modulation):
                                hidden_dim[dim_out] = normalized_phase_kernels_times_dt_per_tau * (tf.matmul(hidden_drop_dim[dim_out], weights) + biases)
                                hidden_drop_dim[dim_out] = hidden_dim[dim_out] # no dropout
                            else:   # if NOT using phase kernel modulation:
                                hidden_dim[dim_out] = tf.nn.tanh(tf.matmul(hidden_drop_dim[dim_out], weights) + biases)
                                hidden_drop_dim[dim_out] = tf.nn.dropout(hidden_dim[dim_out], dropout_keep_prob)
                        else: # Output Layer
                            output_current_dim = Ct_t_minus_1_dim[dim_out] + tf.matmul(Ct_t_minus_1_times_dt_per_tau_dim[dim_out], neg_low_pass_filt_const) + tf.matmul(hidden_drop_dim[dim_out], weights)
                            output_dim[dim_out] = output_current_dim
                else:
                    if (i == self.N_layers - 1):
                        # neg_low_pass_filt_const == -alpha_C = -low_pass_filter_constant
                        neg_low_pass_filt_const = self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"]
                    weights = self.model_params[self.name+'_'+layer_dim_ID+"_weights"]
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = self.model_params[self.name+'_'+layer_dim_ID+"_biases"]
                    
                    if (i < self.N_layers - 2):  # Regular Hidden Layer
                        affine_intermediate_result = np.matmul(hidden_drop_dim[dim_out], weights) + biases
                        if (self.neural_net_activation_func_list[i] == 'identity'):
                            activation_func_output = affine_intermediate_result
                        elif (self.neural_net_activation_func_list[i] == 'tanh'):
                            activation_func_output = np.tanh(affine_intermediate_result)
                        elif (self.neural_net_activation_func_list[i] == 'relu'):
                            activation_func_output = affine_intermediate_result * (affine_intermediate_result > 0)
                        else:
                            sys.exit('Unrecognized activation function: ' + self.neural_net_activation_func_list[i])
                        
                        hidden_dim[dim_out] = activation_func_output
                        hidden_drop_dim[dim_out] = hidden_dim[dim_out]
                    elif (i == self.N_layers - 2): # Final Hidden Layer with Phase LWR Gating/Modulation
                        if (self.is_using_phase_kernel_modulation):
                            hidden_dim[dim_out] = normalized_phase_kernels_times_dt_per_tau * (np.matmul(hidden_drop_dim[dim_out], weights) + biases)
                        else:   # if NOT using phase kernel modulation:
                            hidden_dim[dim_out] = np.tanh(np.matmul(hidden_drop_dim[dim_out], weights) + biases)
                        hidden_drop_dim[dim_out] = hidden_dim[dim_out]
                    else: # Output Layer
                        output_current_dim = Ct_t_minus_1_dim[dim_out] + np.matmul(Ct_t_minus_1_times_dt_per_tau_dim[dim_out], neg_low_pass_filt_const) + np.matmul(hidden_drop_dim[dim_out], weights)
                        output_dim[dim_out] = output_current_dim
        if (layer_num == self.N_layers-1):
            if (self.is_predicting_only == False):
                output = tf.concat(1, output_dim)
            else:
                output = np.hstack(output_dim)
            return output
        else:
            return hidden_dim
    
    # def performNeuralNetworkTraining(self, prediction, ground_truth, initial_learning_rate, beta, N_steps):
    def performNeuralNetworkTraining(self, prediction, ground_truth, initial_learning_rate, beta):
        """
        Perform Neural Network Training (joint, across all output dimensions).
        :param prediction: prediction made by current model on a dataset
        :param ground_truth: the ground truth of the corresponding dataset
        :param initial_learning_rate: initial learning rate
        :param beta: L2 regularization constant
        """
        assert (self.is_predicting_only == False), 'Needs to be inside a TensorFlow session, therefore self.is_predicting_only must be False!'
        
        # Create an operation that calculates L2 prediction loss.
        pred_l2_loss = tf.nn.l2_loss(prediction - ground_truth, name='my_pred_L2_loss')
    
        # Create an operation that calculates L2 regularization loss.
        reg_l2_loss = 0
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
    
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                    if (i == self.N_layers - 1):
                        neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1])
                        reg_l2_loss = reg_l2_loss + tf.nn.l2_loss(neg_low_pass_filt_const)
                    weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                    reg_l2_loss = reg_l2_loss + tf.nn.l2_loss(weights)
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = tf.get_variable('biases', [current_layer_dim_size])
                        reg_l2_loss = reg_l2_loss + tf.nn.l2_loss(biases)
    
        loss = tf.reduce_mean(pred_l2_loss, name='my_pred_L2_loss_mean') + (beta * reg_l2_loss)
    
        # Create a variable to track the global step.
        global_step = tf.Variable(0, name='global_step', trainable=False)
        # Exponentially-decaying learning rate:
        # learning_rate = tf.train.exponential_decay(initial_learning_rate, global_step, N_steps, 0.1)
        # Create the gradient descent optimizer with the given learning rate.
        # Use the optimizer to apply the gradients that minimize the loss
        # (and also increment the global step counter) as a single training step.
        # train_op = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss, global_step=global_step)
        # train_op = tf.train.MomentumOptimizer(learning_rate, momentum=learning_rate/4.0, use_nesterov=True).minimize(loss, global_step=global_step)
        # train_op = tf.train.AdamOptimizer().minimize(loss, global_step=global_step)
        # train_op = tf.train.AdagradOptimizer(initial_learning_rate).minimize(loss, global_step=global_step)
        # train_op = tf.train.AdadeltaOptimizer().minimize(loss, global_step=global_step)
        train_op_dim = tf.train.RMSPropOptimizer(initial_learning_rate).minimize(loss, global_step=global_step)
        
        # return train_op, loss, learning_rate
        return train_op, loss
    
    # def performNeuralNetworkTraining(self, prediction, ground_truth, initial_learning_rate, beta, N_steps):
    def performNeuralNetworkTrainingPerDimOut(self, prediction, ground_truth, initial_learning_rate, beta, dim_out):
        """
        Perform Neural Network Training (per output dimension).
        :param prediction: prediction made by current model on a dataset
        :param ground_truth: the ground truth of the corresponding dataset
        :param initial_learning_rate: initial learning rate
        :param beta: L2 regularization constant
        :param dim_out: output dimension being considered
        """
        assert (self.is_predicting_only == False), 'Needs to be inside a TensorFlow session, therefore self.is_predicting_only must be False!'
        
        # Create an operation that calculates L2 prediction loss.
        pred_l2_loss_dim = tf.nn.l2_loss(prediction[:,dim_out] - ground_truth[:,dim_out])
        
        # Create an operation that calculates L2 regularization loss.
        reg_l2_loss_dim = 0
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
            layer_dim_ID = layer_name + '_' + str(dim_out)
            if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                current_layer_dim_size = self.neural_net_topology[i]
            else: # Output Layer
                current_layer_dim_size = 1
            with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                if (i == self.N_layers - 1):
                    neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1])
                    reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(neg_low_pass_filt_const)
                weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(weights)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                    biases = tf.get_variable('biases', [current_layer_dim_size])
                    reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(biases)
    
            loss_dim = tf.reduce_mean(pred_l2_loss_dim) + (beta * reg_l2_loss_dim)
        
        # Create a variable to track the global step.
        global_step = tf.Variable(0, name='global_step', trainable=False)
        # Exponentially-decaying learning rate:
        # learning_rate = tf.train.exponential_decay(initial_learning_rate, global_step, N_steps, 0.1)
        # Create the gradient descent optimizer with the given learning rate.
        # Use the optimizer to apply the gradients that minimize the loss
        # (and also increment the global step counter) as a single training step.
        # train_op = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss, global_step=global_step)
        # train_op = tf.train.MomentumOptimizer(learning_rate, momentum=learning_rate/4.0, use_nesterov=True).minimize(loss, global_step=global_step)
        # train_op = tf.train.AdamOptimizer().minimize(loss, global_step=global_step)
        # train_op_dim = tf.train.AdagradOptimizer(initial_learning_rate).minimize(loss_dim, global_step=global_step)
        # train_op_dim = tf.train.AdadeltaOptimizer().minimize(loss_dim, global_step=global_step)
        train_op_dim = tf.train.RMSPropOptimizer(initial_learning_rate).minimize(loss_dim, global_step=global_step)
        
        return train_op_dim, loss_dim
    
    # def performNeuralNetworkTraining(self, prediction, ground_truth, initial_learning_rate, beta, N_steps):
    def performNeuralNetworkWeightedTrainingPerDimOut(self, prediction, ground_truth, initial_learning_rate, beta, dim_out, weight):
        """
        Perform Neural Network Training (per output dimension).
        :param prediction: prediction made by current model on a dataset
        :param ground_truth: the ground truth of the corresponding dataset
        :param initial_learning_rate: initial learning rate
        :param beta: L2 regularization constant
        :param dim_out: output dimension being considered
        :param weight: weight vector corresponding to the prediction/dataset
        """
        assert (self.is_predicting_only == False), 'Needs to be inside a TensorFlow session, therefore self.is_predicting_only must be False!'
        
        # Create an operation that calculates L2 prediction loss.
        pred_l2_loss_dim = 0.5 * tf.reduce_sum(weight * tf.square(prediction[:,dim_out] - ground_truth[:,dim_out]))
        
        # Create an operation that calculates L2 regularization loss.
        reg_l2_loss_dim = 0
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
            layer_dim_ID = layer_name + '_' + str(dim_out)
            if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                current_layer_dim_size = self.neural_net_topology[i]
            else: # Output Layer
                current_layer_dim_size = 1
            with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                if (i == self.N_layers - 1):
                    neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1])
                    reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(neg_low_pass_filt_const)
                weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(weights)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                    biases = tf.get_variable('biases', [current_layer_dim_size])
                    reg_l2_loss_dim = reg_l2_loss_dim + tf.nn.l2_loss(biases)
    
            loss_dim = pred_l2_loss_dim + (beta * reg_l2_loss_dim)
        
        # Create a variable to track the global step.
        global_step = tf.Variable(0, name='global_step', trainable=False)
        # Exponentially-decaying learning rate:
        # learning_rate = tf.train.exponential_decay(initial_learning_rate, global_step, N_steps, 0.1)
        # Create the gradient descent optimizer with the given learning rate.
        # Use the optimizer to apply the gradients that minimize the loss
        # (and also increment the global step counter) as a single training step.
        # train_op = tf.train.GradientDescentOptimizer(learning_rate).minimize(loss, global_step=global_step)
        # train_op = tf.train.MomentumOptimizer(learning_rate, momentum=learning_rate/4.0, use_nesterov=True).minimize(loss, global_step=global_step)
        # train_op = tf.train.AdamOptimizer().minimize(loss, global_step=global_step)
        # train_op_dim = tf.train.AdagradOptimizer(initial_learning_rate).minimize(loss_dim, global_step=global_step)
        # train_op_dim = tf.train.AdadeltaOptimizer().minimize(loss_dim, global_step=global_step)
        train_op_dim = tf.train.RMSPropOptimizer(initial_learning_rate).minimize(loss_dim, global_step=global_step)
        
        return train_op_dim, loss_dim

    # Save model in MATLAB format.
    def saveNeuralNetworkToMATLABMatFile(self):
        """
        Save the Neural Network model into a MATLAB *.m file.
        """
        assert (self.is_predicting_only == False), 'Needs to be inside a TensorFlow session, therefore self.is_predicting_only must be False!'
        
        self.model_params={}
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
    
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                    if (i == self.N_layers - 1):
                        neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', [1,1])
                        self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"] = neg_low_pass_filt_const.eval()
                    weights = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                    self.model_params[self.name+'_'+layer_dim_ID+"_weights"] = weights.eval()
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = tf.get_variable('biases', [current_layer_dim_size])
                        self.model_params[self.name+'_'+layer_dim_ID+"_biases"] = biases.eval()
    
        return self.model_params

    # Load model from MATLAB format.
    def loadNeuralNetworkFromMATLABMatFile(self, filepath):
        """
        Load a Neural Network model from a MATLAB *.mat file. Functionally comparable to the defineNeuralNetworkModel() function.
        :param filepath: (relative) path in the directory structure specifying the location of the file to be loaded.
        """
        num_params = 0
        self.model_params = sio.loadmat(filepath, struct_as_record=True)
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
    
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                if (self.is_predicting_only == False):
                    with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=False):
                        if (i == self.N_layers - 1):
                            neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', trainable=False, initializer=self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"])
                            neg_low_pass_filt_const_dim = neg_low_pass_filt_const.get_shape().as_list()
                            num_params += neg_low_pass_filt_const_dim[0] * neg_low_pass_filt_const_dim[1]
                        weights = tf.get_variable('weights', initializer=self.model_params[self.name+'_'+layer_dim_ID+"_weights"])
                        weights_dim = weights.get_shape().as_list()
                        num_params += weights_dim[0] * weights_dim[1]
                        if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                            biases = tf.get_variable('biases', initializer=self.model_params[self.name+'_'+layer_dim_ID+"_biases"][0,:])
                            num_params += biases.get_shape().as_list()[0]
                else:
                    if (i == self.N_layers - 1):
                        neg_low_pass_filt_const = self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"]
                        neg_low_pass_filt_const_dim = list(neg_low_pass_filt_const.shape)
                        num_params += neg_low_pass_filt_const_dim[0] * neg_low_pass_filt_const_dim[1]
                    weights = self.model_params[self.name+'_'+layer_dim_ID+"_weights"]
                    weights_dim = list(weights.shape)
                    num_params += weights_dim[0] * weights_dim[1]
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = self.model_params[self.name+'_'+layer_dim_ID+"_biases"]
                        num_params += list(biases.shape)[0]
        num_params /= self.D_output
        print("Total # of Parameters = %d" % num_params)
        return num_params

    # Save model in *.txt format.
    def saveNeuralNetworkToTextFiles(self, dirpath):
        """
        Save the Neural Network model into text (*.txt) files in directory specified by dirpath.
        """
        recreateDir(dirpath)
        
        for dim_out in range(self.D_output):
            os.makedirs(dirpath + '/' + str(dim_out))
        
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
    
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                if (self.is_predicting_only == False):
                    with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=True):
                        if (i == self.N_layers - 1):
                            neg_low_pass_filt_const_tf = tf.get_variable('neg_low_pass_filt_const', [1,1])
                            neg_low_pass_filt_const = neg_low_pass_filt_const_tf.eval()
                        weights_tf = tf.get_variable('weights', [self.neural_net_topology[i-1], current_layer_dim_size])
                        weights = weights_tf.eval()
                        if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                            biases_tf = tf.get_variable('biases', [current_layer_dim_size])
                            biases = biases_tf.eval()
                else:
                    if (i == self.N_layers - 1):
                        neg_low_pass_filt_const = self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"]
                    weights = self.model_params[self.name+'_'+layer_dim_ID+"_weights"]
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = self.model_params[self.name+'_'+layer_dim_ID+"_biases"]
                if (i == self.N_layers - 1):
                    np.savetxt(dirpath + "/" + str(dim_out) + "/nlpfc" + str(i-1), neg_low_pass_filt_const)
                np.savetxt(dirpath + "/" + str(dim_out) + "/w" + str(i-1), weights)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                    np.savetxt(dirpath + "/" + str(dim_out) + "/b" + str(i-1), biases)
    
        return None

    # Load model from *.txt files format.
    def loadNeuralNetworkFromTextFiles(self, dirpath):
        """
        Load a Neural Network model from text (*.txt) files in directory specified by dirpath. 
        Functionally comparable to the defineNeuralNetworkModel() function.
        :param dirpath: (relative) path in the directory structure specifying the location of the files to be loaded.
        """
        num_params = 0
        self.model_params = {}
        for i in range(1, self.N_layers):
            layer_name = self.getLayerName(i)
            
            for dim_out in range(self.D_output):
                layer_dim_ID = layer_name + '_' + str(dim_out)
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation)
                    current_layer_dim_size = self.neural_net_topology[i]
                else: # Output Layer
                    current_layer_dim_size = 1
                if (i == self.N_layers - 1):
                    neg_low_pass_filt_const_temp = np.loadtxt(dirpath + "/" + str(dim_out) + "/nlpfc" + str(i-1))
                    self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"] = neg_low_pass_filt_const_temp
                weights_temp = np.loadtxt(dirpath + "/" + str(dim_out) + "/w" + str(i-1))
                if (len(weights_temp.shape) == 1):
                    weights_temp = weights_temp.reshape(weights_temp.shape[0], 1)
                self.model_params[self.name+'_'+layer_dim_ID+"_weights"] = weights_temp
                if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                    biases_temp = np.loadtxt(dirpath + "/" + str(dim_out) + "/b" + str(i-1))
                    self.model_params[self.name+'_'+layer_dim_ID+"_biases"] = biases_temp
                if (self.is_predicting_only == False):
                    with tf.variable_scope(self.name+'_'+layer_dim_ID, reuse=False):
                        if (i == self.N_layers - 1):
                            neg_low_pass_filt_const = tf.get_variable('neg_low_pass_filt_const', trainable=False, initializer=self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"])
                            neg_low_pass_filt_const_dim = neg_low_pass_filt_const.get_shape().as_list()
                            num_params += neg_low_pass_filt_const_dim[0] * neg_low_pass_filt_const_dim[1]
                        weights = tf.get_variable('weights', initializer=self.model_params[self.name+'_'+layer_dim_ID+"_weights"])
                        weights_dim = weights.get_shape().as_list()
                        num_params += weights_dim[0] * weights_dim[1]
                        if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                            biases = tf.get_variable('biases', initializer=self.model_params[self.name+'_'+layer_dim_ID+"_biases"][0,:])
                            num_params += biases.get_shape().as_list()[0]
                else:
                    if (i == self.N_layers - 1):
                        neg_low_pass_filt_const = self.model_params[self.name+'_'+layer_dim_ID+"_neg_low_pass_filt_const"]
                        neg_low_pass_filt_const_dim = list(neg_low_pass_filt_const.shape)
                        num_params += neg_low_pass_filt_const_dim[0] * neg_low_pass_filt_const_dim[1]
                    weights = self.model_params[self.name+'_'+layer_dim_ID+"_weights"]
                    weights_dim = list(weights.shape)
                    num_params += weights_dim[0] * weights_dim[1]
                    if (i < self.N_layers - 1): # Hidden Layers (including the Final Hidden Layer with Phase LWR Gating/Modulation); Output Layer does NOT have biases!!!
                        biases = self.model_params[self.name+'_'+layer_dim_ID+"_biases"]
                        num_params += list(biases.shape)[0]
        num_params /= self.D_output
        print("Total # of Parameters = %d" % num_params)
        return num_params
    
    def loadNeuralNetworkFromPath(self, path):
        if (os.path.isdir(path)):
            return self.loadNeuralNetworkFromTextFiles(path)
        else:
            return self.loadNeuralNetworkFromMATLABMatFile(path)