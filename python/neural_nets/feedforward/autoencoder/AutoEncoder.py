#!/usr/bin/env python2
# -*- coding: utf-8 -*-
"""Created on Thu Sep  7 22:00:00 2017

@author: gsutanto
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '../'))
from FeedForwardNeuralNetwork import *
from copy import deepcopy


class AutoEncoder(FeedForwardNeuralNetwork):
  """
    Class for special feed-forward neural network, the AutoEncoder.
    Decoder's topology is the mirror/reverse copy of the encoder's topology.
    """

  def __init__(self,
               name,
               D_input,
               encoder_hidden_layer_topology,
               encoder_hidden_layer_activation_func_list,
               D_latent,
               filepath=''):
    self.name = name

    self.neural_net_topology = [D_input] + encoder_hidden_layer_topology + [
        D_latent
    ] + list(reversed(encoder_hidden_layer_topology)) + [D_input]
    print self.name + ' AutoEncoder Topology:'
    print self.neural_net_topology

    self.D_output = D_input
    self.N_layers = len(self.neural_net_topology)

    if (encoder_hidden_layer_activation_func_list == []):
      self.neural_net_activation_func_list = ['identity'] * self.N_layers
    else:
      assert (len(encoder_hidden_layer_activation_func_list) == len(
          encoder_hidden_layer_topology)), (
              'len(encoder_hidden_layer_activation_func_list) must be == '
              'len(encoder_hidden_layer_topology)')
      self.neural_net_activation_func_list = [
          'identity'
      ] + encoder_hidden_layer_activation_func_list + ['identity'] + list(
          reversed(encoder_hidden_layer_activation_func_list)) + ['identity']
    # First Layer (Input Layer) always uses 'identity' activation function (and it does NOT matter actually; this is mainly for the sake of layer-indexing consistency...).
    assert (
        len(self.neural_net_activation_func_list) == self.N_layers
    ), 'len(self.neural_net_activation_func_list) must be == self.N_layers'
    print 'Neural Network Activation Function List:'
    print self.neural_net_activation_func_list

    if (filepath == ''):
      self.num_params = self.defineNeuralNetworkModel()
    else:
      self.num_params = self.loadNeuralNetworkFromMATLABMatFile(filepath)

  def getLayerName(self, layer_index):
    assert layer_index > 0, 'layer_index must be > 0'
    assert layer_index < self.N_layers, 'layer_index must be < N_layers'
    if (layer_index == self.N_layers - 1):  # Output Layer
      layer_name = 'output'
    elif (layer_index == (self.N_layers - 1) / 2):  # Latent Layer
      layer_name = 'latent'
    elif ((layer_index >= 1) and
          (layer_index < (self.N_layers - 1) / 2)):  # Encoder's Hidden Layer
      layer_name = 'encoder_hidden' + str(layer_index)
    elif ((layer_index > (self.N_layers - 1) / 2) and
          (layer_index < self.N_layers - 1)):  # Decoder's Hidden Layer
      layer_name = 'decoder_hidden' + str(layer_index -
                                          ((self.N_layers - 1) / 2))
    return layer_name

  def encode(self, input_dataset, dropout_keep_prob=1.0):
    """
        Perform encoding on a given input dataset.
        :param input_dataset: input dataset on which encoding will be performed
        :param dropout_keep_prob: probability of keeping a node (instead of
        dropping it; 1.0 means no drop-out)
        :return: latent tensor (in latent layer)
        """
    hidden_drop = input_dataset
    for i in range(1, ((self.N_layers - 1) / 2) + 1):
      layer_name = self.getLayerName(i)

      with tf.variable_scope(self.name + '_' + layer_name, reuse=True):
        weights = tf.get_variable(
            'weights',
            [self.neural_net_topology[i - 1], self.neural_net_topology[i]])
        biases = tf.get_variable('biases', [self.neural_net_topology[i]])

        affine_intermediate_result = tf.matmul(hidden_drop, weights) + biases
        if (self.neural_net_activation_func_list[i] == 'identity'):
          activation_func_output = affine_intermediate_result
        elif (self.neural_net_activation_func_list[i] == 'tanh'):
          activation_func_output = tf.nn.tanh(affine_intermediate_result)
        elif (self.neural_net_activation_func_list[i] == 'relu'):
          activation_func_output = tf.nn.relu(affine_intermediate_result)
        else:
          sys.exit('Unrecognized activation function: ' +
                   self.neural_net_activation_func_list[i])

        if (i < ((self.N_layers - 1) / 2)):  # Encoder's Hidden Layer
          hidden = activation_func_output
          hidden_drop = tf.nn.dropout(hidden, dropout_keep_prob)
        elif (i == (self.N_layers - 1) / 2):  # Latent Layer (no Dropout here!)
          latent = activation_func_output
    return latent

  def decode(self, latent_dataset, dropout_keep_prob=1.0):
    """
        Perform decoding on a given latent dataset.
        :param latent_dataset: latent dataset on which decoding will be
        performed
        :param dropout_keep_prob: probability of keeping a node (instead of
        dropping it; 1.0 means no drop-out)
        :return: output tensor (in output layer)
        """
    hidden_drop = latent_dataset
    for i in range(((self.N_layers - 1) / 2) + 1, self.N_layers):
      layer_name = self.getLayerName(i)

      with tf.variable_scope(self.name + '_' + layer_name, reuse=True):
        weights = tf.get_variable(
            'weights',
            [self.neural_net_topology[i - 1], self.neural_net_topology[i]])
        biases = tf.get_variable('biases', [self.neural_net_topology[i]])

        affine_intermediate_result = tf.matmul(hidden_drop, weights) + biases
        if (self.neural_net_activation_func_list[i] == 'identity'):
          activation_func_output = affine_intermediate_result
        elif (self.neural_net_activation_func_list[i] == 'tanh'):
          activation_func_output = tf.nn.tanh(affine_intermediate_result)
        elif (self.neural_net_activation_func_list[i] == 'relu'):
          activation_func_output = tf.nn.relu(affine_intermediate_result)
        else:
          sys.exit('Unrecognized activation function: ' +
                   self.neural_net_activation_func_list[i])

        if (i < (self.N_layers - 1)):  # Decoder's Hidden Layer
          hidden = activation_func_output
          hidden_drop = tf.nn.dropout(hidden, dropout_keep_prob)
        elif (i == self.N_layers - 1):  # Output Layer (no Dropout here!)
          output = activation_func_output
    return output

  def performNeuralNetworkPrediction(self, dataset, dropout_keep_prob=1.0):
    """
        Perform Neural Network Prediction: reconstruction of a given input
        dataset.
        :param dataset: input dataset on which prediction/reconstruction will be
        performed
        :param dropout_keep_prob: probability of keeping a node (instead of
        dropping it; 1.0 means no drop-out)
        :return: reconstructed tensor (in output layer)
        """
    latent_dataset = self.encode(dataset, dropout_keep_prob)
    reconstructed_dataset = self.decode(latent_dataset, dropout_keep_prob)
    return reconstructed_dataset
