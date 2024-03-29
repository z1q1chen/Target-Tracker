from tensorflow import keras
from os import path

IMAGE_SIZE = (152, 152)
CHANNELS = 3
NUM_CLASSES = 8631
LEARN_RATE = 0.01
MOMENTUM = 0.9


def create_deepface(image_size=IMAGE_SIZE, channels=CHANNELS, num_classes=NUM_CLASSES, learn_rate=LEARN_RATE, momentum=MOMENTUM):
    wt_init = keras.initializers.RandomNormal(mean=0, stddev=0.01)
    bias_init = keras.initializers.Constant(value=0.5)

    def conv2d_layer(**args):
        return keras.layers.Conv2D(**args,
                                   kernel_initializer=wt_init,
                                   bias_initializer=bias_init,
                                   activation=keras.activations.relu)

    def lc2d_layer(**args):
        return keras.layers.LocallyConnected2D(**args,
                                               kernel_initializer=wt_init,
                                               bias_initializer=bias_init,
                                               activation=keras.activations.relu)

    def dense_layer(**args):
        return keras.layers.Dense(**args,
                                  kernel_initializer=wt_init,
                                  bias_initializer=bias_init)

    deepface = keras.models.Sequential([
        keras.layers.InputLayer(input_shape=(
            *image_size, channels), name='I0'),
        conv2d_layer(filters=32, kernel_size=11, name='C1'),
        keras.layers.MaxPooling2D(
            pool_size=3, strides=2, padding='same',  name='M2'),
        conv2d_layer(filters=16, kernel_size=9, name='C3'),
        lc2d_layer(filters=16, kernel_size=9, name='L4'),
        lc2d_layer(filters=16, kernel_size=7, strides=2, name='L5'),
        lc2d_layer(filters=16, kernel_size=5, name='L6'),
        lc2d_layer(filters=16, kernel_size=3, name='L7'),
        keras.layers.Flatten(name='F0'),
        dense_layer(units=4096, activation=keras.activations.relu, name='F7'),
        keras.layers.Dropout(rate=0.5, name='D0'),
        dense_layer(units=4096, activation=keras.activations.relu, name='F8'),
        dense_layer(units=num_classes,
                    activation=keras.activations.softmax, name='F9')
    ], name='DeepFace')
    deepface.summary()
    sgd_opt = keras.optimizers.SGD(lr=learn_rate, momentum=momentum)
    cce_loss = keras.losses.categorical_crossentropy

    deepface.compile(optimizer=sgd_opt, loss=cce_loss, metrics=['accuracy'])
    return deepface
