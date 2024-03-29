from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import tensorflow as tf

_BATCH_NORM_DECAY = 0.997
_BATCH_NORM_EPSILON = 1e-5
DEFAULT_DTYPE = tf.float32
CASTABLE_TYPES = (tf.float16,)
ALLOWED_TYPES = (DEFAULT_DTYPE,) + CASTABLE_TYPES


def block(inputs, filters, training, projection_shortcut, strides,
          data_format):
    shortcut = inputs
    inputs = batch_norm(inputs, training, data_format)
    inputs = tf.nn.relu(inputs)

    if projection_shortcut is not None:
        shortcut = projection_shortcut(inputs)

    inputs = conv2d_fixed_padding(
        inputs=inputs, filters=filters, kernel_size=3, strides=strides,
        data_format=data_format)

    inputs = batch_norm(inputs, training, data_format)
    inputs = tf.nn.relu(inputs)
    inputs = conv2d_fixed_padding(
        inputs=inputs, filters=filters, kernel_size=3, strides=1,
        data_format=data_format)

    return inputs + shortcut


def bottleneck_block(inputs, filters, training, projection_shortcut,
                     strides, data_format):
    shortcut = inputs
    inputs = batch_norm(inputs, training, data_format)
    inputs = tf.nn.relu(inputs)

    if projection_shortcut is not None:
        shortcut = projection_shortcut(inputs)

    inputs = conv2d_fixed_padding(
        inputs=inputs, filters=filters, kernel_size=1, strides=1,
        data_format=data_format)

    inputs = batch_norm(inputs, training, data_format)
    inputs = tf.nn.relu(inputs)
    inputs = conv2d_fixed_padding(
        inputs=inputs, filters=filters, kernel_size=3, strides=strides,
        data_format=data_format)

    inputs = batch_norm(inputs, training, data_format)
    inputs = tf.nn.relu(inputs)
    inputs = conv2d_fixed_padding(
        inputs=inputs, filters=4 * filters, kernel_size=1, strides=1,
        data_format=data_format)

    return inputs + shortcut


def block_layer(inputs, filters, bottleneck, block_fn, blocks, strides,
                training, name, data_format):
    filters_out = filters * 4 if bottleneck else filters

    def projection_shortcut(inputs):
        return conv2d_fixed_padding(
            inputs=inputs, filters=filters_out, kernel_size=1, strides=strides,
            data_format=data_format)
    inputs = block_fn(inputs, filters, training, projection_shortcut, strides,
                      data_format)

    for _ in range(1, blocks):
        inputs = block_fn(inputs, filters, training, None, 1, data_format)

    return tf.identity(inputs, name)


class Model(object):
    def __init__(self, resnet_size, bottleneck, num_classes, num_filters,
                 kernel_size,
                 conv_stride, first_pool_size, first_pool_stride,
                 , data_format=None,
                 dtype=DEFAULT_DTYPE):
        self.resnet_size = resnet_size

        if not data_format:
            data_format = (
                'channels_first' if tf.test.is_built_with_cuda() else 'channels_last')

        self.bottleneck = bottleneck
        if bottleneck:
            self.block_fn = bottleneck_block
        else:
            self.block_fn = block2

        if dtype not in ALLOWED_TYPES:
            raise ValueError('dtype must be one of: {}'.format(ALLOWED_TYPES))

        self.data_format = data_format
        self.num_classes = num_classes
        self.num_filters = num_filters
        self.kernel_size = kernel_size
        self.conv_stride = conv_stride
        self.first_pool_size = first_pool_size
        self.first_pool_stride = first_pool_stride
        self.block_sizes = block_sizes
        self.block_strides = block_strides
        self.dtype = dtype

    def _custom_dtype_getter(self, getter, name, shape=None, dtype=DEFAULT_DTYPE,
                             *args, **kwargs):
        if dtype in CASTABLE_TYPES:
            var = getter(name, shape, tf.float32, *args, **kwargs)
            return tf.cast(var, dtype=dtype, name=name + '_cast')
        else:
            return getter(name, shape, dtype, *args, **kwargs)

    def _model_variable_scope(self):

        return tf.compat.v1.variable_scope('resnet_model',
                                           custom_getter=self._custom_dtype_getter)

    def __call__(self, inputs, training):
        with self._model_variable_scope():
            if self.data_format == 'channels_first':
                inputs = tf.transpose(a=inputs, perm=[0, 3, 1, 2])

            inputs = conv2d_fixed_padding(
                inputs=inputs, filters=self.num_filters, kernel_size=self.kernel_size,
                strides=self.conv_stride, data_format=self.data_format)
            inputs = tf.identity(inputs, 'initial_conv')

            if self.first_pool_size:
                inputs = tf.compat.v1.layers.max_pooling2d(
                    inputs=inputs, pool_size=self.first_pool_size,
                    strides=self.first_pool_stride, padding='SAME',
                    data_format=self.data_format)
                inputs = tf.identity(inputs, 'initial_max_pool')

            for i, num_blocks in enumerate(self.block_sizes):
                num_filters = self.num_filters * (2**i)
                inputs = block_layer(
                    inputs=inputs, filters=num_filters, bottleneck=self.bottleneck,
                    block_fn=self.block_fn, blocks=num_blocks,
                    strides=self.block_strides[i], training=training,
                    name='block_layer{}'.format(i + 1), data_format=self.data_format)

            if self.pre_activation:
                inputs = batch_norm(inputs, training, self.data_format)
                inputs = tf.nn.relu(inputs)

            axes = [2, 3] if self.data_format == 'channels_first' else [1, 2]
            inputs = tf.reduce_mean(
                input_tensor=inputs, axis=axes, keepdims=True)
            inputs = tf.identity(inputs, 'final_reduce_mean')

            inputs = tf.squeeze(inputs, axes)
            inputs = tf.compat.v1.layers.dense(
                inputs=inputs, units=self.num_classes)
            inputs = tf.identity(inputs, 'final_dense')
            return inputs


def batch_norm(inputs, training, data_format):
    return tf.compat.v1.layers.batch_normalization(
        inputs=inputs, axis=1 if data_format == 'channels_first' else 3,
        momentum=_BATCH_NORM_DECAY, epsilon=_BATCH_NORM_EPSILON, center=True,
        scale=True, training=training, fused=True)


def fixed_padding(inputs, kernel_size, data_format):
    pad_total = kernel_size - 1
    pad_beg = pad_total // 2
    pad_end = pad_total - pad_beg

    if data_format == 'channels_first':
        padded_inputs = tf.pad(tensor=inputs,
                               paddings=[[0, 0], [0, 0], [pad_beg, pad_end],
                                         [pad_beg, pad_end]])
    else:
        padded_inputs = tf.pad(tensor=inputs,
                               paddings=[[0, 0], [pad_beg, pad_end],
                                         [pad_beg, pad_end], [0, 0]])
    return padded_inputs


def conv2d_fixed_padding(inputs, filters, kernel_size, strides, data_format):
    if strides > 1:
        inputs = fixed_padding(inputs, kernel_size, data_format)

    return tf.compat.v1.layers.conv2d(
        inputs=inputs, filters=filters, kernel_size=kernel_size, strides=strides,
        padding=('SAME' if strides == 1 else 'VALID'), use_bias=False,
        kernel_initializer=tf.compat.v1.variance_scaling_initializer(),
        data_format=data_format)
